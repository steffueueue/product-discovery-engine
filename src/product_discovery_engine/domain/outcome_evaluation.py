"""Deterministic target comparison, preserving each metric and all uncertainty."""

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, model_validator

from .audit import Actor, AuditEvent, EventType, ObjectKind
from .common import DomainModel, Text
from .outcome_audit import check_event
from .outcome_measurement import (
    Comparator,
    ImprovementDirection,
    OutcomeMeasurementPlan,
    OutcomeObservation,
    TargetKind,
)
from .outcome_policy import OutcomeMeasurementPolicy


class EvaluationState(StrEnum):
    MET = "met"
    PARTIALLY_MET = "partially_met"
    NOT_MET = "not_met"
    INCONCLUSIVE = "inconclusive"
    NOT_EVALUABLE = "not_evaluable"


class MetricEvaluationResult(DomainModel):
    state: EvaluationState
    explanation: Text
    limitations: tuple[Text, ...]
    missing_information: tuple[Text, ...]


def compare_target(
    plan: OutcomeMeasurementPlan,
    metric_id: UUID,
    observations: tuple[OutcomeObservation, ...],
    policy: OutcomeMeasurementPolicy,
    at: AwareDatetime,
) -> MetricEvaluationResult:
    metric = plan.metric(metric_id)
    baseline = plan.baseline(metric_id)
    if len({o.id for o in observations}) != len(observations):
        raise ValueError("duplicate outcome observations")
    if any(o.plan != plan or o.metric_id != metric_id or o.collected_at > at for o in observations):
        raise ValueError(
            "evaluation requires exact plan/version, metric and non-future observations"
        )
    limitations = list(
        plan.interpretation_risks + plan.confounders + plan.implementation.limitations
    )
    limitations.extend(d.description for d in plan.implementation.deviations)
    limitations.extend(o for observation in observations for o in observation.limitations)
    if baseline:
        limitations.extend(baseline.limitations)
    else:
        limitations.append("Baseline unavailable; absolute targets may still be evaluated")
    for release in plan.releases:
        limitations.append(
            f"Observed release audience: {release.audience}; rollout: {release.rollout_scope}"
        )
        limitations.extend(release.limitations)
    if not plan.releases:
        limitations.append("Deployment/release and actual exposure remain unknown")
    if plan.post_hoc:
        limitations.append("Plan/criteria defined or revised after observation window began")
    limitations.append("Target achievement does not establish implementation causality")
    missing: list[str] = []
    state = EvaluationState.INCONCLUSIVE
    explanation = "Measurement is incomplete or unavailable"
    target = metric.target
    if target is None:
        state, explanation = (
            EvaluationState.NOT_EVALUABLE,
            "No predefined target; observations retained",
        )
        missing.append("Predefined target")
    elif policy.require_complete_window and at < metric.outcome_period.end:
        missing.append("Completed measurement window")
    elif not observations:
        missing.append("Actual observations")
    else:
        verdicts: list[bool] = []
        for observation in observations:
            if observation.value is None:
                missing.append(str(observation.unknown_reason))
                continue
            if observation.period != metric.outcome_period:
                missing.append("Full defined outcome period; partial windows are not extrapolated")
                continue
            actual = observation.value
            if target.kind in {TargetKind.NUMERIC, TargetKind.THRESHOLD}:
                if not isinstance(actual, float):
                    missing.append("Numeric actual value")
                    continue
                assert target.value is not None and target.comparator is not None
                verdicts.append(
                    {
                        Comparator.AT_LEAST: actual >= target.value,
                        Comparator.AT_MOST: actual <= target.value,
                        Comparator.GREATER_THAN: actual > target.value,
                        Comparator.LESS_THAN: actual < target.value,
                        Comparator.EQUAL: actual == target.value,
                    }[target.comparator]
                )
            elif target.kind == TargetKind.RANGE:
                if not isinstance(actual, float):
                    missing.append("Numeric actual value")
                    continue
                assert target.lower is not None and target.upper is not None
                verdicts.append(target.lower <= actual <= target.upper)
            elif target.kind == TargetKind.DIRECTIONAL:
                if (
                    not baseline
                    or not isinstance(baseline.value, float)
                    or not isinstance(actual, float)
                ):
                    missing.append("Known comparable numeric baseline and actual")
                    continue
                verdicts.append(
                    actual > baseline.value
                    if metric.direction == ImprovementDirection.INCREASE
                    else actual < baseline.value
                )
            else:
                if not isinstance(actual, str):
                    missing.append("Qualitative actual state")
                    continue
                verdicts.append(actual == target.qualitative_state)
        if missing:
            explanation = "Missing or incomparable measurement inputs prevent a complete evaluation"
        elif all(verdicts):
            state, explanation = (
                EvaluationState.MET,
                "All supplied full-window observations meet the target",
            )
        elif any(verdicts):
            state, explanation = (
                EvaluationState.PARTIALLY_MET,
                "Full-window observations disagree on target achievement",
            )
            limitations.append("Conflicting observations require human investigation")
        else:
            state, explanation = (
                EvaluationState.NOT_MET,
                "Full-window observations do not meet the target",
            )
    return MetricEvaluationResult(
        state=state,
        explanation=explanation,
        limitations=tuple(dict.fromkeys(limitations)),
        missing_information=tuple(dict.fromkeys(missing)),
    )


class OutcomeMetricEvaluation(DomainModel):
    id: UUID
    plan: OutcomeMeasurementPlan
    metric_id: UUID
    observations: tuple[OutcomeObservation, ...]
    policy: OutcomeMeasurementPolicy
    result: MetricEvaluationResult
    evaluated_by: Actor
    evaluated_at: AwareDatetime
    event: AuditEvent

    @model_validator(mode="after")
    def reconstruct(self) -> "OutcomeMetricEvaluation":
        if self.evaluated_at < self.plan.recorded_at or self.result != compare_target(
            self.plan, self.metric_id, self.observations, self.policy, self.evaluated_at
        ):
            raise ValueError("outcome evaluation must reconstruct deterministic comparison")
        check_event(
            self.event,
            EventType.OUTCOME_EVALUATED,
            ObjectKind.OUTCOME_EVALUATION,
            self.id,
            self.evaluated_by,
            self.evaluated_at,
            (self.plan.id, self.metric_id),
            self.policy.version,
            self.plan.version,
        )
        return self


class OutcomeDisposition(StrEnum):
    POSITIVE = "positive"
    MIXED = "mixed"
    NEGATIVE = "negative"
    INCONCLUSIVE = "inconclusive"


def assessment_disposition(evaluations: tuple[OutcomeMetricEvaluation, ...]) -> OutcomeDisposition:
    states = {e.result.state for e in evaluations}
    if not evaluations:
        raise ValueError("outcome assessment requires every metric evaluation")
    if states == {EvaluationState.MET}:
        return OutcomeDisposition.POSITIVE
    if states == {EvaluationState.NOT_MET}:
        return OutcomeDisposition.NEGATIVE
    if states <= {EvaluationState.INCONCLUSIVE, EvaluationState.NOT_EVALUABLE}:
        return OutcomeDisposition.INCONCLUSIVE
    return OutcomeDisposition.MIXED


class OutcomeAssessment(DomainModel):
    plan: OutcomeMeasurementPlan
    evaluations: tuple[OutcomeMetricEvaluation, ...]
    disposition: OutcomeDisposition
    limitations: tuple[Text, ...]

    @model_validator(mode="after")
    def reconstruct(self) -> "OutcomeAssessment":
        if (
            tuple(e.metric_id for e in self.evaluations) != tuple(m.id for m in self.plan.metrics)
            or any(e.plan != self.plan for e in self.evaluations)
            or len({e.id for e in self.evaluations}) != len(self.evaluations)
            or len({e.policy for e in self.evaluations}) != 1
        ):
            raise ValueError("assessment must retain every exact metric evaluation and one policy")
        expected = tuple(
            dict.fromkeys(
                x
                for e in self.evaluations
                for x in e.result.limitations + e.result.missing_information
            )
        )
        if (
            self.disposition != assessment_disposition(self.evaluations)
            or self.limitations != expected
        ):
            raise ValueError(
                "qualitative assessment must expose all metric results and limitations"
            )
        return self
