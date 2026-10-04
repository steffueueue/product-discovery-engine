# Portfolio walkthrough

Product Discovery Engine turns messy product signals into traceable learning,
accountable delivery decisions and measured outcomes. This walkthrough is for hiring
managers, product managers, TPMs and product engineering leaders.

## 1. The product problem

A customer complaint, an interview finding, an analytics trend and a stakeholder request
can all point toward the same initiative without establishing the same claim. Teams can
lose those distinctions as a narrative becomes a roadmap decision and a delivery brief.
AI can accelerate that process while making unsupported certainty sound convincing.

The product preserves the chain: original input, scoped evidence, assumptions, validation,
decision rationale, accountable reviewer, intended versus actual scope and observed result.
The question is whether a team can explain its decision and learn from what followed.

## 2. Design principles

Unknown is a valid knowledge state. Evidence keeps its source, scope, population and
limitations. Contradictions remain visible even when supporting evidence is plentiful.
An important learning question can be a poor delivery candidate. Every consequential
transition keeps its policy basis, exact version and accountable actor.

**AI interprets and drafts. Deterministic code governs policy. Humans remain accountable.**

## 3. End-to-end lifecycle

A signal becomes a structured hypothesis with distinct facts, evidence, assumptions,
inferences and unknowns. Evidence assessment and targeted validation expose what still
needs learning. The **Discovery Gate** checks configured knowledge conditions before
human promotion to delivery candidacy.

Human **delivery selection** records the choice and rationale. A **DeliverySpec** is a
separate versioned delivery specification; drafting, completeness, clarification and
human review precede the **Delivery Gate**. A pass enables a separate human implementation
handoff. Neither gate executes work.

An **implementation record** captures supplied actual scope and deviations. A versioned
measurement plan defines metrics, baselines, targets and windows. Deterministic target
comparison stays separate from human causal interpretation. New evidence returns to
discovery; human review and dedicated closure end the episode.

See the [lifecycle and architecture diagrams](architecture/portfolio-architecture.md).
This is a representative route; parking, rejection and further validation are also possible.

## 4. Search relevance case walkthrough

### Signal and hypothesis

Customers struggle to find relevant products. The working problem is product-discovery
friction. The stronger explanation, “relevance is the principal cause of abandonment,”
is recorded as a high-impact, uncertain assumption. Price remains a competing explanation.
The executable scenario starts with a supplied structured hypothesis linked to an original
submission ID; it does not ingest a live customer interview.

### Evidence and discovery

Synthetic bounded observations support problem existence and the studied segment, without
claiming prevalence across all customers or establishing a causal mechanism. An offline
Challenge Mode proposal flags the relevance/price ambiguity; a human independently reviews it.

The initial readiness conditions block progression. High-impact uncertainty identifies the
causal assumption as a learning priority. A targeted comparison returns a contradictory
validation result. The candidate is reframed around the observed problem, retaining the
refuted assumption, evidence and human review. The Discovery Gate can pass for that bounded
candidate without recommending a build or choosing a solution.

### Selection and delivery

A human chooses catalogue-search scope and records why. The primary demo uses manual,
source-backed and human-decision specification items. Interface and analytics details
initially remain unknown. The interface gap blocks handoff; the analytics gap remains
explicitly nonblocking under the supplied scope/policy.

An owned clarification supplies the existing interface contract. Human resolution creates
an immutable second specification version, preserving the first. Exact review, sufficient
configured completeness, Delivery Gate pass and a separate human authorization permit handoff.
Replacement of ranking architecture is an explicit non-goal.

The optional drafting route is demonstrated separately in
[the offline proposal example](../examples/delivery_specification.py): a proposed “Use
vector embeddings” requirement is rejected because no selected technical solution supports
it. Generated wording never silently chooses the architecture.

### Implementation and outcome

The supplied implementation record narrows delivery to signed-in catalogue users. That
deviation does not rewrite the original specification. Completion leaves actual production
exposure unverified; the example deploys no software and collects no external analytics.

The synthetic plan compares complete 14-day windows for the same study cohort:

| Metric | Baseline | Observation | Intended target | Evaluation |
| --- | --- | --- | --- | --- |
| Primary: search success | 60% | 74% | At least 70% | MET |
| Secondary: abandonment | 30% | 30% | Decrease from baseline | NOT_MET |
| Guardrail: p95 search latency | 180 ms | 290 ms | At most 250 ms | NOT_MET |

The outcome is **MIXED**. Before/after observations have no randomized control and exposure
is unverified, so the human causal interpretation remains **INSUFFICIENT_EVIDENCE**.
A met primary target cannot erase unchanged abandonment or a latency regression.

Three evidence items append to discovery knowledge with metric, observation, plan,
implementation and specification provenance. A human review acknowledges limitations,
records follow-up learning and explicitly links a supplied new hypothesis. Closure ends
this reviewed episode; it proves neither the hypothesis nor the intervention correct.

Run the case using the [README quickstart](../README.md#quickstart).

## 5. Where AI is used

Replaceable providers support structured signal interpretation, Challenge Mode and
specification drafting. Outputs retain input/output and provider, model and prompt
provenance. AI may expose alternatives and suggest wording; review and deterministic
reference checks constrain how it can be consumed.

Offline fixtures and synthetic providers verify contracts without paid calls. Live model
semantics remain [unverified and deferred](evals/deferred-live-verification.md).

## 6. Where deterministic policy is used

Versioned TOML policies drive evidence quality/freshness, source independence, assumption
risk, learning priority, readiness, gates, specification completeness and target comparison.
Explicit lifecycle and version checks prevent stale reviews or generic status changes from
bypassing controlled transitions. There is no composite weighted product-success score.

## 7. Where humans remain accountable

Humans supply evidence-review bases, assess contradiction/challenge dispositions, select
work, accept or reject proposals, resolve clarification, review specifications and authorize
handoff. They record delivery reality, interpret causality, review outcomes and close the
episode. Discovery overrides are explicit and narrowly configured; the Delivery Gate has
no override workflow in v0.1. Actor records are supplied identities, without authentication.

## 8. Key architectural decisions

| Decision | Product consequence |
| --- | --- |
| [Pure domain and immutable snapshots](decisions/0001-domain-foundation.md) | Historical knowledge and matching audits remain inspectable. |
| [Separate learning, readiness and Discovery Gate](decisions/0004-discovery-decisioning.md) | Important uncertainty cannot masquerade as readiness or portfolio value. |
| [Reviewed proposals before authoritative specs](decisions/0005-reviewed-delivery-specification-proposals.md) | AI assistance retains provenance and human acceptance. |
| [Separate completeness, review, gate and handoff](decisions/0006-separate-specification-and-delivery-authority.md) | Text presence does not authorize implementation. |
| [Separate completion, outcomes and causal learning](decisions/0007-separate-implementation-outcomes-and-causal-learning.md) | A launch or met target cannot declare causal success. |

Full records, predecessor snapshots and source artifacts must be retained together.
Audit metadata alone cannot reconstruct material values. This favors explicit traceability
at the cost of larger nested records and expensive validation.

## 9. What the project demonstrates

The project demonstrates product judgment translated into enforceable engineering
contracts: epistemic discipline, accountable workflow design, AI authority boundaries and
an outcome loop that retains failed learning. A modular monolith, typed records, strict
mypy, Ruff and deterministic tests keep these decisions reviewable.

Development used a spec-driven, AI-assisted workflow: product constraints and acceptance
contracts preceded agent implementation, and increments were reviewed and verified before
merge. The [ADRs](README.md#architectural-decisions) expose the consequential tradeoffs.

## 10. Known limitations and productionization boundary

The lifecycle is implemented as models, policies and application operations. There is no
production database, authenticated RBAC, API/web UI, analytics connector or automated
deployment. Callers supply current state; immutable snapshots cannot detect withheld changes
or provide atomic transactions and concurrency control. Source authenticity, semantic
adequacy and experimental validity remain accountable human judgments.

Live provider quality is unverified. Production storage, access controls, retention,
observability, integrations and performance work require separate scope. See the
[release-note draft](releases/v0.1.0.md) for the public v0.1 boundary.
