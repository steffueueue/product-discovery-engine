"""Versioned conservative evaluation and closure policy, independent of AI."""

from pydantic import Field

from .common import DomainModel, Text


class OutcomeMeasurementPolicy(DomainModel):
    version: Text
    allow_inconclusive_closure: bool = Field(strict=True)
    require_complete_window: bool = Field(strict=True)
