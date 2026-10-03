# Working agreements
Read docs/product-specs/discovery-prioritization-system-v0.1.md before material domain changes.
Work milestone by milestone; do not implement deferred workflows without authorization.
Preserve domain, application, AI, infrastructure, and presentation boundaries.
The domain must remain independent of AI providers, UI, storage, and HTTP frameworks.
Keep deterministic business rules out of prompts. Never turn assumptions into facts.
Represent unavailable information explicitly as unknown. Preserve contradictory evidence and provenance.
Preserve original submissions, historical hypothesis versions, and immutable audit events.
Run `.venv/bin/python -m pytest`, `.venv/bin/ruff check .`,
`.venv/bin/ruff format --check .`, and `.venv/bin/mypy src tests` before completing changes.
Use the existing checkout in the isolated cloud environment; do not create a worktree unless requested.
Avoid unnecessary multi-agent architecture, agent frameworks, microservices, and generic abstractions.
Never commit credentials or call live AI services in domain tests.
