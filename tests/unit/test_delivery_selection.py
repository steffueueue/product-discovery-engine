"""Delivery selection cannot be inferred, automated or bypassed during reconstruction."""

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from product_discovery_engine.application.delivery_specification import DeliverySpecificationService
from product_discovery_engine.domain.audit import Actor, ActorKind, EventType
from product_discovery_engine.domain.delivery_selection import DeliverySelection
from product_discovery_engine.domain.hypotheses import Hypothesis
from product_discovery_engine.domain.hypothesis_changes import (
    HypothesisChange,
    transition_hypothesis,
)
from product_discovery_engine.domain.lifecycle import HypothesisStatus, InvalidTransition
from tests.m5_helpers import ACTOR, AT, candidate


@pytest.fixture
def selection() -> DeliverySelection:
    promotion = candidate()
    return DeliverySpecificationService().select(
        promotion.after, promotion, actor=ACTOR, rationale="Explicit governance choice", at=AT
    )


def test_explicit_selection_and_gate_pass_are_separate(selection: DeliverySelection) -> None:
    assert selection.candidacy.gate.result.state.value == "passed"
    assert selection.candidacy.before.status == HypothesisStatus.EVIDENCE_UPDATED
    assert selection.before.status == HypothesisStatus.CANDIDATE_FOR_DELIVERY_PRIORITIZATION
    assert selection.after.status == HypothesisStatus.SELECTED_FOR_DELIVERY
    assert selection.after.version == selection.before.version + 1
    assert selection.after.content == selection.before.content
    assert selection.after.links == selection.before.links
    assert selection.selected_by == ACTOR
    assert selection.event.event_type == EventType.DELIVERY_SELECTION_RECORDED
    assert selection.lifecycle_event.event_type == EventType.DELIVERY_SELECTED
    assert selection.candidacy.gate.hypothesis.status == HypothesisStatus.EVIDENCE_UPDATED
    assert DeliverySelection.model_validate_json(selection.model_dump_json()) == selection


@pytest.mark.parametrize(
    "status",
    [s for s in HypothesisStatus if s != HypothesisStatus.CANDIDATE_FOR_DELIVERY_PRIORITIZATION],
)
def test_selection_rejects_non_candidate_state(
    selection: DeliverySelection, status: HypothesisStatus
) -> None:
    current = Hypothesis.model_validate({**selection.before.model_dump(), "status": status})
    with pytest.raises(ValueError, match="requires candidate"):
        DeliverySpecificationService().select(
            current, selection.candidacy, actor=ACTOR, rationale="Choice", at=AT
        )


@pytest.mark.parametrize(
    "patch", [{"version": 99}, {"id": uuid4()}, {"content": {"title": "tampered"}}]
)
def test_selection_requires_exact_snapshot(
    selection: DeliverySelection, patch: dict[str, object]
) -> None:
    data = selection.before.model_dump()
    if "content" in patch:
        data["content"] = {**selection.before.content.model_dump(), "title": "tampered"}
    else:
        data.update(patch)
    current = Hypothesis.model_validate(data)
    with pytest.raises(ValueError, match="exact current candidacy"):
        DeliverySpecificationService().select(
            current, selection.candidacy, actor=ACTOR, rationale="Choice", at=AT
        )


@pytest.mark.parametrize("kind", [ActorKind.AI, ActorKind.SYSTEM])
def test_no_automated_selection(selection: DeliverySelection, kind: ActorKind) -> None:
    with pytest.raises(ValueError, match="accountable human"):
        DeliverySpecificationService().select(
            selection.before,
            selection.candidacy,
            actor=Actor(kind=kind, id="non-human"),
            rationale="Choice",
            at=AT,
        )


@pytest.mark.parametrize("rationale", ["", "   "])
def test_rationale_required(selection: DeliverySelection, rationale: str) -> None:
    with pytest.raises(ValidationError):
        DeliverySpecificationService().select(
            selection.before, selection.candidacy, actor=ACTOR, rationale=rationale, at=AT
        )


def test_actor_required(selection: DeliverySelection) -> None:
    with pytest.raises(ValidationError):
        DeliverySelection.model_validate({**selection.model_dump(), "selected_by": None})
    with pytest.raises(ValidationError, match="accountable ownership"):
        Actor(kind=ActorKind.HUMAN, id="missing-owner")


def test_generic_transition_and_change_reconstruction_cannot_bypass(
    selection: DeliverySelection,
) -> None:
    with pytest.raises(InvalidTransition, match="requires Delivery Selection"):
        transition_hypothesis(
            selection.before,
            HypothesisStatus.SELECTED_FOR_DELIVERY,
            actor=ACTOR,
            at=AT,
            event_id=uuid4(),
        )
    event = selection.lifecycle_event.model_dump()
    event["event_type"] = EventType.STATUS_CHANGED
    with pytest.raises(ValidationError, match="requires Delivery Selection"):
        HypothesisChange.model_validate(
            {"before": selection.before, "after": selection.after, "event": event}
        )


def test_duplicate_selection_and_backdated_selection_fail(selection: DeliverySelection) -> None:
    with pytest.raises(ValueError, match="requires candidate"):
        DeliverySpecificationService().select(
            selection.after, selection.candidacy, actor=ACTOR, rationale="Again", at=AT
        )
    with pytest.raises(ValueError):
        DeliverySpecificationService().select(
            selection.before,
            selection.candidacy,
            actor=ACTOR,
            rationale="Backdate",
            at=AT - timedelta(seconds=1),
        )


@pytest.mark.parametrize("field", ["rationale", "selected_at", "after", "event", "candidacy"])
def test_tampered_history_rejected(selection: DeliverySelection, field: str) -> None:
    data = selection.model_dump(mode="json")
    if field == "rationale":
        data[field] = "Different reason"
    elif field == "selected_at":
        data[field] = (AT + timedelta(seconds=1)).isoformat()
    elif field == "after":
        data[field]["content"]["title"] = "Unauthorized content change"
    elif field == "event":
        data[field]["metadata"]["related_ids"] = []
    else:
        data[field]["decision_event"]["actor"]["id"] = "wrong-actor"
    with pytest.raises(ValidationError):
        DeliverySelection.model_validate(data)


def test_selection_deeply_immutable(selection: DeliverySelection) -> None:
    for value, field in ((selection, "rationale"), (selection.before.content, "title")):
        with pytest.raises(ValidationError, match="frozen"):
            setattr(value, field, "Changed")
