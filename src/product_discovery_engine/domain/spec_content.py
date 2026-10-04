"""Immutable material specification body, independent of assessment and workflow state."""

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .audit import Actor
from .common import DomainModel, Text
from .delivery_context import DeliverySpecContext
from .delivery_selection import require_human
from .spec_items import ContentOrigin, SpecItem, validate_spec_items
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


class DeliverySpecBody(DomainModel):
    id: UUID
    version: Version
    schema_version: Version = 1
    context: DeliverySpecContext
    items: tuple[SpecItem, ...]
    proposal_reviews: tuple[SpecProposalReview, ...] = ()
    created_by: Actor
    created_at: AwareDatetime
    previous_version: SpecVersionReference | None = None
    revision: MaterialRevision | None = None

    @model_validator(mode="after")
    def validate_draft(self) -> "DeliverySpecBody":
        require_human(self.created_by)
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


def spec_body(spec: DeliverySpecBody) -> DeliverySpecBody:
    """Strip workflow receipts without losing material input or provenance."""
    return DeliverySpecBody.model_validate(
        {k: getattr(spec, k) for k in DeliverySpecBody.model_fields}
    )
