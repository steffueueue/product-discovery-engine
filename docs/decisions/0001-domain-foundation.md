# ADR 0001: Immutable domain snapshots in a modular monolith

Status: accepted for Milestones 0–1.

Use one installable Python package with five logical boundaries. The domain uses
Pydantic v2 for validated, frozen value objects; tuples avoid mutable nested collections.
Use `AwareDatetime` specifically on timestamp fields rather than a wildcard validator
on all domain fields. Constructors revalidate nested model instances. Reference tuples
reject duplicates, and versions/age thresholds are strict integer counters.
Pydantic is a validation dependency, not a persistence or AI dependency. Python 3.12
is the baseline. Pytest, Ruff, Mypy and Hatchling are development/build tools.

Use a discriminating claim enum with category-specific cross-field validation.
An unknown claim states what is missing; other claims require underlying provenance.
A fact designation is a human/domain assertion, not automatic proof of truth.
Provenance always references underlying sources. AI participation is metadata,
never a substitute for the source. Stakeholder rank has no quality weight.

Represent ownership as stable UUID plus display name; absent ownership is explicit
`None`. Unknown substantive hypothesis fields use a reason-bearing `Unknown` object.
Optional solution and strategy fields use `None` when not proposed/configured.

Material content changes, evidence additions and lifecycle transitions return an
old snapshot, new snapshot and immutable audit event. IDs, actor and clock are explicit
inputs so domain behavior is deterministic. No globals, implicit clocks or I/O.
Changed-field metadata is derived once from material differences, not supplied manually.
Change results validate target, timestamps, consecutive versions, statuses, changed fields
and event semantics. Evidence-addition events identify the added evidence UUID.
Only material changes create subsequent versions; unchanged snapshots cannot masquerade
as revisions. Snapshot models and change operations live in separate focused modules.
Consumers must persist snapshots and audit events atomically and apply optimistic
version checks in a future persistence implementation. Full event sourcing is unnecessary.
Never use Pydantic `model_construct` or unchecked `model_copy(update=...)` for domain
mutations; use validated constructors and the supplied change functions.

A conservative lifecycle graph supports the declared states but does not certify
readiness or authorize delivery. Terminal states have no ordinary outgoing edges.
Parking resumes through structuring/evidence collection rather than silently restoring
an earlier stage. Auditable human override is represented by event types, but no
bypass API is implemented before authorization requirements exist.

Freshness uses explicit dates and a versioned policy. Review renews the freshness
clock; invalidation takes precedence. Thresholds are inclusive. A snapshot cannot
be evaluated before its collection/review/invalidation date; historical evaluation
requires its earlier snapshot. Example thresholds are illustrative, never implicit defaults.
Evidence dates compared with mutation timestamps use the UTC calendar date; callers must
supply collection/review/invalidation dates in that convention. A future snapshot cannot
be linked into earlier hypothesis history. Freshness evaluation takes a calendar date,
not a timestamp; it never consults the clock or guesses a timezone.

`SourceType.AI_SUMMARY` explicitly marks derived interpretations. They may be an original
submission or a supplemental provenance reference, but cannot be primary evidence or
stand alone as provenance. Source classifications are caller declarations, not source
authenticity verification. Missing AI-generation metadata remains `None`; only an
explicit boolean establishes declared AI or non-AI origin. `unknown` differs from `other` for source/assumption categories.
Quality scores, aggregation, gate algorithms and AI interpretation remain deferred.


The supported change-result types are restricted to operations implemented in this
milestone. Generic future audit event labels cannot bypass lifecycle or change semantics.
Keep standalone audit representation separate from authorization and executable workflows.
A source reference collection rejects exact duplicates; assumption-targeted evidence must
refer to an assumption already linked to the hypothesis. Stable source equivalence and
external reference existence still need future application/persistence requirements.
Read [the pre-Milestone 2 review](../architecture/milestone-0-1-domain-review.md) for the
reconstruction contract and outstanding risks.
