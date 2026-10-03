from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from product_discovery_engine.domain.audit import Actor, EventType
from product_discovery_engine.domain.common import Owner, Provenance, SourceReference, Unknown
from product_discovery_engine.domain.evidence import Evidence, EvidenceDirection, EvidenceTarget
from product_discovery_engine.domain.hypotheses import (
    Hypothesis,
    HypothesisContent,
    HypothesisLinks,
)
from product_discovery_engine.domain.hypothesis_changes import (
    create_hypothesis,
    link_evidence,
    revise_hypothesis,
    transition_hypothesis,
)
from product_discovery_engine.domain.lifecycle import HypothesisStatus, InvalidTransition

# Ordinary paths exclude candidacy since Milestone 4: dedicated gate promotion tests cover it.
EXPECTED: dict[str, set[str]] = {
    "new": {"structured", "parked", "rejected", "merged"},
    "structured": {"needs_evidence", "ready_to_validate", "parked", "rejected", "merged"},
    "needs_evidence": {"ready_to_validate", "parked", "rejected", "merged"},
    "ready_to_validate": {"validating", "needs_evidence", "parked", "rejected"},
    "validating": {"evidence_updated", "parked"},
    "evidence_updated": {
        "needs_evidence",
        "ready_to_validate",
        "parked",
        "rejected",
        "merged",
    },
    "candidate_for_delivery_prioritization": {
        "selected_for_delivery",
        "needs_evidence",
        "parked",
        "rejected",
    },
    "selected_for_delivery": {"implemented", "parked"},
    "parked": {"structured", "needs_evidence", "rejected", "merged"},
    "rejected": set(),
    "merged": set(),
    "implemented": {"measuring_outcome"},
    "measuring_outcome": {"closed"},
    "closed": set(),
}


@pytest.mark.parametrize("current", list(HypothesisStatus))
@pytest.mark.parametrize("target", list(HypothesisStatus))
def test_transition_matrix(
    hypothesis: Hypothesis, actor: Actor, current: HypothesisStatus, target: HypothesisStatus
) -> None:
    before = Hypothesis.model_validate({**hypothesis.model_dump(), "status": current})
    at = before.updated_at + timedelta(hours=1)
    if target.value not in EXPECTED[current.value]:
        with pytest.raises(InvalidTransition, match="invalid hypothesis transition"):
            transition_hypothesis(before, target, actor=actor, at=at, event_id=UUID(int=100))
        return
    result = transition_hypothesis(before, target, actor=actor, at=at, event_id=UUID(int=100))
    assert result.before == before
    assert result.after.status == target
    assert before.status == current
    assert result.after.version == before.version + 1
    assert result.after.created_at == before.created_at
    assert result.after.updated_at == at
    assert result.event.event_type == EventType.STATUS_CHANGED
    assert result.event.metadata.previous_status == current.value
    assert result.event.metadata.resulting_status == target.value
    assert result.event.metadata.previous_version == 1
    assert result.event.metadata.resulting_version == 2


def test_creation_records_actor_and_target(hypothesis: Hypothesis, actor: Actor) -> None:
    change = create_hypothesis(
        id=hypothesis.id,
        content=hypothesis.content,
        links=hypothesis.links,
        actor=actor,
        at=hypothesis.created_at,
        event_id=UUID(int=100),
    )
    assert change.before is None
    assert change.after.version == 1
    assert change.event.actor == actor
    assert change.event.target.id == hypothesis.id
    assert change.event.event_type == EventType.OBJECT_CREATED
    assert change.event.occurred_at == hypothesis.created_at


def test_material_revision_preserves_history_and_unknown(
    hypothesis: Hypothesis, actor: Actor
) -> None:
    content = HypothesisContent.model_validate(
        {
            **hypothesis.content.model_dump(),
            "desired_outcome": Unknown(reason="Baseline not yet measured"),
            "owner": None,
        }
    )
    result = revise_hypothesis(
        hypothesis,
        content,
        actor=actor,
        at=hypothesis.updated_at + timedelta(days=1),
        event_id=UUID(int=101),
    )
    assert result.after.version == 2
    assert result.after.content.owner is None
    assert isinstance(result.after.content.desired_outcome, Unknown)
    assert hypothesis.content.owner is not None
    assert hypothesis.content.desired_outcome == "Users complete setup unaided"
    assert set(result.event.metadata.changed_fields) == {"desired_outcome", "owner"}
    assert Hypothesis.model_validate_json(result.after.model_dump_json()) == result.after


def test_noop_and_backdated_revision_rejected(hypothesis: Hypothesis, actor: Actor) -> None:
    with pytest.raises(ValueError, match="material"):
        revise_hypothesis(
            hypothesis,
            hypothesis.content,
            actor=actor,
            at=hypothesis.updated_at,
            event_id=UUID(int=101),
        )
    with pytest.raises(ValueError, match="backwards"):
        transition_hypothesis(
            hypothesis,
            HypothesisStatus.STRUCTURED,
            actor=actor,
            at=hypothesis.updated_at - timedelta(days=1),
            event_id=UUID(int=101),
        )


def test_linking_contradiction_is_auditable(
    hypothesis: Hypothesis, actor: Actor, source: SourceReference, provenance: Provenance
) -> None:
    evidence = Evidence(
        id=UUID(int=4),
        hypothesis_id=hypothesis.id,
        statement="Users succeeded",
        source=source,
        collected_on=hypothesis.created_at.date(),
        target=EvidenceTarget.PROBLEM,
        direction=EvidenceDirection.CONTRADICTS,
        methodology_notes=None,
        provenance=provenance,
    )
    result = link_evidence(
        hypothesis, evidence, actor=actor, at=hypothesis.updated_at, event_id=UUID(int=102)
    )
    assert result.after.links.evidence_ids == (evidence.id,)
    assert hypothesis.links.evidence_ids == ()
    assert result.after.version == 2
    assert result.event.event_type == EventType.EVIDENCE_ADDED
    assert evidence.direction == EvidenceDirection.CONTRADICTS
    with pytest.raises(ValueError, match="already linked"):
        link_evidence(
            result.after, evidence, actor=actor, at=hypothesis.updated_at, event_id=UUID(int=103)
        )
    wrong = Evidence.model_validate({**evidence.model_dump(), "hypothesis_id": UUID(int=999)})
    with pytest.raises(ValueError, match="different hypothesis"):
        link_evidence(
            hypothesis, wrong, actor=actor, at=hypothesis.updated_at, event_id=UUID(int=103)
        )
    future = Evidence.model_validate(
        {
            **evidence.model_dump(),
            "collected_on": (hypothesis.created_at + timedelta(days=1)).date(),
        }
    )
    with pytest.raises(ValueError, match="before collection"):
        link_evidence(
            hypothesis, future, actor=actor, at=hypothesis.updated_at, event_id=UUID(int=103)
        )


@pytest.mark.parametrize(
    "patch",
    [
        {"version": 0},
        {"status": "imaginary"},
        {"updated_at": datetime(2025, 1, 1, tzinfo=UTC)},
    ],
)
def test_invalid_hypothesis(hypothesis: Hypothesis, patch: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Hypothesis.model_validate({**hypothesis.model_dump(), **patch})


def test_required_origin_and_unique_links() -> None:
    with pytest.raises(ValidationError, match="original submission"):
        HypothesisLinks(submission_ids=())
    with pytest.raises(ValidationError, match="duplicate"):
        HypothesisLinks(submission_ids=(UUID(int=2),), evidence_ids=(UUID(int=4), UUID(int=4)))


def test_hypothesis_is_deeply_frozen(hypothesis: Hypothesis, owner: Owner) -> None:
    for value, field, replacement in (
        (hypothesis, "version", 2),
        (hypothesis.content, "title", "Changed"),
        (owner, "display_name", "Changed"),
    ):
        with pytest.raises(ValidationError, match="frozen"):
            setattr(value, field, replacement)


@pytest.mark.parametrize(
    "current, target",
    [
        ("new", HypothesisStatus.STRUCTURED),
        (HypothesisStatus.NEW, "structured"),
        (HypothesisStatus.NEW, "invented"),
        ("invented", HypothesisStatus.STRUCTURED),
    ],
)
def test_non_enum_lifecycle_inputs_fail_with_clear_domain_error(
    current: object, target: object
) -> None:
    from typing import cast

    from product_discovery_engine.domain.lifecycle import require_transition

    with pytest.raises(InvalidTransition, match="HypothesisStatus"):
        require_transition(cast(HypothesisStatus, current), cast(HypothesisStatus, target))
