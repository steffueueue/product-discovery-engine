"""Versioned qualitative specification policy; no provider or I/O dependencies."""

from enum import StrEnum
from typing import Annotated

from pydantic import Field, model_validator

from .common import DomainModel, Text
from .spec_items import SpecItemType


class SpecDimension(StrEnum):
    INTENT = "intent"
    PROBLEM = "problem"
    SEGMENT = "segment"
    OUTCOME = "outcome"
    SCOPE = "scope"
    NON_GOALS = "non_goals"
    SOLUTION = "solution"
    FUNCTIONAL = "functional"
    BUSINESS_RULES = "business_rules"
    ACCEPTANCE = "acceptance"
    QUALITY = "quality"
    INTERFACES = "interfaces"
    DATA = "data"
    ANALYTICS = "analytics"
    DEPENDENCIES = "dependencies"
    CONSTRAINTS = "constraints"
    RISKS = "risks"
    OPEN_QUESTIONS = "open_questions"
    TRACEABILITY = "traceability"
    OWNERSHIP = "ownership"


DIMENSION_ITEMS = {
    SpecDimension.INTENT: {SpecItemType.TITLE, SpecItemType.SUMMARY},
    SpecDimension.PROBLEM: {SpecItemType.PROBLEM},
    SpecDimension.SEGMENT: {SpecItemType.SEGMENT},
    SpecDimension.OUTCOME: {SpecItemType.OUTCOME},
    SpecDimension.SCOPE: {SpecItemType.SCOPE},
    SpecDimension.NON_GOALS: {SpecItemType.NON_GOAL},
    SpecDimension.SOLUTION: {SpecItemType.SOLUTION},
    SpecDimension.FUNCTIONAL: {SpecItemType.FUNCTIONAL_REQUIREMENT},
    SpecDimension.BUSINESS_RULES: {SpecItemType.BUSINESS_RULE},
    SpecDimension.ACCEPTANCE: {SpecItemType.ACCEPTANCE_CRITERION},
    SpecDimension.QUALITY: {SpecItemType.QUALITY_REQUIREMENT},
    SpecDimension.INTERFACES: {SpecItemType.INTERFACE},
    SpecDimension.DATA: {SpecItemType.DATA_REQUIREMENT},
    SpecDimension.ANALYTICS: {SpecItemType.ANALYTICS},
    SpecDimension.DEPENDENCIES: {SpecItemType.DEPENDENCY},
    SpecDimension.CONSTRAINTS: {SpecItemType.CONSTRAINT},
    SpecDimension.RISKS: {SpecItemType.RISK},
    SpecDimension.OPEN_QUESTIONS: {SpecItemType.OPEN_QUESTION},
    SpecDimension.TRACEABILITY: set(),
    SpecDimension.OWNERSHIP: set(),
}


class DimensionState(StrEnum):
    UNKNOWN = "unknown"
    INSUFFICIENT = "insufficient"
    PARTIAL = "partial"
    SUFFICIENT = "sufficient"
    NOT_APPLICABLE = "not_applicable"


class GapClassification(StrEnum):
    BLOCKING = "blocking"
    NON_BLOCKING = "non_blocking"
    REVIEW_REQUIRED = "review_required"


class ApplicabilityRule(StrEnum):
    ALWAYS = "always"
    SOLUTION_PRESENT = "solution_present"
    EXPLICIT_CONTEXT = "explicit_context"


class DimensionRequirement(DomainModel):
    dimension: SpecDimension
    item_types: tuple[SpecItemType, ...] = ()
    required: bool = Field(strict=True)
    applicability: ApplicabilityRule = ApplicabilityRule.ALWAYS
    minimum: DimensionState = DimensionState.SUFFICIENT
    gap_classification: GapClassification
    question: Text
    requested_information: Text

    @model_validator(mode="after")
    def safe_requirement(self) -> "DimensionRequirement":
        if not set(self.item_types) <= DIMENSION_ITEMS[self.dimension]:
            raise ValueError("dimension cannot relabel unrelated content as required information")
        if len(set(self.item_types)) != len(self.item_types):
            raise ValueError("duplicate dimension item types")
        if self.minimum not in {DimensionState.PARTIAL, DimensionState.SUFFICIENT}:
            raise ValueError("minimum must require usable specified information")
        if self.required and self.gap_classification == GapClassification.NON_BLOCKING:
            raise ValueError("required missing information cannot silently be non-blocking")
        if self.dimension in {SpecDimension.TRACEABILITY, SpecDimension.OWNERSHIP}:
            if self.item_types or self.applicability != ApplicabilityRule.ALWAYS:
                raise ValueError("traceability and ownership use invariant checks")
        elif not self.item_types:
            raise ValueError("content dimensions need explicit item types")
        return self


class DeliveryCondition(StrEnum):
    READY_STATUS = "ready_status"
    CURRENT_SPEC = "current_spec"
    SELECTION = "selection"
    COMPLETENESS = "completeness"
    APPROVED_REVIEW = "approved_review"
    NO_BLOCKING_GAPS = "no_blocking_gaps"
    CLARIFICATIONS = "clarifications"
    ACCEPTANCE = "acceptance"
    INTERFACES = "interfaces"
    DATA = "data"
    QUALITY = "quality"
    DEPENDENCIES = "dependencies"
    TRACEABILITY = "traceability"
    OWNER = "owner"
    CURRENT_POLICY = "current_policy"
    FRESH_RECORDS = "fresh_records"


class GateRequirement(DomainModel):
    condition: DeliveryCondition
    required: bool = Field(strict=True)


class SpecCompletenessPolicy(DomainModel):
    version: Text
    dimensions: tuple[DimensionRequirement, ...]
    require_blocking_question_owner: bool = Field(strict=True)
    gate_conditions: tuple[GateRequirement, ...]
    validity_hours: Annotated[int, Field(ge=1, le=168, strict=True)]

    @model_validator(mode="after")
    def complete_policy(self) -> "SpecCompletenessPolicy":
        if len(self.dimensions) != len(SpecDimension) or {
            r.dimension for r in self.dimensions
        } != set(SpecDimension):
            raise ValueError("policy must cover each specification dimension exactly once")
        if len(self.gate_conditions) != len(DeliveryCondition) or {
            r.condition for r in self.gate_conditions
        } != set(DeliveryCondition):
            raise ValueError("policy must cover each delivery condition exactly once")
        mandatory = {
            DeliveryCondition.READY_STATUS,
            DeliveryCondition.CURRENT_SPEC,
            DeliveryCondition.SELECTION,
            DeliveryCondition.COMPLETENESS,
            DeliveryCondition.APPROVED_REVIEW,
            DeliveryCondition.NO_BLOCKING_GAPS,
            DeliveryCondition.CLARIFICATIONS,
            DeliveryCondition.CURRENT_POLICY,
            DeliveryCondition.FRESH_RECORDS,
            DeliveryCondition.ACCEPTANCE,
            DeliveryCondition.TRACEABILITY,
            DeliveryCondition.OWNER,
        }
        if any(not r.required for r in self.gate_conditions if r.condition in mandatory):
            raise ValueError("technical and accountable gate safeguards must remain required")
        for dimension in (
            SpecDimension.ACCEPTANCE,
            SpecDimension.TRACEABILITY,
            SpecDimension.OWNERSHIP,
        ):
            rule = self.requirement(dimension)
            if (
                not rule.required
                or rule.minimum != DimensionState.SUFFICIENT
                or rule.applicability != ApplicabilityRule.ALWAYS
            ):
                raise ValueError("acceptance, traceability and ownership must require sufficiency")
        configured = {r.condition: r.required for r in self.gate_conditions}
        for condition, dimension in (
            (DeliveryCondition.INTERFACES, SpecDimension.INTERFACES),
            (DeliveryCondition.DATA, SpecDimension.DATA),
            (DeliveryCondition.QUALITY, SpecDimension.QUALITY),
            (DeliveryCondition.DEPENDENCIES, SpecDimension.DEPENDENCIES),
        ):
            if configured[condition] != self.requirement(dimension).required:
                raise ValueError("gate and completeness applicability requirements must agree")
        return self

    def requirement(self, dimension: SpecDimension) -> DimensionRequirement:
        return next(r for r in self.dimensions if r.dimension == dimension)
