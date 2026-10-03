"""Shared immutable value objects; no I/O or provider dependencies."""

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _require_unique_references(value: tuple[UUID, ...]) -> tuple[UUID, ...]:
    if len(value) != len(set(value)):
        raise ValueError("duplicate references are not allowed")
    return value


ReferenceIds = Annotated[tuple[UUID, ...], AfterValidator(_require_unique_references)]


class DomainModel(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", validate_default=True, revalidate_instances="always"
    )


class Owner(DomainModel):
    id: UUID
    display_name: Text


class SourceType(StrEnum):
    INTERVIEW = "interview"
    ANALYTICS = "analytics"
    EXPERIMENT = "experiment"
    SUPPORT = "support"
    DOCUMENT = "document"
    STAKEHOLDER = "stakeholder"
    OTHER = "other"
    UNKNOWN = "unknown"
    AI_SUMMARY = "ai_summary"


class SourceReference(DomainModel):
    source_type: SourceType
    reference: Text
    owner: Owner | None = None


class Provenance(DomainModel):
    """Underlying sources are mandatory, even for AI-assisted interpretation."""

    sources: tuple[SourceReference, ...]
    submission_ids: ReferenceIds = ()
    ai_generated: bool | None = Field(default=None, strict=True)
    interpretation_notes: Text | None = None

    @field_validator("sources")
    @classmethod
    def require_sources(cls, value: tuple[SourceReference, ...]) -> tuple[SourceReference, ...]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate source references are not allowed")
        if not any(source.source_type != SourceType.AI_SUMMARY for source in value):
            raise ValueError("provenance requires at least one underlying source")
        return value


class Unknown(DomainModel):
    reason: Text


class StrategyReference(DomainModel):
    id: Text
    version: Annotated[int, Field(ge=1, strict=True)]


class Ordinal(StrEnum):
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


ORDINAL_ORDER = tuple(Ordinal)


def ordinal_min(values: tuple[Ordinal, ...]) -> Ordinal:
    return min(values, key=ORDINAL_ORDER.index)
