"""Authoritative structural gaps and explicitly human-reviewed semantic concerns."""

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, model_validator

from .audit import Actor, ActorKind, AuditEvent, AuditMetadata, AuditTarget, EventType, ObjectKind
from .common import DomainModel, Owner, ReferenceIds, Text
from .delivery_selection import require_human
from .spec_completeness_policy import GapClassification, SpecDimension
from .spec_content import DeliverySpecBody, SpecVersionReference


class GapType(StrEnum):
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    CONFLICTING = "conflicting"
    UNSUPPORTED = "unsupported"
    UNRESOLVED_UNKNOWN = "unresolved_unknown"
    TRACEABILITY_GAP = "traceability_gap"


class GapBasis(StrEnum):
    STRUCTURAL = "structural"
    HUMAN_REVIEW = "human_review"


class GapStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    WITHDRAWN = "withdrawn"


def spec_event(
    kind: EventType,
    target_kind: ObjectKind,
    target_id: UUID,
    actor: Actor,
    at: AwareDatetime,
    event_id: UUID,
    related: tuple[UUID, ...] = (),
    reason: str | None = None,
    version: int | None = None,
    *,
    previous_status: str | None = None,
    resulting_status: str | None = None,
) -> AuditEvent:
    return AuditEvent(
        id=event_id,
        actor=actor,
        occurred_at=at,
        event_type=kind,
        target=AuditTarget(kind=target_kind, id=target_id),
        metadata=AuditMetadata(
            related_ids=related,
            reason=reason,
            resulting_version=version,
            previous_status=previous_status,
            resulting_status=resulting_status,
        ),
    )


class GapReview(DomainModel):
    actor: Actor
    at: AwareDatetime
    rationale: Text
    previous_classification: GapClassification
    previous_status: GapStatus
    resulting_classification: GapClassification
    resulting_status: GapStatus
    resolution_references: ReferenceIds = ()
    event: AuditEvent

    @model_validator(mode="after")
    def human_only(self) -> "GapReview":
        require_human(self.actor)
        return self


class SpecGap(DomainModel):
    id: UUID
    spec: SpecVersionReference
    dimension: SpecDimension
    gap_type: GapType
    affected_item_ids: ReferenceIds = ()
    statement: Text
    rationale: Text
    source_basis: Text
    basis: GapBasis
    classification: GapClassification
    detected_classification: GapClassification
    status: GapStatus = GapStatus.OPEN
    detected_at: AwareDatetime
    detected_by: Actor
    owner: Owner | None = None
    event: AuditEvent
    reviews: tuple[GapReview, ...] = ()

    @model_validator(mode="after")
    def accountable_gap(self) -> "SpecGap":
        if self.detected_by.kind == ActorKind.AI:
            raise ValueError("AI proposal cannot materialize an authoritative gap")
        if self.basis == GapBasis.HUMAN_REVIEW:
            require_human(self.detected_by)
        if self.event != spec_event(
            EventType.SPEC_GAP_DETECTED,
            ObjectKind.SPEC_GAP,
            self.id,
            self.detected_by,
            self.detected_at,
            self.event.id,
            (self.spec.id,),
            self.rationale,
            self.spec.version,
        ):
            raise ValueError("gap detection audit must reconstruct")
        if self.basis == GapBasis.STRUCTURAL and self.reviews:
            raise ValueError("structural gaps clear by revision/reassessment, not assertion")
        previous_at = self.detected_at
        classification, status = self.detected_classification, GapStatus.OPEN
        for review in self.reviews:
            if (
                review.previous_classification != classification
                or review.previous_status != status
                or status != GapStatus.OPEN
            ):
                raise ValueError("gap reviews must preserve consecutive authoritative history")
            classification, status = review.resulting_classification, review.resulting_status
            if review.at < previous_at:
                raise ValueError("gap review cannot move time backwards")
            if review.event != spec_event(
                EventType.SPEC_GAP_REVIEWED,
                ObjectKind.SPEC_GAP,
                self.id,
                review.actor,
                review.at,
                review.event.id,
                review.resolution_references,
                review.rationale,
                self.spec.version,
            ):
                raise ValueError("gap review audit must reconstruct")
            previous_at = review.at
        if (self.classification, self.status) != (classification, status):
            raise ValueError("gap classification/status requires exact reviewed history")
        if self.status != GapStatus.OPEN and (
            not self.reviews or not self.reviews[-1].resolution_references
        ):
            raise ValueError("gap resolution/withdrawal requires explicit human references")
        return self

    def require_scope(self, spec: DeliverySpecBody) -> None:
        if self.spec != SpecVersionReference(id=spec.id, version=spec.version):
            raise ValueError("stale or cross-spec gap reference")
        if not set(self.affected_item_ids) <= {i.id for i in spec.items}:
            raise ValueError("gap references unknown items")
