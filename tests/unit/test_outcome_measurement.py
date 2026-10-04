"""Definitions, baseline uncertainty, immutable criteria and deterministic target evaluation."""

from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from examples.outcome_feedback import OutcomeScenario
from product_discovery_engine.domain.common import SourceReference, SourceType
from product_discovery_engine.domain.outcome_evaluation import (
    EvaluationState,
    OutcomeAssessment,
    OutcomeDisposition,
)
from product_discovery_engine.domain.outcome_measurement import (
    BaselineObservation,
    Comparator,
    MeasurementWindow,
    OutcomeMeasurementPlan,
    OutcomeMetricDefinition,
    OutcomeObservation,
    OutcomeTarget,
    TargetKind,
)
from product_discovery_engine.domain.outcome_policy import OutcomeMeasurementPolicy
from product_discovery_engine.infrastructure.configuration import load_outcome_measurement_policy
from tests.m7_helpers import ACTOR, observation_for, plan_for


def test_plan_is_explicit_and_predefined(outcome_scenario: OutcomeScenario) -> None:
    s = outcome_scenario
    assert not s.plan.post_hoc
    assert [m.role.value for m in s.plan.metrics] == ["primary", "secondary", "guardrail"]
    assert s.plan.desired_outcome == s.implemented.after.content.desired_outcome
    assert [b.value for b in s.plan.baselines] == [0.60, 0.30, 180.0]
    assert s.plan.previous is None
    assert s.plan.owner is not None
    assert s.plan.metrics[0].aggregation and s.plan.metrics[0].population


@pytest.mark.parametrize(
    "field,value", [("owner", None), ("metrics", ()), ("desired_outcome", "Invented")]
)
def test_plan_rejects_missing_accountability_or_changed_outcome(
    outcome_scenario: OutcomeScenario,
    field: str,
    value: object,
) -> None:
    data = outcome_scenario.plan.model_dump()
    data[field] = value
    with pytest.raises(ValueError):
        OutcomeMeasurementPlan.model_validate(data)


@pytest.mark.parametrize(
    "field",
    [
        "description",
        "unit",
        "population",
        "aggregation",
        "observation_source",
        "baseline_definition",
    ],
)
def test_metric_name_alone_is_insufficient(outcome_scenario: OutcomeScenario, field: str) -> None:
    data = outcome_scenario.plan.metrics[0].model_dump()
    data.pop(field)
    with pytest.raises(ValueError):
        OutcomeMetricDefinition.model_validate(data)


@pytest.mark.parametrize("kind", list(TargetKind))
def test_target_shapes_are_explicit(kind: TargetKind) -> None:
    data: dict[str, object] = {"kind": kind, "definition": "Human supplied criterion"}
    if kind in {TargetKind.NUMERIC, TargetKind.THRESHOLD}:
        data.update(value=10.0, comparator=Comparator.AT_LEAST)
    elif kind == TargetKind.RANGE:
        data.update(lower=1.0, upper=3.0)
    elif kind == TargetKind.QUALITATIVE:
        data.update(qualitative_state="acceptable")
    target = OutcomeTarget.model_validate(data)
    assert target.kind == kind


@pytest.mark.parametrize(
    "data",
    [
        {"kind": "numeric", "definition": "Missing precision"},
        {"kind": "range", "definition": "Inverted", "lower": 4.0, "upper": 1.0},
        {"kind": "directional", "definition": "Unsupported precision", "value": 0.10},
        {"kind": "qualitative", "definition": "Unspecified state"},
        {"kind": "threshold", "definition": "Bad numeric", "value": True, "comparator": "at_least"},
        {
            "kind": "threshold",
            "definition": "Bad numeric",
            "value": float("nan"),
            "comparator": "at_least",
        },
    ],
)
def test_invalid_targets_rejected(data: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        OutcomeTarget.model_validate(data)


def test_unknown_baseline_is_not_fabricated(outcome_scenario: OutcomeScenario) -> None:
    s = outcome_scenario
    metric = s.plan.metrics[1]
    old = s.plan.baselines[1]
    baseline = s.service.baseline(
        s.completed.id,
        metric.id,
        value=None,
        unknown_reason="Historical instrumentation unavailable",
        period=old.period,
        population=old.population,
        source=old.source,
        methodology=old.methodology,
        provenance=old.provenance,
        actor=ACTOR,
        at=old.collected_at,
    )
    plan = plan_for(s, (metric,), (baseline,))
    result = s.service.evaluate(
        plan,
        metric.id,
        (observation_for(s, plan, metric.id, 0.2),),
        actor=ACTOR,
        at=plan.window.end,
    )
    assert baseline.value is None and result.result.state == EvaluationState.INCONCLUSIVE
    assert result.result.missing_information
    data = baseline.model_dump()
    data["unknown_reason"] = None
    with pytest.raises(ValueError, match="unknown baseline"):
        BaselineObservation.model_validate(data)


def test_no_baseline_and_no_target_remain_visible(outcome_scenario: OutcomeScenario) -> None:
    s = outcome_scenario
    numeric = plan_for(s, (s.plan.metrics[0],), ())
    evaluation = s.service.evaluate(
        numeric,
        numeric.metrics[0].id,
        (observation_for(s, numeric, numeric.metrics[0].id, 0.8),),
        actor=ACTOR,
        at=numeric.window.end,
    )
    assert evaluation.result.state == EvaluationState.MET
    assert any("Baseline unavailable" in x for x in evaluation.result.limitations)
    metric = OutcomeMetricDefinition.model_validate(
        {**s.plan.metrics[0].model_dump(), "target": None}
    )
    plan = plan_for(s, (metric,), ())
    evaluation = s.service.evaluate(
        plan,
        metric.id,
        (observation_for(s, plan, metric.id, 0.8),),
        actor=ACTOR,
        at=plan.window.end,
    )
    assert evaluation.result.state == EvaluationState.NOT_EVALUABLE
    assert "Predefined target" in evaluation.result.missing_information


@pytest.mark.parametrize(
    "field", ["implementation_id", "metric_id", "population", "source", "period"]
)
def test_baseline_binding_rejects_mismatch(outcome_scenario: OutcomeScenario, field: str) -> None:
    s = outcome_scenario
    baseline = s.plan.baselines[0]
    value: object = uuid4() if field.endswith("id") else "Other population"
    if field == "source":
        value = SourceReference(source_type=SourceType.ANALYTICS, reference="other")
    if field == "period":
        value = MeasurementWindow(
            start=baseline.period.start + timedelta(days=1), end=baseline.period.end
        )
    wrong = baseline.model_copy(update={field: value})
    with pytest.raises(ValueError):
        plan_for(s, (s.plan.metrics[0],), (wrong,))


def test_post_hoc_revision_preserves_old_target_and_observations(
    outcome_scenario: OutcomeScenario,
) -> None:
    s = outcome_scenario
    metric = s.plan.metrics[0]
    target = OutcomeTarget(
        kind=TargetKind.NUMERIC,
        definition="Human revised lower target",
        value=0.50,
        comparator=Comparator.AT_LEAST,
    )
    revised_metric = OutcomeMetricDefinition.model_validate(
        {**metric.model_dump(), "target": target}
    )
    revised = s.service.revise_plan(
        s.plan,
        metrics=(revised_metric,) + s.plan.metrics[1:],
        baselines=s.plan.baselines,
        observations=s.observations,
        actor=ACTOR,
        at=s.plan.window.end,
        reason="Post-hoc exploratory criterion; retain original target",
    )
    assert revised.post_hoc and revised.previous == s.plan and revised.version == 2
    assert s.plan.metrics[0].target != revised.metrics[0].target
    assert s.observations[0].plan == s.plan
    assert any(e.event_type.value == "outcome_target_revised" for e in revised.events)
    with pytest.raises(ValueError, match="exact plan"):
        s.service.evaluate(
            revised, metric.id, (s.observations[0],), actor=ACTOR, at=s.plan.window.end
        )
    with pytest.raises(ValidationError):
        revised.__setattr__("post_hoc", False)
    with pytest.raises(ValueError):
        s.service.revise_plan(
            s.plan,
            metrics=(revised_metric,) + s.plan.metrics[1:],
            baselines=s.plan.baselines,
            actor=ACTOR,
            at=s.plan.recorded_at,
            reason="",
        )


def test_baseline_correction_preserves_snapshot_history(outcome_scenario: OutcomeScenario) -> None:
    s = outcome_scenario
    old = s.plan.baselines[0]
    corrected = s.service.baseline(
        s.completed.id,
        old.metric_id,
        value=0.59,
        period=old.period,
        population=old.population,
        source=old.source,
        methodology="Explicit correction",
        provenance=old.provenance,
        actor=ACTOR,
        at=old.collected_at,
    )
    revised = s.service.revise_plan(
        s.plan,
        metrics=s.plan.metrics,
        baselines=(corrected,) + s.plan.baselines[1:],
        actor=ACTOR,
        at=s.plan.recorded_at,
        reason="Correct baseline by new observation identity",
    )
    assert revised.previous is not None and revised.previous.baselines[0].value == 0.60
    assert revised.baselines[0].value == 0.59


@pytest.mark.parametrize(
    "field", ["implementation_id", "metric_id", "population", "period", "source", "provenance"]
)
def test_observation_rejects_cross_scope(outcome_scenario: OutcomeScenario, field: str) -> None:
    observation = outcome_scenario.observations[0]
    data = observation.model_dump()
    if field.endswith("id"):
        data[field] = uuid4()
    elif field == "population":
        data[field] = "Unrelated wider population"
    elif field == "period":
        data[field] = {
            "start": observation.period.start - timedelta(days=1),
            "end": observation.period.end,
        }
    elif field == "source":
        data.pop(field)
    else:
        data[field] = {"sources": ()}
    with pytest.raises(ValueError):
        OutcomeObservation.model_validate(data)


@pytest.mark.parametrize(
    "values,state",
    [
        ((0.8,), EvaluationState.MET),
        ((0.6,), EvaluationState.NOT_MET),
        ((0.8, 0.6), EvaluationState.PARTIALLY_MET),
        ((None,), EvaluationState.INCONCLUSIVE),
        ((), EvaluationState.INCONCLUSIVE),
    ],
)
def test_deterministic_evaluation_states(
    outcome_scenario: OutcomeScenario, values: tuple[float | None, ...], state: EvaluationState
) -> None:
    s = outcome_scenario
    metric = s.plan.metrics[0]
    observations = tuple(observation_for(s, s.plan, metric.id, value) for value in values)
    result = s.service.evaluate(s.plan, metric.id, observations, actor=ACTOR, at=s.plan.window.end)
    assert result.result.state == state
    assert result.observations == observations
    assert (
        "Target achievement does not establish implementation causality"
        in result.result.limitations
    )


@pytest.mark.parametrize(
    "comparator,actual,met",
    [
        (Comparator.AT_LEAST, 0.70, True),
        (Comparator.AT_MOST, 0.70, True),
        (Comparator.GREATER_THAN, 0.70, False),
        (Comparator.LESS_THAN, 0.70, False),
        (Comparator.EQUAL, 0.70, True),
        (Comparator.EQUAL, 0.71, False),
    ],
)
def test_numeric_boundaries(
    outcome_scenario: OutcomeScenario, comparator: Comparator, actual: float, met: bool
) -> None:
    s = outcome_scenario
    metric = OutcomeMetricDefinition.model_validate(
        {
            **s.plan.metrics[0].model_dump(),
            "target": OutcomeTarget(
                kind=TargetKind.THRESHOLD,
                definition="Explicit comparator",
                value=0.70,
                comparator=comparator,
            ),
        }
    )
    plan = plan_for(s, (metric,))
    result = s.service.evaluate(
        plan,
        metric.id,
        (observation_for(s, plan, metric.id, actual),),
        actor=ACTOR,
        at=plan.window.end,
    )
    assert result.result.state == (EvaluationState.MET if met else EvaluationState.NOT_MET)


@pytest.mark.parametrize(
    "kind,actual,state",
    [
        (TargetKind.RANGE, 0.70, EvaluationState.MET),
        (TargetKind.RANGE, 0.90, EvaluationState.NOT_MET),
        (TargetKind.QUALITATIVE, "acceptable", EvaluationState.MET),
        (TargetKind.QUALITATIVE, "uncertain", EvaluationState.NOT_MET),
        (TargetKind.DIRECTIONAL, 0.20, EvaluationState.MET),
        (TargetKind.DIRECTIONAL, 0.30, EvaluationState.NOT_MET),
    ],
)
def test_non_numeric_targets(
    outcome_scenario: OutcomeScenario, kind: TargetKind, actual: float | str, state: EvaluationState
) -> None:
    s = outcome_scenario
    target = OutcomeTarget.model_validate(
        {
            "kind": kind,
            "definition": "Explicit supplied criterion",
            **(
                {"lower": 0.60, "upper": 0.80}
                if kind == TargetKind.RANGE
                else {"qualitative_state": "acceptable"}
                if kind == TargetKind.QUALITATIVE
                else {}
            ),
        }
    )
    metric = OutcomeMetricDefinition.model_validate(
        {**s.plan.metrics[1].model_dump(), "target": target}
    )
    plan = plan_for(s, (metric,))
    result = s.service.evaluate(
        plan,
        metric.id,
        (observation_for(s, plan, metric.id, actual),),
        actor=ACTOR,
        at=plan.window.end,
    )
    assert result.result.state == state


def test_partial_window_and_conflicting_metrics_are_not_averaged(
    outcome_scenario: OutcomeScenario,
) -> None:
    s = outcome_scenario
    observation = s.observations[0]
    partial = s.service.observe(
        s.plan,
        observation.metric_id,
        value=0.8,
        period=MeasurementWindow(
            start=observation.period.start, end=observation.period.end - timedelta(days=1)
        ),
        population=observation.population,
        source=observation.source,
        methodology=observation.methodology,
        provenance=observation.provenance,
        actor=ACTOR,
        at=observation.collected_at,
    )
    result = s.service.evaluate(
        s.plan, partial.metric_id, (partial,), actor=ACTOR, at=s.plan.window.end
    )
    assert result.result.state == EvaluationState.INCONCLUSIVE
    assert s.assessment.disposition == OutcomeDisposition.MIXED
    assert [e.result.state for e in s.assessment.evaluations] == [
        EvaluationState.MET,
        EvaluationState.NOT_MET,
        EvaluationState.NOT_MET,
    ]
    assert "score" not in OutcomeAssessment.model_fields
    assert "success_percentage" not in OutcomeAssessment.model_fields
    with pytest.raises(ValueError):
        s.service.assess(s.plan, s.assessment.evaluations[:1])


def test_evaluation_before_window_end_is_inconclusive(outcome_scenario: OutcomeScenario) -> None:
    s = outcome_scenario
    result = s.service.evaluate(
        s.plan, s.plan.metrics[0].id, (), actor=ACTOR, at=s.plan.window.start
    )
    assert result.result.state == EvaluationState.INCONCLUSIVE
    assert "Completed measurement window" in result.result.missing_information


@pytest.mark.parametrize("record", ["plan", "observation", "baseline"])
def test_measurement_records_are_frozen(outcome_scenario: OutcomeScenario, record: str) -> None:
    s = outcome_scenario
    obj = {"plan": s.plan, "observation": s.observations[0], "baseline": s.plan.baselines[0]}[
        record
    ]
    with pytest.raises(ValidationError):
        obj.__setattr__("id", uuid4())


def test_versioned_policy_configuration() -> None:
    policy = load_outcome_measurement_policy(Path("config/outcome-measurement.v1.toml"))
    assert policy.version == "outcome-measurement.v1" and policy.require_complete_window
    for data in (
        {"version": ""},
        {**policy.model_dump(), "allow_inconclusive_closure": "true"},
        {**policy.model_dump(), "weighted_score": 0.7},
    ):
        with pytest.raises(ValueError):
            OutcomeMeasurementPolicy.model_validate(data)
