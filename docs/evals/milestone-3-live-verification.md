# Milestone 3 live verification: infrastructure blocked

Date: 2026-10-03. Starting branch: `feat/evidence-validation`; local and remote
commit verified as `5adc79a11618cee77f2aac973dc5bd95959d4189` before dispatch.

The existing `Live AI evals` workflow was left unchanged. Its command,
`python -m pytest tests/evals -m live_ai -v`, collects all 18 live tests: eight
Challenge Mode cases and ten Milestone 2 discovery cases. No duplicate workflow,
weakened assertion, changed prompt, alternative model or bypass of checks was added.

## Runs and root cause

- [Initial GitHub run](https://github.com/steffueueue/product-discovery-engine/actions/runs/37149973683)
  on `5adc79a`: **18 failed, 18 deselected**. All failed at the OpenAI provider boundary;
  semantic assertions were never reached. Checkout/install succeeded. The old safe
  exception messages did not distinguish underlying HTTP errors.
- A minimal local request and the affected causality test returned **HTTP 401,
  invalid_api_key** using the cloud environment's credential. This diagnoses local
  access only; it does not establish the status of the separate repository secret.
- The justified implementation fix, `23de6d134b9fd07b501033f3281f470868c2e6ab`, adds
  sanitized HTTP status, allowlisted error-code and connection/timeout diagnostics in
  both OpenAI adapters. It does not expose keys, raw response bodies or provider messages.
  Thirteen new offline regression tests exercise real SDK failures through fake transports.
- [Complete GitHub rerun](https://github.com/steffueueue/product-discovery-engine/actions/runs/37150391884)
  on `23de6d1`: **18 failed, 18 deselected**. Every test reports **HTTP 429**, after the
  existing SDK retries. No specific quota/rate-limit code was available. This confirms
  the repository-side blocker is rate/quota capacity, distinct from local authentication.

Root-cause classification: **infrastructure**. There is no model output on which to
judge reasoning, prompt design or semantic evaluation failures. The diagnostics gap was
an additional provider-integration issue and was fixed without changing product behavior.
Repeated immediate reruns cannot establish semantic reliability while access is blocked.
The account/project quota or rate-limit capacity behind the repository secret needs
attention; no credential or billing change is made or fabricated by this task.

## Eight Challenge Mode cases

All eight are **blocked by HTTP 429 before model output**, not semantically failed or passed.

| Case | Behavior the unchanged live contract must verify |
| --- | --- |
| Correlation vs causation | Identify false causality and plausible confounding |
| Weak anecdotal evidence | Identify stakeholder bias and limited coverage |
| Confirmation-heavy evidence | Seek disconfirmation and retain alternatives |
| Shared-source pseudo-triangulation | Identify shared origins and retain the deterministic single-source state |
| Stale evidence | Ask for review without declaring historical observations false |
| Strong mixed-method evidence | Recognize independent triangulation while retaining causal/reach limits |
| Competing explanations | Preserve price and relevance, without forcing a winner |
| Solution-first framing | Ask whether the underlying customer problem is established |

The ten Milestone 2 cases have the same repository-side HTTP 429 blocker. No live
behavioral verification is claimed for any of the 18 cases.

## Offline verification after the fix

- `env -u OPENAI_API_KEY RUN_LIVE_AI_EVALS=0 .venv/bin/python -m pytest -q`:
  **593 passed, 18 live tests skipped**.
- Ruff lint and formatting check: passed.
- Strict mypy over `src tests examples`: passed.
- Wheel build with `--no-deps --no-build-isolation`: passed.
- Dependency check: no broken requirements.
- Git whitespace checks: passed.

## Final Milestone 3 review

The final review inspected the evidence/validation policy, application boundaries and
corresponding regression tests. No further material domain changes were warranted.

| Required safeguard | Review finding |
| --- | --- |
| Quantity vs quality | Five-dimensional weakest-dimension aggregate; no count bonus |
| Shared families | Canonical family/provenance grouping and transitive overlap tests; duplicate reports cannot independently confirm |
| Qualitative/quantitative parity | Reliability uses method basis, never SourceType; rigorous qualitative evidence and analytics receive equal treatment for equal basis |
| Contradictions visible | Both group lists, full retained knowledge, complete challenge contradiction references and no evidence-dropping reassessment |
| Freshness retains history | Stale/invalidated items remain visible; freshness and invalidation records preserve snapshots/reasons |
| Advisory challenges | Strict true AI/advisory markers, explicit provenance and no final decision fields |
| AI cannot set deterministic state | Challenge schema rejects quality, freshness and triangulation; it exposes no validation lifecycle or accepted-knowledge mutation |
| Criteria history | Predefined signals, criteria versions, before/after snapshots, actor/reason audits and marked post-hoc changes |
| Milestone boundary | No Discovery Priority, Delivery Readiness or Discovery Gate added; follow-up code only improves safe provider failure diagnostics |

Remaining risks: live Challenge Mode semantics are unverified; golden checks are bounded
contracts, not a general reliability certificate; accountable reviewer input and correct
canonical origin identity remain necessary; storage transactions, authorization and
concurrent writes are not implemented. The PR should remain draft while live access is
blocked. Once access is restored, dispatch the same workflow on the feature branch and
assess all 18 results without relaxing tests. Documentation-only commits after `23de6d1`
do not change the evaluated implementation.
