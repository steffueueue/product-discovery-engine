"""Human causal interpretation is separate from deterministic target achievement."""

from datetime import UTC
from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, model_validator

from .audit import Actor, AuditEvent, EventType, ObjectKind
from .common import DomainModel, Ordinal, Text
from .evidence import Evidence, EvidenceDirection, EvidenceTarget, Freshness
from .evidence_assessment import EvidenceQualityAssessment, EvidenceScope
from .outcome_audit import check_event
from .outcome_measurement import OutcomeMeasurementPlan


class CausalState(StrEnum):
    NOT_ASSESSED = "not_assessed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    PLAUSIBLE = "plausible"
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"


class StudyDesign(StrEnum):
    NONE = "none"
    BEFORE_AFTER = "before_after"
    CONTROLLED = "controlled"


class CausalInterpretation(DomainModel):
    id: UUID
    plan: OutcomeMeasurementPlan
    scope: EvidenceScope
    claim: Text
    state: CausalState
    supporting_evidence: tuple[Evidence, ...] = ()
    contradicting_evidence: tuple[Evidence, ...] = ()
    quality: tuple[EvidenceQualityAssessment, ...] = ()
    design: StudyDesign
    design_basis: Text
    assignment_notes: Text | None = None
    instrumentation_notes: Text | None = None
    exposure_population: Text | None = None
    confounders: tuple[Text, ...]
    limitations: tuple[Text, ...]
    interpretation: Text
    reviewed_by: Actor
    reviewed_at: AwareDatetime
    event: AuditEvent

    @model_validator(mode="after")
    def reconstruct(self) -> "CausalInterpretation":
        if self.scope.hypothesis_id != self.plan.hypothesis.id or self.scope.target not in {
            EvidenceTarget.CAUSAL_MECHANISM,
            EvidenceTarget.ASSUMPTION,
        }:
            raise ValueError(
                "causal interpretation requires an exact causal claim/assumption scope"
            )
        if (
            self.scope.claim_id is not None
            and self.scope.claim_id not in self.plan.hypothesis.links.claim_ids
        ):
            raise ValueError("causal claim must belong to original discovery")
        if (
            self.scope.assumption_id is not None
            and self.scope.assumption_id not in self.plan.hypothesis.links.assumption_ids
        ):
            raise ValueError("causal assumption must belong to original discovery")
        evidence = self.supporting_evidence + self.contradicting_evidence
        if len({e.id for e in evidence}) != len(evidence):
            raise ValueError("causal evidence IDs must be unique")
        for items, direction in (
            (self.supporting_evidence, EvidenceDirection.SUPPORTS),
            (self.contradicting_evidence, EvidenceDirection.CONTRADICTS),
        ):
            if any(
                not self.scope.matches(e)
                or e.direction != direction
                or e.invalidated_on is not None
                or e.collected_on > self.reviewed_at.astimezone(UTC).date()
                for e in items
            ):
                raise ValueError(
                    "causal evidence must retain exact target/population and direction"
                )
        if not set(self.plan.confounders) <= set(self.confounders):
            raise ValueError("known plan confounders cannot disappear from causal interpretation")
        if self.reviewed_at < self.plan.recorded_at:
            raise ValueError("causal interpretation cannot precede its plan")
        if len({q.evidence_id for q in self.quality}) != len(self.quality) or any(
            q.evidence_id not in {e.id for e in evidence}
            or q.input_basis.scope != self.scope
            or q.assessed_at > self.reviewed_at
            for q in self.quality
        ):
            raise ValueError("quality must reuse exact scoped Milestone 3 evidence assessments")
        if self.state == CausalState.SUPPORTED:
            if (
                self.design != StudyDesign.CONTROLLED
                or not self.supporting_evidence
                or self.contradicting_evidence
                or self.confounders
                or self.limitations
                or not self.assignment_notes
                or not self.instrumentation_notes
                or self.exposure_population != self.scope.population
            ):
                raise ValueError(
                    "SUPPORTED requires controlled reviewed evidence with unresolved risks absent"
                )
            for evidence_item in self.supporting_evidence:
                lineage = evidence_item.outcome_provenance
                if (
                    lineage is None
                    or lineage.implementation_id != self.plan.implementation.id
                    or lineage.selection_id != self.plan.implementation.selection_id
                    or lineage.authorization_id != self.plan.implementation.authorization.id
                    or lineage.spec_id != self.plan.implementation.spec_id
                    or lineage.spec_version != self.plan.implementation.spec_version
                    or lineage.plan_id != self.plan.id
                    or lineage.plan_version != self.plan.version
                    or lineage.metric_id not in {m.id for m in self.plan.metrics}
                    or self.plan.metric(lineage.metric_id).feedback_scope != self.scope
                    or evidence_item.collected_on < self.plan.window.start.astimezone(UTC).date()
                ):
                    raise ValueError(
                        "SUPPORTED requires evidence of this implementation outcome episode"
                    )
            acceptable = {
                q.evidence_id
                for q in self.quality
                if q.reliability in {Ordinal.HIGH, Ordinal.VERY_HIGH}
                and q.coverage in {Ordinal.MEDIUM, Ordinal.HIGH, Ordinal.VERY_HIGH}
                and q.directness in {Ordinal.HIGH, Ordinal.VERY_HIGH}
                and q.freshness.state == Freshness.CURRENT
                and q.freshness.as_of == self.reviewed_at.astimezone(UTC).date()
            }
            if not {e.id for e in self.supporting_evidence} <= acceptable:
                raise ValueError("SUPPORTED requires existing reliability/coverage quality review")
        if self.state == CausalState.CONTRADICTED and not self.contradicting_evidence:
            raise ValueError("CONTRADICTED requires explicit contradicting evidence")
        check_event(
            self.event,
            EventType.CAUSAL_INTERPRETATION_RECORDED,
            ObjectKind.CAUSAL_INTERPRETATION,
            self.id,
            self.reviewed_by,
            self.reviewed_at,
            (self.plan.id, self.plan.implementation.id),
            self.interpretation,
        )
        return self
