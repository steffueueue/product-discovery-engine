"""Deterministic delivery entry and separate accountable implementation handoff."""

from datetime import timedelta
from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, model_validator

from .audit import Actor, AuditEvent, EventType, ObjectKind
from .common import DomainModel, Text
from .delivery_selection import DeliverySelection, require_human
from .delivery_specification import DeliverySpec, DeliverySpecStatus
from .hypotheses import Hypothesis
from .spec_clarification import ClarificationQuestion, ClarificationStatus
from .spec_completeness import CompletenessState, SpecCompletenessAssessment, dimension_acceptable
from .spec_completeness_policy import (
    DeliveryCondition,
    DimensionState,
    GapClassification,
    SpecCompletenessPolicy,
    SpecDimension,
)
from .spec_content import spec_body
from .spec_gaps import spec_event
from .spec_review import ReviewDisposition, SpecReview


class GateConditionState(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    UNKNOWN = "unknown"
    REVIEW_REQUIRED = "review_required"


class DeliveryGateState(StrEnum):
    PASSED = "passed"
    BLOCKED = "blocked"
    NEEDS_REVIEW = "needs_review"


class DeliveryGateInput(DomainModel):
    spec: DeliverySpec
    current_spec: DeliverySpec
    hypothesis: Hypothesis
    selection: DeliverySelection
    assessment: SpecCompletenessAssessment | None
    review: SpecReview | None
    clarifications: tuple[ClarificationQuestion, ...] = ()

    @model_validator(mode="after")
    def unique_questions(self) -> "DeliveryGateInput":
        if len({q.id for q in self.clarifications}) != len(self.clarifications) or len(
            {q.source_gap.id for q in self.clarifications}
        ) != len(self.clarifications):
            raise ValueError("gate clarification history must be unique by question and gap")
        return self


class DeliveryConditionResult(DomainModel):
    condition: DeliveryCondition
    required: bool
    state: GateConditionState
    explanation: Text


class DeliveryGateResult(DomainModel):
    state: DeliveryGateState
    evaluated_conditions: tuple[DeliveryConditionResult, ...]
    passed_conditions: tuple[DeliveryCondition, ...]
    failed_conditions: tuple[DeliveryCondition, ...]
    unknown_conditions: tuple[DeliveryCondition, ...]
    review_required_conditions: tuple[DeliveryCondition, ...]
    blocking_reasons: tuple[Text, ...]


def evaluate_delivery_conditions(
    inputs: DeliveryGateInput, policy: SpecCompletenessPolicy, at: AwareDatetime
) -> DeliveryGateResult:
    spec, assessment, review = inputs.spec, inputs.assessment, inputs.review
    states: dict[DeliveryCondition, GateConditionState] = {}
    explanations: dict[DeliveryCondition, str] = {}

    def condition(key: DeliveryCondition, passed: bool | None, reason: str) -> None:
        states[key] = (
            GateConditionState.UNKNOWN
            if passed is None
            else GateConditionState.PASSED
            if passed
            else GateConditionState.FAILED
        )
        explanations[key] = reason

    condition(
        DeliveryCondition.READY_STATUS,
        spec.status == DeliverySpecStatus.READY_FOR_DELIVERY,
        "Specification must have controlled READY_FOR_DELIVERY authority",
    )
    condition(
        DeliveryCondition.CURRENT_SPEC,
        spec == inputs.current_spec and (assessment is None or assessment.spec == spec_body(spec)),
        "Exact supplied current specification and assessment body must agree",
    )
    condition(
        DeliveryCondition.SELECTION,
        inputs.selection == spec.context.selection and inputs.hypothesis == inputs.selection.after,
        "Exact selected hypothesis and DeliverySelection must agree",
    )
    condition(
        DeliveryCondition.COMPLETENESS,
        None if assessment is None else assessment.result.state == CompletenessState.COMPLETE,
        "Exact specification completeness must be COMPLETE",
    )
    if assessment is not None and assessment.result.state == CompletenessState.NEEDS_REVIEW:
        states[DeliveryCondition.COMPLETENESS] = GateConditionState.REVIEW_REQUIRED
    condition(
        DeliveryCondition.APPROVED_REVIEW,
        None
        if review is None
        else review.assessment == assessment
        and review.disposition == ReviewDisposition.APPROVED
        and not review.concerns,
        "Accountable human must approve the exact assessment without pending conditions",
    )
    if review is not None and review.disposition == ReviewDisposition.REVIEW_WITH_CONCERNS:
        states[DeliveryCondition.APPROVED_REVIEW] = GateConditionState.REVIEW_REQUIRED
    condition(
        DeliveryCondition.NO_BLOCKING_GAPS,
        None if assessment is None else not assessment.result.blocking_gaps,
        "Authoritative unresolved blocking specification gaps must be absent",
    )
    if (
        assessment is not None
        and not assessment.result.blocking_gaps
        and assessment.result.review_required_gaps
    ):
        states[DeliveryCondition.NO_BLOCKING_GAPS] = GateConditionState.REVIEW_REQUIRED
    required_questions = tuple(
        q
        for q in inputs.clarifications
        if q.source_gap.classification != GapClassification.NON_BLOCKING
    )
    condition(
        DeliveryCondition.CLARIFICATIONS,
        all(
            q.spec.id == spec.id
            and q.spec.context.selection == spec.context.selection
            and q.applies_to(spec)
            for q in inputs.clarifications
        )
        and all(
            q.status in {ClarificationStatus.RESOLVED, ClarificationStatus.WITHDRAWN}
            for q in required_questions
        ),
        "Required clarifications need current resolution or explicit withdrawal",
    )
    for key, dimension in (
        (DeliveryCondition.ACCEPTANCE, SpecDimension.ACCEPTANCE),
        (DeliveryCondition.INTERFACES, SpecDimension.INTERFACES),
        (DeliveryCondition.DATA, SpecDimension.DATA),
        (DeliveryCondition.QUALITY, SpecDimension.QUALITY),
        (DeliveryCondition.DEPENDENCIES, SpecDimension.DEPENDENCIES),
        (DeliveryCondition.TRACEABILITY, SpecDimension.TRACEABILITY),
        (DeliveryCondition.OWNER, SpecDimension.OWNERSHIP),
    ):
        result = (
            next((r for r in assessment.result.dimensions if r.dimension == dimension), None)
            if assessment
            else None
        )
        condition(
            key,
            None
            if result is None or result.state == DimensionState.UNKNOWN
            else dimension_acceptable(result, policy),
            f"Applicable {dimension.value} information must satisfy configured minimum",
        )
        if key == DeliveryCondition.OWNER:
            condition(
                key,
                spec.context.hypothesis.content.owner is not None,
                "Accountable hypothesis owner must be explicitly supplied",
            )
    condition(
        DeliveryCondition.CURRENT_POLICY,
        None
        if assessment is None
        else assessment.policy == policy
        and (review is None or review.assessment.policy == policy)
        and (not spec.status_history or spec.status_history[-1].assessment.policy == policy),
        "Full retained policy must match active configuration",
    )
    records_current = (
        None
        if assessment is None or review is None
        else (
            assessment.assessed_at
            <= review.reviewed_at
            <= at
            < assessment.assessed_at + timedelta(hours=policy.validity_hours)
            and review.reviewed_at <= at
            and bool(spec.status_history)
            and spec.status_history[-1].at <= at
        )
    )
    condition(
        DeliveryCondition.FRESH_RECORDS,
        records_current,
        "Assessment, review and readiness authority must be current and unexpired",
    )
    results = tuple(
        DeliveryConditionResult(
            condition=r.condition,
            required=r.required,
            state=states[r.condition],
            explanation=explanations[r.condition],
        )
        for r in policy.gate_conditions
    )
    blocked = any(
        r.required and r.state in {GateConditionState.FAILED, GateConditionState.UNKNOWN}
        for r in results
    )
    needs_review = any(
        r.required and r.state == GateConditionState.REVIEW_REQUIRED for r in results
    )
    return DeliveryGateResult(
        state=DeliveryGateState.BLOCKED
        if blocked
        else DeliveryGateState.NEEDS_REVIEW
        if needs_review
        else DeliveryGateState.PASSED,
        evaluated_conditions=results,
        passed_conditions=tuple(
            r.condition for r in results if r.state == GateConditionState.PASSED
        ),
        failed_conditions=tuple(
            r.condition for r in results if r.state == GateConditionState.FAILED
        ),
        unknown_conditions=tuple(
            r.condition for r in results if r.state == GateConditionState.UNKNOWN
        ),
        review_required_conditions=tuple(
            r.condition for r in results if r.state == GateConditionState.REVIEW_REQUIRED
        ),
        blocking_reasons=tuple(
            r.explanation for r in results if r.required and r.state != GateConditionState.PASSED
        ),
    )


class DeliveryGate(DomainModel):
    id: UUID
    inputs: DeliveryGateInput
    policy: SpecCompletenessPolicy
    evaluated_by: Actor
    evaluated_at: AwareDatetime
    expires_at: AwareDatetime
    result: DeliveryGateResult
    events: tuple[AuditEvent, ...]

    @model_validator(mode="after")
    def reconstruct(self) -> "DeliveryGate":
        from .audit import ActorKind

        if self.evaluated_by.kind == ActorKind.AI:
            raise ValueError("AI cannot evaluate authoritative Delivery Gate")
        expiry = self.evaluated_at + timedelta(hours=self.policy.validity_hours)
        if self.inputs.assessment is not None:
            expiry = min(
                expiry,
                self.inputs.assessment.assessed_at + timedelta(hours=self.policy.validity_hours),
            )
        if self.expires_at != expiry or self.result != evaluate_delivery_conditions(
            self.inputs, self.policy, self.evaluated_at
        ):
            raise ValueError("Delivery Gate must reconstruct exact deterministic conditions")
        outcome = {
            DeliveryGateState.PASSED: EventType.DELIVERY_GATE_PASSED,
            DeliveryGateState.BLOCKED: EventType.DELIVERY_GATE_BLOCKED,
            DeliveryGateState.NEEDS_REVIEW: EventType.DELIVERY_GATE_REVIEW_REQUIRED,
        }[self.result.state]
        if len(self.events) != 2:
            raise ValueError("delivery gate requires evaluation and outcome audits")
        for event, kind in zip(
            self.events, (EventType.DELIVERY_GATE_EVALUATED, outcome), strict=True
        ):
            if event != spec_event(
                kind,
                ObjectKind.DELIVERY_GATE,
                self.id,
                self.evaluated_by,
                self.evaluated_at,
                event.id,
                (self.inputs.spec.id, self.inputs.selection.id),
                self.policy.version,
                self.inputs.spec.version,
            ):
                raise ValueError("delivery gate audit must reconstruct")
        if self.events[0].id == self.events[1].id:
            raise ValueError("delivery gate audit IDs must be distinct")
        return self

    @property
    def hypothesis_id(self) -> UUID:
        return self.inputs.hypothesis.id

    @property
    def selection_id(self) -> UUID:
        return self.inputs.selection.id


class ImplementationAuthorization(DomainModel):
    id: UUID
    gate: DeliveryGate
    current: DeliveryGateInput
    policy: SpecCompletenessPolicy
    authorizing_human: Actor
    rationale: Text
    authorized_at: AwareDatetime
    conditions: tuple[Text, ...] = ()
    event: AuditEvent

    @model_validator(mode="after")
    def reconstruct(self) -> "ImplementationAuthorization":
        require_human(self.authorizing_human)
        if self.gate.result.state != DeliveryGateState.PASSED:
            raise ValueError("implementation handoff requires ordinary Delivery Gate PASS")
        if self.current != self.gate.inputs or self.policy != self.gate.policy:
            raise ValueError(
                "stale/mismatched gate cannot authorize another specification or policy"
            )
        if not self.gate.evaluated_at <= self.authorized_at < self.gate.expires_at:
            raise ValueError("expired or future gate cannot authorize handoff")
        if (
            evaluate_delivery_conditions(self.current, self.policy, self.authorized_at).state
            != DeliveryGateState.PASSED
        ):
            raise ValueError("delivery conditions must still pass at authorization")
        if self.event != spec_event(
            EventType.IMPLEMENTATION_HANDOFF_AUTHORIZED,
            ObjectKind.IMPLEMENTATION_AUTHORIZATION,
            self.id,
            self.authorizing_human,
            self.authorized_at,
            self.event.id,
            (
                self.gate.id,
                self.current.spec.id,
                self.current.selection.id,
                self.current.hypothesis.id,
            ),
            self.rationale,
            self.current.spec.version,
        ):
            raise ValueError("implementation authorization audit must reconstruct")
        return self

    @property
    def spec_id(self) -> UUID:
        return self.current.spec.id

    @property
    def spec_version(self) -> int:
        return self.current.spec.version

    @property
    def hypothesis_id(self) -> UUID:
        return self.current.hypothesis.id

    @property
    def selection_id(self) -> UUID:
        return self.current.selection.id
