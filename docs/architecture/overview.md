# Architecture overview

Product Discovery Engine v0.1 is a Python modular monolith. Its functional lifecycle
runs from structured discovery through human delivery selection, specification review,
implementation records, outcome measurement and evidence feedback. It models supplied
external reality; it does not execute deployment or collect production analytics.

Start with the [three architecture diagrams](portfolio-architecture.md) and
[authority boundaries](authority-boundaries.md). The [product specification](../product-specs/discovery-prioritization-system-v0.1.md)
is the behavior source of truth; [ADRs](../README.md#architectural-decisions) explain tradeoffs.

## Architectural layers

```text
src/product_discovery_engine/
  domain/          pure typed records, policy, lifecycle, version and audit invariants
  application/     use-case orchestration and replaceable provider protocols
  ai/              versioned interpretation, challenge and drafting prompts
  infrastructure/  TOML loading and concrete OpenAI adapters
  presentation/    reserved boundary; no implemented API or UI
config/            versioned evidence, discovery, specification and outcome policies
tests/             unit, integration, offline evals and opt-in deferred live cases
examples/          credential-free synthetic workflows
docs/              portfolio guides, capability contracts, ADRs, evaluations and history
```

The domain never imports another architectural layer, a provider SDK, storage or an HTTP
framework. Application services coordinate domain operations and consume provider
protocols. Infrastructure implements those protocols and configuration I/O; prompt
instructions live in AI modules. Business policy is implemented in pure code and validated
TOML, with no deterministic rules delegated to model reasoning.

Focused domain files keep records and policies inspectable without a framework or subpackage
per entity. There is no service deployment topology or persistence backend.

## Capability map

| Capability | Contract | Representative implementation |
| --- | --- | --- |
| Structured, advisory signal interpretation | [Discovery analysis](discovery-analysis.md) | [Application provider boundary](../../src/product_discovery_engine/application/discovery_analysis.py) |
| Evidence quality, freshness, independence, validation and Challenge Mode | [Evidence and validation](evidence-validation.md) | [Evidence orchestration](../../src/product_discovery_engine/application/evidence_validation.py) |
| Separate learning priority, Delivery Readiness and Discovery Gate | [Discovery decisioning](discovery-decisioning.md) | [Pure gate policy](../../src/product_discovery_engine/domain/discovery_gate.py) |
| Human selection and reviewed draft proposals | [Delivery specification](delivery-specification.md) | [Specification service](../../src/product_discovery_engine/application/delivery_specification.py) |
| Completeness, clarification, exact review, Delivery Gate and handoff | [Specification and delivery entry](spec-completeness-delivery-gate.md) | [Delivery orchestration](../../src/product_discovery_engine/application/spec_delivery.py) |
| Actual scope, measurement, causal review, appended evidence and closure | [Implementation outcomes](implementation-outcome-feedback.md) | [Outcome service](../../src/product_discovery_engine/application/outcome_feedback.py) |

[The offline search example](../../examples/outcome_feedback.py) composes the deterministic
lifecycle through reviewed closure. It uses a synthetic Challenge Mode provider and manual
specification content; the separate drafting example exercises proposal review.

## Integrity and accountability

Immutable snapshots and consecutive material versions retain decisions against exact
content and policy. Dedicated operations guard consequential lifecycle edges; generic
transitions cannot stand in for selection, handoff, completion, measurement or closure.
Audits agree with the retained before/after records. Preserve full records, predecessor
snapshots and source artifacts: event metadata alone cannot reconstruct material values.

AI interpretation remains advisory. Human review and materialization are explicit, and
accepted wording retains its original provenance. Target comparison remains separate from
human causal interpretation; mixed results and contradictions are preserved.

## Productionization boundary

Callers supply current histories and retain objects in memory. There is no production
database, atomic latest-version transaction, authenticated role system, web UI, analytics
connector or automated deployment. The core cannot detect withheld changes or certify
source truth and semantic adequacy. Nested retained records make validation and future
storage costs explicit risks. No production scale or live model reliability is claimed.

For verification limits, see [evaluations](../evals/README.md). For the original plan,
milestone-era deferrals and reviews, see [development history](../history/development-history.md).
