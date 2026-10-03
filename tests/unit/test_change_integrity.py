"""Regression tests for immutable history and internally consistent audit results."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from product_discovery_engine.domain.audit import Actor, ActorKind, EventType
from product_discovery_engine.domain.common import Owner, Provenance, SourceReference
from product_discovery_engine.domain.evidence import Evidence, EvidenceDirection, EvidenceTarget
from product_discovery_engine.domain.hypotheses import Hypothesis, HypothesisContent
from product_discovery_engine.domain.hypothesis_changes import (
    HypothesisChange,
    create_hypothesis,
    link_evidence,
    revise_hypothesis,
    transition_hypothesis,
)
from product_discovery_engine.domain.lifecycle import HypothesisStatus


@pytest.fixture
def evidence(hypothesis: Hypothesis, source: SourceReference, provenance: Provenance) -> Evidence:
    return Evidence(
        id=UUID(int=4),
        hypothesis_id=hypothesis.id,
        statement="Setup needs work",
        source=source,
        collected_on=hypothesis.created_at.date(),
        target=EvidenceTarget.PROBLEM,
        direction=EvidenceDirection.SUPPORTS,
        methodology_notes=None,
        provenance=provenance,
    )


def test_evidence_added_event_identifies_the_evidence(
    hypothesis: Hypothesis,
    evidence: Evidence,
    actor: Actor,
) -> None:
    result = link_evidence(
        hypothesis, evidence, actor=actor, at=hypothesis.updated_at, event_id=UUID(int=100)
    )
    assert result.event.metadata.related_ids == (evidence.id,)


@pytest.mark.parametrize("operation", ["create", "transition", "revise", "link"])
def test_mutations_reject_naive_time_with_domain_error(
    hypothesis: Hypothesis,
    actor: Actor,
    evidence: Evidence,
    operation: str,
) -> None:
    naive = datetime(2026, 1, 2)
    with pytest.raises(ValueError, match="timezone"):
        if operation == "create":
            create_hypothesis(
                id=hypothesis.id,
                content=hypothesis.content,
                links=hypothesis.links,
                actor=actor,
                at=naive,
                event_id=UUID(int=100),
            )
        elif operation == "transition":
            transition_hypothesis(
                hypothesis,
                HypothesisStatus.STRUCTURED,
                actor=actor,
                at=naive,
                event_id=UUID(int=100),
            )
        elif operation == "revise":
            content = HypothesisContent.model_validate(
                {**hypothesis.content.model_dump(), "title": "Revised title"}
            )
            revise_hypothesis(hypothesis, content, actor=actor, at=naive, event_id=UUID(int=100))
        else:
            link_evidence(hypothesis, evidence, actor=actor, at=naive, event_id=UUID(int=100))


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("after", "id", UUID(int=99)),
        ("after", "version", 3),
        ("after", "created_at", datetime(2025, 12, 1, tzinfo=UTC)),
        ("after", "updated_at", datetime(2026, 1, 2, tzinfo=UTC)),
        ("after", "status", HypothesisStatus.REJECTED),
        ("target", "id", UUID(int=99)),
        ("target", "kind", "evidence"),
        ("metadata", "previous_version", None),
        ("metadata", "previous_status", "parked"),
        ("event", "event_type", EventType.OBJECT_CREATED),
    ],
)
def test_mismatched_snapshot_and_audit_are_rejected(
    hypothesis: Hypothesis,
    actor: Actor,
    section: str,
    field: str,
    value: object,
) -> None:
    result = transition_hypothesis(
        hypothesis,
        HypothesisStatus.STRUCTURED,
        actor=actor,
        at=hypothesis.updated_at,
        event_id=UUID(int=100),
    )
    data = result.model_dump()
    if section in ("target", "metadata"):
        data["event"][section][field] = value
    else:
        data[section][field] = value
    with pytest.raises(ValidationError):
        HypothesisChange.model_validate(data)


def test_creation_cannot_pretend_to_be_later_history(hypothesis: Hypothesis, actor: Actor) -> None:
    result = create_hypothesis(
        id=hypothesis.id,
        content=hypothesis.content,
        links=hypothesis.links,
        actor=actor,
        at=hypothesis.created_at,
        event_id=UUID(int=100),
    )
    data = result.model_dump()
    data["after"]["version"] = 2
    data["event"]["metadata"]["resulting_version"] = 2
    with pytest.raises(ValidationError):
        HypothesisChange.model_validate(data)


def test_nested_unvalidated_model_copy_is_revalidated(owner: Owner) -> None:
    corrupted = owner.model_copy(update={"display_name": ""})
    with pytest.raises(ValidationError):
        Actor(kind=ActorKind.HUMAN, id="user-1", owner=corrupted)


@pytest.mark.parametrize(
    "patch",
    [
        {"reviewed_on": datetime(2026, 1, 2).date()},
        {"invalidated_on": datetime(2026, 1, 2).date(), "invalidation_reason": "Source retracted"},
    ],
)
def test_future_evidence_snapshot_cannot_be_added_to_earlier_history(
    hypothesis: Hypothesis,
    actor: Actor,
    evidence: Evidence,
    patch: dict[str, object],
) -> None:
    future_snapshot = Evidence.model_validate({**evidence.model_dump(), **patch})
    with pytest.raises(ValueError, match="snapshot"):
        link_evidence(
            hypothesis,
            future_snapshot,
            actor=actor,
            at=hypothesis.updated_at,
            event_id=UUID(int=100),
        )


def test_evidence_chronology_uses_utc_calendar_date(
    hypothesis: Hypothesis,
    actor: Actor,
    evidence: Evidence,
) -> None:
    evidence = Evidence.model_validate(
        {**evidence.model_dump(), "collected_on": datetime(2026, 1, 2).date()}
    )
    # The local date is Jan 2 but the same instant in UTC is still Jan 1.
    at = datetime(2026, 1, 2, 1, tzinfo=timezone(timedelta(hours=14)))
    with pytest.raises(ValueError, match="before collection"):
        link_evidence(hypothesis, evidence, actor=actor, at=at, event_id=UUID(int=100))


@pytest.mark.parametrize("fields", [(), ("title",), ("status", "status")])
def test_audit_cannot_misreport_changed_fields(
    hypothesis: Hypothesis,
    actor: Actor,
    fields: tuple[str, ...],
) -> None:
    result = transition_hypothesis(
        hypothesis,
        HypothesisStatus.STRUCTURED,
        actor=actor,
        at=hypothesis.updated_at,
        event_id=UUID(int=100),
    )
    data = result.model_dump()
    data["event"]["metadata"]["changed_fields"] = fields
    with pytest.raises(ValidationError, match="changed fields"):
        HypothesisChange.model_validate(data)


def test_version_only_update_is_not_material_history(hypothesis: Hypothesis, actor: Actor) -> None:
    result = transition_hypothesis(
        hypothesis,
        HypothesisStatus.STRUCTURED,
        actor=actor,
        at=hypothesis.updated_at,
        event_id=UUID(int=100),
    )
    data = result.model_dump()
    data["after"]["status"] = hypothesis.status
    data["event"]["metadata"]["resulting_status"] = hypothesis.status.value
    data["event"]["metadata"]["changed_fields"] = ()
    with pytest.raises(ValidationError, match="material changes"):
        HypothesisChange.model_validate(data)


def test_deserialized_status_change_cannot_bypass_lifecycle(
    hypothesis: Hypothesis,
    actor: Actor,
) -> None:
    result = transition_hypothesis(
        hypothesis,
        HypothesisStatus.STRUCTURED,
        actor=actor,
        at=hypothesis.updated_at,
        event_id=UUID(int=100),
    )
    data = result.model_dump()
    data["after"]["status"] = HypothesisStatus.CLOSED
    data["event"]["metadata"]["resulting_status"] = HypothesisStatus.CLOSED.value
    with pytest.raises(ValidationError, match="invalid hypothesis transition"):
        HypothesisChange.model_validate(data)


def test_evidence_added_audit_cannot_name_another_evidence(
    hypothesis: Hypothesis,
    evidence: Evidence,
    actor: Actor,
) -> None:
    result = link_evidence(
        hypothesis, evidence, actor=actor, at=hypothesis.updated_at, event_id=UUID(int=100)
    )
    data = result.model_dump()
    data["event"]["metadata"]["related_ids"] = (UUID(int=99),)
    with pytest.raises(ValidationError, match="single added evidence"):
        HypothesisChange.model_validate(data)


@pytest.mark.parametrize("kind", [EventType.EVIDENCE_ADDED, EventType.MATERIAL_FIELD_CHANGED])
def test_audit_event_type_must_describe_the_actual_change(
    hypothesis: Hypothesis,
    actor: Actor,
    kind: EventType,
) -> None:
    result = transition_hypothesis(
        hypothesis,
        HypothesisStatus.STRUCTURED,
        actor=actor,
        at=hypothesis.updated_at,
        event_id=UUID(int=100),
    )
    data = result.model_dump()
    data["event"]["event_type"] = kind
    with pytest.raises(ValidationError):
        HypothesisChange.model_validate(data)


@pytest.mark.parametrize("field", ["created_at", "updated_at"])
def test_snapshot_timestamp_fields_require_timezone(hypothesis: Hypothesis, field: str) -> None:
    data = hypothesis.model_dump()
    data[field] = datetime(2026, 1, 1)
    with pytest.raises(ValidationError, match="timezone"):
        Hypothesis.model_validate(data)


@pytest.mark.parametrize(
    "kind",
    [
        EventType.EVIDENCE_INVALIDATED,
        EventType.AI_ASSUMPTION_GENERATED,
        EventType.DECISION_RECORDED,
        EventType.HUMAN_OVERRIDE,
    ],
)
def test_future_event_labels_cannot_bypass_hypothesis_transition_rules(
    hypothesis: Hypothesis,
    actor: Actor,
    kind: EventType,
) -> None:
    valid = transition_hypothesis(
        hypothesis,
        HypothesisStatus.STRUCTURED,
        actor=actor,
        at=hypothesis.updated_at,
        event_id=UUID(int=100),
    )
    payload = valid.model_dump()
    payload["after"]["status"] = HypothesisStatus.CLOSED
    payload["event"]["event_type"] = kind
    payload["event"]["metadata"]["resulting_status"] = HypothesisStatus.CLOSED.value
    payload["event"]["metadata"]["reason"] = "Attempt to relabel an unsupported change"
    with pytest.raises(ValidationError, match="unsupported hypothesis change"):
        HypothesisChange.model_validate(payload)


def test_assumption_evidence_must_target_an_assumption_linked_to_the_hypothesis(
    hypothesis: Hypothesis,
    actor: Actor,
    evidence: Evidence,
) -> None:
    evidence = Evidence.model_validate(
        {
            **evidence.model_dump(),
            "target": EvidenceTarget.ASSUMPTION,
            "target_assumption_id": UUID(int=5),
        }
    )
    with pytest.raises(ValueError, match="assumption.*linked"):
        link_evidence(
            hypothesis, evidence, actor=actor, at=hypothesis.updated_at, event_id=UUID(int=100)
        )


def test_assumption_evidence_can_be_linked_when_its_target_is_related(
    hypothesis: Hypothesis,
    actor: Actor,
    evidence: Evidence,
) -> None:
    hypothesis = Hypothesis.model_validate(
        {
            **hypothesis.model_dump(),
            "links": {**hypothesis.links.model_dump(), "assumption_ids": (UUID(int=5),)},
        }
    )
    evidence = Evidence.model_validate(
        {
            **evidence.model_dump(),
            "target": EvidenceTarget.ASSUMPTION,
            "target_assumption_id": UUID(int=5),
        }
    )
    change = link_evidence(
        hypothesis, evidence, actor=actor, at=hypothesis.updated_at, event_id=UUID(int=100)
    )
    assert change.after.links.evidence_ids == (evidence.id,)
    assert change.after.links.assumption_ids == (UUID(int=5),)


def test_serialized_change_history_preserves_material_state_and_accountability(
    hypothesis: Hypothesis,
    actor: Actor,
    evidence: Evidence,
) -> None:
    from product_discovery_engine.domain.common import Owner, StrategyReference, Unknown

    created = create_hypothesis(
        id=hypothesis.id,
        content=hypothesis.content,
        links=hypothesis.links,
        actor=actor,
        at=hypothesis.created_at,
        event_id=UUID(int=100),
    )
    structured = transition_hypothesis(
        created.after,
        HypothesisStatus.STRUCTURED,
        actor=actor,
        at=hypothesis.created_at + timedelta(hours=1),
        event_id=UUID(int=101),
    )
    content = HypothesisContent(
        title="Investigate setup friction",
        owner=Owner(id=UUID(int=7), display_name="Research lead"),
        problem_statement=hypothesis.content.problem_statement,
        target_segment=Unknown(reason="Segment needs research"),
        desired_outcome=hypothesis.content.desired_outcome,
        strategy=StrategyReference(id="retention", version=2),
    )
    revised = revise_hypothesis(
        structured.after,
        content,
        actor=actor,
        at=structured.after.updated_at + timedelta(hours=1),
        event_id=UUID(int=102),
    )
    supporting = link_evidence(
        revised.after,
        evidence,
        actor=actor,
        at=revised.after.updated_at + timedelta(hours=1),
        event_id=UUID(int=103),
    )
    contradiction = Evidence.model_validate(
        {**evidence.model_dump(), "id": UUID(int=6), "direction": EvidenceDirection.CONTRADICTS}
    )
    contradicting = link_evidence(
        supporting.after,
        contradiction,
        actor=actor,
        at=supporting.after.updated_at + timedelta(hours=1),
        event_id=UUID(int=104),
    )
    restored = tuple(
        HypothesisChange.model_validate_json(change.model_dump_json())
        for change in (created, structured, revised, supporting, contradicting)
    )

    assert restored[0].before is None
    assert [change.after.version for change in restored] == [1, 2, 3, 4, 5]
    for previous, next_change in zip(restored, restored[1:], strict=False):
        assert next_change.before == previous.after
        assert next_change.event.actor == actor
        assert next_change.event.target.id == hypothesis.id
    assert restored[0].after.content.title == "Improve onboarding"
    assert restored[0].after.content.owner == hypothesis.content.owner
    assert restored[2].after.content.owner == content.owner
    assert restored[2].after.content.target_segment == Unknown(reason="Segment needs research")
    assert restored[2].after.content.strategy == StrategyReference(id="retention", version=2)
    assert set(restored[2].event.metadata.changed_fields) == {
        "title",
        "owner",
        "target_segment",
        "strategy",
    }
    assert restored[-1].after.links.submission_ids == hypothesis.links.submission_ids
    assert restored[-1].after.links.evidence_ids == (evidence.id, contradiction.id)
    assert restored[-1].event.metadata.related_ids == (contradiction.id,)
    assert restored[-1].after.status == HypothesisStatus.STRUCTURED
