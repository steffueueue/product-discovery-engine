"""Immutable audit records with typed targets and metadata."""

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .common import DomainModel, Owner, ReferenceIds, Text


class ActorKind(StrEnum):
    HUMAN = "human"
    SYSTEM = "system"
    AI = "ai"


class Actor(DomainModel):
    kind: ActorKind
    id: Text
    owner: Owner | None = None

    @model_validator(mode="after")
    def validate_accountability(self) -> "Actor":
        if self.kind == ActorKind.HUMAN and self.owner is None:
            raise ValueError("human actors require accountable ownership")
        return self


class ObjectKind(StrEnum):
    SUBMISSION = "submission"
    HYPOTHESIS = "hypothesis"
    CLAIM = "claim"
    EVIDENCE = "evidence"
    ASSUMPTION = "assumption"
    DECISION = "decision"
    EVIDENCE_ORIGIN = "evidence_origin"
    VALIDATION_ACTIVITY = "validation_activity"
    VALIDATION_RESULT = "validation_result"
    CHALLENGE_ANALYSIS = "challenge_analysis"
    DELIVERY_SELECTION = "delivery_selection"
    DELIVERY_SPEC = "delivery_spec"
    SPEC_PROPOSAL = "spec_proposal"
    DELIVERY_CONTEXT = "delivery_context"


class AuditTarget(DomainModel):
    kind: ObjectKind
    id: UUID


class EventType(StrEnum):
    OBJECT_CREATED = "object_created"
    MATERIAL_FIELD_CHANGED = "material_field_changed"
    STATUS_CHANGED = "status_changed"
    EVIDENCE_ADDED = "evidence_added"
    EVIDENCE_INVALIDATED = "evidence_invalidated"
    HUMAN_OVERRIDE = "human_override"
    AI_ASSUMPTION_GENERATED = "ai_assumption_generated"
    DECISION_RECORDED = "decision_recorded"
    EVIDENCE_QUALITY_ASSESSED = "evidence_quality_assessed"
    EVIDENCE_FRESHNESS_CHANGED = "evidence_freshness_changed"
    EVIDENCE_ORIGIN_LINKED = "evidence_origin_linked"
    VALIDATION_CREATED = "validation_created"
    VALIDATION_READY = "validation_ready"
    VALIDATION_STARTED = "validation_started"
    VALIDATION_COMPLETED = "validation_completed"
    VALIDATION_CANCELLED = "validation_cancelled"
    VALIDATION_RESULT_RECORDED = "validation_result_recorded"
    VALIDATION_CRITERIA_CHANGED = "validation_criteria_changed"
    ASSUMPTION_RISK_REASSESSED = "assumption_risk_reassessed"
    CHALLENGE_COMPLETED = "challenge_completed"
    DISCOVERY_PRIORITY_ASSESSED = "discovery_priority_assessed"
    DELIVERY_READINESS_ASSESSED = "delivery_readiness_assessed"
    DISCOVERY_GATE_EVALUATED = "discovery_gate_evaluated"
    DISCOVERY_GATE_PASSED = "discovery_gate_passed"
    DISCOVERY_GATE_BLOCKED = "discovery_gate_blocked"
    DISCOVERY_GATE_REVIEW_REQUIRED = "discovery_gate_review_required"
    DISCOVERY_GATE_OVERRIDDEN = "discovery_gate_overridden"
    HYPOTHESIS_PROMOTED = "hypothesis_promoted_to_candidate"
    DELIVERY_SELECTED = "delivery_selected"
    DELIVERY_SELECTION_RECORDED = "delivery_selection_recorded"
    DELIVERY_CONTEXT_RECORDED = "delivery_context_recorded"
    SPEC_DRAFT_GENERATED = "spec_draft_generated"
    SPEC_PROPOSAL_REVIEWED = "spec_proposal_reviewed"
    SPEC_ITEM_ACCEPTED = "spec_item_accepted"
    SPEC_ITEM_REJECTED = "spec_item_rejected"
    SPEC_CREATED = "spec_created"
    SPEC_REVISED = "spec_revised"
    SPEC_SUPERSEDED = "spec_superseded"
    HUMAN_SPEC_ITEM_ADDED = "human_spec_item_added"


class AuditMetadata(DomainModel):
    previous_version: Annotated[int, Field(ge=1, strict=True)] | None = None
    resulting_version: Annotated[int, Field(ge=1, strict=True)] | None = None
    previous_status: Text | None = None
    resulting_status: Text | None = None
    changed_fields: tuple[Text, ...] = ()
    related_ids: ReferenceIds = ()
    reason: Text | None = None

    @model_validator(mode="after")
    def validate_versions(self) -> "AuditMetadata":
        if self.previous_version is not None:
            if self.resulting_version != self.previous_version + 1:
                raise ValueError("audit version changes must increment exactly once")
        return self


class AuditEvent(DomainModel):
    id: UUID
    actor: Actor
    occurred_at: AwareDatetime
    event_type: EventType
    target: AuditTarget
    metadata: AuditMetadata

    @model_validator(mode="after")
    def validate_override(self) -> "AuditEvent":
        if self.event_type in {EventType.HUMAN_OVERRIDE, EventType.DISCOVERY_GATE_OVERRIDDEN}:
            if self.actor.kind != ActorKind.HUMAN or self.metadata.reason is None:
                raise ValueError("human override requires a human actor and a reason")
        return self
