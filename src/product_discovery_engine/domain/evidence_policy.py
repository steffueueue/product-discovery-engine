"""Validated ordinal rubrics, independent of prompts and source-type hierarchies."""

from enum import StrEnum
from typing import Annotated, Literal, cast

from pydantic import Field, model_validator

from .common import ORDINAL_ORDER, DomainModel, Ordinal, Text
from .evidence import Freshness, FreshnessPolicy


class DirectnessBasis(StrEnum):
    BELIEF = "belief"
    INDIRECT_PROXY = "indirect_proxy"
    REPORTED_EXPERIENCE = "reported_experience"
    DIRECT_OBSERVATION = "direct_observation"
    DIRECT_MEASUREMENT = "direct_measurement"


class ReliabilityBasis(StrEnum):
    KNOWN_MAJOR_ERRORS = "known_major_errors"
    UNDOCUMENTED_METHOD = "undocumented_method"
    DOCUMENTED_LIMITATIONS = "documented_limitations"
    REVIEWED_METHOD = "reviewed_method"
    RIGOROUS_CHECKED_METHOD = "rigorous_checked_method"


class CoverageBasis(StrEnum):
    SINGLE_ACCOUNT = "single_account"
    CONVENIENCE_SAMPLE = "convenience_sample"
    BOUNDED_SAMPLE = "bounded_sample"
    REPRESENTATIVE_SEGMENT = "representative_segment"
    REPRESENTATIVE_POPULATION = "representative_population"


class IndependenceBasis(StrEnum):
    UNKNOWN = "unknown"
    SHARED_FAMILY = "shared_family"
    TRACEABLE_ORIGIN = "traceable_origin"
    DISTINCT_FAMILY = "distinct_family"


class RatingTable(DomainModel):
    """TOML tables validate into immutable fields rather than mutable dictionaries."""

    def __getitem__(self, basis: StrEnum) -> Ordinal:
        return cast(Ordinal, getattr(self, basis.value))


class DirectnessRatings(RatingTable):
    belief: Ordinal
    indirect_proxy: Ordinal
    reported_experience: Ordinal
    direct_observation: Ordinal
    direct_measurement: Ordinal


class ReliabilityRatings(RatingTable):
    known_major_errors: Ordinal
    undocumented_method: Ordinal
    documented_limitations: Ordinal
    reviewed_method: Ordinal
    rigorous_checked_method: Ordinal


class CoverageRatings(RatingTable):
    single_account: Ordinal
    convenience_sample: Ordinal
    bounded_sample: Ordinal
    representative_segment: Ordinal
    representative_population: Ordinal


class RecencyRatings(RatingTable):
    current: Ordinal
    review_due: Ordinal
    stale: Ordinal
    invalidated: Ordinal


class IndependenceRatings(RatingTable):
    unknown: Ordinal
    shared_family: Ordinal
    traceable_origin: Ordinal
    distinct_family: Ordinal


class OrdinalRatings(RatingTable):
    very_low: Ordinal
    low: Ordinal
    medium: Ordinal
    high: Ordinal
    very_high: Ordinal


class QualityRubric(DomainModel):
    version: Text
    directness: DirectnessRatings
    reliability: ReliabilityRatings
    coverage: CoverageRatings
    recency: RecencyRatings
    independence: IndependenceRatings
    aggregation: Literal["weakest_dimension"]
    population_sample_cap: Ordinal

    @model_validator(mode="after")
    def validate_semantics(self) -> "QualityRubric":
        if ORDINAL_ORDER.index(self.population_sample_cap) > ORDINAL_ORDER.index(Ordinal.LOW):
            raise ValueError("population claims from nonrepresentative samples must remain low")
        for table, names in (
            (self.directness, tuple(DirectnessBasis)),
            (self.reliability, tuple(ReliabilityBasis)),
            (self.coverage, tuple(CoverageBasis)),
            (self.independence, tuple(IndependenceBasis)),
        ):
            ratings = [ORDINAL_ORDER.index(table[key]) for key in names]
            if ratings != sorted(ratings):
                raise ValueError("quality rubric must preserve increasing basis order")
        recency = [ORDINAL_ORDER.index(self.recency[key]) for key in Freshness]
        if recency != sorted(recency, reverse=True):
            raise ValueError("recency rubric cannot reward staleness or invalidation")
        return self


class FreshnessRule(DomainModel):
    context: Text
    thresholds: FreshnessPolicy
    automatic_staleness: bool = Field(strict=True)


class EvidenceFreshnessPolicy(DomainModel):
    version: Text
    default: FreshnessRule
    contexts: tuple[FreshnessRule, ...] = ()

    @model_validator(mode="after")
    def validate_contexts(self) -> "EvidenceFreshnessPolicy":
        names = [self.default.context, *(r.context for r in self.contexts)]
        if len(names) != len(set(names)):
            raise ValueError("freshness contexts must be unique")
        return self

    def rule(self, context: str | None) -> FreshnessRule:
        if context is None or context == self.default.context:
            return self.default
        for rule in self.contexts:
            if rule.context == context:
                return rule
        raise ValueError("unknown freshness context")


class TriangulationPolicy(DomainModel):
    version: Text
    minimum_independent_groups: Annotated[int, Field(ge=2, strict=True)]
    minimum_distinct_methods: Annotated[int, Field(ge=2, strict=True)]


class RiskRow(DomainModel):
    decision_impact: Ordinal
    by_uncertainty: OrdinalRatings


class AssumptionRiskPolicy(DomainModel):
    version: Text
    matrix: tuple[RiskRow, ...]

    @model_validator(mode="after")
    def validate_matrix(self) -> "AssumptionRiskPolicy":
        if len(self.matrix) != len(Ordinal) or {r.decision_impact for r in self.matrix} != set(
            Ordinal
        ):
            raise ValueError("risk matrix must define every impact level exactly once")
        order = tuple(Ordinal)
        rows = {r.decision_impact: r.by_uncertainty for r in self.matrix}
        for i, impact in enumerate(order):
            for j, uncertainty in enumerate(order):
                rank = order.index(rows[impact][uncertainty])
                if (i and rank < order.index(rows[order[i - 1]][uncertainty])) or (
                    j and rank < order.index(rows[impact][order[j - 1]])
                ):
                    raise ValueError("risk matrix must be monotonic in impact and uncertainty")
        return self

    def assess(self, impact: Ordinal, uncertainty: Ordinal) -> Ordinal:
        return next(
            r.by_uncertainty[uncertainty] for r in self.matrix if r.decision_impact == impact
        )


class EvidencePolicies(DomainModel):
    version: Text
    quality: QualityRubric
    freshness: EvidenceFreshnessPolicy
    triangulation: TriangulationPolicy
    assumption_risk: AssumptionRiskPolicy
