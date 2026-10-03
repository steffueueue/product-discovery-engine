"""Decision consequence and unresolved uncertainty, not least-evidenced ranking."""

from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, model_validator

from .assumptions import Assumption
from .audit import Actor, AuditEvent, AuditMetadata, AuditTarget, EventType, ObjectKind
from .common import DomainModel, Ordinal, ReferenceIds, Text
from .evidence import Evidence, EvidenceDirection
from .evidence_assessment import EvidenceScope, require_evidence_time
from .evidence_policy import AssumptionRiskPolicy


class AssumptionRiskAssessment(DomainModel):
    id: UUID
    assumption_id: UUID
    scope: EvidenceScope
    decision_impact: Ordinal | None
    uncertainty: Ordinal | None
    supporting_evidence_ids: ReferenceIds
    contradicting_evidence_ids: ReferenceIds
    invalidated_evidence_ids: ReferenceIds
    evidence_gaps: tuple[Text, ...]
    risk: Ordinal | None
    explanation: Text
    policy_version: Text
    assessed_at: AwareDatetime
    event: AuditEvent

    @model_validator(mode="after")
    def validate_audit(self) -> "AssumptionRiskAssessment":
        if (
            self.scope.assumption_id != self.assumption_id
            or self.event.event_type != EventType.ASSUMPTION_RISK_REASSESSED
            or self.event.target != AuditTarget(kind=ObjectKind.ASSUMPTION, id=self.assumption_id)
            or self.event.occurred_at != self.assessed_at
            or self.event.metadata.related_ids != (self.id,)
        ):
            raise ValueError("risk assessment scope and audit must identify assumption")
        return self


def assess_assumption_risk(
    assumption: Assumption,
    scope: EvidenceScope,
    evidence: tuple[Evidence, ...],
    *,
    decision_impact: Ordinal | None,
    uncertainty: Ordinal | None,
    rationale: str,
    evidence_gaps: tuple[str, ...],
    policy: AssumptionRiskPolicy,
    actor: Actor,
    at: datetime,
    assessment_id: UUID,
    event_id: UUID,
) -> AssumptionRiskAssessment:
    if scope.assumption_id != assumption.id:
        raise ValueError("risk must be scoped to the explicit assumption")
    if len({e.id for e in evidence}) != len(evidence):
        raise ValueError("duplicate evidence IDs")
    relevant = tuple(e for e in evidence if scope.matches(e))
    for item in relevant:
        require_evidence_time(item, at)
    risk = None
    if decision_impact is not None and uncertainty is not None:
        risk = policy.assess(decision_impact, uncertainty)
    return AssumptionRiskAssessment(
        id=assessment_id,
        assumption_id=assumption.id,
        scope=scope,
        decision_impact=decision_impact,
        uncertainty=uncertainty,
        supporting_evidence_ids=tuple(
            e.id for e in relevant if e.direction == EvidenceDirection.SUPPORTS
        ),
        contradicting_evidence_ids=tuple(
            e.id for e in relevant if e.direction == EvidenceDirection.CONTRADICTS
        ),
        invalidated_evidence_ids=tuple(e.id for e in relevant if e.invalidated_on is not None),
        evidence_gaps=evidence_gaps,
        risk=risk,
        explanation=rationale,
        policy_version=policy.version,
        assessed_at=at,
        event=AuditEvent(
            id=event_id,
            actor=actor,
            occurred_at=at,
            event_type=EventType.ASSUMPTION_RISK_REASSESSED,
            target=AuditTarget(kind=ObjectKind.ASSUMPTION, id=assumption.id),
            metadata=AuditMetadata(related_ids=(assessment_id,), reason=rationale),
        ),
    )
