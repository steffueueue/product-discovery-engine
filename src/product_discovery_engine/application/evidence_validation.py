"""Deterministic knowledge assembly; callers retain snapshots and all returned audits."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import model_validator

from product_discovery_engine.domain.audit import Actor
from product_discovery_engine.domain.common import DomainModel
from product_discovery_engine.domain.evidence import Evidence
from product_discovery_engine.domain.evidence_assessment import (
    EvidenceQualityAssessment,
    EvidenceScope,
    FreshnessRecord,
    QualityInput,
    assess_freshness,
    assess_quality,
)
from product_discovery_engine.domain.evidence_origins import OriginRelationship
from product_discovery_engine.domain.evidence_policy import EvidencePolicies
from product_discovery_engine.domain.triangulation import TriangulationAssessment, triangulate


class EvidenceReviewInput(DomainModel):
    evidence_id: UUID
    basis: QualityInput
    freshness_context: str | None = None


class KnowledgeState(DomainModel):
    scope: EvidenceScope
    evidence: tuple[Evidence, ...]
    origin_relationships: tuple[OriginRelationship, ...]
    quality: tuple[EvidenceQualityAssessment, ...]
    freshness_records: tuple[FreshnessRecord, ...]
    triangulation: TriangulationAssessment

    @model_validator(mode="after")
    def validate_scope(self) -> "KnowledgeState":
        if any(not self.scope.matches(e) for e in self.evidence):
            raise ValueError("knowledge state must retain only the exact target scope")
        ids = tuple(e.id for e in self.evidence)
        if (
            len(set(ids)) != len(ids)
            or tuple(q.evidence_id for q in self.quality) != ids
            or tuple(r.after.evidence_id for r in self.freshness_records) != ids
            or self.triangulation.scope != self.scope
            or self.triangulation.relevant_evidence_ids != ids
        ):
            raise ValueError("knowledge assessment references must match retained evidence")
        if self.triangulation != triangulate(
            self.scope, self.evidence, self.origin_relationships, policy=self.triangulation.policy
        ):
            raise ValueError(
                "knowledge triangulation must match evidence directions and origin history"
            )
        if any(
            q.input_basis.scope != self.scope or q.freshness != r.after
            for q, r in zip(self.quality, self.freshness_records, strict=True)
        ):
            raise ValueError("quality and freshness must share exact retained scope and assessment")
        return self


class EvidenceValidationService:
    def __init__(self, policies: EvidencePolicies) -> None:
        self.policies = EvidencePolicies.model_validate(policies)

    def assess(
        self,
        scope: EvidenceScope,
        evidence: tuple[Evidence, ...],
        relationships: tuple[OriginRelationship, ...],
        reviews: tuple[EvidenceReviewInput, ...],
        *,
        actor: Actor,
        at: datetime,
        previous: KnowledgeState | None = None,
    ) -> KnowledgeState:
        """No automatic acceptance: inputs are explicit reviewer basis, not AI proposals."""
        if len({e.id for e in evidence}) != len(evidence):
            raise ValueError("duplicate evidence IDs")
        relevant = tuple(e for e in evidence if scope.matches(e))
        if previous is not None and previous.scope != scope:
            raise ValueError("previous assessment must have the same scope")
        if len({r.evidence_id for r in reviews}) != len(reviews):
            raise ValueError("duplicate quality review inputs")
        by_id = {r.evidence_id: r for r in reviews}
        if set(by_id) != {e.id for e in relevant}:
            raise ValueError(
                "every relevant item needs explicit quality input, including contradictions"
            )
        if previous is not None and not {e.id for e in previous.evidence} <= {
            e.id for e in relevant
        }:
            raise ValueError("reassessment must retain prior evidence, including contradictions")
        if previous is not None:
            current = {e.id: e for e in relevant}
            for old_item in previous.evidence:
                new_item = current[old_item.id]
                allowed = {"reviewed_on", "invalidated_on", "invalidation_reason"}
                if any(
                    getattr(old_item, name) != getattr(new_item, name)
                    for name in Evidence.model_fields
                    if name not in allowed
                ):
                    raise ValueError(
                        "reassessment cannot rewrite an evidence statement or provenance"
                    )
                if old_item.invalidated_on is not None and (
                    old_item.invalidated_on != new_item.invalidated_on
                    or old_item.invalidation_reason != new_item.invalidation_reason
                ):
                    raise ValueError(
                        "invalidation history cannot be silently reversed or rewritten"
                    )
                if old_item.reviewed_on is not None and (
                    new_item.reviewed_on is None or new_item.reviewed_on < old_item.reviewed_on
                ):
                    raise ValueError("review history cannot move backwards")
        for relation in relationships:
            if relation.event.occurred_at > at:
                raise ValueError("cannot assess source relationships from the future")
        old = {r.after.evidence_id: r.after for r in previous.freshness_records} if previous else {}
        freshness_records = []
        quality = []
        for item in relevant:
            review = by_id[item.id]
            freshness = assess_freshness(
                item,
                policy=self.policies.freshness,
                actor=actor,
                at=at,
                assessment_id=uuid4(),
                event_id=uuid4(),
                context=review.freshness_context,
                previous=old.get(item.id),
            )
            freshness_records.append(freshness)
            quality.append(
                assess_quality(
                    item,
                    review.basis,
                    relevant_evidence=relevant,
                    relationships=relationships,
                    freshness=freshness.after,
                    policy=self.policies.quality,
                    actor=actor,
                    at=at,
                    assessment_id=uuid4(),
                    event_id=uuid4(),
                )
            )
        return KnowledgeState(
            scope=scope,
            evidence=relevant,
            origin_relationships=tuple(r for r in relationships if r.evidence_id in by_id),
            quality=tuple(quality),
            freshness_records=tuple(freshness_records),
            triangulation=triangulate(
                scope, evidence, relationships, policy=self.policies.triangulation
            ),
        )
