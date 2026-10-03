"""Small validated Milestone 4 policies, not a general rules engine."""

from enum import StrEnum
from typing import Annotated

from pydantic import Field, model_validator

from .common import ORDINAL_ORDER, DomainModel, Ordinal, Text
from .evidence import EvidenceTarget, Freshness


class PriorityCategory(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NO_ACTION = "no_action"
    UNKNOWN = "unknown"


class ReadinessState(StrEnum):
    NOT_READY = "not_ready"
    NEEDS_REVIEW = "needs_review"
    READY = "ready"


class ReadinessDimension(StrEnum):
    PROBLEM_EVIDENCE = "problem_evidence"
    TARGET_SEGMENT = "target_segment"
    OUTCOME_CLARITY = "outcome_clarity"
    EVIDENCE_QUALITY = "evidence_quality"
    EVIDENCE_FRESHNESS = "evidence_freshness"
    TRIANGULATION = "triangulation"
    ASSUMPTION_RISK = "assumption_risk"
    CONTRADICTIONS = "contradictions"
    VALIDATION = "validation"
    CHALLENGE = "challenge"
    OWNERSHIP = "ownership"
    STRATEGY = "strategy"
    REACH = "reach"
    VIABILITY = "viability"
    CAUSAL_MECHANISM = "causal_mechanism"
    BUSINESS_IMPACT = "business_impact"
    SOLUTION_EFFECTIVENESS = "solution_effectiveness"


class GateCondition(StrEnum):
    READINESS = "readiness"
    EVIDENCE_TARGETS = "evidence_targets"
    OWNERSHIP = "ownership"
    FRESHNESS = "freshness"
    QUALITY = "quality"
    TRIANGULATION = "triangulation"
    CRITICAL_ASSUMPTIONS = "critical_assumptions"
    VALIDATION = "validation"
    CHALLENGE = "challenge"
    STRATEGY = "strategy"
    CONTRADICTIONS = "contradictions"


Positive = Annotated[int, Field(ge=1, strict=True)]


def at_least(value: Ordinal, threshold: Ordinal) -> bool:
    return ORDINAL_ORDER.index(value) >= ORDINAL_ORDER.index(threshold)


class PriorityRule(DomainModel):
    minimum_impact: Ordinal
    minimum_uncertainty: Ordinal
    category: PriorityCategory


class DiscoveryPriorityPolicy(DomainModel):
    version: Text
    rules: tuple[PriorityRule, ...]
    resolved_uncertainty_at_most: Ordinal
    suppress_active_validation: bool = Field(strict=True)

    @model_validator(mode="after")
    def validate_rules(self) -> "DiscoveryPriorityPolicy":
        keys = [(r.minimum_impact, r.minimum_uncertainty) for r in self.rules]
        if not self.rules or len(keys) != len(set(keys)):
            raise ValueError("priority rules must be nonempty and unique")
        allowed = tuple(PriorityCategory)[:4]
        if any(r.category not in allowed for r in self.rules):
            raise ValueError("priority rules must yield actionable ordinal categories")
        # Evaluate all 25 combinations: later rules cannot mask a higher-priority match.
        for impact in ORDINAL_ORDER:
            for uncertainty in ORDINAL_ORDER:
                here = self.category(impact, uncertainty)
                for higher_impact in ORDINAL_ORDER[ORDINAL_ORDER.index(impact) :]:
                    for higher_uncertainty in ORDINAL_ORDER[ORDINAL_ORDER.index(uncertainty) :]:
                        if allowed.index(self.category(higher_impact, higher_uncertainty)) > (
                            allowed.index(here)
                        ):
                            raise ValueError("priority rules must be monotonic")
        return self

    def category(self, impact: Ordinal, uncertainty: Ordinal) -> PriorityCategory:
        matches = tuple(
            r.category
            for r in self.rules
            if at_least(impact, r.minimum_impact) and at_least(uncertainty, r.minimum_uncertainty)
        )
        if not matches:
            raise ValueError("priority rules must cover every ordinal combination")
        return min(matches, key=tuple(PriorityCategory).index)


class EvidenceRequirement(DomainModel):
    dimension: ReadinessDimension
    target: EvidenceTarget
    minimum_quality: Ordinal
    acceptable_freshness: tuple[Freshness, ...]
    minimum_independent_groups: Positive
    minimum_distinct_methods: Positive
    solution_only: bool = Field(strict=True)

    @model_validator(mode="after")
    def validate_requirement(self) -> "EvidenceRequirement":
        mapping = {
            ReadinessDimension.PROBLEM_EVIDENCE: EvidenceTarget.PROBLEM_EXISTENCE,
            ReadinessDimension.TARGET_SEGMENT: EvidenceTarget.TARGET_SEGMENT,
            ReadinessDimension.REACH: EvidenceTarget.REACH,
            ReadinessDimension.VIABILITY: EvidenceTarget.VIABILITY,
            ReadinessDimension.CAUSAL_MECHANISM: EvidenceTarget.CAUSAL_MECHANISM,
            ReadinessDimension.BUSINESS_IMPACT: EvidenceTarget.BUSINESS_IMPACT,
            ReadinessDimension.SOLUTION_EFFECTIVENESS: EvidenceTarget.SOLUTION,
        }
        if mapping.get(self.dimension) != self.target:
            raise ValueError("invalid evidence target for readiness dimension")
        if self.solution_only != (self.dimension == ReadinessDimension.SOLUTION_EFFECTIVENESS):
            raise ValueError("only solution effectiveness may be solution-only")
        if (
            not self.acceptable_freshness
            or len(set(self.acceptable_freshness)) != len(self.acceptable_freshness)
            or Freshness.INVALIDATED in self.acceptable_freshness
            or self.minimum_distinct_methods > self.minimum_independent_groups
        ):
            raise ValueError("invalid freshness/independent-method requirement")
        return self


class DeliveryReadinessPolicy(DomainModel):
    version: Text
    required_dimensions: tuple[ReadinessDimension, ...]
    evidence_requirements: tuple[EvidenceRequirement, ...]
    critical_impact: Ordinal
    critical_uncertainty: Ordinal
    require_completed_critical_validation: bool = Field(strict=True)
    require_current_validation_evidence: bool = Field(strict=True)
    serious_challenge_at_least: Ordinal
    allow_human_assumption_treatment: bool = Field(strict=True)
    allow_accepted_contradictions: bool = Field(strict=True)
    review_due_requires_review: bool = Field(strict=True)
    challenge_requires_human_review: bool = Field(strict=True)
    strategy_requires_human_acknowledgement: bool = Field(strict=True)

    @model_validator(mode="after")
    def validate_dimensions(self) -> "DeliveryReadinessPolicy":
        dimensions = self.required_dimensions
        requirements = self.evidence_requirements
        if not dimensions or len(dimensions) != len(set(dimensions)):
            raise ValueError("required dimensions must be nonempty and unique")
        if len({r.dimension for r in requirements}) != len(requirements):
            raise ValueError("duplicate evidence requirements")
        if not requirements or len({r.target for r in requirements}) != len(requirements):
            raise ValueError("evidence targets must be nonempty and unique")
        evidence_dimensions = {
            ReadinessDimension.PROBLEM_EVIDENCE,
            ReadinessDimension.TARGET_SEGMENT,
            ReadinessDimension.REACH,
            ReadinessDimension.VIABILITY,
            ReadinessDimension.CAUSAL_MECHANISM,
            ReadinessDimension.BUSINESS_IMPACT,
            ReadinessDimension.SOLUTION_EFFECTIVENESS,
        }
        configured = {r.dimension for r in requirements}
        if not (set(dimensions) & evidence_dimensions) <= configured:
            raise ValueError("required evidence dimension has no target policy")
        if not (set(dimensions) & configured):
            raise ValueError("readiness must require at least one explicit evidence target")
        return self


class DiscoveryGatePolicy(DomainModel):
    version: Text
    required_readiness: ReadinessState
    required_conditions: tuple[GateCondition, ...]
    maximum_age_hours: Positive
    overridable_conditions: tuple[GateCondition, ...]

    @model_validator(mode="after")
    def validate_conditions(self) -> "DiscoveryGatePolicy":
        if self.required_readiness != ReadinessState.READY:
            raise ValueError("ordinary gate requires READY; review is not ordinary pass")
        if (
            not self.required_conditions
            or GateCondition.READINESS not in self.required_conditions
            or len(set(self.required_conditions)) != len(self.required_conditions)
            or len(set(self.overridable_conditions)) != len(self.overridable_conditions)
            or not set(self.overridable_conditions) <= set(self.required_conditions)
        ):
            raise ValueError("invalid/duplicate gate or override conditions")
        return self


class DecisioningPolicies(DomainModel):
    version: Text
    priority: DiscoveryPriorityPolicy
    readiness: DeliveryReadinessPolicy
    gate: DiscoveryGatePolicy

    @model_validator(mode="after")
    def validate_bundle(self) -> "DecisioningPolicies":
        if any(p.version != self.version for p in (self.priority, self.readiness, self.gate)):
            raise ValueError("all decision policies must share the bundle version")
        mapping = {
            GateCondition.OWNERSHIP: ReadinessDimension.OWNERSHIP,
            GateCondition.FRESHNESS: ReadinessDimension.EVIDENCE_FRESHNESS,
            GateCondition.QUALITY: ReadinessDimension.EVIDENCE_QUALITY,
            GateCondition.TRIANGULATION: ReadinessDimension.TRIANGULATION,
            GateCondition.CRITICAL_ASSUMPTIONS: ReadinessDimension.ASSUMPTION_RISK,
            GateCondition.VALIDATION: ReadinessDimension.VALIDATION,
            GateCondition.CHALLENGE: ReadinessDimension.CHALLENGE,
            GateCondition.STRATEGY: ReadinessDimension.STRATEGY,
            GateCondition.CONTRADICTIONS: ReadinessDimension.CONTRADICTIONS,
        }
        if any(
            mapping[c] not in self.readiness.required_dimensions
            for c in self.gate.required_conditions
            if c in mapping
        ):
            raise ValueError("gate condition must have a required readiness dimension")
        return self
