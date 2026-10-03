# Product specification v0.1

Status: source of truth for Milestones 0–2.

The following requirements preserve the founding product brief. Implementation details
and provisional lifecycle semantics are recorded in ADR 0001. Amend this document
and version policies before changing business behavior. Subsequent milestones are
requirements context, not authorization to implement them now.

---

We are building a portfolio-quality, production-oriented project called:

**Product Discovery Engine**

This repository should implement an evidence-driven product decision system that manages the lifecycle from unstructured product signal through discovery, validation, prioritization, specification, implementation, and measured outcome.

Do not treat this as a toy LLM demo.

The product must separate AI interpretation from deterministic product and business logic and must prioritize traceability, evidence provenance, explicit uncertainty, auditability, and maintainability.

## First objective

Bootstrap the repository and implement only:

**Milestone 0 – Repository Foundation**

and

**Milestone 1 – Domain Foundation**

Do NOT yet implement the full AI discovery workflow, specification generation, prioritization UI, autonomous agents, or outcome-measurement workflow.

---

## Before implementation

First inspect the repository.

Then:

1. propose the target repository structure;
2. create an implementation plan for Milestones 0 and 1;
3. identify important architectural decisions;
4. proceed with implementation unless there is a genuinely blocking ambiguity.

Do not stop simply to ask for routine confirmation.

---

## Product principles

The system must follow these principles.

### Evidence over opinion

Every product conclusion must eventually be traceable to evidence, an explicitly identified assumption, configured strategy, or an explicitly labeled inference.

Stakeholder seniority is never evidence strength.

### Unknown is valid

Never fabricate completeness.

When information is unavailable, represent it as unknown.

### Explicit uncertainty

The system should reduce decision-relevant uncertainty rather than manufacture confidence.

### Distinguish knowledge types

Never silently mix:

- fact
- evidence
- assumption
- inference
- unknown

### Contradictory evidence

The system must preserve and expose evidence contradicting a hypothesis rather than optimizing only for confirmation.

### AI vs deterministic logic

AI may later be responsible for:

- natural-language interpretation,
- classification,
- normalization,
- assumption identification,
- semantic analysis,
- validation-method recommendations,
- specification drafting,
- clarification generation.

Deterministic code must own:

- scores,
- lifecycle rules,
- evidence aggregation,
- readiness gates,
- persistence,
- audit events,
- versioning.

### Human accountability

The application supports product decisions. It does not autonomously own them.

Human changes and overrides must eventually become auditable.

---

# Milestone 0 – Repository Foundation

Create a professional Python repository suitable for a public GitHub portfolio.

Use a modular-monolith architecture.

Create at minimum:

- README.md
- AGENTS.md
- pyproject.toml
- .gitignore
- .env.example
- docs/
- config/
- src/
- tests/

Create:

`docs/product-specs/discovery-prioritization-system-v0.1.md`

This document should serve as the project's product source of truth.

For now, populate it with the product architecture and rules described in this task and structure it so that later product requirements can be extended without rewriting application code.

Create an AGENTS.md that instructs future Codex tasks to:

- read the product specification before material domain changes;
- preserve separation between domain, application, AI, infrastructure, and presentation layers;
- keep deterministic business logic out of prompts;
- represent unknown information explicitly;
- never turn assumptions into facts;
- run tests, linting, and type checking before completing changes;
- work milestone by milestone;
- avoid unnecessary multi-agent or microservice architecture.

Establish explicit commands for:

- installing dependencies;
- running tests;
- linting;
- formatting if used;
- type checking.

Use modern, maintained Python tooling and keep dependencies minimal.

---

# Architecture

Use these logical boundaries.

## Domain

Pure business/domain logic.

Must not depend on:

- OpenAI,
- Streamlit,
- SQLite,
- HTTP frameworks,
- specific persistence implementations.

## Application

Use cases and orchestration.

Depends on domain abstractions.

## AI

Future AI adapters and structured interpretation.

Not part of the domain model.

## Infrastructure

Persistence, configuration, model provider implementations, external integrations.

## Presentation

Future UI/API layer.

Do not implement significant presentation functionality yet.

---

# Milestone 1 – Domain Foundation

Implement explicit domain models for at least:

## Submission / Signal

Represents immutable original product input.

Required concepts:

- ID
- original text
- source type
- source reference
- submitter metadata
- creation timestamp

The original input must not be silently rewritten.

## Claim

Create an explicit claim taxonomy:

- Fact
- Evidence
- Assumption
- Inference
- Unknown

Prefer type-safe models and enums over generic dictionaries.

## Hypothesis

Represent at minimum:

- ID
- title
- status
- owner
- problem statement
- target user or segment
- desired outcome
- optional solution hypothesis
- version
- timestamps
- relationship to original submission

Provide foundations for linking:

- claims
- evidence
- assumptions
- future validation
- future decisions
- future specifications

## Evidence

Represent at minimum:

- ID
- statement
- source type
- source reference
- source owner
- collected date
- validity/review metadata
- evidence target
- whether it supports or contradicts the hypothesis
- methodology notes
- provenance

Evidence must support future quality evaluation without embedding quality logic into an LLM prompt.

## Evidence freshness

Support at least:

- current
- review_due
- stale
- invalidated

Implement deterministic freshness behavior through policy/configuration where sensible.

Do not hard-code arbitrary business assumptions into AI logic.

## Assumption

Represent:

- statement
- category
- importance
- uncertainty
- whether AI-generated
- validation state
- owner
- evidence references

Do NOT use unsupported numeric probability percentages.

## Ownership

Model ownership explicitly so important product objects can later have accountable owners.

## Strategy reference

Provide a way for hypotheses and future evaluations to reference a versioned strategy configuration.

Do not yet implement AI-based strategic-fit analysis.

## Audit Event

Create foundations for an immutable decision/audit trail.

Audit events should be capable of representing:

- object created
- material field changed
- status changed
- evidence added
- evidence invalidated
- human override
- future AI-generated assumption
- future decision

Audit events should include:

- actor
- timestamp
- event type
- target object
- relevant metadata

Do not silently overwrite important historical state.

---

# Hypothesis lifecycle

Implement the foundations for these states:

- new
- structured
- needs_evidence
- ready_to_validate
- validating
- evidence_updated
- candidate_for_delivery_prioritization
- selected_for_delivery
- parked
- rejected
- merged
- implemented
- measuring_outcome
- closed

Do not assume every theoretical transition is valid.

Create explicit transition rules.

Invalid transitions must fail clearly.

Human override capability may be represented in the domain design, but detailed authorization can wait.

---

# Provenance

Product knowledge must eventually answer:

“Where did this claim come from?”

Design provenance explicitly.

An AI-generated summary must never become the primary evidence source.

Evidence should always be capable of referencing its underlying source.

---

# Versioning

Provide versioning foundations for material hypothesis state.

Do not silently overwrite historically decision-relevant state.

A complete event-sourcing architecture is NOT required.

Prefer the simplest design that preserves future reconstructability.

---

# Configuration

Create configuration foundations for later:

- strategy
- evidence policy
- scoring policy
- lifecycle gates
- delivery gates

Do not implement the complete algorithms yet.

Business policy must not live exclusively inside prompts.

---

# Repository structure

A reasonable starting point is:

src/
    domain/
        submissions/
        hypotheses/
        evidence/
        assumptions/
        audit/
    application/
    ai/
    infrastructure/
    presentation/

tests/
    unit/
    integration/
    evals/
    fixtures/

docs/
    product-specs/
    architecture/
    decisions/
    evals/

config/

You may improve this structure if you can justify a cleaner design.

Do not create complexity without value.

---

# Testing

Add comprehensive unit tests for deterministic domain behavior.

At minimum test:

- original submissions remain immutable;
- claim taxonomy behaves correctly;
- valid hypothesis lifecycle transitions;
- invalid lifecycle transitions;
- evidence support vs contradiction representation;
- evidence freshness;
- provenance requirements;
- ownership;
- version increments where applicable;
- audit-event creation;
- invalid domain states.

Use mocks/fakes instead of live OpenAI calls.

Milestones 0 and 1 must be testable without an OpenAI API key.

---

# Quality requirements

Use:

- clear Python typing;
- Pydantic or dataclasses where appropriate;
- enums/value objects where they prevent invalid states;
- small focused modules;
- meaningful names;
- docstrings where they add value.

Avoid:

- giant generic models;
- dictionary-driven domain logic;
- hidden global state;
- premature abstractions;
- microservices;
- unnecessary agent frameworks.

---

# Before finishing

Run:

- tests;
- linting;
- type checking.

Fix failures where possible.

Then provide a concise implementation report containing:

1. resulting architecture;
2. important design decisions;
3. changed/created files;
4. tests executed and results;
5. known limitations;
6. deliberate deviations from this specification;
7. recommended next task for Milestone 2.

Do not implement Milestone 2 yet.

The guiding product principle is:

**Prefer transparent incompleteness over fabricated certainty.**
---

## Milestone 1 lifecycle contract

This graph is provisional product policy, with ordinary transitions only. Every
transition increments the snapshot version and records actor, time, previous/resulting
status and versions. Self transitions and all unlisted edges fail. It defines stage
order, not readiness criteria, authorization or evidence quality.

| State | Allowed next states |
| --- | --- |
| new | structured, parked, rejected, merged |
| structured | needs_evidence, ready_to_validate, parked, rejected, merged |
| needs_evidence | ready_to_validate, parked, rejected, merged |
| ready_to_validate | validating, needs_evidence, parked, rejected |
| validating | evidence_updated, parked |
| evidence_updated | needs_evidence, ready_to_validate, candidate_for_delivery_prioritization, parked, rejected, merged |
| candidate_for_delivery_prioritization | selected_for_delivery, needs_evidence, parked, rejected |
| selected_for_delivery | implemented, parked |
| parked | structured, needs_evidence, rejected, merged |
| implemented | measuring_outcome |
| measuring_outcome | closed |
| rejected, merged, closed | none |

An override is a distinct auditable human action, not an unrestricted transition flag.
Execution and detailed authorization are deferred. A future merge use case must record
the destination hypothesis and preserve both histories; the state enum alone does not
implement merging. Later gates must not interpret unconfigured policies as passing.

Freshness uses elapsed whole days from review, or collection if never reviewed.
The review/stale thresholds are inclusive and explicit; invalidation takes precedence.
Source quality, evidence strength and contradiction aggregation have no algorithm yet.
AI-generated provenance retains underlying source references, and uncertainty remains
qualitative. Missing owner is explicit and must be handled by future accountability gates.


## Milestone 1 model integrity contract

- An unavailable source type or assumption category is `unknown`, not implicitly `other`.
- `ai_summary` explicitly identifies derived interpretation. It can be preserved as an
  original submission or supplemental provenance reference. Provenance requires at least
  one underlying source, and an AI summary can never be the primary evidence source.
  Caller-supplied classifications do not certify external source authenticity.
- References within an object are unique. Referenced object existence and authorization
  remain the responsibility of future application/persistence use cases.
- Versions are positive integer counters; freshness thresholds are whole days. Boolean,
  string and fractional substitutes are rejected rather than coerced into business state.
- Timestamp fields require timezone information. Evidence dates used for comparison with
  mutation timestamps use UTC calendar days; a future reviewed/invalidated snapshot
  cannot be linked retroactively. Freshness accepts an explicit calendar date only.
- Hypothesis change results agree with their audit target, timestamp, consecutive versions,
  previous/resulting status, actual material fields and event semantics. Status events
  obey the transition graph. Evidence additions identify the added evidence UUID.
- AI-generation metadata is `true`, `false`, or explicitly unknown (`None`). Missing
  origin information must not default to a declaration of non-AI authorship.
- No material difference means no new material version. Snapshots and audit events remain
  immutable; constructors revalidate supplied nested instances. No unchecked Pydantic
  constructor/copy is an approved domain mutation API.


### Supported mutation boundary and retained history

`HypothesisChange` validates only the implemented Milestone 1 operations: creation,
content revision, ordinary status transition and evidence addition. Future audit event
types, including overrides, cannot stand in for those operations. Their standalone
representation does not implement or authorize a workflow. Public transition functions
require actual lifecycle enum values; serialization adapters may validate textual data
into domain types before invoking them.

Original submissions require string text without coercion. Provenance rejects repeated
identical source references. When assumption-targeted evidence is linked, the target must
appear in that hypothesis's assumption references; object existence is checked later.
Reconstruction requires retention of full before/after snapshots with their audit events,
plus referenced source history. Audit field names and version numbers alone do not
preserve material values and are not a complete event-sourcing design.


## Milestone 2 discovery-analysis contract

Milestone 2 is now authorized independently of the historical Milestone 0–1 scope
above. It introduces reviewable analysis only; Milestones 3–7 remain deferred.

- Preserve immutable original submissions. Separate intake type, underlying problem,
  segment, desired outcome, solution hypothesis and expected behavior change.
- Structure FACT, EVIDENCE, ASSUMPTION, INFERENCE and UNKNOWN separately, using the
  existing domain taxonomy. Missing context remains explicitly unknown.
- All AI interpretations are labeled agent-generated. Assumptions include category,
  rationale, importance, qualitative uncertainty and decision relevance.
- Facts may only preserve supplied existing FACT claims; evidence may only preserve
  supplied, non-invalidated domain Evidence statements. Never promote a submission
  assertion or an evidence item into FACT. Free-text metrics remain unverified proposals.
  Existing source classifications are caller assertions, not truth certification.
- Every citation identifies an input source and an exact excerpt. Preserve competing
  explanations and contradictory signals rather than forcing causal conclusions.
- Strategic fit uses explicit versioned strategy only. Missing/unknown strategy returns
  insufficient_strategy_context. Preliminary qualitative alignment has no scoring model.
- Recommend the assumption whose invalidation most affects the decision, considering
  impact and unresolved uncertainty. Recommend the cheapest credible validation with
  required data, success/failure signals, relative cost/speed and cheaper alternatives.
- Application-consumed AI output must validate against composable Pydantic models.
  Domain logic remains authoritative for lifecycle, gates, scoring and audit mutations.
- The application depends on a provider protocol. OpenAI SDK/configuration is isolated
  in infrastructure. Prompts are versioned interpretation instructions, not business policy.
- Retain analysis input, result, timestamp and provider/model/prompt metadata when saving
  analysis records. No persistence or automatic knowledge/lifecycle acceptance is added.
- Offline evaluation contracts and optional live evaluations cover the ten Milestone 2
  scenarios. Passing schema tests does not establish semantic reliability or factual truth.
