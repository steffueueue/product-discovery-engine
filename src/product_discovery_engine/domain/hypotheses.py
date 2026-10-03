"""Immutable hypothesis content, relationships and versioned snapshots."""

from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .common import DomainModel, Owner, ReferenceIds, StrategyReference, Text, Unknown
from .lifecycle import HypothesisStatus


class HypothesisContent(DomainModel):
    title: Text
    owner: Owner | None
    problem_statement: Text | Unknown
    target_segment: Text | Unknown
    desired_outcome: Text | Unknown
    solution_hypothesis: Text | Unknown | None = None
    strategy: StrategyReference | None = None


class HypothesisLinks(DomainModel):
    submission_ids: ReferenceIds
    claim_ids: ReferenceIds = ()
    evidence_ids: ReferenceIds = ()
    assumption_ids: ReferenceIds = ()
    validation_ids: ReferenceIds = ()
    decision_ids: ReferenceIds = ()
    specification_ids: ReferenceIds = ()

    @model_validator(mode="after")
    def validate_links(self) -> "HypothesisLinks":
        if not self.submission_ids:
            raise ValueError("hypotheses require an original submission")
        return self


class Hypothesis(DomainModel):
    id: UUID
    content: HypothesisContent
    links: HypothesisLinks
    status: HypothesisStatus = HypothesisStatus.NEW
    version: Annotated[int, Field(ge=1, strict=True)] = 1
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_timestamps(self) -> "Hypothesis":
        if self.updated_at < self.created_at:
            raise ValueError("update cannot precede creation")
        return self
