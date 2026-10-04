"""Accountable human review and explicit follow-up recommendations; no execution."""

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, model_validator

from .audit import Actor, AuditEvent, EventType, ObjectKind
from .common import DomainModel, ReferenceIds, Text
from .evidence import Evidence
from .evidence_assessment import require_evidence_time
from .hypotheses import Hypothesis
from .lifecycle import HypothesisStatus
from .outcome_audit import check_event
from .outcome_causality import CausalInterpretation
from .outcome_evaluation import OutcomeAssessment
from .outcome_measurement import require_episode


class FollowUpAction(StrEnum):
    NO_FURTHER_ACTION = "no_further_action"
    FURTHER_MEASUREMENT = "further_measurement"
    ADDITIONAL_VALIDATION = "additional_validation"
    NEW_HYPOTHESIS = "new_hypothesis"
    REVISE_HYPOTHESIS = "revise_hypothesis"
    RECONSIDER_SOLUTION = "rollback_or_reconsider_solution"
    INVESTIGATE_GUARDRAIL = "investigate_guardrail"


class OutcomeReview(DomainModel):
    id: UUID
    hypothesis: Hypothesis
    assessment: OutcomeAssessment
    causal_interpretations: tuple[CausalInterpretation, ...]
    evidence: tuple[Evidence, ...]
    reviewer: Actor
    reviewed_at: AwareDatetime
    rationale: Text
    actions: tuple[FollowUpAction, ...]
    follow_up_learning: tuple[Text, ...]
    unresolved_questions: tuple[Text, ...]
    acknowledged_limitations: tuple[Text, ...]
    event: AuditEvent

    @model_validator(mode="after")
    def reconstruct(self) -> "OutcomeReview":
        plan = self.assessment.plan
        require_episode(self.hypothesis, plan.implementation)
        if self.hypothesis.status != HypothesisStatus.MEASURING_OUTCOME:
            raise ValueError("outcome review requires measuring_outcome")
        if (
            self.hypothesis.version <= plan.hypothesis.version
            or self.hypothesis.updated_at < plan.recorded_at
        ):
            raise ValueError("outcome review cannot precede its measurement episode")
        if self.reviewed_at < self.hypothesis.updated_at:
            raise ValueError("outcome review cannot precede the current hypothesis snapshot")
        for evidence_item in self.evidence:
            require_evidence_time(evidence_item, self.reviewed_at)
        if self.reviewed_at < max(e.evaluated_at for e in self.assessment.evaluations):
            raise ValueError("review cannot precede metric evaluations")
        if any(
            c.plan != plan or c.reviewed_at > self.reviewed_at for c in self.causal_interpretations
        ):
            raise ValueError("review causal interpretations must bind exact current plan/version")
        if len({c.id for c in self.causal_interpretations}) != len(self.causal_interpretations):
            raise ValueError("review causal interpretations must be unique")
        if tuple(e.id for e in self.evidence) != self.hypothesis.links.evidence_ids or any(
            e.hypothesis_id != self.hypothesis.id for e in self.evidence
        ):
            raise ValueError("review must retain all original and feedback evidence")
        if any(
            e not in self.evidence
            for c in self.causal_interpretations
            for e in c.supporting_evidence + c.contradicting_evidence
        ):
            raise ValueError("review cannot hide causal supporting or contradicting evidence")
        for interpretation in self.causal_interpretations:
            relevant = {
                e.id
                for e in self.evidence
                if interpretation.scope.matches(e) and e.invalidated_on is None
            }
            included = {
                e.id
                for e in interpretation.supporting_evidence + interpretation.contradicting_evidence
            }
            if not relevant <= included:
                raise ValueError(
                    "causal review cannot hide known scoped supporting or contradicting evidence"
                )
        required = set(self.assessment.limitations)
        required.update(
            x for c in self.causal_interpretations for x in c.limitations + c.confounders
        )
        if not required <= set(self.acknowledged_limitations):
            raise ValueError("human review must explicitly acknowledge all unresolved limitations")
        if not self.actions or len(set(self.actions)) != len(self.actions):
            raise ValueError("outcome review requires explicit unique follow-up decisions")
        if FollowUpAction.NO_FURTHER_ACTION in self.actions and len(self.actions) != 1:
            raise ValueError("no-further-action cannot conceal other actions")
        check_event(
            self.event,
            EventType.OUTCOME_REVIEW_COMPLETED,
            ObjectKind.OUTCOME_REVIEW,
            self.id,
            self.reviewer,
            self.reviewed_at,
            (self.hypothesis.id, plan.implementation.id, plan.id),
            self.rationale,
            plan.version,
        )
        return self


class FollowUpLearning(DomainModel):
    id: UUID
    review: OutcomeReview
    follow_up_hypothesis: Hypothesis
    outcome_evidence_ids: ReferenceIds
    linked_by: Actor
    linked_at: AwareDatetime
    rationale: Text
    event: AuditEvent

    @model_validator(mode="after")
    def reconstruct(self) -> "FollowUpLearning":
        if self.follow_up_hypothesis.id == self.review.hypothesis.id:
            raise ValueError(
                "follow-up link must identify a distinct explicitly supplied hypothesis"
            )
        available = {e.id for e in self.review.evidence if e.outcome_provenance is not None}
        if not self.outcome_evidence_ids or not set(self.outcome_evidence_ids) <= available:
            raise ValueError("follow-up learning must reference original outcome evidence")
        if self.linked_at < max(self.review.reviewed_at, self.follow_up_hypothesis.created_at):
            raise ValueError("learning link cannot precede review or follow-up creation")
        check_event(
            self.event,
            EventType.FOLLOW_UP_LEARNING_LINKED,
            ObjectKind.FOLLOW_UP_LEARNING,
            self.id,
            self.linked_by,
            self.linked_at,
            (self.review.id, self.follow_up_hypothesis.id) + self.outcome_evidence_ids,
            self.rationale,
        )
        return self
