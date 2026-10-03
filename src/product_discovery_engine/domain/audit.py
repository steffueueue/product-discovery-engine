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
        if self.event_type == EventType.HUMAN_OVERRIDE:
            if self.actor.kind != ActorKind.HUMAN or self.metadata.reason is None:
                raise ValueError("human override requires a human actor and a reason")
        return self
