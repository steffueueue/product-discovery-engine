# Deferred live AI verification checklist

Decision recorded: **2026-10-03, project owner**. Paid OpenAI calls are intentionally
deferred until a later final live-verification phase. Do not run live evaluations during
current development. Live verification is not a requirement for normal CI, milestone
completion or merge, including Milestone 3 and subsequent milestones. Resume only after
an explicit project decision authorizes that phase.

`OPENAI_API_KEY` is optional for normal development. The repository must remain fully
testable without paid API access. Preserve the existing live tests, assertions and
manual workflow for later use; do not turn missing verification into a semantic pass.

## Verification layers

| Layer | What it establishes | Execution and completion policy |
| --- | --- | --- |
| Offline deterministic verification | Domain/application rules, audit history and architecture boundaries | Required normal pytest/quality CI; no credentials or paid calls |
| Offline AI contract/golden tests | Schema, references, fixture expectations and provider handling using fakes/mock transports | Required normal pytest/quality CI; does not establish live model reasoning |
| Paid live-model verification | Observed model behavior on representative cases for a specific commit/model/prompt | Explicitly opt-in, deferred; not required for current milestone completion or merge |

For a credential-free complete run:

```sh
env -u OPENAI_API_KEY -u DISCOVERY_ANALYSIS_MODEL RUN_LIVE_AI_EVALS=0 .venv/bin/python -m pytest
```

Normal CI sets `RUN_LIVE_AI_EVALS=0`. Existing `live_ai` tests retain their opt-in
guards and are skipped in an offline run. That is an execution status, not a live pass.

## Milestone 2: structured discovery analysis

- [ ] Reverify the **ten structured discovery-analysis live cases** in
  `tests/evals/test_discovery_golden.py` against the reviewed final-phase commit/model.
- [ ] Assess solution framing, unsupported numbers, strategy gaps, contradictions,
  unknowns, assumptions, causality, anecdotes and validation recommendations.
- [ ] Record the run URL, commit, configured model, prompt version, totals and per-case
  semantic conclusions; classify infrastructure failures separately.

Historical context: the project owner reported a successful Milestone 2 live run
([review](../architecture/milestone-2-review.md)). This does not verify later changes.
The Milestone 3 rerun of these ten cases returned HTTP 429 before semantic assertions.
Current deferred status is **not reverified**, not a semantic pass or failure.

## Milestone 3: Challenge Mode

- [ ] Run the **eight Challenge Mode live cases** in `tests/evals/test_challenge_golden.py`.
- [ ] Assess correlation versus causation and plausible confounding.
- [ ] Assess weak anecdotal evidence and limited coverage.
- [ ] Assess confirmation-heavy evidence and requests for disconfirmation.
- [ ] Assess shared-source pseudo-triangulation.
- [ ] Assess stale evidence without erasing historical observations.
- [ ] Assess strong mixed-method evidence without quantitative/qualitative bias.
- [ ] Assess competing alternative explanations without forcing a winner.
- [ ] Assess solution-first framing and the underlying customer problem.
- [ ] Record provenance, per-case conclusions and the complete suite result.

Status: **live semantics unverified; intentionally deferred**. All 18 existing cases
were attempted; the complete diagnostic rerun returned HTTP 429 before model assertions.
No semantic conclusion can be drawn. See the
[Milestone 3 attempt report](milestone-3-live-verification.md) for run links and details.

## Future milestones

- [ ] Add live-model checks to this checklist only when they provide genuine value
  beyond deterministic and offline AI contract tests; document the behavior and value.
- [ ] Keep new live checks explicitly opt-in and credential-free CI complete.
- [ ] Carry worthwhile checks into the later authorized verification phase.

This checklist adds no future milestone implementation or paid execution requirement.

## Later-phase execution checklist

- [ ] Obtain the project decision to resume paid live verification and agree the budget.
- [ ] Verify account/project capacity, credentials, model access and the reviewed commit.
- [ ] Collect the existing live cases and any justified later additions without API calls.
- [ ] Use the existing `Live AI evals` workflow (`.github/workflows/live-ai-evals.yml`),
  with repository secret `OPENAI_API_KEY`, variable `DISCOVERY_ANALYSIS_MODEL` and its
  explicit `RUN_LIVE_AI_EVALS=1` opt-in. Do not create a duplicate workflow.
- [ ] Inspect results and logs. A provider failure before assertions is unverified;
  absent or skipped execution is never a semantic pass.
- [ ] Explain and classify failures before modifying code or evaluations. Do not weaken
  expectations merely to get green results; justify any evaluation correction explicitly.
- [ ] For a product fix, add offline regression coverage, rerun affected live cases and
  then the complete live suite during this authorized phase.
- [ ] Attach run/model/prompt/commit evidence and update this checklist with actual results.

Passing live cases provides bounded observations, not proof of general model reliability
or factual truth. Accountable human review remains necessary.

## Milestone 5: specification drafting (later authorized phase only)

Status: **live semantics unverified; intentionally deferred**. Ten new hand-authored offline
contracts and local mocked SDK tests do not establish model reasoning or criterion quality.
No new live test/workflow is required for this milestone; keep the existing 18 live cases.

- [ ] Verify grounded problem/outcome and explicit solution drafting against supplied context.
- [ ] Test hallucination resistance and preservation of unknown solution, interface,
  performance, retention and compliance information.
- [ ] Test unsupported numeric-threshold avoidance, including spelled-out numbers and
  indirect metrics beyond the deterministic lexical guard.
- [ ] Test invented-reference resistance and deterministic rejection of unsupplied IDs,
  hypothesis versions/fields and cross-hypothesis context.
- [ ] Test prevention of evidence-to-solution leaps (query reformulation → vector search),
  and preservation of contradictory/refuted discovery knowledge as uncertainty.
- [ ] Review acceptance-criteria quality, supported outcomes and explicit unknown measures.
- [ ] Review distinction between existing sources, human decisions, generated proposals
  and unknowns; accepting a proposal must retain its origin and complete audit history.
- [ ] Record reviewed commit, provider/model, `delivery-specification.v1` prompt version,
  budget, run evidence and bounded semantic conclusions when paid verification is authorized.


## Milestone 6: no additional live verification

Completeness, gap classification, clarification templates, review/state transitions,
Delivery Gate and handoff are deterministic/human-reviewed. No new AI gap/question
provider or prompt is introduced, so no new live cases are justified in this milestone.
Existing Milestone 2/3/5 offline contracts stay required and paid verification stays
deferred. Structural tests and the offline search handoff do not claim live semantic
verification. Future advisory providers would need offline contracts/golden cases before
any separately authorized, budgeted live phase.


## Milestone 7: no additional live verification

Implementation recording, target evaluation, causal-review constraints, evidence feedback,
human review and closure are deterministic/human operations. No AI provider, narrative
summarizer or prompt was introduced; no new live cases are justified. All existing offline
contracts remain required and the 18 paid live cases remain intentionally deferred.
