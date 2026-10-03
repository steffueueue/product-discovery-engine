"""Qualitative uncertainty avoids unsupported probability estimates."""

from enum import StrEnum
from uuid import UUID

from .common import DomainModel, Owner, Provenance, ReferenceIds, Text


class AssumptionCategory(StrEnum):
    DESIRABILITY = "desirability"
    USABILITY = "usability"
    FEASIBILITY = "feasibility"
    VIABILITY = "viability"
    OTHER = "other"
    UNKNOWN = "unknown"


class Importance(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class Uncertainty(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class ValidationState(StrEnum):
    UNTESTED = "untested"
    IN_PROGRESS = "in_progress"
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"


class Assumption(DomainModel):
    id: UUID
    statement: Text
    category: AssumptionCategory
    importance: Importance
    uncertainty: Uncertainty
    provenance: Provenance
    validation_state: ValidationState = ValidationState.UNTESTED
    owner: Owner | None = None
    evidence_ids: ReferenceIds = ()

    @property
    def ai_generated(self) -> bool | None:
        return self.provenance.ai_generated
