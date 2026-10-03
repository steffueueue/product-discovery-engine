from pathlib import Path

import pytest
from pydantic import ValidationError

from product_discovery_engine.domain.common import Ordinal
from product_discovery_engine.domain.evidence_policy import EvidencePolicies
from product_discovery_engine.infrastructure.configuration import load_evidence_policies
from tests.m3_helpers import policies


def test_policy_bundle_loads_versions_and_immutable_tables() -> None:
    bundle = policies()
    assert bundle.version == "evidence-validation-v1"
    assert bundle.quality.aggregation == "weakest_dimension"
    with pytest.raises(ValidationError):
        bundle.quality.coverage.bounded_sample = Ordinal.VERY_HIGH  # type: ignore[misc]  # Runtime immutability.


@pytest.mark.parametrize("section", ["quality", "freshness", "triangulation", "assumption_risk"])
def test_missing_policy_version_rejected(section: str) -> None:
    data = policies().model_dump()
    del data[section]["version"]
    with pytest.raises(ValidationError):
        EvidencePolicies.model_validate(data)


@pytest.mark.parametrize(
    "patch",
    [
        {"minimum_independent_groups": 1},
        {"minimum_distinct_methods": True},
        {"minimum_distinct_methods": 2.5},
        {"minimum_independent_groups": "3"},
    ],
)
def test_invalid_triangulation_configuration(patch: dict[str, object]) -> None:
    data = policies().model_dump()
    data["triangulation"].update(patch)
    with pytest.raises(ValidationError):
        EvidencePolicies.model_validate(data)


def test_incomplete_rubric_nonmonotonic_risk_and_duplicate_context_fail() -> None:
    data = policies().model_dump()
    del data["quality"]["coverage"]["bounded_sample"]
    with pytest.raises(ValidationError):
        EvidencePolicies.model_validate(data)
    data = policies().model_dump()
    data["assumption_risk"]["matrix"][0]["by_uncertainty"]["very_low"] = "very_high"
    with pytest.raises(ValidationError, match="monotonic"):
        EvidencePolicies.model_validate(data)
    data = policies().model_dump()
    data["freshness"]["contexts"] = (data["freshness"]["default"],)
    with pytest.raises(ValidationError, match="unique"):
        EvidencePolicies.model_validate(data)


def test_invalid_file_fails_at_load_time(tmp_path: Path) -> None:
    path = tmp_path / "invalid.toml"
    path.write_text('version = "v1"\n[quality]\naggregation = "average"')
    with pytest.raises(ValidationError):
        load_evidence_policies(path)


def test_policy_cannot_reward_duplicates_staleness_or_nonrepresentative_prevalence() -> None:
    for section, field, value in [
        ("independence", "shared_family", "very_high"),
        ("recency", "stale", "very_high"),
    ]:
        data = policies().model_dump()
        data["quality"][section][field] = value
        with pytest.raises(ValidationError):
            EvidencePolicies.model_validate(data)
    data = policies().model_dump()
    data["quality"]["population_sample_cap"] = "high"
    with pytest.raises(ValidationError, match="nonrepresentative"):
        EvidencePolicies.model_validate(data)
