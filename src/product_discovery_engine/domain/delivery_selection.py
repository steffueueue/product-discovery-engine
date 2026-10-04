"""Accountable delivery selection consumes exact retained candidacy, never a score or AI."""

from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, model_validator

from .audit import Actor, ActorKind, AuditEvent, AuditMetadata, AuditTarget, EventType, ObjectKind
from .common import DomainModel, Text
from .discovery_promotion import CandidatePromotion
from .hypotheses import Hypothesis
from .lifecycle import HypothesisStatus


def require_human(actor: Actor) -> None:
    actor = Actor.model_validate(actor)
    if actor.kind != ActorKind.HUMAN:
        raise ValueError("delivery decisions require an accountable human actor")


class DeliverySelection(DomainModel):
    id: UUID
    candidacy: CandidatePromotion
    before: Hypothesis
    after: Hypothesis
    selected_by: Actor
    rationale: Text
    selected_at: AwareDatetime
    decision_context: tuple[Text, ...] = ()
    lifecycle_event: AuditEvent
    event: AuditEvent

    @model_validator(mode="after")
    def reconstruct(self) -> "DeliverySelection":
        require_human(self.selected_by)
        if self.before.status != HypothesisStatus.CANDIDATE_FOR_DELIVERY_PRIORITIZATION:
            raise ValueError("delivery selection requires candidate_for_delivery_prioritization")
        if self.before != self.candidacy.after:
            raise ValueError("selection requires the exact current candidacy hypothesis snapshot")
        if self.selected_at < self.before.updated_at:
            raise ValueError("selection cannot precede candidacy")
        expected = Hypothesis.model_validate(
            {
                **self.before.model_dump(),
                "status": HypothesisStatus.SELECTED_FOR_DELIVERY,
                "version": self.before.version + 1,
                "updated_at": self.selected_at,
            }
        )
        if self.after != expected:
            raise ValueError("selection must only promote status and increment version")
        for event, kind, target, metadata in (
            (
                self.lifecycle_event,
                EventType.DELIVERY_SELECTED,
                AuditTarget(kind=ObjectKind.HYPOTHESIS, id=self.before.id),
                AuditMetadata(
                    previous_version=self.before.version,
                    resulting_version=self.after.version,
                    previous_status=self.before.status.value,
                    resulting_status=self.after.status.value,
                    changed_fields=("status",),
                    related_ids=(self.id, self.candidacy.decision_event.id),
                    reason=self.rationale,
                ),
            ),
            (
                self.event,
                EventType.DELIVERY_SELECTION_RECORDED,
                AuditTarget(kind=ObjectKind.DELIVERY_SELECTION, id=self.id),
                AuditMetadata(
                    related_ids=(self.before.id, self.candidacy.decision_event.id),
                    reason=self.rationale,
                ),
            ),
        ):
            if (
                event.actor != self.selected_by
                or event.occurred_at != self.selected_at
                or event.event_type != kind
                or event.target != target
                or event.metadata != metadata
            ):
                raise ValueError("selection audit must reconstruct the human decision")
        if self.event.id == self.lifecycle_event.id:
            raise ValueError("selection audits require distinct IDs")
        return self


def select_for_delivery(
    current: Hypothesis,
    candidacy: CandidatePromotion,
    *,
    selection_id: UUID,
    actor: Actor,
    rationale: str,
    at: datetime,
    lifecycle_event_id: UUID,
    event_id: UUID,
    decision_context: tuple[str, ...] = (),
) -> DeliverySelection:
    current = Hypothesis.model_validate(current)
    candidacy = CandidatePromotion.model_validate(candidacy)
    require_human(actor)
    after = Hypothesis.model_validate(
        {
            **current.model_dump(),
            "status": HypothesisStatus.SELECTED_FOR_DELIVERY,
            "version": current.version + 1,
            "updated_at": at,
        }
    )
    return DeliverySelection(
        id=selection_id,
        candidacy=candidacy,
        before=current,
        after=after,
        selected_by=actor,
        rationale=rationale,
        selected_at=at,
        decision_context=decision_context,
        lifecycle_event=AuditEvent(
            id=lifecycle_event_id,
            actor=actor,
            occurred_at=at,
            event_type=EventType.DELIVERY_SELECTED,
            target=AuditTarget(kind=ObjectKind.HYPOTHESIS, id=current.id),
            metadata=AuditMetadata(
                previous_version=current.version,
                resulting_version=after.version,
                previous_status=current.status.value,
                resulting_status=after.status.value,
                changed_fields=("status",),
                related_ids=(selection_id, candidacy.decision_event.id),
                reason=rationale,
            ),
        ),
        event=AuditEvent(
            id=event_id,
            actor=actor,
            occurred_at=at,
            event_type=EventType.DELIVERY_SELECTION_RECORDED,
            target=AuditTarget(kind=ObjectKind.DELIVERY_SELECTION, id=selection_id),
            metadata=AuditMetadata(
                related_ids=(current.id, candidacy.decision_event.id), reason=rationale
            ),
        ),
    )
