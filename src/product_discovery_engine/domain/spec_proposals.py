"""Retained reviewable drafting proposals and complete human dispositions."""

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BeforeValidator, model_validator

from .audit import Actor, ActorKind, AuditEvent, AuditMetadata, AuditTarget, EventType, ObjectKind
from .common import DomainModel, Text
from .delivery_context import DeliverySpecContext
from .delivery_selection import require_human
from .spec_items import SpecItem, validate_spec_items


def _true(value: object) -> Literal[True]:
    if value is not True:
        raise ValueError("AI proposal marker must be explicit true")
    return True


class DraftingProvenance(DomainModel):
    provider: Text
    model: Text
    prompt_version: Text


class DeliverySpecDraftProposal(DomainModel):
    context_id: UUID
    items: tuple[SpecItem, ...]
    ai_generated: Annotated[Literal[True], BeforeValidator(_true)]


class SpecProposalRecord(DomainModel):
    id: UUID
    context: DeliverySpecContext
    proposal: DeliverySpecDraftProposal
    provenance: DraftingProvenance
    generated_at: AwareDatetime
    event: AuditEvent

    @model_validator(mode="after")
    def reconstruct(self) -> "SpecProposalRecord":
        if self.proposal.context_id != self.context.id:
            raise ValueError("proposal must bind exact input context")
        validate_spec_items(self.context, self.proposal.items)
        if self.generated_at < self.context.assembled_at:
            raise ValueError("proposal cannot precede context")
        if self.event != AuditEvent(
            id=self.event.id,
            actor=Actor(kind=ActorKind.AI, id=self.provenance.provider),
            occurred_at=self.generated_at,
            event_type=EventType.SPEC_DRAFT_GENERATED,
            target=AuditTarget(kind=ObjectKind.SPEC_PROPOSAL, id=self.id),
            metadata=AuditMetadata(related_ids=(self.context.id,)),
        ):
            raise ValueError("proposal audit must match generation and context")
        return self


class ItemDisposition(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ItemReview(DomainModel):
    item_id: UUID
    disposition: ItemDisposition
    rationale: Text


class SpecProposalReview(DomainModel):
    record: SpecProposalRecord
    actor: Actor
    reviewed_at: AwareDatetime
    items: tuple[ItemReview, ...]
    event: AuditEvent
    item_events: tuple[AuditEvent, ...]

    @model_validator(mode="after")
    def reconstruct(self) -> "SpecProposalReview":
        require_human(self.actor)
        if self.reviewed_at < self.record.generated_at:
            raise ValueError("review cannot precede proposal")
        if len({i.item_id for i in self.items}) != len(self.items) or {
            i.item_id for i in self.items
        } != {i.id for i in self.record.proposal.items}:
            raise ValueError("review must accept or reject every proposal item exactly once")
        expected = AuditEvent(
            id=self.event.id,
            actor=self.actor,
            occurred_at=self.reviewed_at,
            event_type=EventType.SPEC_PROPOSAL_REVIEWED,
            target=AuditTarget(kind=ObjectKind.SPEC_PROPOSAL, id=self.record.id),
            metadata=AuditMetadata(related_ids=(self.record.context.id,)),
        )
        if self.event != expected or len(self.item_events) != len(self.items):
            raise ValueError("proposal review audit must reconstruct all dispositions")
        for item, event in zip(self.items, self.item_events, strict=True):
            if event != item_review_event(
                self.record.id, item, self.actor, self.reviewed_at, event.id
            ):
                raise ValueError("item acceptance/rejection audit must match human disposition")
        ids = [self.event.id, *(e.id for e in self.item_events)]
        if len(ids) != len(set(ids)):
            raise ValueError("review audits must have distinct IDs")
        return self

    def accepted_items(self) -> tuple[SpecItem, ...]:
        accepted = {i.item_id for i in self.items if i.disposition == ItemDisposition.ACCEPTED}
        return tuple(i for i in self.record.proposal.items if i.id in accepted)


def item_review_event(
    proposal_id: UUID, item: ItemReview, actor: Actor, at: AwareDatetime, event_id: UUID
) -> AuditEvent:
    return AuditEvent(
        id=event_id,
        actor=actor,
        occurred_at=at,
        event_type=EventType.SPEC_ITEM_ACCEPTED
        if item.disposition == ItemDisposition.ACCEPTED
        else EventType.SPEC_ITEM_REJECTED,
        target=AuditTarget(kind=ObjectKind.SPEC_PROPOSAL, id=proposal_id),
        metadata=AuditMetadata(related_ids=(item.item_id,), reason=item.rationale),
    )
