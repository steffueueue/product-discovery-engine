"""Pure audit construction shared by implementation and outcome operations."""

from datetime import datetime
from uuid import UUID

from .audit import Actor, AuditEvent, AuditMetadata, AuditTarget, EventType, ObjectKind
from .delivery_selection import require_human


def outcome_event(
    kind: EventType,
    target_kind: ObjectKind,
    target_id: UUID,
    actor: Actor,
    at: datetime,
    event_id: UUID,
    related: tuple[UUID, ...] = (),
    reason: str | None = None,
    version: int | None = None,
) -> AuditEvent:
    require_human(actor)
    return AuditEvent(
        id=event_id,
        actor=actor,
        occurred_at=at,
        event_type=kind,
        target=AuditTarget(kind=target_kind, id=target_id),
        metadata=AuditMetadata(related_ids=related, reason=reason, resulting_version=version),
    )


def check_event(
    event: AuditEvent,
    kind: EventType,
    target_kind: ObjectKind,
    target_id: UUID,
    actor: Actor,
    at: datetime,
    related: tuple[UUID, ...] = (),
    reason: str | None = None,
    version: int | None = None,
) -> None:
    if event != outcome_event(
        kind, target_kind, target_id, actor, at, event.id, related, reason, version
    ):
        raise ValueError("outcome audit must reconstruct exact record")
