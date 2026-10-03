"""Guard imports across the entire domain, including future nested packages."""

import ast
import sys
from pathlib import Path

import pytest

# Pure domain models must not perform storage, environment, process or network I/O.
_IO_MODULES = {
    "sqlite3",
    "http",
    "urllib",
    "socket",
    "subprocess",
    "pathlib",
    "os",
    "io",
    "tomllib",
}


def _assert_domain_imports(source: str, *, package_depth: int = 1) -> None:
    allowed = (sys.stdlib_module_names - _IO_MODULES) | {"pydantic"}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                assert node.level <= package_depth, "relative import escapes domain"
                continue
            assert node.module is not None
            modules = [f"{node.module}.{alias.name}" for alias in node.names]
        else:
            continue
        for module in modules:
            assert (
                module.split(".")[0] in allowed
                or module == "product_discovery_engine.domain"
                or module.startswith("product_discovery_engine.domain.")
            ), f"forbidden domain import: {module}"


def test_domain_imports_only_itself_stdlib_and_validation() -> None:
    root = Path(__file__).resolve().parents[2] / "src/product_discovery_engine/domain"
    paths = list(root.rglob("*.py"))
    assert paths, "domain boundary check must inspect actual source files"
    for path in paths:
        _assert_domain_imports(path.read_text(), package_depth=len(path.relative_to(root).parts))


@pytest.mark.parametrize(
    "source",
    [
        "from product_discovery_engine.infrastructure import configuration",
        "from product_discovery_engine import infrastructure",
        "from ..infrastructure import configuration",
        "import sqlite3",
        "import openai",
        "import http.client",
    ],
)
def test_boundary_guard_rejects_framework_and_infrastructure_imports(source: str) -> None:
    with pytest.raises(AssertionError):
        _assert_domain_imports(source)


@pytest.mark.parametrize(
    "source",
    [
        "from .common import Owner",
        "from product_discovery_engine.domain.common import Owner",
        "from product_discovery_engine import domain",
        "from datetime import datetime",
        "from pydantic import BaseModel",
    ],
)
def test_boundary_guard_accepts_domain_and_validation_imports(source: str) -> None:
    _assert_domain_imports(source)
