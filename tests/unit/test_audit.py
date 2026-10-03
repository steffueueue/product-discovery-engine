from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from product_discovery_engine.domain.audit import (
    Actor,
    ActorKind,
    AuditEvent,
    AuditMetadata,
    AuditTarget,
    EventType,
    ObjectKind,
)


@pytest.mark.parametrize("kind", list(EventType))
def test_event_types_and_roundtrip(kind: EventType, actor: Actor) -> None:
    event = AuditEvent(
        id=UUID(int=100),
        actor=actor,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        event_type=kind,
        target=AuditTarget(kind=ObjectKind.HYPOTHESIS, id=UUID(int=10)),
        metadata=AuditMetadata(reason="Explicit accountable decision"),
    )
    assert event.event_type == kind
    assert AuditEvent.model_validate_json(event.model_dump_json()) == event
    with pytest.raises(ValidationError, match="frozen"):
        event.metadata.reason = "Rewritten history"  # type: ignore[misc]  # Exercise runtime immutability.


def test_human_actor_requires_owner() -> None:
    with pytest.raises(ValidationError, match="ownership"):
        Actor(kind=ActorKind.HUMAN, id="user")


@pytest.mark.parametrize("kind", [ActorKind.SYSTEM, ActorKind.AI])
def test_non_human_cannot_override(kind: ActorKind) -> None:
    with pytest.raises(ValidationError, match="human actor"):
        AuditEvent(
            id=UUID(int=100),
            actor=Actor(kind=kind, id="service"),
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            event_type=EventType.HUMAN_OVERRIDE,
            target=AuditTarget(kind=ObjectKind.HYPOTHESIS, id=UUID(int=10)),
            metadata=AuditMetadata(reason="Not allowed"),
        )


def test_override_requires_reason(actor: Actor) -> None:
    with pytest.raises(ValidationError, match="reason"):
        AuditEvent(
            id=UUID(int=100),
            actor=actor,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            event_type=EventType.HUMAN_OVERRIDE,
            target=AuditTarget(kind=ObjectKind.HYPOTHESIS, id=UUID(int=10)),
            metadata=AuditMetadata(),
        )


def test_audit_version_must_increment_exactly_once() -> None:
    with pytest.raises(ValidationError):
        AuditMetadata(previous_version=2, resulting_version=4)


def test_standalone_audit_event_rejects_naive_timestamp(actor: Actor) -> None:
    with pytest.raises(ValidationError, match="timezone"):
        AuditEvent(
            id=UUID(int=100),
            actor=actor,
            occurred_at=datetime(2026, 1, 1),
            event_type=EventType.OBJECT_CREATED,
            target=AuditTarget(kind=ObjectKind.HYPOTHESIS, id=UUID(int=10)),
            metadata=AuditMetadata(),
        )
