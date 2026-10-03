# Milestone 3 implementation and critical review

Baseline: fetched `origin/main`, switched to local `main`, verified exact commit
`d4104df8e8755ba368316b31f2a136ac4daf077d` (Milestone 2 merge), then created the fresh
`feat/evidence-validation` branch. No previous feature branch was reused.

## Implementation report

1. **Architecture:** retained modular monolith boundaries; pure domain policies and
   immutable records, deterministic application knowledge assembly, advisory challenge
   protocol, versioned prompts and isolated OpenAI/TOML adapters. No new dependencies.
2. **Files:** the complete manifest below identifies all intended changes. Domain,
   application, AI, infrastructure, configuration, tests, docs and one synthetic example
   are included. Standard CI explicitly disables live calls. The existing opt-in live
   workflow discovers all new cases without duplicate workflow changes.
3. **Quality:** five ordinal dimensions, explicit rationale/input basis, exact scope,
   version/time/audit and weakest-dimension aggregate. Unknown reviewer basis stays
   unknown. There is no count bonus or source-type hierarchy. Policy tables are immutable.
4. **Freshness:** configurable CURRENT, REVIEW_DUE, STALE and INVALIDATED with collection,
   review, validity/review-after metadata and explicit reasons. Historical context can
   suppress automatic staleness. Full records and invalidation snapshots preserve history.
5. **Independence:** canonical origin families and underlying source/provenance references
   merge transitively. Unknown origins do not certify independence. Duplicate IDs and
   conflicting origin snapshots fail. Relationship creation is audited.
6. **Triangulation:** relevant item count is separate from traceable groups and independent
   method matching. Both directions are exposed. Shared-corpus reports cannot triangulate;
   mixed evidence is unresolved. Constructors and knowledge assembly validate reconstruction.
7. **Target safeguards:** exact hypothesis/claim-or-assumption/target/population matching;
   fourteen additional explicit targets; no legacy aliases. Population prevalence coverage
   from nonrepresentative samples is capped at LOW. Legacy assessment needs a claim reference.
8. **Risk:** explicit ordinal decision impact and uncertainty use a validated monotonic
   5×5 lookup. Unknown inputs remain unknown; both evidence directions and gaps are retained.
   Evidence count and validation cost do not determine risk or information gain.
9. **Validation:** PLANNED → READY → RUNNING → COMPLETED, with cancellation from nonterminal
   states only. Activities require an owner and predefined criteria. Dependency attestations,
   versions, criteria history and creation/start/completion/cancellation audits are explicit.
   Result recording appends evidence, retains before/after assumptions and rejects invalidated
   generated evidence. Partial support remains conservatively inconclusive in the old enum.
10. **Challenge Mode:** typed advisory items and results, explicit provider/model/prompt
    provenance, input-reference checks, sanitized failures and completion audits. AI output
    has no quality/freshness/triangulation/lifecycle/final-decision fields. Both boolean markers
    must be exactly true. The OpenAI adapter uses the existing model/key conventions.
11. **Confirmation safeguards:** support and contradiction are visible; all contradictions,
    including invalidated history, must appear in challenge output. Disconfirmation needs and
    limitations are mandatory. Refuted assumptions and historical evidence survive. Reassessment
    cannot drop records or rewrite statements/provenance or reverse invalidation. Criteria-only
    version bumps and unmarked post-hoc revisions fail.
12. **Tests/evals:** 159 additional offline tests, including eight challenge golden cases,
    plus eight additional opt-in live cases. Coverage includes dimensional policies, scope,
    coverage/prevalence distinction, time, invalidation, shared/transitive origins, method
    diversity, directional symmetry, risk matrix, all 25 lifecycle edges, criteria/result
    integrity, audit reconstruction, adapter fakes and invalid provider output.
13. **Verification:** full credential-free offline pytest: **580 passed, 18 skipped** (all
    live evaluations); Ruff lint passed; Ruff format check passed; strict mypy passed across
    `src tests examples`; wheel build passed; `pip check` found no broken requirements;
    Git whitespace checks passed. The end-to-end synthetic example ran successfully.
    Initial unqualified pytest inherited a live opt-in flag and ten existing live cases
    failed on unavailable network access; subsequent offline checks explicitly disabled live
    evaluation and removed `OPENAI_API_KEY`. No live semantic reliability is claimed.
14. **Known limitations:** no database, UI, scheduler, authorization or referential-integrity
    backend. Explicit reviewer basis is not factual certification. Source families and freshness
    contexts require accountable configuration. Offline fixtures do not measure actual AI quality.
    No unsupported population percentage, causal probability or economic estimate is computed.
15. **Architectural risks:** callers must retain snapshots, source artifacts and policy versions
    and later persist combined records atomically. Canonical origin errors can misstate independence;
    conservative overlap grouping can undercount. Dependency completion is caller-attested. Challenge
    prose can remain incomplete or biased despite structural safeguards. Large-scale performance and
    concurrent writes are not assessed. No new workflow was added to conceal these limitations.
16. **Deferred:** Discovery Priority, Delivery Readiness and Discovery Gate (Milestone 4),
    plus portfolio prioritization, selection/delivery, spec generation, delivery gates,
    implementation records and outcome measurement. No PR creation or merge is part of this task.

## Critical self-review

| Review concern | Finding / protection |
| --- | --- |
| Item count mistaken for quality | Weakest-dimension policy; separate item/source/method counts, no quality total |
| Shared sources double counted | Transitive family/provenance grouping; shared-corpus and bridge regression tests |
| Quantitative evidence privileged | Reliability/directness use reviewed method basis, never SourceType |
| Qualitative evidence universally weak | Rigorous qualitative reliability test; coverage remains independently scoped |
| Stale evidence discarded | Retained knowledge and low recency, historical review context, explicit reasons |
| Support privileged | Symmetric support/disconfirmation aggregation and quality tests |
| Contradictions disappearing | Required review input, both group lists, no prior-record dropping, challenge completeness checks |
| Numeric pseudo-precision | Ordinal values and integer source counts only; explicit policy lookup |
| AI entering deterministic policy | Import boundary test, isolated provider and rejection of authoritative output fields |
| Post-hoc criteria rewritten silently | Criteria versions, before/after values, actor/reason audit, explicit post-hoc marker and locked result version |
| Invalid validation transitions | Exhaustive 25-edge graph tests, terminal-state protection and dependency checks |
| Challenge makes product decision | Advisory-only schema rejects final decisions; no gate or decision operation |
| Milestone 2 regressions | Existing offline tests pass; validation method enum re-export preserves its public import and values |

Genuine issues fixed during review: missing explicit claim scope, evidence-removal and
same-ID rewriting paths in reassessment, invalidated generated evidence establishing a
validation conclusion, reconstructed triangulation counts/directions, criteria-version-only
changes, unmarked post-hoc criterion edits and numeric substitutes for AI/advisory markers.
The review did not add Milestone 4 functionality.

## Changed-file manifest

- `.github/workflows/ci.yml`
- `README.md`
- `config/evidence-policies.v1.toml`
- `docs/architecture/evidence-validation.md`
- `docs/architecture/milestone-3-review.md`
- `docs/architecture/overview.md`
- `docs/decisions/0003-evidence-validation.md`
- `docs/evals/README.md`
- `docs/product-specs/discovery-prioritization-system-v0.1.md`
- `examples/evidence_validation.py`
- `src/product_discovery_engine/ai/challenge_prompts.py`
- `src/product_discovery_engine/application/analysis_models.py`
- `src/product_discovery_engine/application/challenge_analysis.py`
- `src/product_discovery_engine/application/evidence_validation.py`
- `src/product_discovery_engine/domain/assumption_risk.py`
- `src/product_discovery_engine/domain/audit.py`
- `src/product_discovery_engine/domain/common.py`
- `src/product_discovery_engine/domain/evidence.py`
- `src/product_discovery_engine/domain/evidence_assessment.py`
- `src/product_discovery_engine/domain/evidence_origins.py`
- `src/product_discovery_engine/domain/evidence_policy.py`
- `src/product_discovery_engine/domain/triangulation.py`
- `src/product_discovery_engine/domain/validation.py`
- `src/product_discovery_engine/domain/validation_methods.py`
- `src/product_discovery_engine/infrastructure/configuration.py`
- `src/product_discovery_engine/infrastructure/openai_challenge.py`
- `tests/__init__.py`
- `tests/evals/README.md`
- `tests/evals/test_challenge_golden.py`
- `tests/fixtures/README.md`
- `tests/fixtures/challenge_analysis.json`
- `tests/integration/test_evidence_configuration.py`
- `tests/m3_helpers.py`
- `tests/unit/test_assumption_risk.py`
- `tests/unit/test_challenge_analysis.py`
- `tests/unit/test_evidence_validation.py`
- `tests/unit/test_validation.py`

## Live-verification follow-up

The initial offline totals above describe `5adc79a`. The follow-up safe-provider-diagnostics
fix raises offline coverage to **593 passed, 18 live tests skipped**. Both dispatched GitHub
live suites failed before model output; the rerun confirms HTTP 429 on every case. See
[the live verification report](../evals/milestone-3-live-verification.md) for run links,
root-cause classification, all eight case assessments, complete checks and the final review.
Live semantic behavior remains unverified; no evaluation was weakened.
