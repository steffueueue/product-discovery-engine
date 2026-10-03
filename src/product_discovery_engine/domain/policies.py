"""Versioned policy foundations, without scoring or gate algorithms."""

from typing import Annotated, Literal

from pydantic import Field

from .common import DomainModel, StrategyReference, Text, Unknown
from .evidence import FreshnessPolicy


class StrategyPolicy(DomainModel):
    reference: StrategyReference
    objective: Text | Unknown


class DeferredPolicy(DomainModel):
    version: Annotated[int, Field(ge=1, strict=True)]
    configured: Literal[False] = False
    reason: Text


class ProductPolicies(DomainModel):
    strategy: StrategyPolicy
    evidence: FreshnessPolicy
    scoring: DeferredPolicy
    lifecycle_gates: DeferredPolicy
    delivery_gates: DeferredPolicy
