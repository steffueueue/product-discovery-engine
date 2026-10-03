# Discovery-analysis evaluations

Paid live-model verification is intentionally deferred by project decision to a later
final phase. Do not run live evaluations during current development. It is not required
for normal CI, milestone completion or merge. `OPENAI_API_KEY` is optional for normal
development; offline deterministic and AI contract/golden tests require no paid access.
The [deferred verification checklist](deferred-live-verification.md) distinguishes the
three layers and tracks all 18 existing live cases for later execution. Deferred or
skipped live checks must never be represented as a live semantic pass.

See [Milestone 2 architecture and evaluation commands](../architecture/discovery-analysis.md).

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

The [Milestone 3 live verification report](milestone-3-live-verification.md) records the
actual dispatched GitHub runs. The latest run is infrastructure-blocked by HTTP 429 on
all 18 cases; it does not establish live semantic quality. Safe adapter diagnostics now
expose HTTP status and allowlisted codes without raw provider payloads.
The unchanged live tests and manual workflow remain available for the later phase.
