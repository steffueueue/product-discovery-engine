"""Deterministic next-learning assessments; no portfolio score or arbitrary tie-break."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, model_validator

from .assumption_risk import AssumptionRiskAssessment
from .assumptions import Assumption, ValidationState
from .audit import Actor, AuditEvent, AuditMetadata, AuditTarget, EventType, ObjectKind
from .common import DomainModel, Ordinal, ReferenceIds, Text
from .decisioning_policy import DiscoveryPriorityPolicy, PriorityCategory, at_least
from .hypotheses import Hypothesis
from .validation import RelativeCost, RelativeSpeed, ValidationActivity, ValidationStatus


class LearningTargetKind(StrEnum):
    ASSUMPTION = "assumption"
    UNKNOWN = "unknown"
    EVIDENCE_GAP = "evidence_gap"
    CONTRADICTION = "contradiction"


class LearningAction(StrEnum):
    VALIDATE = "validate"
    REFRAME = "reframe"
    CLARIFY = "clarify"
    MONITOR_ACTIVE_VALIDATION = "monitor_active_validation"
    UNBLOCK = "unblock"
    NO_ACTION = "no_action"


class LearningInput(DomainModel):
    hypothesis: Hypothesis
    target_id: UUID
    target_kind: LearningTargetKind
    target_description: Text
    assumption: Assumption | None = None
    risk_assessment: AssumptionRiskAssessment | None = None
    decision_impact: Ordinal | None
    unresolved_uncertainty: Ordinal | None
    evidence_gaps: tuple[Text, ...]
    contradictory_evidence_ids: ReferenceIds = ()
    freshness_concerns: tuple[Text, ...] = ()
    expected_information_gain: Ordinal | None
    relative_cost: RelativeCost | None
    relative_speed: RelativeSpeed | None
    validations: tuple[ValidationActivity, ...] = ()
    proposed_validation_id: UUID | None = None
    completed_dependency_ids: ReferenceIds = ()
    blockers: tuple[Text, ...] = ()

    @model_validator(mode="after")
    def validate_input(self) -> "LearningInput":
        if (self.target_kind == LearningTargetKind.ASSUMPTION) != (self.assumption is not None):
            raise ValueError("assumption learning target requires the assumption snapshot")
        if self.assumption is not None and (
            self.target_id != self.assumption.id
            or self.assumption.id not in self.hypothesis.links.assumption_ids
        ):
            raise ValueError("learning assumption must be linked to hypothesis")
        if self.risk_assessment is not None:
            risk = self.risk_assessment
            if (
                risk.assumption_id != self.target_id
                or risk.scope.hypothesis_id != self.hypothesis.id
                or risk.decision_impact != self.decision_impact
                or risk.uncertainty != self.unresolved_uncertainty
                or risk.evidence_gaps != self.evidence_gaps
                or risk.contradicting_evidence_ids != self.contradictory_evidence_ids
            ):
                raise ValueError("priority inputs must preserve supplied assumption risk")
        if len({v.id for v in self.validations}) != len(self.validations) or any(
            v.hypothesis_id != self.hypothesis.id
            or v.id not in self.hypothesis.links.validation_ids
            or v.target_assumption_id not in self.hypothesis.links.assumption_ids
            for v in self.validations
        ):
            raise ValueError("validation snapshots must uniquely belong to learning target")
        if self.proposed_validation_id is not None:
            proposal = next(
                (v for v in self.validations if v.id == self.proposed_validation_id), None
            )
            if (
                proposal is None
                or proposal.target_assumption_id != self.target_id
                or (
                    proposal.expected_information_gain,
                    proposal.relative_cost,
                    proposal.relative_speed,
                )
                != (self.expected_information_gain, self.relative_cost, self.relative_speed)
            ):
                raise ValueError("learning proposal must preserve validation gain/cost/speed")
        return self


class PriorityResult(DomainModel):
    assumption_risk: Ordinal | None
    underlying_priority: PriorityCategory
    priority: PriorityCategory
    action: LearningAction
    actionable: bool
    validation_context_complete: bool
    dependency_ids: ReferenceIds
    blocker_summary: tuple[Text, ...]
    explanation: Text


def evaluate_priority(inputs: LearningInput, policy: DiscoveryPriorityPolicy) -> PriorityResult:
    impact, uncertainty = inputs.decision_impact, inputs.unresolved_uncertainty
    unresolved = bool(
        (
            inputs.assumption is not None
            and inputs.assumption.validation_state
            in {ValidationState.REFUTED, ValidationState.INCONCLUSIVE}
        )
        or inputs.evidence_gaps
        or inputs.freshness_concerns
        or (
            set(inputs.contradictory_evidence_ids)
            - set(inputs.risk_assessment.invalidated_evidence_ids if inputs.risk_assessment else ())
        )
    )
    invalidated = (
        set(inputs.risk_assessment.invalidated_evidence_ids) if inputs.risk_assessment else set()
    )
    active_contradictions = set(inputs.contradictory_evidence_ids) - invalidated
    if impact is None or uncertainty is None:
        base = PriorityCategory.UNKNOWN
    elif not unresolved and at_least(policy.resolved_uncertainty_at_most, uncertainty):
        base = PriorityCategory.NO_ACTION
    else:
        base = policy.category(impact, uncertainty)
    relevant_validations = tuple(
        v for v in inputs.validations if v.target_assumption_id == inputs.target_id
    )
    validation_context_complete = {v.id for v in inputs.validations} == set(
        inputs.hypothesis.links.validation_ids
    )
    dependencies = tuple(dict.fromkeys(d for v in relevant_validations for d in v.dependencies))
    pending = tuple(
        dict.fromkeys(
            d
            for v in inputs.validations
            if v.status not in {ValidationStatus.COMPLETED, ValidationStatus.CANCELLED}
            for d in v.dependencies
            if d not in inputs.completed_dependency_ids
        )
    )
    blockers = inputs.blockers + tuple(f"Incomplete dependency: {d}" for d in pending)
    active = any(
        v.status in {ValidationStatus.READY, ValidationStatus.RUNNING} for v in relevant_validations
    ) or (
        inputs.assumption is not None
        and inputs.assumption.validation_state == ValidationState.IN_PROGRESS
    )
    action = LearningAction.VALIDATE
    priority = base
    if active and policy.suppress_active_validation:
        priority, action = PriorityCategory.NO_ACTION, LearningAction.MONITOR_ACTIVE_VALIDATION
    elif blockers:
        action = LearningAction.UNBLOCK
    elif active_contradictions or (
        inputs.assumption and inputs.assumption.validation_state == ValidationState.REFUTED
    ):
        action = LearningAction.REFRAME
    elif base == PriorityCategory.UNKNOWN:
        action = LearningAction.CLARIFY
    elif base == PriorityCategory.NO_ACTION:
        action = LearningAction.NO_ACTION
    context_label = "complete" if validation_context_complete else "unknown/incomplete"
    explanation = (
        f"Impact={impact.value if impact else 'unknown'}, "
        f"uncertainty={uncertainty.value if uncertainty else 'unknown'}; "
        f"rule category={base.value}; action={action.value}. "
        "Cost, speed and information gain remain explicit planning inputs; they never demote "
        "critical learning or break a category tie. Unknown does not imply low importance. "
        f"Validation context is {context_label}."
    )
    return PriorityResult(
        assumption_risk=inputs.risk_assessment.risk if inputs.risk_assessment else None,
        underlying_priority=base,
        priority=priority,
        action=action,
        actionable=action
        in {LearningAction.VALIDATE, LearningAction.REFRAME, LearningAction.CLARIFY}
        and priority != PriorityCategory.NO_ACTION
        and validation_context_complete,
        validation_context_complete=validation_context_complete,
        dependency_ids=dependencies,
        blocker_summary=blockers,
        explanation=explanation,
    )


class DiscoveryPriorityAssessment(DomainModel):
    id: UUID
    inputs: LearningInput
    policy: DiscoveryPriorityPolicy
    policy_version: Text
    assessed_at: AwareDatetime
    result: PriorityResult
    event: AuditEvent

    @model_validator(mode="after")
    def validate_record(self) -> "DiscoveryPriorityAssessment":
        if (
            self.assessed_at < self.inputs.hypothesis.updated_at
            or any(v.updated_at > self.assessed_at for v in self.inputs.validations)
            or (
                self.inputs.risk_assessment is not None
                and self.inputs.risk_assessment.assessed_at > self.assessed_at
            )
        ):
            raise ValueError("priority assessment cannot precede its inputs")
        if self.policy_version != self.policy.version or self.result != evaluate_priority(
            self.inputs, self.policy
        ):
            raise ValueError("priority result must reconstruct from retained inputs/policy")
        require_decision_audit(
            self.event,
            self.id,
            self.inputs.hypothesis.id,
            EventType.DISCOVERY_PRIORITY_ASSESSED,
            self.assessed_at,
        )
        return self


def decision_audit(
    id: UUID,
    record_id: UUID,
    hypothesis_id: UUID,
    event_type: EventType,
    actor: Actor,
    at: datetime,
    *,
    reason: str | None = None,
) -> AuditEvent:
    return AuditEvent(
        id=id,
        actor=actor,
        occurred_at=at,
        event_type=event_type,
        target=AuditTarget(kind=ObjectKind.DECISION, id=record_id),
        metadata=AuditMetadata(related_ids=(hypothesis_id,), reason=reason),
    )


def require_decision_audit(
    event: AuditEvent,
    record_id: UUID,
    hypothesis_id: UUID,
    event_type: EventType,
    at: datetime,
) -> None:
    if (
        event.target != AuditTarget(kind=ObjectKind.DECISION, id=record_id)
        or event.event_type != event_type
        or event.occurred_at != at
        or event.metadata.related_ids != (hypothesis_id,)
    ):
        raise ValueError("decision audit must match assessment, hypothesis and timestamp")


def assess_discovery_priority(
    inputs: LearningInput,
    *,
    policy: DiscoveryPriorityPolicy,
    actor: Actor,
    at: datetime,
    assessment_id: UUID,
    event_id: UUID,
) -> DiscoveryPriorityAssessment:
    inputs = LearningInput.model_validate(inputs)
    policy = DiscoveryPriorityPolicy.model_validate(policy)
    return DiscoveryPriorityAssessment(
        id=assessment_id,
        inputs=inputs,
        policy=policy,
        policy_version=policy.version,
        assessed_at=at,
        result=evaluate_priority(inputs, policy),
        event=decision_audit(
            event_id,
            assessment_id,
            inputs.hypothesis.id,
            EventType.DISCOVERY_PRIORITY_ASSESSED,
            actor,
            at,
        ),
    )


class PriorityGroups(DomainModel):
    ordinal_ties: tuple[tuple[DiscoveryPriorityAssessment, ...], ...]
    unknown_to_clarify: tuple[DiscoveryPriorityAssessment, ...]


def priority_ties(
    assessments: tuple[DiscoveryPriorityAssessment, ...],
) -> PriorityGroups:
    """Group learning targets within one snapshot; unknown is outside ordinal ordering."""
    assessments = tuple(DiscoveryPriorityAssessment.model_validate(a) for a in assessments)
    if len({a.id for a in assessments}) != len(assessments):
        raise ValueError("duplicate priority assessments")
    if assessments and any(
        a.inputs.hypothesis != assessments[0].inputs.hypothesis or a.policy != assessments[0].policy
        for a in assessments
    ):
        raise ValueError(
            "learning targets must share one hypothesis snapshot and policy; no portfolio ranking"
        )
    return PriorityGroups(
        ordinal_ties=tuple(
            group
            for category in PriorityCategory
            if category != PriorityCategory.UNKNOWN
            and (group := tuple(a for a in assessments if a.result.priority == category))
        ),
        unknown_to_clarify=tuple(
            a for a in assessments if a.result.priority == PriorityCategory.UNKNOWN
        ),
    )
