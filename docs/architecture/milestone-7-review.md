# Milestone 7 implementation and verification report

## Architecture and delivered scope

1. **Resulting architecture:** existing modular monolith; pure deterministic domain records
   and policies, focused OutcomeFeedbackService orchestration, TOML configuration I/O and
   a credential-free executable scenario. No AI/provider/UI/storage boundary was introduced.
2. **Created/changed files:** eight `domain/outcome_*.py` modules plus
   `domain/implementation.py`, `application/outcome_feedback.py`,
   `config/outcome-measurement.v1.toml`, `examples/outcome_feedback.py`, three unit-test
   modules, shared test helpers and an integration test. Existing audit/evidence/lifecycle/
   configuration models, scenario helper, transition matrix, README, overview, deferred
   checklist and product specification were extended. Architecture documentation and
   ADR 0007 were added.
3. **Implementation model:** immutable owned PLANNED/IN_PROGRESS/COMPLETED/CANCELLED
   snapshots retain exact full authorization, hypothesis/selection/spec-version binding,
   actual delivery, completion actor/time, artifacts, limitations, predecessors and audits.
4. **Implementation lifecycle:** explicit planning/start, accountable completion or
   cancellation; terminal records cannot restart. Authorization alone and work started
   cannot produce implemented. Start rejects mismatched/stale current packets/policies.
5. **Spec deviations:** item-level omitted/changed/reduced/additional/interface-changed
   behavior remains explicit with rationale and individual audits. Completion structurally
   accounts for delivery-facing items. Original DeliverySpec history is unchanged.
6. **Deployment/release:** optional ReleaseObservation retains supplied environment,
   audience, time, rollout, version and provenance. It executes nothing. Plans carry
   release/exposure limitations; completion without release information remains unknown.
7. **Measurement plan:** immutable versioned exact implemented-hypothesis/completed-record
   binding, desired-outcome field/version, explicit metrics/baselines/windows, source/method,
   owner, risks/confounders, predecessor, change reason and audits.
8. **Metric definitions:** name/description/unit/direction/role/population/aggregation/source,
   optional cadence, baseline definition/period, outcome period, optional target and exact
   original-discovery feedback scope. Names alone never define a conversion denominator.
9. **Baseline/target semantics:** known values or explicit unknown reasons; no invented
   baseline/precision. Numeric comparator/threshold, range, directional, qualitative state
   or no target. Absolute thresholds may evaluate without baseline; directional change
   needs one. Post-hoc revisions preserve old definitions and explicit marking.
10. **Observations:** immutable exact plan-version/implementation/metric/window/population,
    actual number/state or unknown reason, source, collection time, method, limitations,
    provenance and audit. No causal state is inferred.
11. **Target evaluation:** recomputable MET/PARTIALLY_MET/NOT_MET/INCONCLUSIVE/NOT_EVALUABLE
    retains full plan/baseline/target/actual/window, explanation, missing information,
    limitations and active policy/time. Partial periods are not extrapolated.
12. **Causal interpretation:** separate accountable human NOT_ASSESSED/INSUFFICIENT_EVIDENCE/
    PLAUSIBLE/SUPPORTED/CONTRADICTED assertion with exact scope, scoped evidence, existing
    quality reviews and study design. Controlled design, current-episode outcome provenance,
    assignment/instrumentation/exposure and appropriate quality are prerequisites for
    SUPPORTED; before/after sequence and prior unrelated experiments cannot produce it.
13. **Multiple metrics/guardrails:** every metric remains individually evaluated; no weighted
    product-success score. A guardrail regression remains visible alongside primary success.
14. **Outcome assessment:** transparent qualitative POSITIVE/MIXED/NEGATIVE/INCONCLUSIVE
    pattern derived from all metrics and exposed limitations; never autonomous product success.
15. **Outcome evidence:** human materialization produces new Evidence with observed values,
    source, methodology/limitations, accountable rationale and typed implementation/selection/
    authorization/spec-version/plan-version/metric/observation provenance.
16. **Discovery feedback:** append-only HypothesisChange and existing KnowledgeState
    reassessment preserve all previous evidence and immutable original selection/spec history.
    Cross-claim/population feedback is rejected. Unknown actuals cannot fabricate directional
    support; their observations/evaluations/reviews retain missing information.
17. **Follow-up learning:** explicit recommendations and a human link to an already supplied
    distinct hypothesis with original outcome-evidence provenance. No automatic duplication,
    roadmap generation, rollback, ticket creation or action execution.
18. **Lifecycle transitions:** dedicated audited selected_for_delivery → implemented →
    measuring_outcome → closed receipts consume completion, plan and review respectively.
    Exact current snapshots, versions, policies and actors are checked; generic transitions
    and STATUS_CHANGED histories cannot bypass those rules.
19. **OutcomeReview:** accountable human, exact current hypothesis/assessment/plan, all metric
    and causal evaluations, original/feedback evidence, rationale, acknowledged limitations,
    unresolved questions and explicit next actions. Known scoped causal evidence cannot be
    hidden from review. AI/system final reviewers are rejected.
20. **Closure:** ends a reviewed lifecycle episode; proves no claim. V1 requires complete
    windows and permits explicitly reviewed inconclusive closure. A policy forbidding
    inconclusive/unevaluable closure blocks it, including within mixed metric results.
21. **Auditability:** planning/start/completion/cancellation/deviations, releases, plans,
    baselines/targets/revisions, observations/evaluations/causal reviews, all lifecycle edges,
    evidence feedback, review, follow-up links and closure retain matching audits. Save full
    predecessor/current records and source artifacts; IDs alone do not reconstruct history.
22. **Tests added:** implementation binding/status/scope/deviation/immutability/audit,
    metric definitions and target shapes/boundaries, known/unknown/missing baselines,
    window/population/source mismatches, criteria history, all evaluation states, conflicting
    observations/multiple metrics/guardrails, causal-design/quality/provenance/contradiction
    safeguards, appended knowledge/history, human review, stale versions, controlled lifecycle,
    explicit follow-up links and configurable inconclusive closure.
23. **Verification results:** see the completed verification table below. Live checks remain
    deferred and skipped, never claimed as a semantic pass. No paid API call was made.
24. **End-to-end example:** search handoff → explicit bounded delivery with scope deviation →
    implemented → predefined primary/business/guardrail metrics → measuring_outcome → primary
    MET, unchanged abandonment NOT_MET and latency NOT_MET → MIXED with unresolved causality →
    three appended evidence items and existing knowledge reassessment → human review → explicit
    follow-up learning → closed. Historical evidence/specifications remain unchanged.
25. **Known limitations:** external reality/source truth and semantic adequacy remain human
    assertions; no collection connectors, statistical inference/power estimation, automatic
    exposure data, actor authentication, persistence or latest-version repository lookup.
26. **Architectural risks:** complete nested snapshots preserve reconstruction but duplicate
    history and make revalidation relatively expensive. Callers can omit external changes;
    snapshots cannot replace atomic transactions, global IDs or concurrency control. Short
    handoff expiry conservatively requires timely start. Baseline/target meaning and quality
    review remain accountable; structural checks do not certify causality.
27. **Post-v0.1 hardening:** production storage/normalized retained records/transactions,
    authenticated roles and authorization, source verification, observability/performance,
    redaction/retention, analytics integrations, product UI and final repository polish remain
    separate future work. Paid live-model verification requires a separately authorized phase.

## Critical self-review

- Authorization, work started, completion and release remain distinct supplied concepts.
- Completion never implies global availability; unknown release and partial exposure are visible.
- Target achievement never sets causal state; before/after evidence cannot satisfy SUPPORTED.
- Missing baselines/targets/actuals remain unknown/absent; post-hoc changes preserve old versions.
- Multiple metrics retain opposing results; no arbitrary average hides a guardrail regression.
- Failure/inconclusive learning retains original decisions and appends scoped evidence.
- Causal support requires current implementation-episode provenance and existing quality review;
  final review cannot hide known scoped supporting/contradicting evidence.
- All three outcome lifecycle edges reject generic transition/deserialization bypass.
- Closed denotes reviewed episode, with accountable human and visible unresolved limitations.
- No new AI agent/provider, paid call, production backend, UI or autonomous action was introduced.
- Regression verification covers historical Milestone 0–6 behavior and existing offline AI contracts.

## Verification

| Check | Result |
| --- | --- |
| Full credential-free pytest | **1,099 passed, 18 intentionally skipped**; 1,117 collected |
| New Milestone 7 coverage | 106 new parametrized unit/integration cases in the complete suite |
| Final cancellation regression after last self-review refinement | **1 passed**; cancellation cannot invent an unrecorded start |
| Ruff lint | Passed |
| Ruff format --check | Passed; 143 files already formatted |
| Strict mypy src tests | Passed; 107 source files |
| Wheel/package build | Passed; product_discovery_engine-0.1.0-py3-none-any.whl |
| pip dependency check | Passed; no broken requirements |
| Git whitespace check | Passed for all staged files |
| Existing offline examples | All four passed: evidence_validation, discovery_decisioning, delivery_specification, spec_delivery |
| Milestone 7 offline example | Passed: mixed outcome, unresolved causality, three new evidence items, retained history, human review/follow-up/closure |
| Paid/live AI execution | Not run; all 18 existing live checks deliberately skipped |

The full offline command was:

```sh
env -u OPENAI_API_KEY -u DISCOVERY_ANALYSIS_MODEL RUN_LIVE_AI_EVALS=0 .venv/bin/python -m pytest
```

The full suite completed in 589.80 seconds in this environment while another verification
run overlapped. The final cancellation-only regression completed in 122.97 seconds with
its full shared scenario fixture. These are execution observations, not a production
performance benchmark. Expensive nested snapshot revalidation remains an explicit
post-v0.1 hardening risk; no validation invariant was weakened to reduce runtime.

All five examples were run with the same credential-free environment. Existing live cases,
assertions and manual workflows remain intact. Skipped/deferred paid verification makes
no claim about live model semantics.
