# Product specification v0.1

Status: source of truth for Milestones 0–7; v0.1 functional lifecycle complete.

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


## Milestone 3 evidence-and-validation contract

Milestone 3 is authorized independently of the historical scope statements above.
Milestone 4 and later workflows remain deferred. The implementation contract and initial
rubric are detailed in [evidence and validation](../architecture/evidence-validation.md)
and [ADR 0003](../decisions/0003-evidence-validation.md).

- Evaluate directness, reliability, coverage, recency and independence using explicit
  ordinal policy; preserve rationale, target, policy version, timestamp and audit.
  Quantity never supplies a quality bonus. Unknown inputs remain unknown.
- Bind every assessment to an explicit claim/assumption, target and population.
  Existence observations never establish frequency, reach, economic impact, causality
  or solution suitability. Nonrepresentative population claims stay low in coverage.
- Preserve CURRENT, REVIEW_DUE, STALE and INVALIDATED with configured review intervals,
  applicability/review metadata, reasons and immutable history. Age does not make a
  historical observation false. Preserve the existing Milestone 1 freshness API.
- Record underlying origins; group shared-family and overlapping provenance transitively.
  Count meaningful independent source/method diversity separately from quality.
  Both support and contradiction remain visible; mixed evidence has no forced winner.
- Assess assumption risk from decision impact and unresolved uncertainty through a
  versioned ordinal matrix, preserving both evidence directions and explicit gaps.
- Store owned validation activities with constrained methods, inputs, predefined
  success/failure criteria, ordinal information gain, cost/speed, dependencies and
  explicit PLANNED → READY → RUNNING → COMPLETED lifecycle plus cancellation.
  Reject invalid transitions; audit creation, start, completion and cancellation.
- Results are SUPPORTED, PARTIALLY_SUPPORTED, INCONCLUSIVE or CONTRADICTED, generating
  new evidence without overwriting history. Retain refuted assumptions. Preserve old/new
  criteria and actor/reason/version audits, explicitly identifying post-hoc changes.
- Challenge Mode is structured, AI-labeled advisory interpretation searching for
  disconfirmation, biases, alternatives and overlooked risks. Keep input/output,
  provider/model/prompt provenance and completion audit. AI never determines quality,
  freshness, triangulation, accepted evidence, validation lifecycle or final decisions.
- Configuration is validated independently of prompts. Offline unit/evaluation tests
  need no credentials; live evaluations extend the existing opt-in workflow.
- Discovery Priority, Delivery Readiness, Discovery Gate, portfolio prioritization,
  selection/delivery, spec generation, implementation and outcomes remain unimplemented.


## Milestone 4 – Discovery Decisioning contract

Milestone 4 is authorized independently of the historical Milestone 0–3 scope statements
above. This contract supersedes their Milestone 4 deferral; their historical contracts
remain intact. Milestone 5 and later workflows remain deferred. See
[discovery decisioning](../architecture/discovery-decisioning.md) and
[ADR 0004](../decisions/0004-discovery-decisioning.md) for implemented semantics.

- **Discovery Priority** asks what to learn next. Use explicit monotonic ordinal
  impact/uncertainty rules, preserving assumption-risk, gaps, contradictions, freshness,
  validation, gain, cost, speed and dependencies. Do not rank initiatives or compute one
  numeric product score. Critical expensive learning is not demoted by cost. Preserve
  within-category ties; unknown targets are outside ordinal ordering. Grouping is limited
  to one hypothesis snapshot/policy. Incomplete linked validation context is explicit.
- Monitor active validation instead of proposing duplicate tests. Keep blocked learning
  visible. Inconclusive learning remains open; refutation/contradiction may require
  reframing rather than confirmation seeking. Missing values never become optimistic defaults.
- **Delivery Readiness** separately assesses knowledge maturity with UNKNOWN, INSUFFICIENT,
  PARTIAL, SUFFICIENT and NOT_APPLICABLE dimensions, resulting in NOT_READY, NEEDS_REVIEW
  or READY. Required unknown/insufficient dimensions block; required partials require review.
- Preserve exact evidence target, claim/assumption and population boundaries. Problem
  existence cannot imply reach, viability, causal mechanism, business impact or solution
  effectiveness. Required quality/freshness/independence are policy-driven. Count gives no
  quality bonus; same-origin reports do not establish independent triangulation. Filtering
  old/weak evidence cannot erase known source overlap. Historical evidence remains visible.
- V1 requires problem/segment support, outcome clarity, quality/freshness/triangulation,
  assumption/contradiction/validation review, Challenge Mode, owner and explicit strategy.
  Reach, viability, causal mechanism and business impact are separately evaluated optional
  targets. Solution effectiveness applies only when a solution exists; absence is
  NOT_APPLICABLE, while an unknown solution remains UNKNOWN.
- Unresolved high-impact/high-uncertainty or high-impact refuted assumptions need resolution
  or explicit configured human treatment tied to the exact retained risk assessment.
  Low-impact uncertainty need not block. Critical assumptions require defensible completed
  validation when configured; explicitly required activities preserve criteria-bound results.
  Invalidated validation dependencies cannot satisfy readiness; v1 requires current dependencies.
- Contradictions remain visible with explicit human classification: healthy mixed evidence
  requires review, unresolved material/critical-invalidating contradiction blocks, and
  investigated acceptance may satisfy configured conditions. No supporting majority wins.
- Challenge Mode remains advisory. Application orchestration checks its actual retained
  record against current scoped knowledge and problem statement. Required human review
  independently records severity/disposition for every item. AI severity does not determine
  readiness. Serious unresolved human-reviewed challenges block, unknown human severity
  blocks, and reviewed acceptance/addressing remains explicit.
- Strategy requires actual versioned configuration and a known objective, with explicit
  human acknowledgement where configured. A reference alone or
  `insufficient_strategy_context` never passes. No AI alignment substitutes for this review.
- **Discovery Gate** evaluates configured conditions as PASSED, FAILED, UNKNOWN or
  REVIEW_REQUIRED and returns PASSED, BLOCKED or NEEDS_REVIEW with explicit reasons.
  Missing readiness and any unknown required condition prevent ordinary PASS. Retain
  full hypothesis/readiness/policy snapshots, references, version, time and conditions.
- Gate invariants require the exact material hypothesis, complete current policy,
  applicable assessment, and an `evidence_updated` source lifecycle state. V1 gates expire
  within 24 hours from readiness and before the next UTC day. Outdated/mismatched policies,
  stale gates, different hypotheses and newer material versions cannot authorize promotion.
- Normal candidacy movement uses the explicit application promotion operation, consuming
  current hypothesis, ordinary gate PASS, active policy, human actor and timestamp. Retain
  before/after snapshots and separate lifecycle/decision audits. Generic ordinary status
  transitions and deserialization cannot bypass the gate. Promotion increments version
  and stops at `candidate_for_delivery_prioritization`.
- Human override is a separate retained record with actor/ownership, reason, timestamp,
  original gate/result, policy, explicitly overridden conditions, candidacy action and audit.
  It never changes the original gate to PASSED. V1 permits only known readiness/challenge/
  contradiction concerns; unknowns, technical prerequisites and expired gates cannot be
  bypassed. Override promotion explicitly consumes the record and uses its human actor.
- Validate the versioned TOML bundle independently of AI: reject unknown dimensions,
  invalid ordinals/targets, duplicate/incomplete rules, impossible method/freshness
  requirements, missing versions and inconsistent gate/readiness configuration.
- Audit every priority/readiness assessment, gate evaluation/outcome, override and candidacy
  promotion. Results are immutable, recomputable snapshots. Retain source/knowledge,
  validation and actual advisory records alongside references; no persistence is supplied.
- Current-state checks after external evidence invalidation, validation or review changes
  remain caller responsibilities until an atomic persistence boundary exists. A snapshot
  and expiry check cannot discover changes withheld from the operation.
- All Milestone 4 execution and verification is credential-free. Add no AI decision agent
  or new live-model behavior/tests; keep existing 18 opt-in live evaluations unchanged and
  intentionally deferred. No paid API call is authorized by this milestone.
- A gate pass is not a build recommendation. Portfolio ranking, ROI/RICE/WSJF, automatic
  `selected_for_delivery`, DeliverySpec/spec drafting/clarification/completeness, Delivery
  Gate, implementation/outcomes, deployment UI and persistence backend remain deferred.


## Milestone 5 – Delivery Selection & Specification Drafting contract

Milestone 5 is authorized independently of the historical Milestone 0–4 scope statements.
Their contracts remain preserved; this section supersedes their delivery-selection/spec-
drafting deferral only. Milestone 6 and later functionality remains deferred. See
[delivery specification architecture](../architecture/delivery-specification.md) and
[ADR 0005](../decisions/0005-reviewed-delivery-specification-proposals.md).

- Discovery Gate PASS establishes consideration/candidacy, never a build decision.
  Explicit DeliverySelection requires an accountable human, nonempty rationale, exact
  current candidacy snapshot and retained candidacy/discovery decision. No AI, score,
  ranking or generic lifecycle transition may select delivery work.
- Selection produces `selected_for_delivery`, increments the hypothesis version once,
  changes only status/update time, and retains immutable before/after snapshots, strategy,
  optional decision context, human actor/time/reason and separate decision/lifecycle audits.
  Stale versions, wrong hypotheses, duplicate/noncandidate selection and tampering fail.
- DeliverySpec is a first-class versioned immutable DRAFT artifact, separate from the
  discovery hypothesis/history. It binds the exact selected hypothesis/version and
  DeliverySelection, creation actor/time, schema version, predecessor and last material
  revision actor/time/reason/changed item IDs. Incomplete or empty drafts are valid.
- Structured typed items cover title, summary, problem, segment, outcome, scope, non-goals,
  solution intent, functional/business/quality/data/analytics requirements, given/when/then
  acceptance criteria with individually traceable clauses, interfaces, dependencies,
  constraints, risks and open questions. No complete-section requirement or generic content dictionary is introduced.
- Every material statement distinguishes SOURCE_BACKED, HUMAN_DECISION, AI_PROPOSAL or
  UNKNOWN origin. Stable references identify supplied hypotheses/fields, claims, evidence,
  assumptions, results, strategy, selection, human decisions, constraints and source artifacts.
  Invented, cross-hypothesis and omitted-context references are rejected.
- Draft context retains exact selection/discovery history, accepted claim snapshots,
  assumptions, evidence including contradictions, validation, readiness/gate, human-reviewed
  Challenge Mode dispositions, strategy and explicit human constraints/system information.
  Providers cannot invent external context or treat linked-but-unsupplied claim IDs as sources.
- Exact source-backed restatements preserve knowledge scope. Discovery evidence never
  automatically becomes a solution requirement. Solution-facing source-backed items require
  explicit solution intent, constraints or system facts; human decisions retain their own
  origin. Human acceptance never retroactively turns an AI proposal into evidence.
- Optional AI drafting returns a schema-validated, clearly generated proposal linked to
  exact context and actual provider/model/prompt version. It does not mutate authoritative
  specs. Independent human review records acceptance/rejection, actor/time and rationale
  for every item. Separate human materialization creates/revises the authoritative draft.
- Missing solution, endpoint/schema, performance threshold or policy remains explicitly
  unknown. AI cannot fill absent solution intent. Generated numeric wording and endpoint-
  like interface details need explicit sourced/human content rather than fabricated values.
  Proposed criteria/quality considerations retain their proposed status and review trail.
  These are conservative structural/lexical guards, not proof of general semantic truth.
- Material revision increments exactly once, rejects no-ops, requires human actor/reason,
  preserves original creation metadata and previous proposal/decision provenance, and
  retains full before/after snapshots. Reworded/reclassified statements use new item IDs.
  Supersession links old/new versions through an immutable audit; old snapshots stay intact.
- Audit selection, lifecycle promotion, explicit context input, draft generation, proposal
  review, each acceptance/rejection, creation, human requirement/constraint addition, material revision
  and supersession. Callers retain full records; no persistence or event sourcing is supplied.
- Domain/application/provider boundaries remain intact. The optional OpenAI adapter uses
  existing configuration, strict structured output, `store=False`, validated results,
  sanitized errors and versioned interpretation prompts. Business rules remain in code.
- Normal development and CI remain credential-free. Offline fakes, ten A–J golden cases
  and mocked SDK tests verify contracts; paid live verification and all existing live tests
  remain intentionally deferred. No paid model call or Live AI evals workflow is run, and
  no semantic pass is claimed. Extend the deferred checklist for drafting behavior.
- No portfolio ranking/allocation, automatic selection, implementation/code-generation
  workflow, production deployment, outcome measurement, feedback loop, persistence backend
  or deployment UI is added. Current-state and concurrency checks remain caller responsibilities.
- **Milestone 6 deferrals:** completeness scoring/gate; blocking/nonblocking gap classification;
  targeted clarification questions/ownership; question/answer resolution lifecycle;
  NEEDS_CLARIFICATION/READY_FOR_REVIEW behavior based on completeness; READY_FOR_DELIVERY;
  Delivery Gate; implementation authorization. Future enum values are representational only:
  Milestone 5 constructors/operations authorize DRAFT only.


## Milestone 6 – Spec Completeness, Clarification & Delivery Gate contract

Milestone 6 is authorized independently of historical Milestone 0–5 scope statements.
Their historical contracts remain intact. This contract supersedes their Milestone 6
deferral. See [architecture](../architecture/spec-completeness-delivery-gate.md) and
[ADR 0006](../decisions/0006-separate-specification-and-delivery-authority.md).

- Completeness, gaps, clarification, accountable SpecReview, delivery readiness, Delivery
  Gate and ImplementationAuthorization are separate decisions. Completeness cannot
  authorize implementation, and AI cannot own these authoritative decisions.
- Use deterministic qualitative dimension states UNKNOWN, INSUFFICIENT, PARTIAL,
  SUFFICIENT and NOT_APPLICABLE, with INCOMPLETE, NEEDS_REVIEW and COMPLETE overall states.
  Never use percentages, a weighted completeness score or LLM-authoritative assessments.
- Validate versioned policy covering intent, traceable problem, segment, outcome, scope,
  non-goals, applicable solution intent, functional/business/acceptance/quality information,
  interfaces, data, analytics, dependencies, constraints, risks, open questions, traceability
  and ownership. Required/optional treatment, applicability, minimum states, gap rules,
  targeted question wording, gate conditions and expiry live outside AI prompts.
- Applicability depends on supplied hypothesis or explicit accountable human context.
  Non-applicable dimensions do not fail. Missing applicability remains unknown. Never
  invent integrations, thresholds, compliance obligations or ownership.
- First-class SpecGap records retain exact spec/version, dimension/type, affected items,
  statement, rationale, source/basis, detector/time, classification/status and immutable
  review/resolution references. BLOCKING, NON_BLOCKING and REVIEW_REQUIRED are explicit;
  invalid/unknown classifications never silently become non-blocking.
- Deterministic structural gaps differ from human semantic concerns. Human materialization
  and consecutive reviews retain original/current classification and audit. Structural
  absence clears through revision/reassessment. AI output alone cannot create authoritative
  gaps; optional AI gap/question generation is not introduced in v1.
- ClarificationQuestion binds an exact authoritative unresolved gap and spec version.
  Questions target required information using policy wording, inherit gap classification
  and have explicitly supplied ownership where configured. Prevent duplicate questions
  against retained supplied history. Questions do not invent facts or answer themselves.
- Immutable ClarificationAnswer retains human actor/time, actual source references,
  artifacts, limitations and a strict human-decision marker. OPEN → ANSWERED does not
  resolve the gap or mutate the spec. Explicit human resolution consumes the latest answer.
- Material answer acceptance creates v+1, retains the complete before/after change, and
  materializes that answer's exact wording/provenance into new fact/item identities.
  Reassessment must establish a sufficient authoritative state. Existing old specs stay
  unchanged. Same-version semantic resolution needs explicit reviewed gap disposition.
- Old unresolved questions/gaps cannot silently carry to incompatible versions. Detect
  stale scope, connect explicit resolution to its resulting version, or explicitly withdraw
  a question for the supplied current version. Retain all historic state.
- DRAFT and NEEDS_CLARIFICATION may reach READY_FOR_REVIEW only through current exact
  assessment; blocking gaps and required supplied unresolved clarifications prevent it.
  NEEDS_CLARIFICATION requires authoritative unresolved blocking gaps, not AI suggestions.
- SpecReview is explicit accountable HUMAN review of an exact current assessment/spec.
  Preserve APPROVED, CHANGES_REQUESTED or REVIEW_WITH_CONCERNS, all reviewed gaps, rationale,
  concerns, actor/time and audit. READY_FOR_DELIVERY requires sufficient information,
  COMPLETE assessment, no unresolved blocking/review-required gaps, required ownership and
  an exact APPROVED review without pending concerns. It only permits gate evaluation.
- Non-DRAFT spec snapshots carry validated status authority. Generic status mutation
  cannot bypass it. Material revisions reset to DRAFT. Supersession provides a validated
  terminal historical view linked to the exact replacement without mutating old snapshots.
- Delivery Gate operates on the exact current selected hypothesis, DeliverySelection,
  spec/version, current assessment/review, gap/clarification state and full active policy.
  Do not rerun Discovery Priority or portfolio selection. Conditions include ready status,
  identity/linkage, approval, completeness, blocking gaps, clarification resolution,
  acceptance, applicable interface/data/quality/dependency information, traceability,
  owner, policy agreement and freshness. Required UNKNOWN prevents ordinary PASS.
- Retain PASSED/BLOCKED/NEEDS_REVIEW with evaluated/passed/failed/unknown/review conditions,
  explanations, policy/time, expiry and audits. V1 validity is at most 24 hours from
  assessment. Wrong identity/version, outdated records, changed full policy, unresolved
  required clarification and expired gates cannot authorize handoff.
- ImplementationAuthorization is a separate explicit accountable HUMAN record after
  ordinary gate PASS, retaining exact spec/version, hypothesis/selection, gate, current
  input packet/policy, actor/time, rationale, conditions and audit. V1 supports no overrides.
  Handoff neither changes the hypothesis to implemented nor proves implementation occurred.
- Audit assessment, gap detection/review, question creation/ownership/answers/resolution/
  withdrawal, controlled states, review, supersession, gate evaluation/outcomes and handoff.
  Retain immutable full records; no persistence or role-authority system is supplied.
- Services require complete supplied current histories. Snapshot validation and expiry
  cannot discover withheld external changes or replace future atomic latest-state checks.
- Complete offline tests/quality/package checks and existing AI contracts require no key.
  The search example stops after owned interface clarification, immutable v2, exact human
  review, gate PASS and explicit handoff. Paid API calls/live evaluations remain deferred;
  no new AI provider, prompt or live-semantic checks are added in this milestone.
- Milestone 7 remains deferred: actual implementation records, production code-generation
  execution, deployment/completion, implemented transition from authorization, outcome
  metrics, baseline/target/actual comparison, measurement windows, outcome evaluation,
  discovery feedback, measuring_outcome/closed execution and production persistence/UI.


## Milestone 7 – Implementation Outcome & Feedback Loop contract

Milestone 7 is authorized independently of the historical Milestone 0–6 scope statements.
Their contracts remain preserved. This contract supersedes their implementation/outcome/
feedback deferrals and completes the v0.1 functional lifecycle. See
[implementation and outcome architecture](../architecture/implementation-outcome-feedback.md)
and [ADR 0007](../decisions/0007-separate-implementation-outcomes-and-causal-learning.md).

- ImplementationAuthorization permits exact specification handoff only. Explicit immutable
  ImplementationRecord snapshots represent supplied external reality, not software execution.
  Planning/start require valid exact hypothesis/selection/spec-version/authorization bindings,
  accountable owner/actor/time and audit. Handoff never automatically starts or completes work.
- PLANNED → IN_PROGRESS/CANCELLED and IN_PROGRESS → COMPLETED/CANCELLED are explicit operations.
  Completion requires time, actual delivered scope, item-level accounting, omissions/deviations,
  human actor and limitations. Artifact/release references may remain unknown. Terminal records
  cannot silently restart; original snapshots and authorized DeliverySpec remain unchanged.
- Deviations identify omitted/changed/reduced/additional/interface-changed behavior and exact
  original spec items where applicable. Deviations are retained facts, not automatic failure.
  Additional behavior never silently rewrites the intended spec.
- Completion is not deployment. Optional ReleaseObservation retains supplied environment,
  audience, release time, rollout, version, provenance and accountable actor. Partial exposure
  and limitations remain visible; neither exposure nor release is inferred from completion.
- Only the dedicated completed-record operation may move selected_for_delivery → implemented.
  It consumes the exact current authorized hypothesis and exact completed implementation and
  retains before/after snapshots, consecutive version, human actor, rationale and audit.
- OutcomeMeasurementPlan binds completed implementation, exact implemented hypothesis and
  original desired-outcome field/version. Retain source/method, owner, metric definitions,
  baseline/target definitions, measurement windows, known confounders/risks, version and audit.
- Metric definitions require name, description, unit, population, aggregation/denominator,
  source, direction, baseline period, outcome period and exact feedback claim/assumption scope.
  Primary/secondary/guardrail roles are explicit. Metric names alone are insufficient.
- Baselines retain known value or explicit unknown reason, period/population/source/method,
  collection time, limitations and provenance. Numeric comparator, threshold, inclusive range,
  directional and qualitative-state targets are explicit; no predefined target remains absent.
  Do not turn qualitative goals into fabricated numbers or invent missing baselines.
- Plans should predate observations. Revisions preserve full old definitions, new version,
  actor/time/reason and target audit; initial late plans and changes after measurement begins
  are explicitly post-hoc. Baseline corrections use new IDs with old snapshots retained.
  Older observations cannot silently be evaluated against rewritten criteria.
- Immutable observations retain exact implementation/plan-version/metric/window/population,
  actual value/state or unknown reason, source, method, collection time, limitations/provenance.
  Wrong bindings, sources, populations, windows and future collection fail. An observation
  is not a causal conclusion.
- Dedicated implemented → measuring_outcome requires an exact completed implementation,
  explicit plan and current implemented hypothesis. Elapsed time alone cannot enter the state.
- Deterministic evaluations preserve metric/baseline/target/actual/window, MET/PARTIALLY_MET/
  NOT_MET/INCONCLUSIVE/NOT_EVALUABLE, explanation, missing information, limitations, time and
  policy. Partial windows are not extrapolated. Multiple observations remain visible; missing
  numeric baseline prevents directional comparison, but absolute targets may still evaluate.
- Target met does not imply causality. CausalInterpretation separately retains exact claim/
  assumption scope, supporting/contradicting evidence, existing Milestone 3 quality reviews,
  design, assignment/instrumentation/exposure basis, confounders, limitations and human review.
  Before/after sequence cannot produce SUPPORTED. Controlled designs need explicit reviewed
  evidence and cannot conceal unresolved contradictions or fabricate confidence percentages.
- OutcomeAssessment qualitatively preserves every metric and all limitations. Mixed or negative
  guardrail/business metrics cannot disappear behind primary improvement. No weighted success
  percentage, arbitrary product score or autonomous product-success decision is introduced.
- Human materialization appends new Evidence with actual values, source, methodology/limitations,
  rationale and provenance to implementation/selection/authorization/spec-version/plan-version/
  metric/observation. Evidence targets exactly the metric's claim/assumption/population; unrelated
  claims cannot be validated. Causal-mechanism support requires separate causal authority.
  Unknown actual values retain missing information rather than fabricated directional evidence.
- Existing EvidenceValidationService evaluates outcome evidence with the established quality,
  freshness and source-independence concepts. New knowledge retains old evidence. Contradictions,
  unchanged business metrics, failed outcomes, selection reasons and authorized specs remain
  historically reconstructable. Linking evidence does not automatically validate an assumption.
- OutcomeReview requires a human accountable reviewer, current measuring hypothesis, full plan/
  metric evaluations/causal interpretations/evidence, time, disposition through assessment,
  rationale, visible acknowledged limitations, unresolved questions and explicit next actions.
  AI cannot be the final reviewer. Recommendations execute no action automatically.
- FollowUpLearning explicitly links a supplied distinct hypothesis and original outcome evidence
  to the review with provenance and human audit. It does not duplicate/create hypotheses or
  generate roadmap items automatically.
- Dedicated measuring_outcome → closed requires exact current human review, completed/acceptable
  measurement, active policy, accountable actor, closure rationale and audit. Generic lifecycle
  transitions and generic STATUS_CHANGED histories reject all three controlled outcome edges.
  Wrong/stale hypothesis/implementation/plan/review/policy references fail.
- Versioned outcome policy requires full measurement windows by default and explicitly permits
  human-reviewed inconclusive closure. Policy can forbid INCONCLUSIVE/NOT_EVALUABLE closure;
  missing-data limitations always remain visible. Closed means reviewed lifecycle episode,
  not correctness, target achievement or causal proof.
- Audit planning/start/completion/cancellation/deviations, release observations, implemented,
  plan/baseline/target creation/revision, observations, measuring_outcome, evaluation, causal
  interpretation, outcome evidence, human review, follow-up links and closure. Retain full
  immutable snapshots/audits/sources together; event metadata alone cannot reconstruct values.
- Core behavior and verification remain deterministic and credential-free. The offline search
  scenario preserves primary improvement, unchanged abandonment and a latency regression as
  MIXED, leaves causality unresolved, appends evidence, records human review/follow-up and closes.
  No new AI provider/prompt/live cases are added; paid verification remains intentionally deferred.
- Production persistence, transactions/RBAC, web UI, deployment execution, external analytics,
  automated Jira/roadmap creation, rollback, multi-agent architecture and portfolio optimization
  remain post-v0.1 hardening/productization. Supplied current snapshots cannot detect withheld
  external changes; authentic source/human identity and semantic review are caller responsibilities.
