# Milestone 5 implementation and verification report

Date: 2026-10-04. Scope: Delivery Selection & Specification Drafting only.
Baseline: fetched `origin/main`, switched to exact main snapshot
`e4b4655901f4b9a85214a448733b02feb52d362e`, verified the expected Milestone 4 merge and
created fresh `feat/delivery-specification`. No previous feature branch was reused.

## Resulting architecture and models

1. **Architecture:** the existing modular monolith retains domain/application/AI/
   infrastructure boundaries. Pure domain records/operations implement selection, closed
   context, typed statements, proposal review and immutable draft changes. One application
   service coordinates them through an optional provider protocol. No new dependency.
2. **Changed files:** the complete file inventory is below. Historical product contracts
   are preserved; Milestone 5 is appended. Existing live tests/workflows are unchanged.
3. **Delivery Selection:** `DeliverySelection` retains exact candidacy before/after
   snapshots, discovery decision/history, human actor/owner, rationale, time, strategy,
   optional decision context and two distinct reconstructable audits. Noncandidate, stale,
   mismatched, repeated, nonhuman, empty-rationale and backdated attempts fail.
4. **Lifecycle:** dedicated selection alone promotes candidacy to `selected_for_delivery`
   and increments the version. Generic transitions and ordinary change reconstruction
   reject the edge. Gate PASS alone neither changes state nor selects work.
5. **DeliverySpec:** immutable positive version/schema counters, DRAFT-only status, exact
   selected hypothesis/version and selection through retained context, creation actor/time,
   predecessor and material revision metadata. Empty/incomplete drafts remain valid.
6. **Items/provenance:** typed content covers all requested product/software concepts.
   `SpecStatement` and structured criterion clauses distinguish source-backed, human decision,
   AI proposal and unknown; exact source references and conservative solution/numeric/API
   guards prevent silent grounding. Every criterion clause has its own provenance.
7. **AI drafting:** optional `SpecificationDraftingProvider` returns a context-bound,
   schema-validated generated proposal; retained records preserve actual provider/model/
   prompt provenance. Optional OpenAI Responses adapter reuses existing config, strict
   structured output, `store=False`, timeout/retry and safe errors. Prompts are versioned.
8. **Human acceptance:** every proposal item receives a human accepted/rejected disposition,
   rationale, actor/time and audit. Separate human materialization consumes exact reviewed
   context. Rejected content stays in history; accepted AI origin never becomes evidence.
   AI can organize existing human decisions but cannot invent one with that label.
9. **Revision/versioning:** consecutive versions preserve old snapshots, original creation
   metadata, human facts and reviewed proposal history. Reasons/actors/times are required;
   no-ops fail. Existing item identities cannot be reworded; replacement uses a new ID.
   Deterministic changed IDs expose additions/removals. Prior contexts remain reconstructable.
10. **Auditability:** selection, lifecycle promotion, context inputs, generation, review,
    item acceptance/rejection, creation, human requirement/constraint additions, revision
    and supersession have immutable, reconstructable audits. Supersession does not mutate
    the old version's DRAFT status. Callers must retain complete returned records.

## Evaluation, tests, verification and example

11. **Offline AI evaluations:** ten hand-authored A–J cases exercise problem-only and
    explicitly supported solution hypotheses, unsupported latency, unknown interface,
    query-reformulation/embedding leap, explicit platform constraint, contradictory
    evidence, invented reference, proposed structured criteria and explicit human decisions.
    They establish contracts, not live semantics.
12. **Deterministic tests:** 94 new offline cases: 30 selection, 47 specification,
    7 mocked SDK/prompt, 10 golden contracts. Coverage includes exact ID/version/selection/
    context binding, lifecycle bypass, actor/reason, nested provenance, unknowns, invented/
    omitted references, unsupported numbers/APIs, criteria, reviews, immutable revisions,
    no-op/history/supersession/tampering and inaccessible Milestone 6 statuses. Existing
    transition-matrix expectations now correctly exclude generic selection.
13. **Complete verification:**

    | Check | Result |
    | --- | --- |
    | Full credential-free pytest | **875 passed, 18 existing live cases skipped** |
    | Ruff lint | Passed |
    | Ruff format --check | Passed |
    | Strict mypy `src tests` | Passed |
    | Package/wheel build, no dependencies/no build isolation | Passed |
    | `pip check` | No broken requirements |
    | Git whitespace check | Passed |
    | Existing evidence-validation example | Passed |
    | Existing discovery-decisioning example | Passed |
    | New Milestone 5 example | Passed |

    Full pytest runs unset `OPENAI_API_KEY`/`DISCOVERY_ANALYSIS_MODEL` and explicitly set
    `RUN_LIVE_AI_EVALS=0`. OpenAI adapter tests use local httpx mock transport. No paid API
    call or Live AI evals workflow was triggered; skipped live tests are not semantic passes.
14. **End-to-end example:** synthetic search discovery reaches candidacy separately from
    gate evaluation; human selection produces selected delivery, explicit context retains
    discovery history, fake drafting preserves problem/outcome refs and unknown solution/
    interface/latency. Human review rejects unsupported embeddings, creates DRAFT v1, and
    a human scope decision creates DRAFT v2 while v1 and prior AI reviews remain intact.
    The flow stops without completeness analysis, clarification generation or Delivery Gate.
15. **Deferred live verification:** checklist adds grounded drafting, hallucination resistance,
    unknown preservation, numeric-threshold avoidance (including language beyond lexical
    guards), invented references, problem-to-solution leaps and criterion quality. Actual
    provider semantic behavior remains intentionally unverified until explicitly authorized.

## Limits, risks and exact deferrals

16. **Known limitations:** synchronous provider; exact source restatement rather than
    semantic paraphrase verification; conservative digit/API guards may reject otherwise
    valid proposed identifiers. Spelled-out numbers and indirect unsupported implications
    still need human review. No source fetching, context-size budgeting or UI. Drafts do
    not have completeness policy. No persistence/transactions or latest-state lookup.
17. **Architectural risks:** accountable source assertions do not certify truth. Supplied
    snapshots cannot detect withheld external changes; competing callers can branch history.
    Future storage must enforce authorization, unique IDs and atomic current-version checks.
    Full retained context duplicates data and can contain sensitive text; production access,
    retention and redaction policy is still needed. `store=False` does not establish complete
    provider retention behavior. No business policy is delegated to a model.
18. **Milestone 6 remains deferred:** automatic completeness scoring; completeness gate;
    blocking/nonblocking gap classification; targeted clarification questions; clarification
    ownership; question/answer resolution lifecycle; NEEDS_CLARIFICATION/READY_FOR_REVIEW
    behavior based on completeness; READY_FOR_DELIVERY transitions; Delivery Gate;
    implementation authorization. No ranking/allocation, automatic selection, implementation,
    production deployment, outcomes/feedback, persistence backend or deployment UI was added.

## Complete file inventory

Created:

- `src/product_discovery_engine/domain/delivery_selection.py`
- `src/product_discovery_engine/domain/delivery_context.py`
- `src/product_discovery_engine/domain/spec_items.py`
- `src/product_discovery_engine/domain/spec_proposals.py`
- `src/product_discovery_engine/domain/delivery_specification.py`
- `src/product_discovery_engine/application/delivery_specification.py`
- `src/product_discovery_engine/ai/specification_prompts.py`
- `src/product_discovery_engine/infrastructure/openai_specification.py`
- `examples/delivery_specification.py`
- `tests/m5_helpers.py`
- `tests/unit/test_delivery_selection.py`
- `tests/unit/test_delivery_specification.py`
- `tests/unit/test_openai_specification.py`
- `tests/evals/test_specification_golden.py`
- `tests/fixtures/specification_drafting.json`
- `docs/architecture/delivery-specification.md`
- `docs/architecture/milestone-5-review.md`
- `docs/decisions/0005-reviewed-delivery-specification-proposals.md`

Modified:

- `src/product_discovery_engine/domain/audit.py`
- `src/product_discovery_engine/domain/lifecycle.py`
- `tests/unit/test_hypotheses.py`
- `docs/product-specs/discovery-prioritization-system-v0.1.md`
- `docs/evals/deferred-live-verification.md`
- `tests/evals/README.md`
- `tests/fixtures/README.md`
- `README.md`

## Critical self-review

Reviewed all 19 requested risks. Genuine issues corrected: generic selection bypass;
source-backed observation-to-requirement relabeling; invented/omitted refs; provenance
laundering during revision; generated numeric/API details; absent solution invention;
acceptance clauses hiding unsupported values or unreviewed AI origin beneath an unknown
summary; materialization against a different newly supplied context; and missing explicit
human constraint-addition audit classification. Existing discovery behavior stays green.

No new complete/readiness/delivery-gate workflow exists. Historical later hypothesis
states remain representational foundations; Milestone 5 adds no implementation operation.
The branch is committed and pushed without creating a PR or merging.
