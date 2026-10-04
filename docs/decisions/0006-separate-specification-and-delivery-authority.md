# ADR 0006: separate completeness, clarification, review, gating and handoff

Status: accepted. Date: 2026-10-04.

## Context

Milestone 5 preserves selected hypotheses, grounded specification drafts, reviewed AI
proposals and immutable material revisions. It intentionally does not establish sufficient
information, resolve unknowns, approve delivery readiness or authorize implementation.
Collapsing those decisions would turn interpretation or text presence into build authority.

## Decision

Use separate explicit immutable records and operations for qualitative completeness,
authoritative SpecGaps, owned clarification questions/answers/resolution, human SpecReview,
controlled DeliverySpec status, deterministic Delivery Gate and ImplementationAuthorization.
Keep policy in validated versioned TOML. Bind every decision to full exact material content,
version, selection, policy, human accountability and time. Preserve history and audit events.

- Reject one numeric completeness score: it hides missing mandatory information and lets
  sufficient unrelated sections compensate for blocking unknowns. Use explicit dimension
  states and policy-driven NOT_APPLICABLE instead.
- Reject AI-authoritative gap classification: semantic suggestions are interpretations,
  not deterministic policy or accountable decisions. This milestone adds human semantic
  review only; any future AI provider needs retained proposals and accepted/rejected human
  dispositions before materialization.
- ANSWERED is not RESOLVED: answers can be inadequate or contradictory. Human resolution
  must connect the latest immutable answer to the authoritative resulting state. Material
  answers need a consecutive new spec version, exact answer/provenance materialization,
  reassessment and retained original history.
- READY_FOR_DELIVERY is not Delivery Gate PASS: readiness records accountable review of
  sufficient specification content; the gate separately checks current entry conditions,
  selection linkage, clarification state, policy and expiry.
- Delivery Gate PASS is not implementation completed: it only enables a separate human
  handoff authorization. Neither operation marks the hypothesis implemented. Actual
  implementation and outcomes remain Milestone 7.

Use an immutable material body independent of workflow receipts to avoid assessment/status
cycles. Non-DRAFT snapshots require validated exact-content authority. Material revisions
reset to DRAFT and invalidate reuse of old reviews/gates. SUPERSEDED is an explicit
historical view of a retained consecutive revision; original snapshots stay unchanged.
No gate overrides or new AI gap/question providers are needed for this milestone.

## Consequences

Decisions are understandable, auditable and testable offline without paid APIs. Unknown
required conditions fail safely; optional gaps remain visible. The design requires more
explicit records than a score or boolean and duplicates some nested history. Callers must
retain complete records and provide real current state. Pure models cannot discover omitted
changes or authenticate human identities; production persistence, atomic current-version
checks, access control and retention remain future hardening requirements. Structural
checks never claim full semantic understanding or source truth.

See [architecture](../architecture/spec-completeness-delivery-gate.md) for implemented
policy, lifecycle, gates, invariants, verification and exact deferrals.
