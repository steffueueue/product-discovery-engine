"""Controlled transition authorization; a pass never means 'build this product'."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, model_validator

from .audit import Actor, ActorKind, AuditEvent, EventType
from .common import DomainModel, Text
from .decisioning_policy import (
    DecisioningPolicies,
    GateCondition,
    ReadinessDimension,
    ReadinessState,
)
from .delivery_readiness import DeliveryReadinessAssessment, DimensionState
from .discovery_priority import decision_audit, require_decision_audit
from .hypotheses import Hypothesis
from .lifecycle import HypothesisStatus


class GateState(StrEnum):
    PASSED = "passed"
    BLOCKED = "blocked"
    NEEDS_REVIEW = "needs_review"


class ConditionState(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    UNKNOWN = "unknown"
    REVIEW_REQUIRED = "review_required"


class GatePrerequisite(StrEnum):
    SNAPSHOT = "snapshot"
    POLICY = "policy"
    LIFECYCLE = "lifecycle"
    ASSESSMENT_CURRENT = "assessment_current"


class ConditionResult(DomainModel):
    condition: GateCondition | GatePrerequisite
    state: ConditionState
    explanation: Text


class GateResult(DomainModel):
    conditions: tuple[ConditionResult, ...]
    passed_conditions: tuple[Text, ...]
    failed_conditions: tuple[Text, ...]
    unknown_conditions: tuple[Text, ...]
    blocking_reasons: tuple[Text, ...]
    review_required_reasons: tuple[Text, ...]
    state: GateState
    explanation: Text


def _dimension_condition(states: tuple[DimensionState, ...]) -> ConditionState:
    if DimensionState.UNKNOWN in states:
        return ConditionState.UNKNOWN
    if DimensionState.INSUFFICIENT in states:
        return ConditionState.FAILED
    if DimensionState.PARTIAL in states:
        return ConditionState.REVIEW_REQUIRED
    return ConditionState.PASSED


def evaluate_gate_conditions(
    hypothesis: Hypothesis,
    readiness: DeliveryReadinessAssessment | None,
    policies: DecisioningPolicies,
    at: datetime,
) -> GateResult:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("gate evaluation requires a timezone-aware timestamp")
    conditions = []

    def add(
        condition: GateCondition | GatePrerequisite, state: ConditionState, explanation: str
    ) -> None:
        conditions.append(
            ConditionResult(condition=condition, state=state, explanation=explanation)
        )

    add(
        GatePrerequisite.LIFECYCLE,
        ConditionState.PASSED
        if hypothesis.status == HypothesisStatus.EVIDENCE_UPDATED
        else ConditionState.FAILED,
        "Candidacy is allowed only from evidence_updated",
    )
    if readiness is None:
        for prerequisite in (
            GatePrerequisite.SNAPSHOT,
            GatePrerequisite.POLICY,
            GatePrerequisite.ASSESSMENT_CURRENT,
        ):
            add(prerequisite, ConditionState.UNKNOWN, "Required readiness assessment missing")
    else:
        add(
            GatePrerequisite.SNAPSHOT,
            ConditionState.PASSED
            if readiness.inputs.hypothesis == hypothesis
            else ConditionState.FAILED,
            "Exact full material hypothesis snapshot must match",
        )
        add(
            GatePrerequisite.POLICY,
            ConditionState.PASSED
            if readiness.policy == policies.readiness
            and readiness.policy_version == policies.version
            else ConditionState.FAILED,
            "Retained readiness policy must match the current complete policy snapshot/version",
        )
        current = (
            readiness.assessed_at <= at
            and at - readiness.assessed_at < timedelta(hours=policies.gate.maximum_age_hours)
            and readiness.assessed_at.astimezone(UTC).date() == at.astimezone(UTC).date()
        )
        add(
            GatePrerequisite.ASSESSMENT_CURRENT,
            ConditionState.PASSED if current else ConditionState.FAILED,
            "Readiness must be within configured age and have same UTC-day freshness",
        )
    mapping = {
        GateCondition.OWNERSHIP: ReadinessDimension.OWNERSHIP,
        GateCondition.FRESHNESS: ReadinessDimension.EVIDENCE_FRESHNESS,
        GateCondition.QUALITY: ReadinessDimension.EVIDENCE_QUALITY,
        GateCondition.TRIANGULATION: ReadinessDimension.TRIANGULATION,
        GateCondition.CRITICAL_ASSUMPTIONS: ReadinessDimension.ASSUMPTION_RISK,
        GateCondition.VALIDATION: ReadinessDimension.VALIDATION,
        GateCondition.CHALLENGE: ReadinessDimension.CHALLENGE,
        GateCondition.STRATEGY: ReadinessDimension.STRATEGY,
        GateCondition.CONTRADICTIONS: ReadinessDimension.CONTRADICTIONS,
    }
    for condition in policies.gate.required_conditions:
        if readiness is None:
            add(condition, ConditionState.UNKNOWN, "Required readiness assessment missing")
            continue
        if condition == GateCondition.READINESS:
            state = {
                ReadinessState.READY: ConditionState.PASSED,
                ReadinessState.NOT_READY: ConditionState.FAILED,
                ReadinessState.NEEDS_REVIEW: ConditionState.REVIEW_REQUIRED,
            }[readiness.result.state]
            add(condition, state, readiness.result.explanation)
        elif condition == GateCondition.EVIDENCE_TARGETS:
            required = {r.dimension for r in policies.readiness.evidence_requirements}
            results = tuple(
                d for d in readiness.result.dimensions if d.required and d.dimension in required
            )
            add(
                condition,
                _dimension_condition(tuple(r.state for r in results)),
                "Required target claims evaluated in their exact scope; solution-only claims "
                "are not applicable when no solution exists",
            )
        else:
            result = next(
                d for d in readiness.result.dimensions if d.dimension == mapping[condition]
            )
            add(condition, _dimension_condition((result.state,)), result.explanation)
    blocking = tuple(
        c.explanation
        for c in conditions
        if c.state in {ConditionState.FAILED, ConditionState.UNKNOWN}
    )
    review = tuple(c.explanation for c in conditions if c.state == ConditionState.REVIEW_REQUIRED)
    gate_state = (
        GateState.BLOCKED if blocking else (GateState.NEEDS_REVIEW if review else GateState.PASSED)
    )
    return GateResult(
        conditions=tuple(conditions),
        passed_conditions=tuple(
            c.condition.value for c in conditions if c.state == ConditionState.PASSED
        ),
        failed_conditions=tuple(
            c.condition.value for c in conditions if c.state == ConditionState.FAILED
        ),
        unknown_conditions=tuple(
            c.condition.value for c in conditions if c.state == ConditionState.UNKNOWN
        ),
        blocking_reasons=blocking,
        review_required_reasons=review,
        state=gate_state,
        explanation=(
            f"{gate_state.value}: candidacy eligibility only; "
            "no delivery selection or authorization"
        ),
    )


def gate_expiry(
    at: datetime, readiness: DeliveryReadinessAssessment | None, policies: DecisioningPolicies
) -> datetime:
    reference = readiness.assessed_at if readiness else at
    utc_day = reference.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return min(
        utc_day + timedelta(days=1), reference + timedelta(hours=policies.gate.maximum_age_hours)
    )


_GATE_EVENTS = {
    GateState.PASSED: EventType.DISCOVERY_GATE_PASSED,
    GateState.BLOCKED: EventType.DISCOVERY_GATE_BLOCKED,
    GateState.NEEDS_REVIEW: EventType.DISCOVERY_GATE_REVIEW_REQUIRED,
}


class DiscoveryGateEvaluation(DomainModel):
    id: UUID
    hypothesis: Hypothesis
    readiness: DeliveryReadinessAssessment | None
    policies: DecisioningPolicies
    policy_version: Text
    evaluated_at: AwareDatetime
    expires_at: AwareDatetime
    result: GateResult
    evaluation_event: AuditEvent
    outcome_event: AuditEvent

    @property
    def readiness_assessment_id(self) -> UUID | None:
        return self.readiness.id if self.readiness else None

    @model_validator(mode="after")
    def reconstruct(self) -> "DiscoveryGateEvaluation":
        if self.evaluated_at < self.hypothesis.updated_at:
            raise ValueError("gate cannot precede hypothesis snapshot")
        if (
            self.policy_version != self.policies.version
            or self.expires_at != gate_expiry(self.evaluated_at, self.readiness, self.policies)
            or self.result
            != evaluate_gate_conditions(
                self.hypothesis, self.readiness, self.policies, self.evaluated_at
            )
        ):
            raise ValueError("gate result must reconstruct from retained inputs/policies")
        require_decision_audit(
            self.evaluation_event,
            self.id,
            self.hypothesis.id,
            EventType.DISCOVERY_GATE_EVALUATED,
            self.evaluated_at,
        )
        require_decision_audit(
            self.outcome_event,
            self.id,
            self.hypothesis.id,
            _GATE_EVENTS[self.result.state],
            self.evaluated_at,
        )
        if (
            self.evaluation_event.id == self.outcome_event.id
            or self.evaluation_event.actor != self.outcome_event.actor
        ):
            raise ValueError("gate audits must have distinct IDs and the same evaluation actor")
        return self


def evaluate_discovery_gate(
    hypothesis: Hypothesis,
    readiness: DeliveryReadinessAssessment | None,
    *,
    policies: DecisioningPolicies,
    actor: Actor,
    at: datetime,
    gate_id: UUID,
    evaluation_event_id: UUID,
    outcome_event_id: UUID,
) -> DiscoveryGateEvaluation:
    hypothesis = Hypothesis.model_validate(hypothesis)
    policies = DecisioningPolicies.model_validate(policies)
    readiness = DeliveryReadinessAssessment.model_validate(readiness) if readiness else None
    result = evaluate_gate_conditions(hypothesis, readiness, policies, at)
    return DiscoveryGateEvaluation(
        id=gate_id,
        hypothesis=hypothesis,
        readiness=readiness,
        policies=policies,
        policy_version=policies.version,
        evaluated_at=at,
        expires_at=gate_expiry(at, readiness, policies),
        result=result,
        evaluation_event=decision_audit(
            evaluation_event_id,
            gate_id,
            hypothesis.id,
            EventType.DISCOVERY_GATE_EVALUATED,
            actor,
            at,
        ),
        outcome_event=decision_audit(
            outcome_event_id, gate_id, hypothesis.id, _GATE_EVENTS[result.state], actor, at
        ),
    )


class OverrideAction(StrEnum):
    AUTHORIZE_CANDIDACY = "authorize_candidacy"


class DiscoveryGateOverride(DomainModel):
    id: UUID
    original_gate: DiscoveryGateEvaluation
    actor: Actor
    reason: Text
    overridden_at: AwareDatetime
    policy_version: Text
    action: OverrideAction
    overridden_conditions: tuple[GateCondition, ...]
    event: AuditEvent

    @model_validator(mode="after")
    def validate_override(self) -> "DiscoveryGateOverride":
        gate = self.original_gate
        unmet = tuple(
            c.condition for c in gate.result.conditions if c.state != ConditionState.PASSED
        )
        if (
            self.actor.kind != ActorKind.HUMAN
            or self.policy_version != gate.policy_version
            or not gate.evaluated_at <= self.overridden_at < gate.expires_at
            or gate.result.state == GateState.PASSED
            or any(c.state == ConditionState.UNKNOWN for c in gate.result.conditions)
            or len(set(self.overridden_conditions)) != len(self.overridden_conditions)
            or set(unmet) != set(self.overridden_conditions)
            or not set(self.overridden_conditions) <= set(gate.policies.gate.overridable_conditions)
        ):
            raise ValueError(
                "override needs a human, current gate, and explicitly permitted known conditions"
            )
        require_decision_audit(
            self.event,
            self.id,
            gate.hypothesis.id,
            EventType.DISCOVERY_GATE_OVERRIDDEN,
            self.overridden_at,
        )
        if self.event.actor != self.actor or self.event.metadata.reason != self.reason:
            raise ValueError("override audit must preserve actor and reason")
        return self


def override_discovery_gate(
    gate: DiscoveryGateEvaluation,
    *,
    actor: Actor,
    reason: str,
    at: datetime,
    override_id: UUID,
    event_id: UUID,
) -> DiscoveryGateOverride:
    gate = DiscoveryGateEvaluation.model_validate(gate)
    return DiscoveryGateOverride(
        id=override_id,
        original_gate=gate,
        actor=actor,
        reason=reason,
        overridden_at=at,
        policy_version=gate.policy_version,
        action=OverrideAction.AUTHORIZE_CANDIDACY,
        overridden_conditions=tuple(
            c
            for c in gate.policies.gate.required_conditions
            if any(
                r.condition == c and r.state != ConditionState.PASSED
                for r in gate.result.conditions
            )
        ),
        event=decision_audit(
            event_id,
            override_id,
            gate.hypothesis.id,
            EventType.DISCOVERY_GATE_OVERRIDDEN,
            actor,
            at,
            reason=reason,
        ),
    )
