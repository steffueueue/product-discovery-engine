# Product Discovery Engine

Evidence-driven foundations for accountable product decisions, from original signals
through hypothesis validation and eventual measured outcomes. Prefer transparent
incompleteness over fabricated certainty.

**Implemented: Milestones 0–7 (v0.1 functional lifecycle through reviewed outcomes).**
This Python modular monolith accepts immutable submissions and returns structured,
reviewable AI interpretation through replaceable providers, plus deterministic evidence
assessment and audited validation records. Offline tests need no API
key. Live analysis requires explicitly configured OpenAI credentials and model.
`OPENAI_API_KEY` is optional for normal development; normal pytest and CI require no
paid API access. Paid live-model verification is intentionally deferred to a later final
phase by project decision and is not required for milestone completion or merge.
The 18 existing live evaluations remain explicitly opt-in. See the
[deferred verification checklist](docs/evals/deferred-live-verification.md) and
[previous attempt report](docs/evals/milestone-3-live-verification.md).
Deferred or skipped live checks must never be reported as a semantic pass.
Discovery Priority, Delivery Readiness and Discovery Gate are implemented separately.
Human delivery selection, reviewed specification drafting, completeness, clarification and
Delivery Gate, implementation records, outcome measurement and reviewed evidence feedback are
implemented. Production persistence, UI, deployment execution and portfolio ranking remain deferred.
See [Milestone 2 usage and limitations](docs/architecture/discovery-analysis.md).

## Development

Requires Python 3.12 or newer. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
env -u OPENAI_API_KEY -u DISCOVERY_ANALYSIS_MODEL RUN_LIVE_AI_EVALS=0 .venv/bin/python -m pytest
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


## Milestone 3: evidence and validation

The deterministic layer now assesses claim-scoped quality/freshness, underlying-source
independence, triangulation and assumption risk. Validation activities preserve
predefined criteria, explicit lifecycle and append-only results/audits. Challenge Mode
is a separate structured advisory capability with disconfirmation and provenance guards.
See [the architecture and end-to-end example](docs/architecture/evidence-validation.md).

```sh
RUN_LIVE_AI_EVALS=0 .venv/bin/python -m pytest
.venv/bin/python examples/evidence_validation.py
```

Milestone 3 supplies knowledge inputs to the separate Milestone 4 decisioning layer.


## Milestone 4: discovery decisioning

Deterministic learning priority, qualitative delivery readiness and an audited Discovery
Gate are separate policies in `config/discovery-decisioning.v1.toml`. Unknowns, evidence
targets, independent sources, freshness and human review remain explicit. Candidacy now
requires a current gate pass through the dedicated human promotion operation; ordinary
status transitions cannot bypass it. Overrides are separate, narrowly configured audits.

```sh
.venv/bin/python examples/discovery_decisioning.py
```

The offline synthetic learning loop initially blocks, incorporates validation and human
review, then stops at `candidate_for_delivery_prioritization`. No build recommendation
or delivery selection follows. Read the [architecture, policy tables and limits](docs/architecture/discovery-decisioning.md),
[ADR](docs/decisions/0004-discovery-decisioning.md) and
[verification report](docs/architecture/milestone-4-review.md).

### Milestone 5: delivery selection and draft specifications

[Delivery specification architecture](docs/architecture/delivery-specification.md) and
[ADR 0005](docs/decisions/0005-reviewed-delivery-specification-proposals.md) explain the
separate human selection, optional AI proposal, explicit review and immutable DRAFT versions.
Run the complete credential-free synthetic flow with:

```sh
env -u OPENAI_API_KEY -u DISCOVERY_ANALYSIS_MODEL RUN_LIVE_AI_EVALS=0 .venv/bin/python examples/delivery_specification.py
```

Gate PASS does not select work. Draft creation does not authorize implementation.
Milestone 6 adds completeness, clarification workflows, Delivery Gate and human handoff.


Milestone 6 adds qualitative specification completeness, authoritative gaps, owned
clarifications, exact human review, controlled delivery readiness, deterministic Delivery
Gate and separate implementation handoff. Run `.venv/bin/python examples/spec_delivery.py`
for the credential-free search example. It stops at handoff; the hypothesis remains selected.
See [Milestone 6 architecture](docs/architecture/spec-completeness-delivery-gate.md) and
[ADR 0006](docs/decisions/0006-separate-specification-and-delivery-authority.md).


## Milestone 7: implementation outcomes and learning

Explicit implementation records preserve authorized scope, actual completion and deviations.
Versioned measurement plans retain baselines, predefined targets, metric populations/windows,
primary/secondary/guardrail results and post-hoc changes. Target achievement remains separate
from human causal interpretation. Outcome evidence appends original discovery knowledge;
human review and dedicated lifecycle operations control measurement and closure.

```sh
env -u OPENAI_API_KEY -u DISCOVERY_ANALYSIS_MODEL RUN_LIVE_AI_EVALS=0 .venv/bin/python examples/outcome_feedback.py
```

The search example retains improved search success, unchanged abandonment and a latency
regression as MIXED, with unresolved causality, new evidence, explicit follow-up learning
and human-reviewed closure. Closed means episode reviewed, not hypothesis proven.
Read [the architecture and limitations](docs/architecture/implementation-outcome-feedback.md),
[ADR 0007](docs/decisions/0007-separate-implementation-outcomes-and-causal-learning.md) and
[verification report](docs/architecture/milestone-7-review.md). No paid API calls are needed.
Production hardening and final repository polish remain separate work.
