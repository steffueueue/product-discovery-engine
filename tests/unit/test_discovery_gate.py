"""Gate fail-safe semantics, immutable reconstruction, controlled promotion and overrides."""

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from product_discovery_engine.application.discovery_decisioning import DiscoveryDecisioningService
from product_discovery_engine.domain.audit import Actor, ActorKind, EventType
from product_discovery_engine.domain.decisioning_inputs import ReadinessInput
from product_discovery_engine.domain.decisioning_policy import DecisioningPolicies
from product_discovery_engine.domain.discovery_gate import (
    ConditionState,
    DiscoveryGateEvaluation,
    DiscoveryGateOverride,
    GateState,
    override_discovery_gate,
)
from product_discovery_engine.domain.discovery_promotion import (
    CandidatePromotion,
    promote_candidate,
)
from product_discovery_engine.domain.hypotheses import Hypothesis, HypothesisContent
from product_discovery_engine.domain.hypothesis_changes import (
    HypothesisChange,
    revise_hypothesis,
    transition_hypothesis,
)
from product_discovery_engine.domain.lifecycle import HypothesisStatus, InvalidTransition
from tests.m4_helpers import ACTOR, AT, Scenario, build_scenario, gate, readiness


@pytest.fixture(scope="module")
def scenario() -> Scenario:
    return build_scenario()


def evaluated(scenario: Scenario) -> DiscoveryGateEvaluation:
    return gate(
        scenario.final.hypothesis, readiness(scenario.final, scenario.policies), scenario.policies
    )


def needs_review(scenario: Scenario) -> DiscoveryGateEvaluation:
    assert scenario.final.challenge is not None
    challenge = {**scenario.final.challenge.model_dump(), "review": None, "items": ()}
    inputs = ReadinessInput.model_validate({**scenario.final.model_dump(), "challenge": challenge})
    return gate(inputs.hypothesis, readiness(inputs, scenario.policies), scenario.policies)


def promote(
    scenario: Scenario,
    record: DiscoveryGateEvaluation,
    hypothesis: Hypothesis | None = None,
) -> CandidatePromotion:
    return promote_candidate(
        hypothesis or record.hypothesis,
        record,
        policies=scenario.policies,
        actor=ACTOR,
        at=AT,
        lifecycle_event_id=uuid4(),
        decision_event_id=uuid4(),
    )


def test_ordinary_pass_retains_conditions_and_audits(scenario: Scenario) -> None:
    record = evaluated(scenario)
    assert record.result.state == GateState.PASSED
    assert all(c.state == ConditionState.PASSED for c in record.result.conditions)
    assert record.readiness is not None
    assert record.readiness_assessment_id == record.readiness.id
    assert record.evaluation_event.event_type == EventType.DISCOVERY_GATE_EVALUATED
    assert record.outcome_event.event_type == EventType.DISCOVERY_GATE_PASSED
    assert record.result.failed_conditions == record.result.unknown_conditions == ()


def test_ordinary_blocked_lists_gaps_and_unknowns(scenario: Scenario) -> None:
    record = gate(
        scenario.initial.hypothesis,
        readiness(scenario.initial, scenario.policies),
        scenario.policies,
    )
    assert record.result.state == GateState.BLOCKED
    assert "critical_assumptions" in record.result.failed_conditions
    assert "validation" in record.result.failed_conditions
    assert record.result.blocking_reasons
    assert record.outcome_event.event_type == EventType.DISCOVERY_GATE_BLOCKED
    with pytest.raises(ValueError, match="ordinary.*PASS"):
        promote(scenario, record)


def test_review_required_is_distinct_from_pass(scenario: Scenario) -> None:
    record = needs_review(scenario)
    assert record.result.state == GateState.NEEDS_REVIEW
    assert not record.result.blocking_reasons
    assert record.result.review_required_reasons
    assert record.outcome_event.event_type == EventType.DISCOVERY_GATE_REVIEW_REQUIRED
    with pytest.raises(ValueError, match="ordinary.*PASS"):
        promote(scenario, record)


def test_missing_readiness_assessment_cannot_pass(scenario: Scenario) -> None:
    record = gate(scenario.final.hypothesis, None, scenario.policies)
    assert record.result.state == GateState.BLOCKED
    assert "readiness" in record.result.unknown_conditions
    assert record.readiness_assessment_id is None


@pytest.mark.parametrize("field", ["owner", "strategy"])
def test_unknown_required_condition_never_passes(scenario: Scenario, field: str) -> None:
    data = scenario.final.model_dump()
    data["hypothesis"]["content"][field] = None
    if field == "strategy":
        data["strategy_context"] = None
        data["strategy_acknowledgement"] = None
    inputs = ReadinessInput.model_validate(data)
    record = gate(inputs.hypothesis, readiness(inputs, scenario.policies), scenario.policies)
    assert record.result.state == GateState.BLOCKED
    assert ("ownership" if field == "owner" else field) in record.result.unknown_conditions
    assert any(c.state == ConditionState.UNKNOWN for c in record.result.conditions)


def test_missing_challenge_and_unreviewed_strategy_do_not_pass(scenario: Scenario) -> None:
    for field in ("challenge", "strategy_acknowledgement"):
        inputs = ReadinessInput.model_validate({**scenario.final.model_dump(), field: None})
        record = gate(inputs.hypothesis, readiness(inputs, scenario.policies), scenario.policies)
        assert record.result.state != GateState.PASSED


def test_outdated_readiness_and_gate_policy_rejected(scenario: Scenario) -> None:
    data = scenario.policies.model_dump()
    for key in ("priority", "readiness", "gate"):
        data[key]["version"] = "decisioning.v2"
    data["version"] = "decisioning.v2"
    changed = DecisioningPolicies.model_validate(data)
    record = gate(scenario.final.hypothesis, readiness(scenario.final, scenario.policies), changed)
    assert record.result.state == GateState.BLOCKED
    assert "policy" in record.result.failed_conditions
    service = DiscoveryDecisioningService(changed)
    with pytest.raises(ValueError, match="outdated|mismatched"):
        service.promote(scenario.final.hypothesis, evaluated(scenario), actor=ACTOR, at=AT)


def test_same_version_changed_policy_snapshot_does_not_authorize(scenario: Scenario) -> None:
    data = scenario.policies.model_dump()
    data["gate"]["maximum_age_hours"] = 1
    changed = DecisioningPolicies.model_validate(data)
    with pytest.raises(ValueError, match="outdated|mismatched"):
        promote_candidate(
            scenario.final.hypothesis,
            evaluated(scenario),
            policies=changed,
            actor=ACTOR,
            at=AT,
            lifecycle_event_id=uuid4(),
            decision_event_id=uuid4(),
        )


@pytest.mark.parametrize("delta", [timedelta(days=1), timedelta(hours=24), timedelta(hours=-1)])
def test_expired_or_future_gate_cannot_promote(scenario: Scenario, delta: timedelta) -> None:
    record = evaluated(scenario)
    with pytest.raises(ValueError, match="expired|precedes"):
        promote_candidate(
            record.hypothesis,
            record,
            policies=scenario.policies,
            actor=ACTOR,
            at=AT + delta,
            lifecycle_event_id=uuid4(),
            decision_event_id=uuid4(),
        )
    stale = gate(
        scenario.final.hypothesis, record.readiness, scenario.policies, at=AT + timedelta(days=1)
    )
    assert stale.result.state == GateState.BLOCKED
    assert "assessment_current" in stale.result.failed_conditions


def test_gate_expiry_uses_utc_day_boundary(scenario: Scenario) -> None:
    record = evaluated(scenario)
    assert record.expires_at.hour == 0
    assert record.expires_at.date() == (AT + timedelta(days=1)).date()


def test_valid_promotion_preserves_before_after_and_matching_audits(scenario: Scenario) -> None:
    record = evaluated(scenario)
    result = promote(scenario, record)
    assert result.before == scenario.final.hypothesis
    assert result.after.version == result.before.version + 1
    assert result.after.status == HypothesisStatus.CANDIDATE_FOR_DELIVERY_PRIORITIZATION
    assert result.after.content == result.before.content
    assert result.lifecycle_event.metadata.related_ids == (record.id,)
    assert result.override is None
    assert CandidatePromotion.model_validate_json(result.model_dump_json()) == result
    assert result.decision_event.target.id == record.id
    with pytest.raises(ValueError, match="obsolete"):
        promote(scenario, record, result.after)


def test_gate_for_hypothesis_a_cannot_promote_b(scenario: Scenario) -> None:
    hypothesis = Hypothesis.model_validate(
        {**scenario.final.hypothesis.model_dump(), "id": uuid4()}
    )
    with pytest.raises(ValueError, match="different|obsolete"):
        promote(scenario, evaluated(scenario), hypothesis)


def test_material_revision_invalidates_old_gate(scenario: Scenario) -> None:
    record = evaluated(scenario)
    content = HypothesisContent.model_validate(
        {**record.hypothesis.content.model_dump(), "desired_outcome": "Different outcome"}
    )
    change = revise_hypothesis(record.hypothesis, content, actor=ACTOR, at=AT, event_id=uuid4())
    with pytest.raises(ValueError, match="obsolete"):
        promote(scenario, record, change.after)
    rechecked = gate(change.after, record.readiness, scenario.policies)
    assert "snapshot" in rechecked.result.failed_conditions


def test_generic_transition_and_deserialized_status_change_cannot_bypass_gate(
    scenario: Scenario,
) -> None:
    with pytest.raises(InvalidTransition, match="Discovery Gate"):
        transition_hypothesis(
            scenario.final.hypothesis,
            HypothesisStatus.CANDIDATE_FOR_DELIVERY_PRIORITIZATION,
            actor=ACTOR,
            at=AT,
            event_id=uuid4(),
        )
    ordinary = transition_hypothesis(
        scenario.final.hypothesis, HypothesisStatus.PARKED, actor=ACTOR, at=AT, event_id=uuid4()
    )
    data = ordinary.model_dump()
    data["after"]["status"] = HypothesisStatus.CANDIDATE_FOR_DELIVERY_PRIORITIZATION
    data["event"]["metadata"]["resulting_status"] = (
        HypothesisStatus.CANDIDATE_FOR_DELIVERY_PRIORITIZATION.value
    )
    with pytest.raises(ValidationError, match="Discovery Gate"):
        HypothesisChange.model_validate(data)


@pytest.mark.parametrize("kind", [ActorKind.SYSTEM, ActorKind.AI])
def test_human_accountability_required_for_promotion(scenario: Scenario, kind: ActorKind) -> None:
    with pytest.raises(ValueError, match="human"):
        promote_candidate(
            scenario.final.hypothesis,
            evaluated(scenario),
            policies=scenario.policies,
            actor=Actor(kind=kind, id="machine"),
            at=AT,
            lifecycle_event_id=uuid4(),
            decision_event_id=uuid4(),
        )


def test_override_is_a_separate_audited_action_and_original_stays_review(
    scenario: Scenario,
) -> None:
    record = needs_review(scenario)
    override = override_discovery_gate(
        record,
        actor=ACTOR,
        reason="Human accepts bounded residual challenge review concern",
        at=AT,
        override_id=uuid4(),
        event_id=uuid4(),
    )
    assert record.result.state == GateState.NEEDS_REVIEW
    assert override.original_gate == record
    assert override.action.value == "authorize_candidacy"
    assert override.event.event_type == EventType.DISCOVERY_GATE_OVERRIDDEN
    assert DiscoveryGateOverride.model_validate_json(override.model_dump_json()) == override
    result = promote_candidate(
        record.hypothesis,
        record,
        policies=scenario.policies,
        actor=ACTOR,
        at=AT,
        lifecycle_event_id=uuid4(),
        decision_event_id=uuid4(),
        override=override,
    )
    assert result.override == override
    assert "override" in str(result.lifecycle_event.metadata.reason)
    assert result.gate.result.state == GateState.NEEDS_REVIEW
    assert CandidatePromotion.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("kind", [ActorKind.SYSTEM, ActorKind.AI])
def test_override_rejects_non_human_actor(scenario: Scenario, kind: ActorKind) -> None:
    with pytest.raises(ValueError, match="human"):
        override_discovery_gate(
            needs_review(scenario),
            actor=Actor(kind=kind, id="machine"),
            reason="Attempt",
            at=AT,
            override_id=uuid4(),
            event_id=uuid4(),
        )


@pytest.mark.parametrize("reason", ["", "   "])
def test_override_requires_reason(scenario: Scenario, reason: str) -> None:
    with pytest.raises(ValidationError):
        override_discovery_gate(
            needs_review(scenario),
            actor=ACTOR,
            reason=reason,
            at=AT,
            override_id=uuid4(),
            event_id=uuid4(),
        )


def test_override_missing_actor_is_rejected(scenario: Scenario) -> None:
    record = override_discovery_gate(
        needs_review(scenario),
        actor=ACTOR,
        reason="Reviewed",
        at=AT,
        override_id=uuid4(),
        event_id=uuid4(),
    )
    data = record.model_dump()
    del data["actor"]
    with pytest.raises(ValidationError):
        DiscoveryGateOverride.model_validate(data)


@pytest.mark.parametrize("case", ["unknown", "unpermitted", "passed", "expired"])
def test_override_cannot_bypass_unknown_integrity_or_unpermitted_condition(
    scenario: Scenario, case: str
) -> None:
    if case == "unknown":
        record = gate(scenario.final.hypothesis, None, scenario.policies)
    elif case == "unpermitted":
        record = gate(
            scenario.initial.hypothesis,
            readiness(scenario.initial, scenario.policies),
            scenario.policies,
        )
    elif case == "passed":
        record = evaluated(scenario)
    else:
        record = needs_review(scenario)
    with pytest.raises(ValueError, match="permitted known conditions"):
        override_discovery_gate(
            record,
            actor=ACTOR,
            reason="Cannot bypass",
            at=AT + timedelta(days=1) if case == "expired" else AT,
            override_id=uuid4(),
            event_id=uuid4(),
        )


@pytest.mark.parametrize("field", ["result", "policy_version", "expires_at", "outcome_event"])
def test_gate_deserialization_rejects_tampered_decision_or_audit(
    scenario: Scenario, field: str
) -> None:
    record = evaluated(scenario)
    assert DiscoveryGateEvaluation.model_validate_json(record.model_dump_json()) == record
    data = record.model_dump()
    if field == "result":
        data[field]["state"] = GateState.BLOCKED
    elif field == "policy_version":
        data[field] = "other-version"
    elif field == "expires_at":
        data[field] += timedelta(days=1)
    else:
        data[field]["event_type"] = EventType.DISCOVERY_GATE_BLOCKED
    with pytest.raises(ValidationError):
        DiscoveryGateEvaluation.model_validate(data)


def test_ai_override_actor_cannot_be_smuggled_by_model_copy(scenario: Scenario) -> None:
    record = override_discovery_gate(
        needs_review(scenario),
        actor=ACTOR,
        reason="Reviewed",
        at=AT,
        override_id=uuid4(),
        event_id=uuid4(),
    )
    forged = record.model_copy(update={"actor": Actor(kind=ActorKind.AI, id="agent")})
    with pytest.raises(ValidationError):
        promote_candidate(
            record.original_gate.hypothesis,
            record.original_gate,
            policies=scenario.policies,
            actor=ACTOR,
            at=AT,
            lifecycle_event_id=uuid4(),
            decision_event_id=uuid4(),
            override=forged,
        )
