"""Decision-relevant learning, explicit unknowns, validation context and category ties."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from product_discovery_engine.domain.assumptions import ValidationState
from product_discovery_engine.domain.common import ORDINAL_ORDER, Ordinal
from product_discovery_engine.domain.decisioning_policy import PriorityCategory
from product_discovery_engine.domain.discovery_priority import (
    DiscoveryPriorityAssessment,
    LearningAction,
    LearningInput,
    LearningTargetKind,
    assess_discovery_priority,
    priority_ties,
)
from product_discovery_engine.domain.validation import RelativeCost, RelativeSpeed, ValidationStatus
from tests.m4_helpers import ACTOR, AT, Scenario, build_scenario


@pytest.fixture(scope="module")
def scenario() -> Scenario:
    return build_scenario()


def learning(scenario: Scenario, **patch: object) -> LearningInput:
    return LearningInput.model_validate(
        {
            **scenario.learning.model_dump(),
            "risk_assessment": None,
            "proposed_validation_id": None,
            **patch,
        }
    )


def assess(scenario: Scenario, inputs: LearningInput) -> DiscoveryPriorityAssessment:
    return assess_discovery_priority(
        inputs,
        policy=scenario.policies.priority,
        actor=ACTOR,
        at=AT,
        assessment_id=uuid4(),
        event_id=uuid4(),
    )


@pytest.mark.parametrize(
    "impact, uncertainty, expected",
    [
        (Ordinal.VERY_HIGH, Ordinal.HIGH, PriorityCategory.CRITICAL),
        (Ordinal.HIGH, Ordinal.HIGH, PriorityCategory.HIGH),
        (Ordinal.LOW, Ordinal.VERY_HIGH, PriorityCategory.LOW),
        (Ordinal.MEDIUM, Ordinal.HIGH, PriorityCategory.MEDIUM),
        (None, Ordinal.HIGH, PriorityCategory.UNKNOWN),
        (Ordinal.HIGH, None, PriorityCategory.UNKNOWN),
    ],
)
def test_explicit_impact_uncertainty_rules(
    scenario: Scenario,
    impact: Ordinal | None,
    uncertainty: Ordinal | None,
    expected: PriorityCategory,
) -> None:
    result = assess(
        scenario, learning(scenario, decision_impact=impact, unresolved_uncertainty=uncertainty)
    )
    assert result.result.priority == expected
    assert result.inputs.decision_impact == impact
    assert result.inputs.unresolved_uncertainty == uncertainty
    if expected == PriorityCategory.UNKNOWN:
        assert result.result.action == LearningAction.CLARIFY


@pytest.mark.parametrize("cost", list(RelativeCost))
@pytest.mark.parametrize("speed", list(RelativeSpeed))
def test_cost_speed_cannot_demote_critical_learning(
    scenario: Scenario,
    cost: RelativeCost,
    speed: RelativeSpeed,
) -> None:
    result = assess(
        scenario,
        learning(
            scenario,
            relative_cost=cost,
            relative_speed=speed,
            expected_information_gain=Ordinal.VERY_HIGH,
        ),
    )
    assert result.result.priority == PriorityCategory.CRITICAL
    assert "never demote critical" in result.result.explanation


@pytest.mark.parametrize("status", [ValidationStatus.READY, ValidationStatus.RUNNING])
def test_active_validation_avoids_duplicate_action(
    scenario: Scenario, status: ValidationStatus
) -> None:
    activity = scenario.learning.validations[0].model_dump()
    activity["status"] = status
    result = assess(scenario, learning(scenario, validations=(activity,)))
    assert result.result.priority == PriorityCategory.NO_ACTION
    assert result.result.underlying_priority == PriorityCategory.CRITICAL
    assert result.result.action == LearningAction.MONITOR_ACTIVE_VALIDATION
    assert not result.result.actionable


def test_assumption_in_progress_suppresses_duplicates_without_activity(scenario: Scenario) -> None:
    assert scenario.learning.assumption is not None
    assumption = {
        **scenario.learning.assumption.model_dump(),
        "validation_state": ValidationState.IN_PROGRESS,
    }
    result = assess(scenario, learning(scenario, assumption=assumption, validations=()))
    assert result.result.action == LearningAction.MONITOR_ACTIVE_VALIDATION


def test_inconclusive_validation_remains_high(scenario: Scenario) -> None:
    assert scenario.learning.assumption is not None
    assumption = {
        **scenario.learning.assumption.model_dump(),
        "validation_state": ValidationState.INCONCLUSIVE,
    }
    activity = {
        **scenario.learning.validations[0].model_dump(),
        "status": ValidationStatus.COMPLETED,
    }
    result = assess(scenario, learning(scenario, assumption=assumption, validations=(activity,)))
    assert result.result.priority == PriorityCategory.CRITICAL
    assert result.result.actionable


@pytest.mark.parametrize(
    "kind",
    [LearningTargetKind.CONTRADICTION, LearningTargetKind.EVIDENCE_GAP, LearningTargetKind.UNKNOWN],
)
def test_non_assumption_learning_targets(scenario: Scenario, kind: LearningTargetKind) -> None:
    result = assess(
        scenario,
        learning(
            scenario,
            target_kind=kind,
            assumption=None,
            contradictory_evidence_ids=(uuid4(),)
            if kind == LearningTargetKind.CONTRADICTION
            else (),
        ),
    )
    assert result.result.priority == PriorityCategory.CRITICAL
    if kind == LearningTargetKind.CONTRADICTION:
        assert result.result.action == LearningAction.REFRAME


def test_refutation_reframes_instead_of_confirmation_seeking(scenario: Scenario) -> None:
    assert scenario.learning.assumption is not None
    assumption = {
        **scenario.learning.assumption.model_dump(),
        "validation_state": ValidationState.REFUTED,
    }
    result = assess(scenario, learning(scenario, assumption=assumption))
    assert result.result.action == LearningAction.REFRAME


def test_blocked_learning_is_visible(scenario: Scenario) -> None:
    dependency = uuid4()
    activity = {**scenario.learning.validations[0].model_dump(), "dependencies": (dependency,)}
    result = assess(
        scenario, learning(scenario, validations=(activity,), blockers=("Missing access",))
    )
    assert result.result.priority == PriorityCategory.CRITICAL
    assert result.result.action == LearningAction.UNBLOCK
    assert result.result.dependency_ids == (dependency,)
    assert "Missing access" in result.result.blocker_summary
    assert not result.result.actionable
    unblocked = assess(
        scenario,
        learning(scenario, validations=(activity,), completed_dependency_ids=(dependency,)),
    )
    assert unblocked.result.actionable


def test_category_ties_preserved_despite_cost_gain_or_input_order(scenario: Scenario) -> None:
    first = assess(
        scenario,
        learning(scenario, relative_cost=RelativeCost.HIGH, expected_information_gain=Ordinal.HIGH),
    )
    second = assess(
        scenario,
        learning(
            scenario, relative_cost=RelativeCost.LOW, expected_information_gain=Ordinal.VERY_HIGH
        ),
    )
    low = assess(scenario, learning(scenario, decision_impact=Ordinal.LOW))
    assert priority_ties((low, second, first)).ordinal_ties == ((second, first), (low,))
    assert priority_ties((first, second)).ordinal_ties == ((first, second),)


def test_resolved_learning_is_no_action_but_freshness_gaps_reopen(scenario: Scenario) -> None:
    inputs = learning(scenario, unresolved_uncertainty=Ordinal.LOW, evidence_gaps=())
    assert assess(scenario, inputs).result.priority == PriorityCategory.NO_ACTION
    reopened = LearningInput.model_validate(
        {**inputs.model_dump(), "freshness_concerns": ("Review due",)}
    )
    assert assess(scenario, reopened).result.priority == PriorityCategory.LOW
    assert assess(scenario, reopened).result.actionable


@pytest.mark.parametrize("impact", ORDINAL_ORDER)
@pytest.mark.parametrize("uncertainty", ORDINAL_ORDER)
def test_ordinal_policy_is_monotonic(
    scenario: Scenario, impact: Ordinal, uncertainty: Ordinal
) -> None:
    policy = scenario.policies.priority
    category = policy.category(impact, uncertainty)
    for higher in ORDINAL_ORDER[ORDINAL_ORDER.index(impact) :]:
        assert tuple(PriorityCategory).index(policy.category(higher, uncertainty)) <= tuple(
            PriorityCategory
        ).index(category)


def test_missing_planning_inputs_remain_unknown(scenario: Scenario) -> None:
    result = assess(
        scenario,
        learning(scenario, expected_information_gain=None, relative_cost=None, relative_speed=None),
    )
    assert result.inputs.expected_information_gain is None
    assert result.inputs.relative_cost is None
    assert result.inputs.relative_speed is None


def test_priority_reconstructs_and_rejects_tampering(scenario: Scenario) -> None:
    record = assess(scenario, scenario.learning)
    assert DiscoveryPriorityAssessment.model_validate_json(record.model_dump_json()) == record
    data = record.model_dump()
    data["result"]["priority"] = PriorityCategory.LOW
    with pytest.raises(ValidationError, match="reconstruct"):
        DiscoveryPriorityAssessment.model_validate(data)
    data = record.model_dump()
    data["inputs"]["unresolved_uncertainty"] = Ordinal.LOW
    with pytest.raises(ValidationError, match="preserve"):
        DiscoveryPriorityAssessment.model_validate(data)


def test_unknown_is_outside_ordinal_tie_ordering(scenario: Scenario) -> None:
    known = assess(scenario, scenario.learning)
    unknown = assess(scenario, learning(scenario, decision_impact=None))
    groups = priority_ties((unknown, known))
    assert groups.ordinal_ties == ((known,),)
    assert groups.unknown_to_clarify == (unknown,)


def test_learning_groups_cannot_become_portfolio_ranking(scenario: Scenario) -> None:
    first = assess(scenario, scenario.learning)
    data = scenario.learning.model_dump()
    data["hypothesis"]["content"]["title"] = "Different material snapshot"
    second = assess(scenario, LearningInput.model_validate(data))
    with pytest.raises(ValueError, match="no portfolio ranking"):
        priority_ties((first, second))


def test_missing_linked_validation_context_is_explicit_and_not_actionable(
    scenario: Scenario,
) -> None:
    result = assess(scenario, learning(scenario, validations=()))
    assert result.result.priority == PriorityCategory.CRITICAL
    assert not result.result.validation_context_complete
    assert not result.result.actionable


def test_completed_validation_dependencies_do_not_create_false_blocker(scenario: Scenario) -> None:
    activity = {
        **scenario.learning.validations[0].model_dump(),
        "status": ValidationStatus.COMPLETED,
        "dependencies": (uuid4(),),
    }
    result = assess(scenario, learning(scenario, validations=(activity,)))
    assert result.result.action == LearningAction.VALIDATE
    assert not result.result.blocker_summary
