"""Deterministic claim-scoped quality and auditable freshness assessments."""

from datetime import UTC, date, datetime
from uuid import UUID

from pydantic import AwareDatetime, model_validator

from .audit import Actor, AuditEvent, AuditMetadata, AuditTarget, EventType, ObjectKind
from .common import DomainModel, Ordinal, Text, ordinal_min
from .evidence import Evidence, EvidenceTarget, Freshness
from .evidence_origins import OriginRelationship, group_sources
from .evidence_policy import (
    CoverageBasis,
    DirectnessBasis,
    EvidenceFreshnessPolicy,
    IndependenceBasis,
    QualityRubric,
    ReliabilityBasis,
)


class EvidenceScope(DomainModel):
    hypothesis_id: UUID
    target: EvidenceTarget
    claim_id: UUID | None = None
    assumption_id: UUID | None = None
    population: Text | None = None

    @model_validator(mode="after")
    def validate_target(self) -> "EvidenceScope":
        if (self.target == EvidenceTarget.ASSUMPTION) != (self.assumption_id is not None):
            raise ValueError("assumption scope requires exactly one assumption reference")
        if self.claim_id is None and self.assumption_id is None:
            raise ValueError("assessment scope requires an explicit claim or assumption reference")
        return self

    @classmethod
    def of(cls, evidence: Evidence) -> "EvidenceScope":
        return cls(
            hypothesis_id=evidence.hypothesis_id,
            target=evidence.target,
            claim_id=evidence.target_claim_id,
            assumption_id=evidence.target_assumption_id,
            population=evidence.population,
        )

    def matches(self, evidence: Evidence) -> bool:
        return self == self.of(evidence)


class FreshnessAssessment(DomainModel):
    id: UUID
    evidence_id: UUID
    as_of: date
    state: Freshness
    reason: Text
    context: Text
    policy_version: Text
    assessed_at: AwareDatetime


class FreshnessRecord(DomainModel):
    before: FreshnessAssessment | None
    after: FreshnessAssessment
    event: AuditEvent | None

    @model_validator(mode="after")
    def validate_record(self) -> "FreshnessRecord":
        if self.before is not None and (
            self.before.id == self.after.id
            or self.before.evidence_id != self.after.evidence_id
            or self.before.as_of > self.after.as_of
            or self.before.assessed_at > self.after.assessed_at
        ):
            raise ValueError("freshness history must preserve identity and chronology")
        changed = self.before is None or self.before.state != self.after.state
        if changed != (self.event is not None):
            raise ValueError("freshness changes require an audit event")
        if self.event is not None and (
            self.event.event_type != EventType.EVIDENCE_FRESHNESS_CHANGED
            or self.event.target != AuditTarget(kind=ObjectKind.EVIDENCE, id=self.after.evidence_id)
            or self.event.occurred_at != self.after.assessed_at
            or self.event.metadata.related_ids != (self.after.id,)
            or self.event.metadata.previous_status
            != (self.before.state.value if self.before else None)
            or self.event.metadata.resulting_status != self.after.state.value
            or self.event.metadata.reason != self.after.reason
        ):
            raise ValueError("freshness audit does not match assessment")
        return self


def require_evidence_time(evidence: Evidence, at: datetime) -> date:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("assessment requires an aware timestamp")
    day = at.astimezone(UTC).date()
    if any(
        value is not None and value > day
        for value in (
            evidence.collected_on,
            evidence.reviewed_on,
            evidence.invalidated_on,
        )
    ):
        raise ValueError("cannot evaluate a future evidence snapshot")
    if (
        evidence.invalidated_on is None
        and evidence.valid_from is not None
        and evidence.valid_from > day
    ):
        raise ValueError("evidence is not yet valid; retain it as pending context")
    return day


def assess_freshness(
    evidence: Evidence,
    *,
    policy: EvidenceFreshnessPolicy,
    actor: Actor,
    at: datetime,
    assessment_id: UUID,
    event_id: UUID,
    context: str | None = None,
    previous: FreshnessAssessment | None = None,
) -> FreshnessRecord:
    evidence = Evidence.model_validate(evidence)
    day = require_evidence_time(evidence, at)
    rule = policy.rule(context)
    state = evidence.freshness(as_of=day, policy=rule.thresholds)
    reason = "Within configured review interval"
    if state == Freshness.INVALIDATED:
        reason = "Explicit invalidation: " + str(evidence.invalidation_reason)
    else:
        if state == Freshness.STALE and not rule.automatic_staleness:
            state = Freshness.REVIEW_DUE
        if evidence.review_after is not None and day >= evidence.review_after:
            if evidence.reviewed_on is None or evidence.reviewed_on < evidence.review_after:
                if state == Freshness.CURRENT:
                    state = Freshness.REVIEW_DUE
                reason = "Explicit review_after reached; historical evidence is not declared false"
        if state == Freshness.STALE:
            reason = "Configured stale interval reached; retained for review, not declared false"
        elif state == Freshness.REVIEW_DUE and reason.startswith("Within"):
            reason = "Configured review interval reached; recheck relevance and methodology"
    after = FreshnessAssessment(
        id=assessment_id,
        evidence_id=evidence.id,
        as_of=day,
        state=state,
        reason=reason,
        context=rule.context,
        policy_version=policy.version,
        assessed_at=at,
    )
    event = None
    if previous is None or previous.state != state:
        event = AuditEvent(
            id=event_id,
            actor=actor,
            occurred_at=at,
            event_type=EventType.EVIDENCE_FRESHNESS_CHANGED,
            target=AuditTarget(kind=ObjectKind.EVIDENCE, id=evidence.id),
            metadata=AuditMetadata(
                previous_status=previous.state.value if previous else None,
                resulting_status=state.value,
                related_ids=(after.id,),
                reason=reason,
            ),
        )
    return FreshnessRecord(before=previous, after=after, event=event)


class EvidenceInvalidation(DomainModel):
    before: Evidence
    after: Evidence
    event: AuditEvent

    @model_validator(mode="after")
    def validate_record(self) -> "EvidenceInvalidation":
        expected = {
            **self.before.model_dump(),
            "invalidated_on": self.after.invalidated_on,
            "invalidation_reason": self.after.invalidation_reason,
        }
        if (
            self.before.invalidated_on is not None
            or self.after.invalidated_on is None
            or self.after != Evidence.model_validate(expected)
            or self.event.event_type != EventType.EVIDENCE_INVALIDATED
            or self.event.target != AuditTarget(kind=ObjectKind.EVIDENCE, id=self.after.id)
            or self.event.occurred_at.astimezone(UTC).date() != self.after.invalidated_on
            or self.event.metadata.reason != self.after.invalidation_reason
        ):
            raise ValueError("invalidation must retain original evidence and matching audit")
        return self


def invalidate_evidence(
    evidence: Evidence,
    *,
    reason: str,
    actor: Actor,
    at: datetime,
    event_id: UUID,
) -> EvidenceInvalidation:
    day = require_evidence_time(evidence, at)
    after = Evidence.model_validate(
        {**evidence.model_dump(), "invalidated_on": day, "invalidation_reason": reason}
    )
    return EvidenceInvalidation(
        before=evidence,
        after=after,
        event=AuditEvent(
            id=event_id,
            actor=actor,
            occurred_at=at,
            event_type=EventType.EVIDENCE_INVALIDATED,
            target=AuditTarget(kind=ObjectKind.EVIDENCE, id=evidence.id),
            metadata=AuditMetadata(
                changed_fields=("invalidated_on", "invalidation_reason"), reason=reason
            ),
        ),
    )


class QualityInput(DomainModel):
    scope: EvidenceScope
    directness: DirectnessBasis | None
    reliability: ReliabilityBasis | None
    coverage: CoverageBasis | None
    rationale: Text
    methodology_basis: Text
    population_basis: Text


class EvidenceQualityAssessment(DomainModel):
    id: UUID
    evidence_id: UUID
    input_basis: QualityInput
    directness: Ordinal | None
    reliability: Ordinal | None
    coverage: Ordinal | None
    recency: Ordinal
    independence: Ordinal
    independence_basis: IndependenceBasis
    freshness: FreshnessAssessment
    source_group_evidence_ids: tuple[UUID, ...]
    policy_version: Text
    aggregate: Ordinal | None
    explanation: Text
    assessed_at: AwareDatetime
    event: AuditEvent

    @model_validator(mode="after")
    def validate_assessment(self) -> "EvidenceQualityAssessment":
        if (
            self.event.event_type != EventType.EVIDENCE_QUALITY_ASSESSED
            or self.event.target != AuditTarget(kind=ObjectKind.EVIDENCE, id=self.evidence_id)
            or self.event.occurred_at != self.assessed_at
            or self.event.metadata.related_ids != (self.id,)
            or self.freshness.evidence_id != self.evidence_id
            or self.freshness.assessed_at != self.assessed_at
        ):
            raise ValueError("quality assessment must match freshness and audit")
        dimensions = (
            self.directness,
            self.reliability,
            self.coverage,
            self.recency,
            self.independence,
        )
        known = tuple(d for d in dimensions if d is not None)
        expected = ordinal_min(known) if len(known) == 5 else None
        if self.aggregate != expected:
            raise ValueError("quality aggregate must be weakest known dimension or unknown")
        return self


def assess_quality(
    evidence: Evidence,
    basis: QualityInput,
    *,
    relevant_evidence: tuple[Evidence, ...],
    relationships: tuple[OriginRelationship, ...],
    freshness: FreshnessAssessment,
    policy: QualityRubric,
    actor: Actor,
    at: datetime,
    assessment_id: UUID,
    event_id: UUID,
) -> EvidenceQualityAssessment:
    require_evidence_time(evidence, at)
    if not basis.scope.matches(evidence):
        raise ValueError("quality input must match exact evidence target/claim/population")
    if evidence not in relevant_evidence or any(
        not basis.scope.matches(e) for e in relevant_evidence
    ):
        raise ValueError("quality context must include the assessed snapshot and only its scope")
    if freshness.as_of != at.astimezone(UTC).date():
        raise ValueError("quality needs freshness assessed for the same day")
    groups = group_sources(relevant_evidence, relationships)
    group = next(g for g in groups if evidence.id in g.evidence_ids)
    independence_basis = IndependenceBasis.UNKNOWN
    if group.traceable:
        if len(group.evidence_ids) > 1:
            independence_basis = IndependenceBasis.SHARED_FAMILY
        elif len(groups) > 1 and all(g.traceable for g in groups):
            independence_basis = IndependenceBasis.DISTINCT_FAMILY
        else:
            independence_basis = IndependenceBasis.TRACEABLE_ORIGIN
    directness = policy.directness[basis.directness] if basis.directness else None
    reliability = policy.reliability[basis.reliability] if basis.reliability else None
    coverage = policy.coverage[basis.coverage] if basis.coverage else None
    # Sample observations never establish prevalence in a wider population.
    if coverage is not None and evidence.target in {EvidenceTarget.REACH, EvidenceTarget.FREQUENCY}:
        if basis.coverage in {
            CoverageBasis.SINGLE_ACCOUNT,
            CoverageBasis.CONVENIENCE_SAMPLE,
            CoverageBasis.BOUNDED_SAMPLE,
        }:
            coverage = ordinal_min((coverage, policy.population_sample_cap))
    recency = policy.recency[freshness.state]
    independence = policy.independence[independence_basis]
    dimensions = (directness, reliability, coverage, recency, independence)
    known = tuple(d for d in dimensions if d is not None)
    aggregate = ordinal_min(known) if len(known) == 5 else None
    explanation = "Weakest dimension controls quality; item quantity has no quality bonus"
    if aggregate is None:
        explanation = "Unspecified dimension: aggregate quality is unknown"
    return EvidenceQualityAssessment(
        id=assessment_id,
        evidence_id=evidence.id,
        input_basis=basis,
        directness=directness,
        reliability=reliability,
        coverage=coverage,
        recency=recency,
        independence=independence,
        independence_basis=independence_basis,
        freshness=freshness,
        source_group_evidence_ids=group.evidence_ids,
        policy_version=policy.version,
        aggregate=aggregate,
        explanation=explanation,
        assessed_at=at,
        event=AuditEvent(
            id=event_id,
            actor=actor,
            occurred_at=at,
            event_type=EventType.EVIDENCE_QUALITY_ASSESSED,
            target=AuditTarget(kind=ObjectKind.EVIDENCE, id=evidence.id),
            metadata=AuditMetadata(related_ids=(assessment_id,), reason=basis.rationale),
        ),
    )
