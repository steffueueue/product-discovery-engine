"""TOML parsing stays outside the pure domain."""

import tomllib
from pathlib import Path

from product_discovery_engine.domain.policies import ProductPolicies


def load_policies(path: Path) -> ProductPolicies:
    with path.open("rb") as handle:
        return ProductPolicies.model_validate(tomllib.load(handle))
