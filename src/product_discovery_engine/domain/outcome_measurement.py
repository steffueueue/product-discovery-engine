"""Immutable measurement definitions, criteria history and scoped observations."""

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .audit import Actor, AuditEvent, EventType, ObjectKind
from .common import DomainModel, Owner, Provenance, SourceReference, SourceType, Text, Unknown
from .delivery_context import ReferenceKind, SpecReference
from .evidence_assessment import EvidenceScope
from .hypotheses import Hypothesis
from .implementation import ImplementationRecord, ImplementationStatus, ReleaseObservation
from .lifecycle import HypothesisStatus
from .outcome_audit import check_event
from .spec_content import Version

Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class MeasurementWindow(DomainModel):
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def ordered(self) -> "MeasurementWindow":
        if self.end <= self.start:
            raise ValueError("measurement window must have positive duration")
        return self

    def contains(self, other: "MeasurementWindow") -> bool:
        return self.start <= other.start < other.end <= self.end


class MetricRole(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    GUARDRAIL = "guardrail"


class ImprovementDirection(StrEnum):
    INCREASE = "increase"
    DECREASE = "decrease"
    NONE = "none"


class TargetKind(StrEnum):
    NUMERIC = "numeric"
    THRESHOLD = "threshold"
    RANGE = "range"
    DIRECTIONAL = "directional"
    QUALITATIVE = "qualitative"


class Comparator(StrEnum):
    AT_LEAST = "at_least"
    AT_MOST = "at_most"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    EQUAL = "equal"


class OutcomeTarget(DomainModel):
    kind: TargetKind
    definition: Text
    value: Number | None = None
    comparator: Comparator | None = None
    lower: Number | None = None
    upper: Number | None = None
    qualitative_state: Text | None = None

    @model_validator(mode="after")
    def explicit_shape(self) -> "OutcomeTarget":
        numeric = self.kind in {TargetKind.NUMERIC, TargetKind.THRESHOLD}
        if numeric != (self.value is not None and self.comparator is not None):
            raise ValueError("numeric target requires explicit value and comparator")
        if not numeric and (self.value is not None or self.comparator is not None):
            raise ValueError("non-numeric targets cannot carry a numeric threshold")
        if self.kind == TargetKind.RANGE:
            if self.lower is None or self.upper is None or self.lower > self.upper:
                raise ValueError("range target requires ordered explicit limits")
        elif self.lower is not None or self.upper is not None:
            raise ValueError("only a range target has range limits")
        if (self.kind == TargetKind.QUALITATIVE) != (self.qualitative_state is not None):
            raise ValueError("qualitative target requires an explicit observed-state criterion")
        return self


class OutcomeMetricDefinition(DomainModel):
    id: UUID
    name: Text
    description: Text
    unit: Text
    direction: ImprovementDirection
    role: MetricRole
    population: Text
    aggregation: Text
    observation_source: SourceReference
    cadence: Text | None = None
    baseline_definition: Text
    baseline_period: MeasurementWindow
    outcome_period: MeasurementWindow
    target: OutcomeTarget | None = None
    feedback_scope: EvidenceScope

    @model_validator(mode="after")
    def definition_integrity(self) -> "OutcomeMetricDefinition":
        if self.feedback_scope.population != self.population:
            raise ValueError("metric feedback scope must use the exact population")
        if self.baseline_period.end > self.outcome_period.start:
            raise ValueError("baseline period must precede the outcome period")
        if self.observation_source.source_type == SourceType.AI_SUMMARY:
            raise ValueError("metric observation source must be underlying data")
        if self.target and self.target.kind == TargetKind.DIRECTIONAL:
            if self.direction == ImprovementDirection.NONE:
                raise ValueError("directional target requires a defined improvement direction")
        return self


class BaselineObservation(DomainModel):
    id: UUID
    implementation_id: UUID
    metric_id: UUID
    value: Number | Text | None
    unknown_reason: Text | None = None
    period: MeasurementWindow
    population: Text
    source: SourceReference
    collected_at: AwareDatetime
    methodology: Text
    limitations: tuple[Text, ...] = ()
    provenance: Provenance
    recorded_by: Actor
    event: AuditEvent

    @model_validator(mode="after")
    def reconstruct(self) -> "BaselineObservation":
        if (self.value is None) != (self.unknown_reason is not None):
            raise ValueError("unknown baseline requires an explicit reason")
        if self.collected_at < self.period.end:
            raise ValueError("baseline collection cannot precede its measurement period")
        if (
            self.source not in self.provenance.sources
            or self.source.source_type == SourceType.AI_SUMMARY
        ):
            raise ValueError("baseline requires its underlying source in provenance")
        check_event(
            self.event,
            EventType.OUTCOME_BASELINE_RECORDED,
            ObjectKind.OUTCOME_BASELINE,
            self.id,
            self.recorded_by,
            self.collected_at,
            (self.implementation_id, self.metric_id),
            self.methodology,
        )
        return self


def require_episode(hypothesis: Hypothesis, implementation: ImplementationRecord) -> None:
    original = implementation.authorization.current.hypothesis
    if (
        hypothesis.id != original.id
        or hypothesis.content != original.content
        or hypothesis.created_at != original.created_at
    ):
        raise ValueError("outcome belongs to a different or revised hypothesis episode")
    for field in type(original.links).model_fields:
        old, new = getattr(original.links, field), getattr(hypothesis.links, field)
        if (field == "evidence_ids" and new[: len(old)] != old) or (
            field != "evidence_ids" and old != new
        ):
            raise ValueError("outcome episode must preserve the original discovery links")
    if implementation.status != ImplementationStatus.COMPLETED:
        raise ValueError("outcome measurement requires completed implementation")
    if hypothesis.version < original.version or hypothesis.updated_at < original.updated_at:
        raise ValueError("outcome hypothesis cannot precede the authorized episode")
    if hypothesis.status in {
        HypothesisStatus.IMPLEMENTED,
        HypothesisStatus.MEASURING_OUTCOME,
        HypothesisStatus.CLOSED,
    }:
        assert implementation.completed_at is not None
        if (
            hypothesis.version <= original.version
            or hypothesis.updated_at < implementation.completed_at
        ):
            raise ValueError("implemented episode requires a consecutive completion-era hypothesis")


class OutcomeMeasurementPlan(DomainModel):
    id: UUID
    version: Version = 1
    hypothesis: Hypothesis
    implementation: ImplementationRecord
    desired_outcome_reference: SpecReference
    desired_outcome: Text | Unknown
    metrics: tuple[OutcomeMetricDefinition, ...]
    baselines: tuple[BaselineObservation, ...] = ()
    releases: tuple[ReleaseObservation, ...] = ()
    window: MeasurementWindow
    observation_source: Text
    analysis_method: Text
    owner: Owner
    confounders: tuple[Text, ...] = ()
    interpretation_risks: tuple[Text, ...] = ()
    created_at: AwareDatetime
    recorded_by: Actor
    recorded_at: AwareDatetime
    reason: Text
    post_hoc: bool = Field(strict=True)
    previous: "OutcomeMeasurementPlan | None" = None
    events: tuple[AuditEvent, ...]

    @model_validator(mode="after")
    def reconstruct(self) -> "OutcomeMeasurementPlan":
        require_episode(self.hypothesis, self.implementation)
        if self.hypothesis.status != HypothesisStatus.IMPLEMENTED:
            raise ValueError("plan binds the exact implemented hypothesis snapshot")
        if self.desired_outcome != self.hypothesis.content.desired_outcome or (
            self.desired_outcome_reference
            != SpecReference(
                kind=ReferenceKind.HYPOTHESIS,
                id=str(self.hypothesis.id),
                version=self.hypothesis.version,
                field="desired_outcome",
            )
        ):
            raise ValueError("plan must preserve the original desired outcome")
        if self.created_at < self.hypothesis.updated_at or self.recorded_at < self.created_at:
            raise ValueError("plan cannot precede implementation or its creation")
        assert self.implementation.completed_at is not None
        if self.window.start < self.implementation.completed_at:
            raise ValueError("outcome window cannot precede implementation completion")
        if not self.metrics or len({m.id for m in self.metrics}) != len(self.metrics):
            raise ValueError("plan requires unique metric definitions")
        if len({r.id for r in self.releases}) != len(self.releases):
            raise ValueError("release observations must have unique IDs")
        for release in self.releases:
            if (
                release.implementation != self.implementation
                or release.recorded_at > self.recorded_at
            ):
                raise ValueError("plan release must reference exact completed implementation")
            if self.window.start < release.released_at:
                raise ValueError("outcome window cannot precede observed release")
        metric_ids = {m.id for m in self.metrics}
        for metric in self.metrics:
            scope = metric.feedback_scope
            if (
                scope.hypothesis_id != self.hypothesis.id
                or scope.claim_id is not None
                and scope.claim_id not in self.hypothesis.links.claim_ids
                or scope.assumption_id is not None
                and scope.assumption_id not in self.hypothesis.links.assumption_ids
            ):
                raise ValueError("metric feedback target must be linked to the original hypothesis")
            if not self.window.contains(metric.outcome_period):
                raise ValueError("metric outcome period lies outside the plan window")
        if len({b.metric_id for b in self.baselines}) != len(self.baselines) or len(
            {b.id for b in self.baselines}
        ) != len(self.baselines):
            raise ValueError("baseline observations must be unique by metric and ID")
        for baseline in self.baselines:
            if baseline.metric_id not in metric_ids:
                raise ValueError("baseline references an undefined metric")
            metric = next(m for m in self.metrics if m.id == baseline.metric_id)
            if (
                baseline.implementation_id != self.implementation.id
                or baseline.population != metric.population
                or baseline.period != metric.baseline_period
                or baseline.source != metric.observation_source
                or baseline.collected_at > self.recorded_at
            ):
                raise ValueError(
                    "baseline must match exact implementation, metric, period and source"
                )
        if self.previous is None:
            if self.version != 1 or self.created_at != self.recorded_at:
                raise ValueError("initial measurement plan starts at version 1")
        else:
            old = self.previous
            stable = (
                "id",
                "hypothesis",
                "implementation",
                "desired_outcome_reference",
                "desired_outcome",
                "created_at",
                "owner",
            )
            if (
                any(getattr(self, f) != getattr(old, f) for f in stable)
                or self.version != old.version + 1
                or self.recorded_at < old.recorded_at
            ):
                raise ValueError("plan revisions must retain exact consecutive history")
            if not any(
                getattr(self, f) != getattr(old, f)
                for f in (
                    "metrics",
                    "baselines",
                    "releases",
                    "window",
                    "observation_source",
                    "analysis_method",
                    "confounders",
                    "interpretation_risks",
                )
            ):
                raise ValueError("plan revision must change material definitions")
            if not set(old.releases) <= set(self.releases):
                raise ValueError("plan cannot erase release history")
            predecessor: OutcomeMeasurementPlan | None = old
            while predecessor is not None:
                retained = {b.id: b for b in predecessor.baselines}
                for baseline in self.baselines:
                    if baseline.id in retained and retained[baseline.id] != baseline:
                        raise ValueError("baseline IDs cannot rewrite any historical observation")
                predecessor = predecessor.previous
            new_baselines = {b.metric_id: b for b in self.baselines}
            for baseline in old.baselines:
                replacement = new_baselines.get(baseline.metric_id)
                if replacement is None or (
                    replacement.id == baseline.id and replacement != baseline
                ):
                    raise ValueError(
                        "baseline correction requires a new identity and retained history"
                    )
            if {m.id for m in old.metrics} != metric_ids:
                raise ValueError("plan revision cannot silently remove/change metric identities")
        earliest = min(m.outcome_period.start for m in self.metrics)
        if self.previous:
            earliest = min(earliest, *(m.outcome_period.start for m in self.previous.metrics))
        if self.post_hoc != (
            self.recorded_at >= earliest or bool(self.previous and self.previous.post_hoc)
        ):
            raise ValueError("post-hoc criterion changes must be explicitly marked")
        kinds: list[tuple[EventType, tuple[UUID, ...], str]] = [
            (
                EventType.OUTCOME_PLAN_REVISED if self.previous else EventType.OUTCOME_PLAN_CREATED,
                (self.implementation.id, self.hypothesis.id),
                self.reason,
            )
        ]
        previous_metrics = {m.id: m for m in self.previous.metrics} if self.previous else {}
        for metric in self.metrics:
            old_metric = previous_metrics.get(metric.id)
            if metric.target is not None and old_metric is None:
                kinds.append(
                    (EventType.OUTCOME_TARGET_RECORDED, (metric.id,), metric.target.definition)
                )
            elif old_metric is not None and metric.target != old_metric.target:
                kinds.append((EventType.OUTCOME_TARGET_REVISED, (metric.id,), self.reason))
        if len(self.events) != len(kinds) or len({e.id for e in self.events}) != len(self.events):
            raise ValueError("plan and criteria require distinct matching audits")
        for event, (kind, related, reason) in zip(self.events, kinds, strict=True):
            check_event(
                event,
                kind,
                ObjectKind.OUTCOME_PLAN,
                self.id,
                self.recorded_by,
                self.recorded_at,
                related,
                reason,
                self.version,
            )
        return self

    def metric(self, metric_id: UUID) -> OutcomeMetricDefinition:
        for metric in self.metrics:
            if metric.id == metric_id:
                return metric
        raise ValueError("unknown outcome metric")

    def baseline(self, metric_id: UUID) -> BaselineObservation | None:
        return next((b for b in self.baselines if b.metric_id == metric_id), None)


class OutcomeObservation(DomainModel):
    id: UUID
    plan: OutcomeMeasurementPlan
    implementation_id: UUID
    metric_id: UUID
    value: Number | Text | None
    unknown_reason: Text | None = None
    period: MeasurementWindow
    population: Text
    source: SourceReference
    collected_at: AwareDatetime
    methodology: Text
    limitations: tuple[Text, ...] = ()
    provenance: Provenance
    recorded_by: Actor
    event: AuditEvent

    @model_validator(mode="after")
    def reconstruct(self) -> "OutcomeObservation":
        metric = self.plan.metric(self.metric_id)
        if self.implementation_id != self.plan.implementation.id:
            raise ValueError("observation references the wrong implementation")
        if self.population != metric.population or self.source != metric.observation_source:
            raise ValueError("observation must match exact metric population and source")
        if not metric.outcome_period.contains(self.period):
            raise ValueError("observation lies outside the defined outcome window")
        if self.collected_at < max(self.period.end, self.plan.recorded_at):
            raise ValueError("collection cannot precede measurement or its plan version")
        if (self.value is None) != (self.unknown_reason is not None):
            raise ValueError("unknown actual observation requires an explicit reason")
        if self.source not in self.provenance.sources:
            raise ValueError("observation primary source must be preserved in provenance")
        check_event(
            self.event,
            EventType.OUTCOME_OBSERVED,
            ObjectKind.OUTCOME_OBSERVATION,
            self.id,
            self.recorded_by,
            self.collected_at,
            (self.plan.id, self.implementation_id, self.metric_id),
            self.methodology,
            self.plan.version,
        )
        return self
