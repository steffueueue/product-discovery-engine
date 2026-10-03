# ADR 0004: separate learning priority, readiness and discovery gating

Status: accepted for Milestone 4.

## Context

The evidence/validation layer preserves claim targets, unknowns, source dependence,
freshness, competing explanations and ordinal risk. A consequential uncertain assumption
can be the best next learning target precisely because the hypothesis is not ready.
Conversely, mature knowledge says nothing about an initiative's relative portfolio value.
Human accountability must remain visible when moving toward delivery prioritization.

## Decision

Implement three separate deterministic, versioned policies outside AI prompts:

1. Discovery Priority groups decision-relevant learning targets into ordinal categories
   using explicit impact/uncertainty rules. Preserve ties; unknown is outside ordinal order.
2. Delivery Readiness evaluates explicit knowledge dimensions and target-specific evidence,
   ownership, strategy and human-reviewed challenges. Missing required information blocks.
3. Discovery Gate consumes readiness and configured conditions to authorize a narrowly
   controlled transition into `candidate_for_delivery_prioritization`.

Retain immutable input/policy/result/audit snapshots with deterministic reconstruction.
Bind promotion to the exact current hypothesis, complete current policy and bounded gate
validity. Require a human actor; keep overrides separate from ordinary passes, with reason,
audit and explicit permitted conditions. Reuse Milestone 3 evidence and validation rules;
keep AI output advisory and require actual retained Challenge Mode records in application use.

## Alternatives considered

- **One composite weighted score:** rejected. Revenue, risk, uncertainty, quality and
  readiness are not interchangeable quantities. Decimal weighting invents precision,
  hides missing evidence and permits favorable dimensions to cancel blocking gaps.
  It also confuses important learning with attractive delivery work.
- **Lexicographic tie-breaking by cost/speed:** feasible later as an explicit learning
  policy, but rejected for v1. Planning context is retained and category ties stay visible;
  a cheap low-impact test must not outrank critical expensive learning.
- **AI decision agent:** rejected. Interpretation cannot own deterministic readiness,
  lifecycle authority or overrides. No new semantic behavior needs paid model verification.
- **Generic rules engine/event-sourcing backend:** rejected. Small validated policy models
  and immutable records are sufficient for this milestone; storage and authorization remain
  future application responsibilities.
- **Ungated generic status transition:** rejected. A stage edge alone cannot certify
  evidence completeness, human review, policy applicability or current snapshot identity.

## Consequences

The architecture exposes incompleteness and keeps evidence/assumptions/history inspectable.
Several learning targets can tie. Readiness can be conditional on the configured claim
and population, and a pass still needs a human transition operation. This adds more typed
records than a single score but makes review and reconstruction tractable.

Conservative source-overlap grouping and explicit contradiction treatment may delay
readiness. Human inputs, external source identity and semantic review remain trusted
assertions. Persistence must eventually save complete records and enforce current-state
checks atomically; immutable records alone do not supply transactions or authorization.

Portfolio prioritization remains deferred: delivery opportunity cost, strategic tradeoffs,
ROI, RICE/WSJF and initiative selection need a separate authorized product contract.
Milestone 5 specification drafting and every later delivery workflow remain unimplemented.
