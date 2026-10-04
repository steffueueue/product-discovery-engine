# ADR 0007: separate implementation, outcome achievement and causal learning

Status: accepted for Milestone 7.

## Context

Milestone 6 ends at a human authorization to hand off an exact DeliverySpec. That decision
says nothing about actual work, release, exposure or outcome. Treating a launch followed
by a metric improvement as success would also conflate target achievement with causality.
Negative, partial and inconclusive results are valuable learning and must retain the
original selection reasons, authorized specification and historical discovery evidence.

## Decision

Model implementation completion, outcome achievement and causal learning separately.

- Immutable ImplementationRecord snapshots bind the exact authorization/hypothesis/
  selection/spec/version and preserve actual delivery, deviations and accountability.
- Optional ReleaseObservation represents a supplied external fact. Completion does not
  imply deployment everywhere; unknown exposure remains unknown.
- Versioned OutcomeMeasurementPlan and explicit metric/baseline/target definitions precede
  interpretation where possible. Post-hoc changes retain old criteria and are marked.
- Immutable OutcomeObservation is scoped evidence. Deterministic per-metric comparison
  evaluates targets without averaging metrics or producing an arbitrary success score.
- Separate human CausalInterpretation retains design, scoped evidence, existing quality
  concepts, confounders and limitations. Before/after improvement cannot yield SUPPORTED.
- Outcome evidence appends knowledge with full provenance; it never rewrites old evidence
  or deletes failed initiatives. Existing quality and knowledge services remain authoritative.
- Dedicated audited lifecycle operations consume actual completion, explicit plans and
  exact human reviews. Closed means reviewed episode, not hypothesis proven correct.
- Follow-up recommendations and links are explicit human operations. They execute no
  rollback, deployment, new hypothesis, ticket or roadmap action automatically.

All business rules remain pure domain/policy code. No new AI decision provider is needed.
`config/outcome-measurement.v1.toml` supplies versioned window/closure policy. Paid model
verification remains deferred; normal CI is complete without credentials.

## Consequences

The v0.1 functional lifecycle is now complete and failed/inconclusive outcomes remain
reconstructable. Human ownership is mandatory at delivery completion, causal review and
final closure. Missing targets/baselines/exposure stay visible. Controlled causal support
uses conservative structural requirements and existing evidence-quality concepts, not
an invented evidence hierarchy or probability.

Callers must retain full snapshots, sources and audits and supply actual latest history.
A database, authenticated roles, source verification, atomic transactions, normalized
storage/performance, analytics connectors and product UI are later hardening work.
Large nested snapshots impose storage and validation costs; no production scale claim is
made. Metric meaning and experimental validity still need accountable semantic review.
