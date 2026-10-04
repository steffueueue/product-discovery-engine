"""Dedicated lifecycle receipts: completion, measurement planning and reviewed closure."""

from uuid import UUID

from pydantic import model_validator

from .audit import AuditEvent, AuditMetadata, AuditTarget, EventType, ObjectKind
from .common import DomainModel, Text
from .delivery_selection import require_human
from .hypotheses import Hypothesis
from .implementation import ImplementationRecord, ImplementationStatus
from .lifecycle import HypothesisStatus
from .outcome_evaluation import EvaluationState
from .outcome_measurement import OutcomeMeasurementPlan, require_episode
from .outcome_policy import OutcomeMeasurementPolicy
from .outcome_review import OutcomeReview


class OutcomeLifecycleChange(DomainModel):
    before: Hypothesis
    after: Hypothesis
    implementation: ImplementationRecord
    plan: OutcomeMeasurementPlan | None = None
    review: OutcomeReview | None = None
    policy: OutcomeMeasurementPolicy
    rationale: Text
    event: AuditEvent

    @model_validator(mode="after")
    def reconstruct(self) -> "OutcomeLifecycleChange":
        require_human(self.event.actor)
        if self.implementation.status != ImplementationStatus.COMPLETED:
            raise ValueError("outcome lifecycle requires actual completed implementation")
        at = self.after.updated_at
        assert self.implementation.completed_at is not None
        if at < self.before.updated_at or at < self.implementation.completed_at:
            raise ValueError("lifecycle cannot precede current snapshot/completion")
        related: tuple[UUID, ...]
        edge = (self.before.status, self.after.status)
        if edge == (HypothesisStatus.SELECTED_FOR_DELIVERY, HypothesisStatus.IMPLEMENTED):
            if self.before != self.implementation.authorization.current.hypothesis:
                raise ValueError("implementation must consume exact current authorized hypothesis")
            if self.plan is not None or self.review is not None:
                raise ValueError("implementation transition consumes only completion")
            kind, related = EventType.HYPOTHESIS_IMPLEMENTED, (self.implementation.id,)
        elif edge == (HypothesisStatus.IMPLEMENTED, HypothesisStatus.MEASURING_OUTCOME):
            if self.plan is None or self.plan.implementation != self.implementation:
                raise ValueError(
                    "measurement transition requires exact implementation and explicit plan"
                )
            if self.before != self.plan.hypothesis or self.plan.recorded_at > at or self.review:
                raise ValueError(
                    "measurement must consume exact current planned hypothesis/version"
                )
            kind, related = (
                EventType.HYPOTHESIS_MEASURING_OUTCOME,
                (self.implementation.id, self.plan.id),
            )
        elif edge == (HypothesisStatus.MEASURING_OUTCOME, HypothesisStatus.CLOSED):
            if self.review is None or self.plan is None:
                raise ValueError("closure requires explicit accountable OutcomeReview")
            if (
                self.review.hypothesis != self.before
                or self.review.assessment.plan != self.plan
                or self.plan.implementation != self.implementation
                or self.review.reviewed_at > at
                or self.review.reviewer != self.event.actor
                or any(e.policy != self.policy for e in self.review.assessment.evaluations)
            ):
                raise ValueError(
                    "closure review must match exact current episode, actor and policy"
                )
            if self.policy.require_complete_window and at < self.plan.window.end:
                raise ValueError("closure requires the completed measurement window")
            if not self.policy.allow_inconclusive_closure and any(
                e.result.state in {EvaluationState.INCONCLUSIVE, EvaluationState.NOT_EVALUABLE}
                for e in self.review.assessment.evaluations
            ):
                raise ValueError("inconclusive closure is not permitted by active policy")
            kind, related = (
                EventType.HYPOTHESIS_CLOSED,
                (self.implementation.id, self.plan.id, self.review.id),
            )
        else:
            raise ValueError("unsupported outcome lifecycle transition")
        require_episode(self.before, self.implementation)
        expected = Hypothesis.model_validate(
            {
                **self.before.model_dump(),
                "status": self.after.status,
                "version": self.before.version + 1,
                "updated_at": at,
            }
        )
        if self.after != expected or self.event != AuditEvent(
            id=self.event.id,
            actor=self.event.actor,
            occurred_at=at,
            event_type=kind,
            target=AuditTarget(kind=ObjectKind.HYPOTHESIS, id=self.before.id),
            metadata=AuditMetadata(
                previous_version=self.before.version,
                resulting_version=self.after.version,
                previous_status=self.before.status.value,
                resulting_status=self.after.status.value,
                changed_fields=("status",),
                related_ids=related,
                reason=self.rationale,
            ),
        ):
            raise ValueError("outcome lifecycle receipt must reconstruct snapshots and audit")
        return self
