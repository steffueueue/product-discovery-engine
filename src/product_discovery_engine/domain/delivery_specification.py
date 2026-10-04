"""Authoritative, deliberately incomplete draft versions and reconstructable changes."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .audit import Actor, AuditEvent, AuditMetadata, AuditTarget, EventType, ObjectKind
from .common import DomainModel, Text
from .delivery_context import DeliverySpecContext, ReferenceKind
from .delivery_selection import require_human
from .spec_items import ContentOrigin, SpecItem, SpecItemType, validate_spec_items
from .spec_proposals import SpecProposalReview

Version = Annotated[int, Field(ge=1, strict=True)]


class DeliverySpecStatus(StrEnum):
    DRAFT = "draft"
    NEEDS_CLARIFICATION = "needs_clarification"
    READY_FOR_REVIEW = "ready_for_review"
    READY_FOR_DELIVERY = "ready_for_delivery"
    SUPERSEDED = "superseded"


class SpecVersionReference(DomainModel):
    id: UUID
    version: Version


class MaterialRevision(DomainModel):
    actor: Actor
    at: AwareDatetime
    reason: Text
    changed_item_ids: tuple[UUID, ...]

    @model_validator(mode="after")
    def require_actor_and_changes(self) -> "MaterialRevision":
        require_human(self.actor)
        if not self.changed_item_ids or len(set(self.changed_item_ids)) != len(
            self.changed_item_ids
        ):
            raise ValueError("material revision requires unique changed item IDs")
        return self


class DeliverySpec(DomainModel):
    id: UUID
    version: Version
    schema_version: Version = 1
    status: DeliverySpecStatus = DeliverySpecStatus.DRAFT
    context: DeliverySpecContext
    items: tuple[SpecItem, ...]
    proposal_reviews: tuple[SpecProposalReview, ...] = ()
    created_by: Actor
    created_at: AwareDatetime
    previous_version: SpecVersionReference | None = None
    revision: MaterialRevision | None = None

    @model_validator(mode="after")
    def validate_draft(self) -> "DeliverySpec":
        require_human(self.created_by)
        if self.status != DeliverySpecStatus.DRAFT:
            raise ValueError("Milestone 5 only authorizes DRAFT specifications")
        validate_spec_items(self.context, self.items)
        if self.created_at < self.context.selection.selected_at:
            raise ValueError("spec creation cannot precede selection")
        material_at = self.revision.at if self.revision else self.created_at
        if material_at < self.context.assembled_at:
            raise ValueError("materialization cannot precede context")
        if self.version == 1:
            if self.previous_version is not None or self.revision is not None:
                raise ValueError("v1 cannot have a predecessor or revision")
            if any(r.record.context != self.context for r in self.proposal_reviews):
                raise ValueError("initial materialization requires exact reviewed context")
        elif (
            self.previous_version != SpecVersionReference(id=self.id, version=self.version - 1)
            or self.revision is None
            or self.revision.at < self.created_at
        ):
            raise ValueError("revision requires consecutive predecessor and revision metadata")
        if len({r.record.id for r in self.proposal_reviews}) != len(self.proposal_reviews):
            raise ValueError("proposal reviews must be unique")
        accepted: dict[UUID, SpecItem] = {}
        proposed_ids: set[UUID] = set()
        for review in self.proposal_reviews:
            if (
                review.record.context.selection != self.context.selection
                or review.reviewed_at > material_at
            ):
                raise ValueError(
                    "review must bind the same exact selection and precede materialization"
                )
            for item in review.record.proposal.items:
                if item.id in proposed_ids:
                    raise ValueError("proposal item identities cannot be reused across proposals")
                proposed_ids.add(item.id)
            accepted.update({i.id: i for i in review.accepted_items()})
        for item in self.items:
            if item.id in proposed_ids:
                if accepted.get(item.id) != item:
                    raise ValueError(
                        "proposal item must be human accepted with unchanged origin/content"
                    )
            elif any(s.origin == ContentOrigin.AI_PROPOSAL for s in item.statements()):
                raise ValueError(
                    "AI output alone cannot create authoritative specification content"
                )
        return self

    @property
    def hypothesis_id(self) -> UUID:
        return self.context.hypothesis.id

    @property
    def hypothesis_version(self) -> int:
        return self.context.hypothesis.version

    @property
    def selection_id(self) -> UUID:
        return self.context.selection.id


def changed_items(before: DeliverySpec, after: DeliverySpec) -> tuple[UUID, ...]:
    old = {i.id: i for i in before.items}
    new = {i.id: i for i in after.items}
    return tuple(
        sorted((id for id in old.keys() | new.keys() if old.get(id) != new.get(id)), key=str)
    )


def expected_spec_events(
    before: DeliverySpec | None, after: DeliverySpec, event_ids: tuple[UUID, ...]
) -> tuple[AuditEvent, ...]:
    actor = after.revision.actor if after.revision else after.created_by
    at = after.revision.at if after.revision else after.created_at
    target = AuditTarget(kind=ObjectKind.DELIVERY_SPEC, id=after.id)
    specs: list[tuple[EventType, AuditMetadata]] = []
    if before is None:
        specs.append(
            (
                EventType.SPEC_CREATED,
                AuditMetadata(
                    resulting_version=1,
                    resulting_status=DeliverySpecStatus.DRAFT.value,
                    related_ids=(after.context.id, after.selection_id, after.hypothesis_id),
                ),
            )
        )
    else:
        assert after.revision is not None
        specs.append(
            (
                EventType.SPEC_REVISED,
                AuditMetadata(
                    previous_version=before.version,
                    resulting_version=after.version,
                    previous_status=before.status.value,
                    resulting_status=after.status.value,
                    changed_fields=tuple(str(i) for i in after.revision.changed_item_ids),
                    related_ids=(after.context.id,),
                    reason=after.revision.reason,
                ),
            )
        )
        specs.append(
            (
                EventType.SPEC_SUPERSEDED,
                AuditMetadata(
                    previous_version=before.version,
                    resulting_version=after.version,
                    related_ids=(after.id,),
                    reason=after.revision.reason,
                ),
            )
        )
    old = {i.id for i in before.items} if before else set()
    for item in after.items:
        if item.id not in old:
            specs.append(
                (
                    EventType.HUMAN_SPEC_ITEM_ADDED
                    if (
                        any(s.origin == ContentOrigin.HUMAN_DECISION for s in item.statements())
                        or (
                            item.kind == SpecItemType.CONSTRAINT
                            and any(r.kind == ReferenceKind.CONSTRAINT for r in item.references)
                        )
                    )
                    else EventType.SPEC_ITEM_ACCEPTED,
                    AuditMetadata(
                        resulting_version=after.version,
                        related_ids=(item.id,),
                        reason=after.revision.reason
                        if after.revision
                        else "Human materialization of draft",
                    ),
                )
            )
    if len(event_ids) != len(specs) or len(set(event_ids)) != len(event_ids):
        raise ValueError("spec change requires one distinct audit ID per event")
    return tuple(
        AuditEvent(
            id=id, actor=actor, occurred_at=at, event_type=kind, target=target, metadata=metadata
        )
        for id, (kind, metadata) in zip(event_ids, specs, strict=True)
    )


class DeliverySpecChange(DomainModel):
    before: DeliverySpec | None
    after: DeliverySpec
    events: tuple[AuditEvent, ...]

    @model_validator(mode="after")
    def reconstruct(self) -> "DeliverySpecChange":
        before, after = self.before, self.after
        if before is None:
            if after.version != 1:
                raise ValueError("creation starts spec history at v1")
        else:
            if (
                after.id != before.id
                or after.version != before.version + 1
                or after.created_by != before.created_by
                or after.created_at != before.created_at
                or after.schema_version != before.schema_version
                or after.context.selection != before.context.selection
            ):
                raise ValueError(
                    "revision must preserve identity, selection and consecutive history"
                )
            assert after.revision is not None
            prior_at = before.revision.at if before.revision else before.created_at
            if after.revision.at < prior_at:
                raise ValueError("revision cannot move time backwards")
            changes = changed_items(before, after)
            if not changes or after.revision.changed_item_ids != changes:
                raise ValueError("no-op revision or mismatched changed material items")
            # Rewording/reclassifying an item needs a new identity. Old decisions and
            # AI origin cannot be laundered by updating an existing identity.
            old = {i.id: i for i in before.items}
            if any(i.id in old and i != old[i.id] for i in after.items):
                raise ValueError(
                    "revised statements require new item IDs; preserve original provenance"
                )
            if after.proposal_reviews[: len(before.proposal_reviews)] != before.proposal_reviews:
                raise ValueError(
                    "revision must preserve previous accepted/rejected AI proposal history"
                )
            if any(
                r.record.context != after.context
                for r in after.proposal_reviews[len(before.proposal_reviews) :]
            ):
                raise ValueError("new revision proposals require exact reviewed context")
            if not set(before.context.delivery_facts) <= set(after.context.delivery_facts):
                raise ValueError(
                    "revision context must retain prior human decisions and constraints"
                )
        expected = expected_spec_events(before, after, tuple(e.id for e in self.events))
        if self.events != expected:
            raise ValueError("spec audit does not reconstruct material history")
        return self


def create_delivery_spec(
    context: DeliverySpecContext,
    items: tuple[SpecItem, ...],
    *,
    spec_id: UUID,
    actor: Actor,
    at: datetime,
    reviews: tuple[SpecProposalReview, ...] = (),
    event_ids: tuple[UUID, ...],
) -> DeliverySpecChange:
    after = DeliverySpec(
        id=spec_id,
        version=1,
        context=context,
        items=items,
        proposal_reviews=reviews,
        created_by=actor,
        created_at=at,
    )
    return DeliverySpecChange(
        before=None, after=after, events=expected_spec_events(None, after, event_ids)
    )


def revise_delivery_spec(
    before: DeliverySpec,
    context: DeliverySpecContext,
    items: tuple[SpecItem, ...],
    *,
    actor: Actor,
    at: datetime,
    reason: str,
    reviews: tuple[SpecProposalReview, ...] = (),
    event_ids: tuple[UUID, ...],
) -> DeliverySpecChange:
    before = DeliverySpec.model_validate(before)
    old = {i.id: i for i in before.items}
    new = {i.id: i for i in items}
    changed = tuple(
        sorted((id for id in old.keys() | new.keys() if old.get(id) != new.get(id)), key=str)
    )
    after = DeliverySpec(
        id=before.id,
        version=before.version + 1,
        schema_version=before.schema_version,
        context=context,
        items=items,
        proposal_reviews=before.proposal_reviews + reviews,
        created_by=before.created_by,
        created_at=before.created_at,
        previous_version=SpecVersionReference(id=before.id, version=before.version),
        revision=MaterialRevision(actor=actor, at=at, reason=reason, changed_item_ids=changed),
    )
    return DeliverySpecChange(
        before=before, after=after, events=expected_spec_events(before, after, event_ids)
    )
