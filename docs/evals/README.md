# Discovery-analysis evaluations

See [Milestone 2 architecture and evaluation commands](../architecture/discovery-analysis.md).

Ten golden input/result fixtures live in `tests/fixtures/discovery_analysis.json`.
Offline tests validate review contracts and domain-context safeguards without making calls.
Live tests are separately marked `live_ai`, require `RUN_LIVE_AI_EVALS=1`, API credentials
and an explicitly configured model, and otherwise skip cleanly. They test behavior rather
than exact prose and are not proof of general model reliability.
