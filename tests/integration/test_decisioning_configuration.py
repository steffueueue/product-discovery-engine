"""Versioned validated config rejects unsafe or impossible business policy."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from product_discovery_engine.domain.decisioning_policy import DecisioningPolicies
from product_discovery_engine.infrastructure.configuration import load_decisioning_policies

PATH = Path(__file__).resolve().parents[2] / "config/discovery-decisioning.v1.toml"


def test_load_configuration_without_credentials() -> None:
    policy = load_decisioning_policies(PATH)
    assert policy.version == "discovery-decisioning.v1"
    assert (
        policy.priority.version == policy.readiness.version == policy.gate.version == policy.version
    )
    assert DecisioningPolicies.model_validate_json(policy.model_dump_json()) == policy


@pytest.mark.parametrize(
    "case",
    [
        "missing_version",
        "unknown_dimension",
        "invalid_ordinal",
        "duplicate_rule",
        "missing_coverage",
        "unknown_gate",
        "duplicate_gate",
        "unsafe_readiness",
        "wrong_target",
        "invalid_target",
        "duplicate_target",
        "impossible_methods",
        "invalidated_allowed",
        "missing_required_target",
        "gate_dimension_missing",
        "mismatched_version",
        "bool_age",
        "unknown_field",
        "solution_punished",
        "unconfigured_override",
    ],
)
def test_invalid_configuration_rejected(case: str) -> None:
    data = load_decisioning_policies(PATH).model_dump()
    if case == "missing_version":
        del data["version"]
    elif case == "unknown_dimension":
        data["readiness"]["required_dimensions"] += ("roi",)
    elif case == "invalid_ordinal":
        data["priority"]["rules"][0]["minimum_impact"] = "extreme"
    elif case == "duplicate_rule":
        data["priority"]["rules"] += (data["priority"]["rules"][0],)
    elif case == "missing_coverage":
        data["priority"]["rules"] = data["priority"]["rules"][:-1]
    elif case == "unknown_gate":
        data["gate"]["required_conditions"] += ("roi_positive",)
    elif case == "duplicate_gate":
        data["gate"]["required_conditions"] += ("readiness",)
    elif case == "unsafe_readiness":
        data["gate"]["required_readiness"] = "needs_review"
    elif case == "wrong_target":
        data["readiness"]["evidence_requirements"][0]["target"] = "reach"
    elif case == "invalid_target":
        data["readiness"]["evidence_requirements"][0]["target"] = "market_size_guess"
    elif case == "duplicate_target":
        data["readiness"]["evidence_requirements"] += (
            data["readiness"]["evidence_requirements"][0],
        )
    elif case == "impossible_methods":
        data["readiness"]["evidence_requirements"][0]["minimum_distinct_methods"] = 3
    elif case == "invalidated_allowed":
        data["readiness"]["evidence_requirements"][0]["acceptable_freshness"] = ("invalidated",)
    elif case == "missing_required_target":
        data["readiness"]["evidence_requirements"] = data["readiness"]["evidence_requirements"][1:]
    elif case == "gate_dimension_missing":
        data["readiness"]["required_dimensions"] = ("problem_evidence",)
    elif case == "mismatched_version":
        data["readiness"]["version"] = "other"
    elif case == "bool_age":
        data["gate"]["maximum_age_hours"] = True
    elif case == "unknown_field":
        data["priority"]["roi_weight"] = 0.2
    elif case == "solution_punished":
        data["readiness"]["evidence_requirements"][-1]["solution_only"] = False
    else:
        data["gate"]["required_conditions"] = ("readiness",)
    with pytest.raises(ValidationError):
        DecisioningPolicies.model_validate(data)
