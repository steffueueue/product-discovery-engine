# AI, deterministic policy and human accountability

**AI interprets and drafts. Deterministic code governs policy. Humans remain accountable.**
These are implemented authority boundaries, not an autonomous-agent roadmap. The
[visual architecture](portfolio-architecture.md#b-authority-boundary) shows the handoffs.

## AI may interpret, classify, challenge, draft and propose

| Capability | Reviewable output | Authority limit |
| --- | --- | --- |
| Signal interpretation | Structured problem, segment, outcome, claims, assumptions and unknowns | Cannot promote an assertion into a fact or mutate lifecycle state. |
| Challenge Mode | Counterarguments, competing explanations and proposed validation | AI severity is advisory; humans independently review dispositions. |
| Specification drafting | Typed, context-bound proposed wording | Cannot select work, accept its own items, declare readiness or authorize implementation. |

Application protocols separate these capabilities from provider implementations. Inputs,
outputs and provider/model/prompt metadata are retained. Code validates schema, supplied
references and grounding constraints; those checks do not establish arbitrary semantic
truth. Accepted AI-origin wording keeps its origin and proposal/review history.

Representative entry points: [discovery provider protocol](../../src/product_discovery_engine/application/discovery_analysis.py),
[specification service](../../src/product_discovery_engine/application/delivery_specification.py),
[OpenAI adapter](../../src/product_discovery_engine/infrastructure/openai_analysis.py) and
[versioned prompts](../../src/product_discovery_engine/ai/prompts.py).
Live semantics remain [unverified](../evals/deferred-live-verification.md).

## Deterministic code owns policy and integrity

- **Evidence:** configured quality/freshness, claim/population applicability, underlying-source independence and contradiction-preserving knowledge assessment.
- **Decisioning:** ordinal learning priority, qualitative Delivery Readiness and Discovery Gate conditions; no portfolio ranking or weighted magic score.
- **Delivery:** structural completeness/gap rules, clarification/state validity, Delivery Gate and exact handoff requirements.
- **Outcomes:** metric/window/plan binding, target comparison and transparent multi-metric assessment; target evaluation never assigns causal success.
- **Integrity:** valid lifecycle operations, exact versions, immutable material history and matching audit consistency.

Versioned TOML configurations are validated by typed policies. Missing required inputs
remain unknown or block progression. Human semantic inputs can be required by policy;
structural sufficiency cannot substitute for meaningful requirements or trustworthy sources.

The core checks supplied current snapshots. It cannot discover withheld external changes,
authenticate actors, persist history or provide atomic concurrency control. Callers must
retain full before/after records, sources and audits together.

## Humans own consequential judgments and decisions

Humans select delivery work with rationale, accept or reject proposed specification items,
materialize authoritative versions, supply evidence-review bases and review contradictions
and challenges. They resolve clarifications, review exact specifications, authorize handoff,
record actual implementation, interpret causality, review outcomes and authorize closure.

A Discovery Gate pass establishes candidacy for consideration. **Delivery selection remains
a separate human choice.** A Delivery Gate pass enables separate human handoff authorization;
it does not assert completion, deployment or exposure.

Overrides exist only for explicitly configured Discovery Gate conditions. They retain the
original nonpassing gate, reason, actor and separate audit; they cannot bypass unknown
required inputs, technical prerequisites or expiry. **The v0.1 Delivery Gate has no override
workflow.** No generic override flag grants unrestricted transition authority.

Causal interpretation is a human assertion constrained by study design, scoped evidence
and quality requirements. Before/after metric improvement cannot yield supported causality.
Final closure requires exact current human review and the active outcome policy. It ends
an episode while preserving unresolved questions; it does not prove correctness.

Supplied HUMAN actor records express accountability without implementing authenticated roles.

## Intentionally rejected architecture choices

| Rejected choice | Why | Decision record |
| --- | --- | --- |
| LLM decides readiness or promotes lifecycle | Interpretation cannot certify policy conditions or current-state integrity. | [ADR 0004](../decisions/0004-discovery-decisioning.md) |
| LLM auto-selects the roadmap item | Knowledge maturity does not settle opportunity cost or human delivery intent. | [ADR 0005](../decisions/0005-reviewed-delivery-specification-proposals.md) |
| One weighted magic score for priority/readiness/completeness | Favorable dimensions would hide blocking unknowns and invent precision. | [ADR 0004](../decisions/0004-discovery-decisioning.md), [ADR 0006](../decisions/0006-separate-specification-and-delivery-authority.md) |
| AI-generated requirement becomes authoritative automatically | Generation is not acceptance; origin and individual dispositions must survive. | [ADR 0005](../decisions/0005-reviewed-delivery-specification-proposals.md) |
| Target met means causal success | Descriptive achievement cannot resolve confounders or establish attribution. | [ADR 0007](../decisions/0007-separate-implementation-outcomes-and-causal-learning.md) |
| Generic status setter bypasses a gate/review | A status label is not an authorization receipt tied to exact content and policy. | [ADR 0006](../decisions/0006-separate-specification-and-delivery-authority.md), [ADR 0007](../decisions/0007-separate-implementation-outcomes-and-causal-learning.md) |

In the search case, the stronger relevance/abandonment assumption is contradicted, yet a
bounded problem-focused candidate can proceed after human review. Later search success
meets its target while abandonment and latency do not. Policy retains the mixed pattern;
humans retain unresolved causal learning. See the [case walkthrough](../portfolio-walkthrough.md#4-search-relevance-case-walkthrough).
