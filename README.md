# Product Discovery Engine

Evidence-driven foundations for accountable product decisions, from original signals
through hypothesis validation and eventual measured outcomes. Prefer transparent
incompleteness over fabricated certainty.

**Implemented: Milestones 0–2 (repository, domain foundation, discovery analysis).**
This Python modular monolith accepts immutable submissions and returns structured,
reviewable AI interpretation through a replaceable provider. Offline tests need no API
key. Live analysis requires explicitly configured OpenAI credentials and model.
Scoring, delivery selection, specification generation and outcome measurement are deferred.
See [Milestone 2 usage and limitations](docs/architecture/discovery-analysis.md).

## Development

Requires Python 3.12 or newer. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy src tests
```

Format with `.venv/bin/ruff format .`. Build a distributable wheel with
`.venv/bin/python -m pip wheel . --no-deps --wheel-dir dist`.
Dependency ranges are declared in `pyproject.toml`; `requirements-dev.lock` records
exact runtime/development/build dependencies for reproducible Python 3.12 setup:

```sh
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
```

## Domain capabilities

- Immutable original submissions and hypothesis snapshots.
- Fact, evidence, assumption, inference and unknown claim categories.
- Source provenance, accountable owners and versioned strategy references.
- Supporting and contradicting evidence with deterministic policy-based freshness.
- Qualitative assumption uncertainty; no invented probability percentages.
- Explicit lifecycle transitions and auditable material revisions/evidence additions.

Hypothesis snapshots live in `domain/hypotheses.py`; audited changes live in
`domain/hypothesis_changes.py`. Domain operations return snapshots and events; callers
must retain the full snapshots together with their audit events. Event metadata alone
does not reconstruct material field values. Durable storage, referential integrity across objects, concurrency handling and authorization
are not implemented yet. Model validation cannot establish factual truth or external
source authenticity. Declared lifecycle eligibility does not imply readiness gates passed.

Read the [product source of truth](docs/product-specs/discovery-prioritization-system-v0.1.md),
[architecture](docs/architecture/overview.md), and [design decisions](docs/decisions/0001-domain-foundation.md).
For the current risks, read the [domain review](docs/architecture/milestone-0-1-domain-review.md).
`config/policies.example.toml` is explicitly illustrative; no scoring/gate implementation
or production strategy is configured. Tests use in-memory objects and deterministic clocks.
