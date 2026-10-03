# Discovery-analysis evaluations

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
