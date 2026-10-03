"""Application paths require existing advisory records; the entire loop stays offline."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from examples.discovery_decisioning import Scenario, build_scenario, main
from product_discovery_engine.application.discovery_decisioning import DiscoveryDecisioningService
from product_discovery_engine.domain.audit import Actor, ActorKind
from product_discovery_engine.domain.decisioning_inputs import HumanReview, ReadinessInput
from tests.m4_helpers import ACTOR, AT


@pytest.fixture(scope="module")
def scenario() -> Scenario:
    return build_scenario()


def test_full_learning_loop_and_advisory_boundary(scenario: Scenario) -> None:
    service = DiscoveryDecisioningService(scenario.policies)
    first = service.readiness(
        scenario.initial, actor=ACTOR, at=AT, challenge_record=scenario.initial_challenge
    )
    final = service.readiness(
        scenario.final, actor=ACTOR, at=AT, challenge_record=scenario.final_challenge
    )
    assert first.result.state.value == "not_ready"
    assert final.result.state.value == "ready"
    initial_gate = service.gate(scenario.initial.hypothesis, first, actor=ACTOR, at=AT)
    final_gate = service.gate(scenario.final.hypothesis, final, actor=ACTOR, at=AT)
    assert initial_gate.result.state.value == "blocked"
    assert final_gate.result.state.value == "passed"
    change = service.promote(scenario.final.hypothesis, final_gate, actor=ACTOR, at=AT)
    assert change.after.status.value == "candidate_for_delivery_prioritization"
    assert scenario.final_challenge.result.items[0].severity.value == "very_high"
    assert scenario.final.challenge is not None
    assert scenario.final.challenge.items[0].disposition.value == "addressed"
    assert (
        service.priority(scenario.learning, actor=ACTOR, at=AT).result.priority.value == "critical"
    )


def test_missing_or_wrong_advisory_record_rejected(scenario: Scenario) -> None:
    service = DiscoveryDecisioningService(scenario.policies)
    with pytest.raises(ValueError, match="actual retained"):
        service.readiness(scenario.final, actor=ACTOR, at=AT)
    with pytest.raises(ValueError, match="actual retained"):
        service.readiness(
            scenario.final, actor=ACTOR, at=AT, challenge_record=scenario.initial_challenge
        )
    inputs = ReadinessInput.model_validate({**scenario.final.model_dump(), "challenge": None})
    with pytest.raises(ValueError, match="explicit Challenge"):
        service.readiness(inputs, actor=ACTOR, at=AT, challenge_record=scenario.final_challenge)


def test_current_advisory_knowledge_and_statement_must_match(scenario: Scenario) -> None:
    service = DiscoveryDecisioningService(scenario.policies)
    data = scenario.final.model_dump()
    data["hypothesis"]["content"]["problem_statement"] = "Different problem"
    with pytest.raises(ValueError, match="current statement"):
        service.readiness(
            ReadinessInput.model_validate(data),
            actor=ACTOR,
            at=AT,
            challenge_record=scenario.final_challenge,
        )


@pytest.mark.parametrize("version", [True, "1", 1.5, 0])
def test_review_material_versions_are_strict(version: object) -> None:
    with pytest.raises(ValidationError):
        HumanReview.model_validate(
            {
                "hypothesis_id": uuid4(),
                "hypothesis_version": version,
                "actor": ACTOR,
                "reason": "Reviewed",
                "reviewed_at": AT,
            }
        )


@pytest.mark.parametrize("kind", [ActorKind.AI, ActorKind.SYSTEM])
def test_human_reviews_cannot_be_ai_advisory_truth(kind: ActorKind) -> None:
    with pytest.raises(ValidationError, match="human"):
        HumanReview(
            hypothesis_id=uuid4(),
            hypothesis_version=1,
            actor=Actor(kind=kind, id="machine"),
            reason="Review",
            reviewed_at=AT,
        )


def test_example_runs_offline(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("RUN_LIVE_AI_EVALS", "0")
    main()
    output = capsys.readouterr().out
    assert "critical validate" in output
    assert "not_ready blocked" in output
    assert "ready passed" in output
    assert "candidate_for_delivery_prioritization" in output
    assert "No delivery selection" in output
