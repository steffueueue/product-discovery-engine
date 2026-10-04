# Development history

The functional product lifecycle was completed through Milestone 7 at
`a7384876b920b356c101270c8e57836fc8ef277d`. Portfolio presentation is separate from
functional milestones. Current scope is described in the [README](../../README.md) and
[current architecture overview](../architecture/overview.md).

## Functional increments

| Increment | Scope | Historical review |
| --- | --- | --- |
| 0–1 | Repository foundation, immutable domain, provenance and audit | [Validation](../architecture/milestone-0-1-validation.md), [domain review](../architecture/milestone-0-1-domain-review.md) |
| 2 | Structured, advisory discovery analysis | [Review](../architecture/milestone-2-review.md) |
| 3 | Evidence policy, validation and Challenge Mode | [Review](../architecture/milestone-3-review.md) |
| 4 | Learning priority, readiness and Discovery Gate | [Review](../architecture/milestone-4-review.md) |
| 5 | Human selection and reviewed draft specifications | [Review](../architecture/milestone-5-review.md) |
| 6 | Completeness, clarification, Delivery Gate and handoff | [Review](../architecture/milestone-6-review.md) |
| 7 | Implementation records, outcomes, feedback and closure | [Review](../architecture/milestone-7-review.md) |

All original review documents and ADRs remain at their existing paths. Their deferrals
refer to the milestone at the time; later contracts supersede earlier deferred scope.
The [product specification](../product-specs/discovery-prioritization-system-v0.1.md)
retains the founding brief and each authorized increment.

## Preserved repository narratives

The two snapshots below preserve the original README and architecture plan from the
functional baseline. Only relative links have been rebased. They contain historical
plans, stale future-tense descriptions and repeated milestone details; they are archival
material rather than current setup or capability guidance.

<details>
<summary>README before portfolio presentation</summary>

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
[deferred verification checklist](../evals/deferred-live-verification.md) and
[previous attempt report](../evals/milestone-3-live-verification.md).
Deferred or skipped live checks must never be reported as a semantic pass.
Discovery Priority, Delivery Readiness and Discovery Gate are implemented separately.
Human delivery selection, reviewed specification drafting, completeness, clarification and
Delivery Gate, implementation records, outcome measurement and reviewed evidence feedback are
implemented. Production persistence, UI, deployment execution and portfolio ranking remain deferred.
See [Milestone 2 usage and limitations](../architecture/discovery-analysis.md).

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

Read the [product source of truth](../product-specs/discovery-prioritization-system-v0.1.md),
[architecture](../architecture/overview.md), and [design decisions](../decisions/0001-domain-foundation.md).
For the current risks, read the [domain review](../architecture/milestone-0-1-domain-review.md).
`config/policies.example.toml` is explicitly illustrative; no scoring/gate implementation
or production strategy is configured. Tests use in-memory objects and deterministic clocks.


## Milestone 3: evidence and validation

The deterministic layer now assesses claim-scoped quality/freshness, underlying-source
independence, triangulation and assumption risk. Validation activities preserve
predefined criteria, explicit lifecycle and append-only results/audits. Challenge Mode
is a separate structured advisory capability with disconfirmation and provenance guards.
See [the architecture and end-to-end example](../architecture/evidence-validation.md).

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
or delivery selection follows. Read the [architecture, policy tables and limits](../architecture/discovery-decisioning.md),
[ADR](../decisions/0004-discovery-decisioning.md) and
[verification report](../architecture/milestone-4-review.md).

### Milestone 5: delivery selection and draft specifications

[Delivery specification architecture](../architecture/delivery-specification.md) and
[ADR 0005](../decisions/0005-reviewed-delivery-specification-proposals.md) explain the
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
See [Milestone 6 architecture](../architecture/spec-completeness-delivery-gate.md) and
[ADR 0006](../decisions/0006-separate-specification-and-delivery-authority.md).


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
Read [the architecture and limitations](../architecture/implementation-outcome-feedback.md),
[ADR 0007](../decisions/0007-separate-implementation-outcomes-and-causal-learning.md) and
[verification report](../architecture/milestone-7-review.md). No paid API calls are needed.
Production hardening and final repository polish remain separate work.

</details>

<details>
<summary>Architecture overview before portfolio presentation</summary>

# Architecture and implementation plan

```
src/product_discovery_engine/
  domain/          # pure typed models, lifecycle, freshness, snapshot changes, audit
  application/     # future use cases, depending on domain abstractions
  ai/              # future interpretation adapters; no business rules in prompts
  infrastructure/  # TOML policy loading; future persistence/provider adapters
  presentation/    # future API/UI
config/            # versioned illustrative policy configuration
tests/            # unit, integration, evals, fixtures
docs/             # product specs, architecture, decisions, evals
```

Domain modules are focused files rather than a subpackage per entity; the current
size does not justify deeper nesting. No service framework, database or AI SDK is needed.
Infrastructure imports the domain; the domain never imports another architectural layer.
`domain/hypotheses.py` contains the snapshot models; `domain/hypothesis_changes.py`
contains material change functions and audit consistency validation. Configuration
infrastructure only reads TOML and delegates business-policy validation to the domain.

Milestone 0: establish packaging, commands, ignore rules, agent instructions, source
of truth and policy layout. Milestone 1: add immutable models, provenance, ownership,
explicit uncertainty, transition graph, freshness rules, versioned change results and
unit tests. Verify installation, build, tests, formatting, lint and strict typing.

Milestone 2 should first define application use cases and repository ports, then
transactional persistence for snapshots/audit events. Define approved gate requirements
before implementing readiness or prioritization. AI integration is a separate later step.


## Milestone 2

Structured review proposals, provider protocol, source/strategy checks and an isolated
OpenAI Responses adapter are now implemented. See [discovery analysis](../architecture/discovery-analysis.md)
and [ADR 0002](../decisions/0002-discovery-analysis.md). The domain remains unchanged.


## Milestone 3

Deterministic evidence/validation domain policies and snapshots, knowledge assembly,
and a separate structured Challenge Mode provider are implemented. See
[evidence and validation](../architecture/evidence-validation.md) and
[ADR 0003](../decisions/0003-evidence-validation.md). Persistence and Milestone 4 gates
remain deferred; domain models import no provider SDK or I/O dependencies.


## Milestone 4

Three separate deterministic policies now own learning priority, knowledge readiness and
discovery gating. Human promotion consumes immutable gate/current-policy/current-snapshot
inputs and stops at delivery candidacy. Generic status changes cannot bypass the gate.
Domain knowledge packets translate and reconstruct Milestone 3 evidence; Challenge Mode
remains advisory with explicit human review. See [discovery decisioning](../architecture/discovery-decisioning.md)
and [ADR 0004](../decisions/0004-discovery-decisioning.md). Milestone 4 deferrals in earlier
sections describe those historical milestones. Milestone 5 adds human selection and drafting;
Milestone 6 adds completeness and handoff below. Milestone 7 completes the functional loop below; persistence remains deferred.


## Specification completeness and delivery handoff

[Milestone 6](../architecture/spec-completeness-delivery-gate.md) separates structural completeness,
owned clarification, human review, controlled readiness, deterministic delivery entry
and human implementation authorization. It retains exact immutable material versions
and stops before implementation execution or outcomes. Policy is in
`config/spec-completeness.v1.toml`; the offline example is `examples/spec_delivery.py`.


## Implementation outcomes and feedback

[Milestone 7](../architecture/implementation-outcome-feedback.md) separates supplied implementation reality,
optional release observations, versioned measurement planning, deterministic target comparison,
human causal interpretation, appended discovery evidence and accountable review/closure.
`OutcomeFeedbackService` orchestrates pure domain records under
`config/outcome-measurement.v1.toml`; the complete offline flow is
`examples/outcome_feedback.py`. [ADR 0007](../decisions/0007-separate-implementation-outcomes-and-causal-learning.md)
explains why completion, outcome achievement and learning stay separate. Production storage,
authenticated roles, UI, execution/integrations and final repository polish remain deferred.

</details>
