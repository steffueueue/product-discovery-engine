"""Authoritative, deliberately incomplete draft versions and reconstructable changes."""

from datetime import datetime
from uuid import UUID

from pydantic import model_validator

from .audit import Actor, AuditEvent, AuditMetadata, AuditTarget, EventType, ObjectKind
from .common import DomainModel
from .delivery_context import DeliverySpecContext, ReferenceKind
from .spec_content import (
    DeliverySpecBody,
    spec_body,
)
from .spec_content import (
    DeliverySpecStatus as DeliverySpecStatus,
)
from .spec_content import (
    MaterialRevision as MaterialRevision,
)
from .spec_content import (
    SpecVersionReference as SpecVersionReference,
)
from .spec_items import ContentOrigin, SpecItem, SpecItemType
from .spec_proposals import SpecProposalReview
from .spec_review import SpecStatusRecord, SpecSupersession


class DeliverySpec(DeliverySpecBody):
    status: DeliverySpecStatus = DeliverySpecStatus.DRAFT
    status_history: tuple[SpecStatusRecord, ...] = ()
    supersession: SpecSupersession | None = None

    @model_validator(mode="after")
    def validate_status_authority(self) -> "DeliverySpec":
        body = spec_body(self)
        if len({r.event.id for r in self.status_history}) != len(self.status_history):
            raise ValueError("status audit IDs must be unique within specification history")
        previous = DeliverySpecStatus.DRAFT
        previous_at = self.revision.at if self.revision else self.created_at
        for record in self.status_history:
            if record.assessment.spec != body:
                raise ValueError("status authority must bind exact specification body")
            if record.before != previous or record.at < previous_at:
                raise ValueError("status history must be consecutive and chronological")
            previous, previous_at = record.after, record.at
        if self.supersession is not None:
            if (
                self.supersession.previous != body
                or self.supersession.event.occurred_at < previous_at
            ):
                raise ValueError(
                    "supersession must bind exact prior body and follow status history"
                )
            previous = DeliverySpecStatus.SUPERSEDED
        if self.status != previous:
            raise ValueError("non-DRAFT status requires exact assessment/review authority")
        return self


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
        if after.status != DeliverySpecStatus.DRAFT or after.status_history or after.supersession:
            raise ValueError("material creation/revision must reset review authority to DRAFT")
        if before is not None and before.status == DeliverySpecStatus.SUPERSEDED:
            raise ValueError("cannot revise a superseded specification")
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
            if before.status_history:
                prior_at = max(prior_at, before.status_history[-1].at)
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
