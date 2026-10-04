"""Append-only post-implementation knowledge, preserving original discovery history."""

from datetime import UTC

from pydantic import model_validator

from .audit import AuditEvent, EventType, ObjectKind
from .common import DomainModel, Text
from .evidence import Evidence, EvidenceTarget, PostImplementationProvenance
from .evidence_assessment import EvidenceScope
from .hypothesis_changes import HypothesisChange, link_evidence
from .outcome_audit import check_event
from .outcome_causality import CausalInterpretation, CausalState
from .outcome_measurement import OutcomeObservation, require_episode


def outcome_methodology(observation: OutcomeObservation) -> str:
    plan = observation.plan
    limitations = list(
        observation.limitations
        + plan.interpretation_risks
        + plan.confounders
        + plan.implementation.limitations
    )
    limitations.extend(d.description for d in plan.implementation.deviations)
    for release in plan.releases:
        limitations.append(f"Release audience {release.audience}; rollout {release.rollout_scope}")
        limitations.extend(release.limitations)
    if not plan.releases:
        limitations.append("Deployment and actual exposure remain unknown")
    limitations.append("Observation does not establish causality")
    return observation.methodology + "; Limitations: " + "; ".join(dict.fromkeys(limitations))


class OutcomeEvidenceFeedback(DomainModel):
    observation: OutcomeObservation
    prior_evidence: tuple[Evidence, ...]
    evidence: Evidence
    change: HypothesisChange
    rationale: Text
    causal_interpretation: CausalInterpretation | None = None
    event: AuditEvent

    @model_validator(mode="after")
    def reconstruct(self) -> "OutcomeEvidenceFeedback":
        before = self.change.before
        if before is None:
            raise ValueError("feedback requires the original current hypothesis")
        implementation = self.observation.plan.implementation
        require_episode(before, implementation)
        scope = self.observation.plan.metric(self.observation.metric_id).feedback_scope
        if EvidenceScope.of(self.evidence) != scope:
            raise ValueError(
                "outcome evidence cannot cross metric claim/assumption/population targets"
            )
        if tuple(e.id for e in self.prior_evidence) != before.links.evidence_ids or any(
            e.hypothesis_id != before.id for e in self.prior_evidence
        ):
            raise ValueError("feedback must retain every historical linked evidence snapshot")
        if self.evidence.id in before.links.evidence_ids or self.evidence.outcome_provenance != (
            PostImplementationProvenance(
                implementation_id=implementation.id,
                selection_id=implementation.selection_id,
                spec_id=implementation.spec_id,
                spec_version=implementation.spec_version,
                authorization_id=implementation.authorization.id,
                plan_id=self.observation.plan.id,
                plan_version=self.observation.plan.version,
                metric_id=self.observation.metric_id,
                observation_id=self.observation.id,
            )
        ):
            raise ValueError("new outcome evidence must retain the full implementation lineage")
        if (
            self.evidence.source != self.observation.source
            or self.evidence.collected_on != self.observation.collected_at.astimezone(UTC).date()
            or self.evidence.provenance != self.observation.provenance
            or self.evidence.methodology_notes != outcome_methodology(self.observation)
        ):
            raise ValueError(
                "outcome evidence must preserve actual source, methodology and provenance"
            )
        if self.observation.value is None:
            raise ValueError("unknown observations cannot create directional support/contradiction")
        expected_statement = (
            f"{self.observation.plan.metric(self.observation.metric_id).name}: "
            f"observed {self.observation.value} "
            f"{self.observation.plan.metric(self.observation.metric_id).unit}. "
            f"Human feedback: {self.rationale}"
        )
        if self.evidence.statement != expected_statement:
            raise ValueError("feedback must preserve observed value and accountable interpretation")
        if scope.target == EvidenceTarget.CAUSAL_MECHANISM:
            interpretation = self.causal_interpretation
            if (
                interpretation is None
                or interpretation.scope != scope
                or interpretation.plan != self.observation.plan
            ):
                raise ValueError("causal feedback requires a separate exact causal interpretation")
            if interpretation.reviewed_at > self.event.occurred_at:
                raise ValueError("causal feedback cannot precede its interpretation")
            expected = (
                CausalState.SUPPORTED
                if self.evidence.direction.value == "supports"
                else CausalState.CONTRADICTED
            )
            if interpretation.state != expected:
                raise ValueError("observations alone cannot materialize causal support")
        if self.change != link_evidence(
            before,
            self.evidence,
            actor=self.event.actor,
            at=self.event.occurred_at,
            event_id=self.change.event.id,
        ):
            raise ValueError("feedback must append one evidence item without rewriting history")
        if self.event.occurred_at < self.observation.collected_at:
            raise ValueError("feedback cannot precede collection")
        check_event(
            self.event,
            EventType.OUTCOME_EVIDENCE_ADDED,
            ObjectKind.EVIDENCE,
            self.evidence.id,
            self.event.actor,
            self.event.occurred_at,
            (implementation.id, self.observation.plan.id, self.observation.id),
            self.rationale,
        )
        return self

    @property
    def current_evidence(self) -> tuple[Evidence, ...]:
        return self.prior_evidence + (self.evidence,)
