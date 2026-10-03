# Discovery-analysis evaluations

Paid live-model verification is intentionally deferred by project decision. Do not run
live evaluations during current development. `OPENAI_API_KEY` is optional for normal
development; normal pytest/CI and milestone completion require no paid API access.
Offline deterministic tests and offline AI contract/golden tests remain required.
All 18 live tests remain unchanged and opt-in for the later final verification phase.
See the [project checklist](../../docs/evals/deferred-live-verification.md) and
[attempt report](../../docs/evals/milestone-3-live-verification.md). HTTP 429 prevented
previous attempts from reaching semantic assertions; deferral, skipped execution and
offline fixture passes must never be reported as a live semantic pass.

See [Milestone 2 architecture and evaluation commands](../../docs/architecture/discovery-analysis.md).

Ten golden input/result fixtures live in `tests/fixtures/discovery_analysis.json`.
Offline tests validate review contracts and domain-context safeguards without making calls.
Live tests are separately marked `live_ai`, require `RUN_LIVE_AI_EVALS=1`, API credentials
and an explicitly configured model, and otherwise skip cleanly. They test behavior rather
than exact prose and are not proof of general model reliability.


### Challenge Mode

`tests/fixtures/challenge_analysis.json` adds eight cases: correlation/confounding,
stakeholder anecdote, confirmation-heavy inputs, shared-source reports, historical
freshness, independent mixed methods, competing price/relevance explanations and
solution-first framing. `test_challenge_golden.py` checks the same expectations offline
and with opt-in live models. Fixture passes establish schema/reference/semantic contracts,
not live model quality. The existing manual live workflow already discovers these tests.
Use `RUN_LIVE_AI_EVALS=0` for offline verification; CI explicitly uses that setting.
