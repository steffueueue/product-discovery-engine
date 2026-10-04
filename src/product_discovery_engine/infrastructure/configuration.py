"""TOML parsing stays outside the pure domain."""

import tomllib
from pathlib import Path

from product_discovery_engine.domain.decisioning_policy import DecisioningPolicies
from product_discovery_engine.domain.evidence_policy import EvidencePolicies
from product_discovery_engine.domain.outcome_policy import OutcomeMeasurementPolicy
from product_discovery_engine.domain.policies import ProductPolicies
from product_discovery_engine.domain.spec_completeness_policy import SpecCompletenessPolicy


def load_policies(path: Path) -> ProductPolicies:
    with path.open("rb") as handle:
        return ProductPolicies.model_validate(tomllib.load(handle))


def load_evidence_policies(path: Path) -> "EvidencePolicies":
    """Validate the complete Milestone 3 bundle at load time."""
    with path.open("rb") as handle:
        return EvidencePolicies.model_validate(tomllib.load(handle))


def load_decisioning_policies(path: Path) -> "DecisioningPolicies":
    """Validate Milestone 4 independently of model/provider configuration."""
    with path.open("rb") as handle:
        return DecisioningPolicies.model_validate(tomllib.load(handle))


def load_spec_completeness_policy(path: Path) -> "SpecCompletenessPolicy":
    """Load and validate the independent Milestone 6 policy."""
    with path.open("rb") as handle:
        return SpecCompletenessPolicy.model_validate(tomllib.load(handle))


def load_outcome_measurement_policy(path: Path) -> "OutcomeMeasurementPolicy":
    """Load the independent deterministic Milestone 7 policy."""
    with path.open("rb") as handle:
        return OutcomeMeasurementPolicy.model_validate(tomllib.load(handle))
