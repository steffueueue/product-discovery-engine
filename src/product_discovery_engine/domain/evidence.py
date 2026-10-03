"""Evidence direction and freshness are independent of source seniority."""

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import Field, model_validator

from .common import DomainModel, Provenance, SourceReference, SourceType, Text


class EvidenceDirection(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"


class EvidenceTarget(StrEnum):
    PROBLEM = "problem"
    SEGMENT = "segment"
    OUTCOME = "outcome"
    SOLUTION = "solution"
    ASSUMPTION = "assumption"
    PROBLEM_EXISTENCE = "problem_existence"
    TARGET_SEGMENT = "target_segment"
    FREQUENCY = "frequency"
    SEVERITY = "severity"
    REACH = "reach"
    DESIRABILITY = "desirability"
    USER_VALUE = "user_value"
    BEHAVIOR = "behavior"
    USABILITY = "usability"
    FEASIBILITY = "feasibility"
    VIABILITY = "viability"
    ECONOMICS = "economics"
    BUSINESS_IMPACT = "business_impact"
    CAUSAL_MECHANISM = "causal_mechanism"


class Freshness(StrEnum):
    CURRENT = "current"
    REVIEW_DUE = "review_due"
    STALE = "stale"
    INVALIDATED = "invalidated"


class FreshnessPolicy(DomainModel):
    version: Annotated[int, Field(ge=1, strict=True)]
    review_after_days: Annotated[int, Field(ge=0, strict=True)]
    stale_after_days: Annotated[int, Field(ge=1, strict=True)]

    @model_validator(mode="after")
    def validate_thresholds(self) -> "FreshnessPolicy":
        if self.stale_after_days <= self.review_after_days:
            raise ValueError("stale threshold must exceed review threshold")
        return self


class Evidence(DomainModel):
    id: UUID
    hypothesis_id: UUID
    statement: Text
    source: SourceReference
    collected_on: date
    target: EvidenceTarget
    target_assumption_id: UUID | None = None
    target_claim_id: UUID | None = None
    population: Text | None = None
    valid_from: date | None = None
    review_after: date | None = None
    direction: EvidenceDirection
    methodology_notes: Text | None
    provenance: Provenance
    reviewed_on: date | None = None
    invalidated_on: date | None = None
    invalidation_reason: Text | None = None

    @model_validator(mode="after")
    def validate_evidence(self) -> "Evidence":
        if self.source.source_type == SourceType.AI_SUMMARY:
            raise ValueError("an AI summary cannot be the primary evidence source")
        if self.source not in self.provenance.sources:
            raise ValueError("primary source must be preserved in provenance")
        if (self.target == EvidenceTarget.ASSUMPTION) != (self.target_assumption_id is not None):
            raise ValueError("assumption target requires exactly one assumption reference")
        if (self.invalidated_on is None) != (self.invalidation_reason is None):
            raise ValueError("invalidation requires date and reason")
        if self.review_after is not None and self.review_after < (
            self.valid_from or self.collected_on
        ):
            raise ValueError("review_after cannot precede validity/collection")
        for value in (self.reviewed_on, self.invalidated_on):
            if value is not None and value < self.collected_on:
                raise ValueError("review/invalidation cannot precede collection")
        return self

    def freshness(self, *, as_of: date, policy: FreshnessPolicy) -> Freshness:
        if isinstance(as_of, datetime):
            raise ValueError("freshness requires a calendar date, not a timestamp")
        if as_of < self.collected_on:
            raise ValueError("as_of cannot precede collection")
        if self.reviewed_on is not None and as_of < self.reviewed_on:
            raise ValueError("cannot evaluate a snapshot before its review")
        if self.invalidated_on is not None:
            if as_of < self.invalidated_on:
                raise ValueError("use a historical snapshot before invalidation")
            return Freshness.INVALIDATED
        age = (as_of - (self.reviewed_on or self.collected_on)).days
        if age >= policy.stale_after_days:
            return Freshness.STALE
        if age >= policy.review_after_days:
            return Freshness.REVIEW_DUE
        return Freshness.CURRENT
