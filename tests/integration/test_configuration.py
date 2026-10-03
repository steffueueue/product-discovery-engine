from pathlib import Path

import pytest
from pydantic import ValidationError

from product_discovery_engine.domain.common import Unknown
from product_discovery_engine.domain.policies import ProductPolicies
from product_discovery_engine.infrastructure.configuration import load_policies


def test_example_policies_are_valid_and_explicitly_incomplete() -> None:
    policies = load_policies(Path(__file__).resolve().parents[2] / "config/policies.example.toml")
    assert isinstance(policies.strategy.objective, Unknown)
    assert policies.strategy.reference.version == 1
    assert policies.evidence.review_after_days == 30
    assert policies.scoring.configured is False
    assert policies.lifecycle_gates.configured is False
    assert policies.delivery_gates.configured is False


def test_unimplemented_policies_cannot_claim_readiness() -> None:
    policies = load_policies(Path(__file__).resolve().parents[2] / "config/policies.example.toml")
    data = policies.model_dump()
    data["scoring"]["configured"] = True
    with pytest.raises(ValidationError):
        ProductPolicies.model_validate(data)


def test_invalid_business_policy_is_rejected_by_domain(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[2] / "config/policies.example.toml"
    path = tmp_path / "invalid.toml"
    path.write_text(example.read_text().replace("stale_after_days = 90", "stale_after_days = 30"))
    with pytest.raises(ValidationError, match="stale threshold"):
        load_policies(path)


def test_missing_policy_file_does_not_invent_defaults(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_policies(tmp_path / "missing.toml")


def test_malformed_toml_is_not_treated_as_unconfigured_policy(tmp_path: Path) -> None:
    import tomllib

    path = tmp_path / "invalid.toml"
    path.write_text("[incomplete")
    with pytest.raises(tomllib.TOMLDecodeError):
        load_policies(path)
