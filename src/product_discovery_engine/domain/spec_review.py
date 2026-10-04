"""Accountable exact-spec review and deterministic state-transition authority."""

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, model_validator

from .audit import Actor, AuditEvent, AuditMetadata, AuditTarget, EventType, ObjectKind
from .common import DomainModel, ReferenceIds, Text
from .delivery_selection import require_human
from .spec_completeness import CompletenessState, SpecCompletenessAssessment
from .spec_content import DeliverySpecBody, DeliverySpecStatus, SpecVersionReference
from .spec_gaps import spec_event


class ReviewDisposition(StrEnum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REVIEW_WITH_CONCERNS = "review_with_concerns"


class SpecReview(DomainModel):
    id: UUID
    assessment: SpecCompletenessAssessment
    reviewer: Actor
    reviewed_at: AwareDatetime
    reviewed_gaps: ReferenceIds
    disposition: ReviewDisposition
    rationale: Text
    concerns: tuple[Text, ...] = ()
    event: AuditEvent

    @model_validator(mode="after")
    def reconstruct(self) -> "SpecReview":
        require_human(self.reviewer)
        self.assessment.require_current(
            self.assessment.spec, self.assessment.policy, self.reviewed_at
        )
        if set(self.reviewed_gaps) != {g.id for g in self.assessment.gaps}:
            raise ValueError("review must explicitly cover every retained assessment gap")
        if self.disposition == ReviewDisposition.APPROVED and not reviewable(self.assessment):
            raise ValueError("blocking or insufficient information prevents approved review")
        if self.event != spec_event(
            EventType.SPEC_REVIEW_RECORDED,
            ObjectKind.SPEC_REVIEW,
            self.id,
            self.reviewer,
            self.reviewed_at,
            self.event.id,
            (self.assessment.id, self.assessment.spec.id),
            self.rationale,
            self.assessment.spec.version,
        ):
            raise ValueError("spec review audit must reconstruct")
        return self


def reviewable(assessment: SpecCompletenessAssessment) -> bool:
    return not assessment.result.blocking_gaps and not assessment.result.missing_requirements


def delivery_ready(assessment: SpecCompletenessAssessment, review: SpecReview | None) -> bool:
    return (
        reviewable(assessment)
        and assessment.result.state == CompletenessState.COMPLETE
        and review is not None
        and review.assessment == assessment
        and review.disposition == ReviewDisposition.APPROVED
        and not review.concerns
    )


class SpecStatusRecord(DomainModel):
    before: DeliverySpecStatus
    after: DeliverySpecStatus
    assessment: SpecCompletenessAssessment
    review: SpecReview | None = None
    actor: Actor
    at: AwareDatetime
    rationale: Text
    event: AuditEvent

    @model_validator(mode="after")
    def reconstruct(self) -> "SpecStatusRecord":
        require_human(self.actor)
        self.assessment.require_current(self.assessment.spec, self.assessment.policy, self.at)
        edges = {
            DeliverySpecStatus.DRAFT: {
                DeliverySpecStatus.NEEDS_CLARIFICATION,
                DeliverySpecStatus.READY_FOR_REVIEW,
            },
            DeliverySpecStatus.NEEDS_CLARIFICATION: {
                DeliverySpecStatus.DRAFT,
                DeliverySpecStatus.READY_FOR_REVIEW,
            },
            DeliverySpecStatus.READY_FOR_REVIEW: {
                DeliverySpecStatus.DRAFT,
                DeliverySpecStatus.NEEDS_CLARIFICATION,
                DeliverySpecStatus.READY_FOR_DELIVERY,
            },
            DeliverySpecStatus.READY_FOR_DELIVERY: {
                DeliverySpecStatus.DRAFT,
                DeliverySpecStatus.NEEDS_CLARIFICATION,
            },
        }
        if self.after not in edges.get(self.before, set()):
            raise ValueError("invalid specification status transition")
        if self.review is not None and (
            self.review.assessment != self.assessment or self.review.reviewed_at > self.at
        ):
            raise ValueError("review must bind exact assessment and precede transition")
        if (
            self.after == DeliverySpecStatus.NEEDS_CLARIFICATION
            and not self.assessment.result.blocking_gaps
        ):
            raise ValueError("needs clarification requires authoritative unresolved blocking gaps")
        if self.after == DeliverySpecStatus.READY_FOR_REVIEW and not reviewable(self.assessment):
            raise ValueError(
                "ready for review requires sufficient information and no blocking gaps"
            )
        if self.after == DeliverySpecStatus.READY_FOR_DELIVERY and not delivery_ready(
            self.assessment, self.review
        ):
            raise ValueError(
                "ready for delivery requires exact complete assessment and approved human review"
            )
        kind = {
            DeliverySpecStatus.NEEDS_CLARIFICATION: EventType.SPEC_NEEDS_CLARIFICATION,
            DeliverySpecStatus.READY_FOR_REVIEW: EventType.SPEC_READY_FOR_REVIEW,
            DeliverySpecStatus.READY_FOR_DELIVERY: EventType.SPEC_READY_FOR_DELIVERY,
            DeliverySpecStatus.DRAFT: EventType.STATUS_CHANGED,
        }[self.after]
        if self.event != spec_event(
            kind,
            ObjectKind.DELIVERY_SPEC,
            self.assessment.spec.id,
            self.actor,
            self.at,
            self.event.id,
            (self.assessment.id,) + ((self.review.id,) if self.review else ()),
            self.rationale,
            self.assessment.spec.version,
            previous_status=self.before.value,
            resulting_status=self.after.value,
        ):
            raise ValueError("spec status audit must reconstruct")
        return self


class SpecSupersession(DomainModel):
    previous: DeliverySpecBody
    replacement: DeliverySpecBody
    event: AuditEvent

    @model_validator(mode="after")
    def reconstruct(self) -> "SpecSupersession":
        old, new = self.previous, self.replacement
        if (
            old.id != new.id
            or new.version != old.version + 1
            or new.previous_version != SpecVersionReference(id=old.id, version=old.version)
            or new.context.selection != old.context.selection
            or new.revision is None
            or new.created_at != old.created_at
            or new.created_by != old.created_by
        ):
            raise ValueError("supersession requires consecutive immutable material history")
        previous_at = old.revision.at if old.revision else old.created_at
        if (
            new.revision.at < previous_at
            or new.schema_version != old.schema_version
            or new.proposal_reviews[: len(old.proposal_reviews)] != old.proposal_reviews
            or not set(old.context.delivery_facts) <= set(new.context.delivery_facts)
        ):
            raise ValueError(
                "supersession must retain original time, schema and reviewed provenance"
            )
        old_items, new_items = {i.id: i for i in old.items}, {i.id: i for i in new.items}
        changes = tuple(
            sorted(
                (
                    id
                    for id in old_items.keys() | new_items.keys()
                    if old_items.get(id) != new_items.get(id)
                ),
                key=str,
            )
        )
        if (
            not changes
            or new.revision.changed_item_ids != changes
            or any(i.id in old_items and i != old_items[i.id] for i in new.items)
        ):
            raise ValueError("supersession must retain original item identities")
        if self.event != AuditEvent(
            id=self.event.id,
            actor=new.revision.actor,
            occurred_at=new.revision.at,
            event_type=EventType.SPEC_SUPERSEDED,
            target=AuditTarget(kind=ObjectKind.DELIVERY_SPEC, id=old.id),
            metadata=AuditMetadata(
                previous_version=old.version,
                resulting_version=new.version,
                related_ids=(new.id,),
                reason=new.revision.reason,
            ),
        ):
            raise ValueError("supersession audit must reconstruct")
        return self
