# Milestone 4 implementation and critical review

Baseline: fetched `origin/main`, switched to local `main`, verified exact Milestone 3
merge `7609f0fab5b9393833139a57159ffc4f61d76996`, and created the fresh
`feat/discovery-decisioning` branch. No prior feature branch or worktree was reused.

## Resulting architecture and implemented behavior

1. **Architecture:** six focused pure-domain decisioning modules, one application service,
   existing TOML infrastructure and existing evidence/validation/advisory boundaries.
   Immutable inputs, policies, results and audits reconstruct deterministically. No new
   dependency, model provider, prompt, persistence backend or presentation layer.
2. **Discovery Priority:** explicit ordinal impact/uncertainty rule table; CRITICAL/HIGH/
   MEDIUM/LOW plus NO_ACTION and separate UNKNOWN. Preserve risk, gaps, contradictions,
   freshness, validation context, gain/cost/speed and dependencies. Monitor active tests;
   show blockers; reframe contradictions/refutation. Categories preserve ties within one
   hypothesis; unknown is outside ordering. Cost/speed/gain do not break ties in v1.
3. **Delivery Readiness:** qualitative dimensions and NOT_READY/NEEDS_REVIEW/READY. Required
   unknowns block; required partials require review. Exact target/population support,
   weakest-dimension quality, independent qualifying support, freshness, critical assumptions,
   validation, human challenge/contradiction/strategy review and owner are assessed separately.
   No solution means solution effectiveness is NOT_APPLICABLE. Optional reach, viability,
   causal mechanism and business impact remain unknown without their own evidence.
4. **Discovery Gate:** explicit condition records with passed/failed/unknown/review reasons,
   readiness reference, full hypothesis/policies, version, time and expiry. Ordinary PASS
   requires READY, configured minimum conditions and technical snapshot/policy/time/lifecycle
   invariants. Missing readiness is a blocked record with unknown conditions.
5. **Lifecycle:** dedicated explicit human promotion returns before/after hypotheses and
   separate lifecycle/decision audits. It increments the material version and stops at
   `candidate_for_delivery_prioritization`. Generic status changes and serialized ordinary
   history cannot bypass the gate. Wrong hypothesis, old material snapshot, changed policy
   or expired gate fails. The existing stage graph is retained as stage policy only.
6. **Overrides:** separate immutable original-gate/actor/reason/time/policy/action/conditions/
   audit record. Only configured known conditions can be overridden; never unknowns or
   technical prerequisites. Original result stays distinct from PASSED. Promotion explicitly
   consumes the override and same accountable human. Role authorization remains deferred.
7. **Configuration:** versioned validated `config/discovery-decisioning.v1.toml` with three
   typed policy models. Reject unsafe/unknown dimensions, ordinals, targets, duplicate rules,
   missing coverage/version, impossible freshness/method settings and inconsistent gate
   requirements. Business policy never lives in AI prompts; no generic rules engine.
8. **Auditability:** priority/readiness assessed; gate evaluated/passed/blocked/review-required;
   gate overridden; candidacy promoted; decision recorded. Full deterministic inputs,
   policy snapshots, source history and human reviews remain inspectable. Retain actual
   advisory/validation records alongside references. No previous record is silently changed.

## Intended file manifest

| Area | Created/changed files |
| --- | --- |
| Domain policies/inputs | `src/product_discovery_engine/domain/decisioning_policy.py`, `decisioning_inputs.py` |
| Domain assessments | `src/product_discovery_engine/domain/discovery_priority.py`, `delivery_readiness.py` |
| Domain gate/promotion | `src/product_discovery_engine/domain/discovery_gate.py`, `discovery_promotion.py` |
| Existing domain integration | `src/product_discovery_engine/domain/audit.py`, `lifecycle.py`, `triangulation.py` |
| Application | `src/product_discovery_engine/application/discovery_decisioning.py` |
| Configuration | `src/product_discovery_engine/infrastructure/configuration.py`, `config/discovery-decisioning.v1.toml` |
| Example | `examples/discovery_decisioning.py` |
| Tests | `tests/m4_helpers.py`, `tests/unit/test_discovery_priority.py`, `test_delivery_readiness.py`, `test_discovery_gate.py`, `test_hypotheses.py`, `tests/integration/test_decisioning_configuration.py`, `test_discovery_decisioning.py` |
| Architecture | `docs/architecture/discovery-decisioning.md`, `milestone-4-review.md`, `overview.md` |
| Product/decision/docs | `docs/product-specs/discovery-prioritization-system-v0.1.md`, `docs/decisions/0004-discovery-decisioning.md`, `README.md` |

`triangulation.py` exposes the existing method-matching helper for readiness reuse;
its Milestone 3 calculation is unchanged. The sole historical-test expectation change
removes ungated candidacy from the generic ordinary-transition path; dedicated tests
now verify the gated path and serialized bypass rejection. Historical Milestone 0–3
product contracts are preserved; the new Milestone 4 contract supersedes their deferral.

## Tests added and verification

169 new offline cases cover explicit priority categories, all ordinal risk combinations,
expensive/slow critical learning, active/inconclusive/refuted/blocked validation, missing
planning/context, ties and no portfolio grouping; exact targets/populations, nonrepresentative
reach, weak/unknown quality, same-origin reports, independent methods, stale/review-due/
invalidated evidence, critical/low-impact assumptions, contradiction dispositions, ownership,
strategy objectives, conditional solutions, human challenge review; pass/block/review/unknown
conditions, missing readiness, policy mismatch, expired/wrong/old gates, promotion/accountability,
serialized bypasses, narrowly configured overrides and audit reconstruction. Configuration
rejection and the full service learning loop are tested without credentials.

Invariant-style regressions verify that duplicate same-origin evidence cannot improve
independence/quality, filtering a stale bridging record cannot manufacture independence,
invalidated/stale validation dependencies cannot satisfy the gate, required unknowns never
pass, risk/decision/audit tampering fails reconstruction, old gates cannot promote changed
hypotheses, and overrides never rewrite ordinary gate outcomes. No property-test dependency
or new live evaluation was added.

| Verification | Result |
| --- | --- |
| `env -u OPENAI_API_KEY -u DISCOVERY_ANALYSIS_MODEL RUN_LIVE_AI_EVALS=0 .venv/bin/python -m pytest -q` | 770 passed, 18 opt-in live tests skipped |
| `.venv/bin/ruff check .` | Passed |
| `.venv/bin/ruff format --check .` | Passed; 91 files already formatted |
| `.venv/bin/mypy src tests` | Passed; 67 source files, strict configuration |
| `.venv/bin/python -m pip wheel . --no-deps --no-build-isolation --wheel-dir dist` | Built `product_discovery_engine-0.1.0-py3-none-any.whl` |
| `.venv/bin/python -m pip check` | No broken requirements |
| `git diff --check` / staged whitespace check | Passed |
| Credential-free `examples/discovery_decisioning.py` | Passed; CRITICAL → NOT_READY/BLOCKED → READY/PASSED → candidacy |
| Credential-free `examples/evidence_validation.py` | Existing Milestone 3 example passed unchanged |

All existing offline tests remain green with the authorized lifecycle-contract update.
The 18 existing opt-in live evaluations, prompts and AI provider adapters are unchanged.
No live AI workflow was triggered and no paid OpenAI call was made. Paid semantic
verification remains intentionally deferred; skipped live tests are not a semantic pass.

## Example behavior

The runnable synthetic search scenario retains independent problem/segment evidence.
A very-high-impact uncertain relevance/price causal assumption yields CRITICAL learning.
Initial readiness is NOT_READY and the gate is BLOCKED. A predefined controlled comparison
completes and refutes the causal assumption, appending evidence rather than erasing history.
The human explicitly treats the refutation, accepts the investigated contradiction,
addresses the advisory challenge and acknowledges the actual versioned strategy objective.
The problem-only knowledge state becomes READY under v1, the gate PASSES, and an explicit
human operation promotes candidacy. Reach/viability/causal mechanism/business impact remain
unknown; no relevance solution is endorsed and no delivery selection follows.

## Critical self-review and remaining risks

The review checked all 18 requested failure modes: separate capabilities; learning rather
than portfolio ranking; impact/uncertainty distinction; no cheap-test dominance; no quantity
quality bonus; real source independence; visible contradiction; retained stale history;
unknown fail-safe; advisory AI boundary; explicit strategy; conditional solution readiness;
no build implication; no automated delivery selection; no decimals; visible overrides;
material-snapshot binding; no Milestone 5 scope.

Genuine issues found and fixed during review:

- preserve full-history source-overlap components when filtering support for freshness/quality;
- block required validation when its generated evidence is stale/invalidated;
- prevent missing linked validation context from becoming an actionable duplicate learning recommendation;
- require actual strategy objective/context rather than a version reference alone;
- retain/reconstruct risk policy and reject changed ordinal risk;
- keep UNKNOWN learning targets outside ordinal ordering and prevent cross-hypothesis grouping.

Known limits: human judgments, semantic acceptance and external source identity remain
assertions, not factual certification. Challenge Mode reviews one scope; humans must review
the broader hypothesis. Initial policy thresholds are explicit but not empirically calibrated.
Ties intentionally leave test selection to humans. The wheel contains the library; deploy
external versioned TOML policies alongside it, following the existing configuration approach.

Architectural risks: no storage, transactions, authorization roles, global uniqueness,
atomic compare-and-swap or lookup of latest external evidence exists. Promotion validates
explicit snapshots and expiry; callers must reassess after evidence invalidation, new
validation or changed review information even when evidence IDs did not change. A future
persistence boundary must atomically compare current state and save complete decisions/audits.
Retain actual advisory/validation/source records alongside their references. Full immutable
records duplicate context and incur revalidation cost; large-scale performance is unmeasured.

Milestone 5 remains explicitly deferred: DeliverySpec generation, drafting, clarification,
spec completeness and Delivery Gate. Portfolio ranking/ROI/RICE/WSJF, automatic
`selected_for_delivery`, implementation records, outcomes, deployment UI and persistence
backend are also unimplemented. No PR creation, merge or Milestone 5 work is part of this task.
