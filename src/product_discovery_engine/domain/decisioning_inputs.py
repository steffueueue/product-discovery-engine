"""Explicit reviewed knowledge inputs; missing reviews are unknown, never optimistic."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .assumption_risk import AssumptionRiskAssessment
from .assumptions import Assumption
from .audit import Actor, ActorKind
from .common import DomainModel, Ordinal, ReferenceIds, Text
from .evidence import Evidence, EvidenceDirection
from .evidence_assessment import (
    EvidenceQualityAssessment,
    EvidenceScope,
    FreshnessRecord,
    assess_freshness,
    assess_quality,
)
from .evidence_origins import OriginRelationship
from .evidence_policy import AssumptionRiskPolicy, EvidencePolicies
from .hypotheses import Hypothesis
from .policies import StrategyPolicy
from .triangulation import TriangulationAssessment, triangulate
from .validation import ValidationActivity, ValidationEffect, ValidationResult, ValidationStatus


class HumanReview(DomainModel):
    hypothesis_id: UUID
    hypothesis_version: Annotated[int, Field(ge=1, strict=True)]
    actor: Actor
    reason: Text
    reviewed_at: AwareDatetime

    @model_validator(mode="after")
    def require_human(self) -> "HumanReview":
        if (
            self.actor.kind != ActorKind.HUMAN
            or type(self.hypothesis_version) is not int
            or (self.hypothesis_version < 1)
        ):
            raise ValueError("review requires an accountable human and positive material version")
        return self

    def require_context(self, hypothesis: Hypothesis, at: datetime) -> None:
        if (self.hypothesis_id, self.hypothesis_version) != (hypothesis.id, hypothesis.version):
            raise ValueError("human review must address this hypothesis version")
        if not hypothesis.updated_at <= self.reviewed_at <= at:
            raise ValueError("human review must follow material snapshot and precede assessment")


class AssumptionTreatment(DomainModel):
    risk_assessment_id: UUID
    review: HumanReview
    action: Text


class ReviewedAssumption(DomainModel):
    assumption: Assumption
    risk: AssumptionRiskAssessment | None
    risk_policy: AssumptionRiskPolicy | None = None
    treatment: AssumptionTreatment | None = None

    @model_validator(mode="after")
    def validate_risk(self) -> "ReviewedAssumption":
        if self.risk is not None:
            risk = self.risk
            if risk.assumption_id != self.assumption.id or self.risk_policy is None:
                raise ValueError("risk must address retained assumption and retain its policy")
            expected = (
                None
                if risk.decision_impact is None or risk.uncertainty is None
                else (self.risk_policy.assess(risk.decision_impact, risk.uncertainty))
            )
            if risk.policy_version != self.risk_policy.version or risk.risk != expected:
                raise ValueError("assumption risk must reconstruct from retained policy")
        elif self.risk_policy is not None:
            raise ValueError("risk policy requires its assessment")
        if self.treatment is not None and (
            self.risk is None
            or self.treatment.risk_assessment_id != self.risk.id
            or self.treatment.review.reviewed_at < self.risk.assessed_at
        ):
            raise ValueError("human treatment must address the retained risk assessment")
        return self


class ContradictionDisposition(StrEnum):
    HEALTHY_MIXED = "healthy_mixed"
    UNRESOLVED_MATERIAL = "unresolved_material"
    INVALIDATES_CRITICAL = "invalidates_critical"
    INVESTIGATED_ACCEPTED = "investigated_accepted"


class ContradictionReview(DomainModel):
    scope: EvidenceScope
    contradicting_evidence_ids: ReferenceIds
    disposition: ContradictionDisposition
    review: HumanReview


class ChallengeDisposition(StrEnum):
    ADDRESSED = "addressed"
    ACCEPTED = "accepted"
    UNRESOLVED = "unresolved"


class ChallengeItemReview(DomainModel):
    item_id: Text
    human_severity: Ordinal | None
    disposition: ChallengeDisposition
    rationale: Text


class ChallengeCompletion(DomainModel):
    record_id: UUID
    hypothesis_id: UUID
    analyzed_at: AwareDatetime
    evidence_ids: ReferenceIds
    item_ids: tuple[Text, ...]

    @model_validator(mode="after")
    def unique_items(self) -> "ChallengeCompletion":
        if not self.item_ids or len(self.item_ids) != len(set(self.item_ids)):
            raise ValueError("challenge item references must be nonempty and unique")
        return self


class ChallengeReview(DomainModel):
    completion: ChallengeCompletion
    items: tuple[ChallengeItemReview, ...]
    review: HumanReview | None

    @model_validator(mode="after")
    def match_items(self) -> "ChallengeReview":
        ids = tuple(i.item_id for i in self.items)
        if (
            len(ids) != len(set(ids))
            or (self.review is not None and set(ids) != set(self.completion.item_ids))
            or (self.review is None and self.items)
        ):
            raise ValueError("human challenge review must address every advisory item exactly once")
        if self.review is not None and self.review.reviewed_at < self.completion.analyzed_at:
            raise ValueError("human review cannot precede Challenge Mode completion")
        return self


class StrategyAcknowledgement(DomainModel):
    strategy: StrategyPolicy
    review: HumanReview


class DecisionKnowledge(DomainModel):
    scope: EvidenceScope
    evidence: tuple[Evidence, ...]
    origin_relationships: tuple[OriginRelationship, ...]
    quality: tuple[EvidenceQualityAssessment, ...]
    freshness_records: tuple[FreshnessRecord, ...]
    triangulation: TriangulationAssessment
    policies: EvidencePolicies

    @model_validator(mode="after")
    def reconstruct_evidence(self) -> "DecisionKnowledge":
        ids = tuple(e.id for e in self.evidence)
        if (
            len(ids) != len(set(ids))
            or any(not self.scope.matches(e) for e in self.evidence)
            or tuple(q.evidence_id for q in self.quality) != ids
            or tuple(r.after.evidence_id for r in self.freshness_records) != ids
            or self.triangulation
            != triangulate(
                self.scope,
                self.evidence,
                self.origin_relationships,
                policy=self.policies.triangulation,
            )
        ):
            raise ValueError("decision knowledge must preserve exact evidence scope and provenance")
        for evidence, quality, freshness in zip(
            self.evidence, self.quality, self.freshness_records, strict=True
        ):
            expected_freshness = assess_freshness(
                evidence,
                policy=self.policies.freshness,
                actor=quality.event.actor,
                at=quality.assessed_at,
                assessment_id=freshness.after.id,
                event_id=quality.event.id,
                context=freshness.after.context,
            ).after
            expected_quality = assess_quality(
                evidence,
                quality.input_basis,
                relevant_evidence=self.evidence,
                relationships=self.origin_relationships,
                freshness=expected_freshness,
                policy=self.policies.quality,
                actor=quality.event.actor,
                at=quality.assessed_at,
                assessment_id=quality.id,
                event_id=quality.event.id,
            )
            if quality != expected_quality or freshness.after != expected_freshness:
                raise ValueError("quality/freshness must reconstruct from original reviewer basis")
        return self


class ReadinessInput(DomainModel):
    hypothesis: Hypothesis
    target_scopes: tuple[EvidenceScope, ...]
    knowledge: tuple[DecisionKnowledge, ...]
    assumptions: tuple[ReviewedAssumption, ...]
    validations: tuple[ValidationActivity, ...]
    validation_results: tuple[ValidationResult, ...] = ()
    required_validation_ids: ReferenceIds = ()
    contradictions: tuple[ContradictionReview, ...] = ()
    challenge: ChallengeReview | None = None
    strategy_context: StrategyPolicy | None = None
    strategy_acknowledgement: StrategyAcknowledgement | None = None

    @model_validator(mode="after")
    def validate_links(self) -> "ReadinessInput":
        hypothesis = self.hypothesis
        if len({s.target for s in self.target_scopes}) != len(self.target_scopes):
            raise ValueError("one explicit claim/population scope per readiness target required")
        scopes = tuple(k.scope for k in self.knowledge)
        if len(scopes) != len(set(scopes)):
            raise ValueError("duplicate knowledge scopes")
        for scope in (*self.target_scopes, *scopes):
            if (
                scope.hypothesis_id != hypothesis.id
                or (scope.claim_id is not None and scope.claim_id not in hypothesis.links.claim_ids)
                or (
                    scope.assumption_id is not None
                    and scope.assumption_id not in hypothesis.links.assumption_ids
                )
            ):
                raise ValueError("readiness scope must identify this hypothesis and linked target")
        evidence = tuple(e for k in self.knowledge for e in k.evidence)
        if len({e.id for e in evidence}) != len(evidence) or (
            {e.id for e in evidence} != set(hypothesis.links.evidence_ids)
        ):
            raise ValueError("readiness must retain all linked evidence exactly once")
        ids = tuple(a.assumption.id for a in self.assumptions)
        if len(ids) != len(set(ids)) or set(ids) != set(hypothesis.links.assumption_ids):
            raise ValueError("readiness must inspect every linked assumption")
        validation_ids = tuple(v.id for v in self.validations)
        if (
            len(validation_ids) != len(set(validation_ids))
            or (set(validation_ids) != set(hypothesis.links.validation_ids))
            or any(
                v.hypothesis_id != hypothesis.id or v.target_assumption_id not in ids
                for v in self.validations
            )
        ):
            raise ValueError("readiness must retain all linked validation snapshots")
        if not set(self.required_validation_ids) <= set(validation_ids):
            raise ValueError("required validation must be linked")
        if len({r.activity_id for r in self.validation_results}) != len(self.validation_results):
            raise ValueError("duplicate results for a validation activity")
        for result in self.validation_results:
            activity = next((v for v in self.validations if v.id == result.activity_id), None)
            if (
                activity is None
                or activity.status != ValidationStatus.COMPLETED
                or result.tested_assumption_id != activity.target_assumption_id
                or result.criteria_version != activity.criteria_version
                or result.completed_at > activity.updated_at
                or not set(result.generated_evidence_ids) <= {e.id for e in evidence}
            ):
                raise ValueError(
                    "validation result must match criteria/activity and linked evidence"
                )
            generated = tuple(e for e in evidence if e.id in result.generated_evidence_ids)
            if any(e.target_assumption_id != result.tested_assumption_id for e in generated):
                raise ValueError("validation evidence must target the exact tested assumption")
            directions = {e.direction for e in generated}
            expected = {
                ValidationEffect.SUPPORTS: {EvidenceDirection.SUPPORTS},
                ValidationEffect.CONTRADICTS: {EvidenceDirection.CONTRADICTS},
                ValidationEffect.MIXED: set(EvidenceDirection),
            }.get(result.effect)
            if expected is not None and directions != expected:
                raise ValueError("validation effect must preserve original evidence directions")
        if len({r.scope for r in self.contradictions}) != len(self.contradictions):
            raise ValueError("duplicate contradiction reviews")
        for review in self.contradictions:
            packet = next((k for k in self.knowledge if k.scope == review.scope), None)
            if (
                packet is None
                or set(review.contradicting_evidence_ids)
                != {
                    e.id
                    for e in packet.evidence
                    if e.direction == EvidenceDirection.CONTRADICTS and e.invalidated_on is None
                }
                or not review.contradicting_evidence_ids
            ):
                raise ValueError(
                    "contradiction review must retain every active contradiction in scope"
                )
        if self.challenge is not None and (
            self.challenge.completion.hypothesis_id != hypothesis.id
            or not set(self.challenge.completion.evidence_ids) <= {e.id for e in evidence}
        ):
            raise ValueError("challenge completion must belong to retained hypothesis knowledge")
        if (
            self.strategy_context is not None
            and self.strategy_context.reference != hypothesis.content.strategy
        ):
            raise ValueError("strategy context must identify the hypothesis strategy reference")
        if self.strategy_acknowledgement is not None and (
            self.strategy_acknowledgement.strategy != self.strategy_context
        ):
            raise ValueError(
                "strategy acknowledgement must retain the configured strategy snapshot"
            )
        return self

    def require_time(self, at: datetime) -> None:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("readiness requires a timezone-aware timestamp")
        if at < self.hypothesis.updated_at:
            raise ValueError("readiness cannot precede material hypothesis snapshot")
        day = at.astimezone(UTC).date()
        for knowledge in self.knowledge:
            if any(q.assessed_at > at or q.freshness.as_of != day for q in knowledge.quality):
                raise ValueError("readiness requires same-day freshness, not future knowledge")
        for item in self.assumptions:
            if item.risk is not None:
                risk = item.risk
                if risk.assessed_at > at or risk.scope.hypothesis_id != self.hypothesis.id:
                    raise ValueError(
                        "risk assessment must belong to this hypothesis and precede review"
                    )
                packet = next((k for k in self.knowledge if k.scope == risk.scope), None)
                relevant = packet.evidence if packet else ()
                if (
                    set(risk.supporting_evidence_ids)
                    != {e.id for e in relevant if e.direction == EvidenceDirection.SUPPORTS}
                    or set(risk.contradicting_evidence_ids)
                    != {e.id for e in relevant if e.direction == EvidenceDirection.CONTRADICTS}
                    or set(risk.invalidated_evidence_ids)
                    != {e.id for e in relevant if e.invalidated_on is not None}
                ):
                    raise ValueError("risk assessment must reflect retained scoped evidence")
            if item.treatment:
                item.treatment.review.require_context(self.hypothesis, at)
        for review in self.contradictions:
            review.review.require_context(self.hypothesis, at)
        if self.challenge:
            if self.challenge.completion.analyzed_at > at:
                raise ValueError("Challenge Mode cannot complete in the future")
            if self.challenge.review:
                self.challenge.review.require_context(self.hypothesis, at)
        if self.strategy_acknowledgement:
            self.strategy_acknowledgement.review.require_context(self.hypothesis, at)
        if any(v.updated_at > at for v in self.validations):
            raise ValueError("validation cannot be from the future")
