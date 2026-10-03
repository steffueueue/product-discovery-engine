# Architecture and domain review before Milestone 2

Scope: the current implementation, AGENTS.md and product specification v0.1.
No Milestone 2 use cases, persistence, UI, AI integration or product features were added.

| Area | Assessment |
| --- | --- |
| Domain independence | Domain imports only its own modules, standard-library value/collection utilities and Pydantic validation. No I/O, clocks, persistence, UI or provider calls occur in domain code. Infrastructure only parses TOML and delegates validation to domain policy types. |
| Knowledge taxonomy | `ClaimKind` explicitly distinguishes fact, evidence, assumption, inference and unknown. Known categories require provenance; evidence and assumption categories require their corresponding references. Unknown cannot assert evidence. No operation promotes a category automatically. A fact label does not establish factual truth. |
| Original submissions | Frozen models and nested immutable values preserve the text. Strict string validation now prevents silent decoding of bytes. Whitespace and Unicode normalization forms survive serialization without rewriting. |
| Provenance | A nonempty underlying source is mandatory, primary evidence must match its provenance, and AI summaries cannot be primary evidence or establish provenance alone. Repeated identical source references are now rejected. Source authenticity remains a declared input, not a verified property. |
| Support/contradiction | A required direction enum represents each explicitly. Adding contradictory evidence preserves existing supporting links; neither direction is filtered or assigned an implicit score. |
| Freshness | Versioned policy and explicit calendar date determine inclusive review/stale boundaries. Review resets the clock; invalidation takes precedence for a valid historical snapshot. No hidden clock or AI confidence is involved. UTC date comparison is documented for timestamp-based mutations. |
| Lifecycle | The graph is explicit, immutable and tested across all 196 pairs. Non-enum inputs now raise `InvalidTransition` instead of being silently accepted or causing `KeyError`/`AttributeError`. Future event labels cannot bypass the graph through a change record. |
| Ownership/versioning | Stable owner IDs, explicit missing ownership, accountable human actors, positive integer versions and consecutive audited snapshots are sufficient foundations. Authorization and concurrency are not implemented. |
| Audit reconstruction | A `HypothesisChange` retains full typed before/after snapshots plus an audit event. A serialized multi-step history test reconstructs owners, strategy references, unknown fields, status, evidence links and versions. Event metadata alone cannot reconstruct field values: snapshot retention is required. Unsupported change operations are now rejected. |
| Complexity | Focused modules, one validated snapshot-change mechanism and a small shared immutable model base remain appropriate. No repositories, event bus, event-sourcing engine, provider interface hierarchy or agent framework was added. |

## Confirmed issues fixed in this review

1. Relabeling a transition with an unimplemented audit event type bypassed operation
   semantics. `HypothesisChange` now accepts only its implemented creation, content
   revision, status transition and evidence-addition operations. Other audit event
   types remain representable as standalone foundation records without executable
   hypothesis workflows.
2. Raw lifecycle strings could be accepted through enum/string equality, or fail with
   incidental Python errors. The transition function now enforces its enum contract
   and raises a clear domain error.
3. Provenance accepted identical source references repeatedly. Validation rejects
   exact duplicates without silently discarding attribution.
4. Submission construction silently decoded byte input. Original text now requires
   a string; normalization/decoding belongs outside this immutable source model.
5. Evidence could target an assumption unrelated to its hypothesis. The existing
   evidence-link operation now checks the hypothesis's known assumption references.
   External referenced-object existence is still a future application responsibility.

## Types and tests

Domain state is held in typed models, enums and immutable reference tuples.
The lifecycle mapping is an enum-to-frozen-set policy table, not a generic record.
The dictionary used to rebuild validated links is a serialization/construction boundary;
no scores or decisions are dictionary-driven. Adding a custom cloning abstraction or
five separate claim classes would currently add complexity without resolving a known defect.
The assumption's AI-origin property derives from provenance rather than duplicating it.
Uncertainty and importance are qualitative enums, with unknown represented explicitly;
unsupported numeric probability/confidence inputs are rejected.

The existing lifecycle matrix asserts a separately declared product contract rather than
reading the implementation's transition table. Enum and round-trip checks establish
representation/immutability contracts; they are supplemented by operation tests.
The architecture tests deliberately inspect imports to verify AGENTS.md's boundary.
New regression tests assert rejected invalid states, not private helper calls. The history
scenario validates material behavior across existing operations and JSON serialization;
it does not add a replay engine, persistence adapter or business workflow.

## Remaining architectural risks

- Future persistence must atomically retain snapshots and audit events, enforce unique
  event IDs and optimistic versions, and prevent divergent or incomplete history chains.
  Models validate one change record, not an entire durable journal.
- Audit metadata is not a self-contained event-sourcing payload. Reconstruction depends
  on retaining typed snapshots and referenced evidence/strategy history. Evidence has no
  mutation/versioning workflow yet; future persistence must preserve the source state
  used for a decision rather than resolving every reference to its latest value.
- Referential existence, actor authentication, authorization and ownership/readiness gates
  remain unresolved application concerns. An enum-valid stage is not a readiness decision.
- Fact labels, qualitative uncertainty and source classifications are caller assertions;
  the domain cannot detect fabricated sources, mislabeled AI summaries, equivalent source
  aliases or a semantically unsupported claim. These require later evidence review rules.
- The lifecycle graph and example freshness thresholds are provisional policy, not
  approved production strategy or scoring. Persisted freshness evaluations must retain
  their evaluation date and policy version if they become decision evidence.
- Frozen Pydantic models prevent normal mutation; unchecked construction/copy or deliberate
  Python object tampering is not a supported API or security boundary. Serialized model
  evolution will require migrations once durable storage exists.
- Static import checks are a useful guard, not a proof against arbitrary dynamic imports
  or I/O. GitHub-hosted CI and broader Python-version compatibility are not validated here.


## Verification

- Full suite: 367 passed; no failures or skips, including 17 cases added in this review.
- Ruff lint and format checks passed; strict Mypy passed across 26 Python source/test files.
- Dependency checks and Hatchling wheel/source-distribution builds passed.
- Rebuilt wheel contents from the source distribution match the directly built wheel.
- Installed that rebuilt wheel with pinned dependencies in an isolated environment;
  verified imports resolve to its site-packages and all 367 tests passed there as well.
