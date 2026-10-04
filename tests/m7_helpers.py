"""Shared offline outcome episode and explicit scoped measurement inputs."""

from datetime import datetime
from uuid import UUID

from examples.discovery_decisioning import ACTOR as ACTOR
from examples.discovery_decisioning import AT as AT
from examples.outcome_feedback import OutcomeScenario
from product_discovery_engine.domain.common import Provenance
from product_discovery_engine.domain.outcome_measurement import (
    BaselineObservation,
    OutcomeMeasurementPlan,
    OutcomeMetricDefinition,
    OutcomeObservation,
)


def plan_for(
    scenario: OutcomeScenario,
    metrics: tuple[OutcomeMetricDefinition, ...],
    baselines: tuple[BaselineObservation, ...] | None = None,
) -> OutcomeMeasurementPlan:
    plan = scenario.plan
    return scenario.service.create_plan(
        scenario.implemented.after,
        scenario.completed,
        metrics=metrics,
        baselines=tuple(b for b in plan.baselines if b.metric_id in {m.id for m in metrics})
        if baselines is None
        else baselines,
        window=plan.window,
        observation_source=plan.observation_source,
        analysis_method=plan.analysis_method,
        owner=plan.owner,
        actor=ACTOR,
        at=plan.recorded_at,
        reason="Explicit test criteria before observations",
        confounders=plan.confounders,
        interpretation_risks=plan.interpretation_risks,
    )


def observation_for(
    scenario: OutcomeScenario,
    plan: OutcomeMeasurementPlan,
    metric_id: UUID,
    value: float | str | None,
    *,
    at: datetime | None = None,
) -> OutcomeObservation:
    metric = plan.metric(metric_id)
    return scenario.service.observe(
        plan,
        metric_id,
        value=value,
        period=metric.outcome_period,
        population=metric.population,
        source=metric.observation_source,
        methodology=metric.aggregation,
        provenance=Provenance(sources=(metric.observation_source,), ai_generated=False),
        actor=ACTOR,
        at=at or plan.window.end,
        unknown_reason="Tracking failure; actual unavailable" if value is None else None,
    )
