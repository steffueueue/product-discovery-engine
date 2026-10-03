# Architecture and implementation plan

```
src/product_discovery_engine/
  domain/          # pure typed models, lifecycle, freshness, snapshot changes, audit
  application/     # future use cases, depending on domain abstractions
  ai/              # future interpretation adapters; no business rules in prompts
  infrastructure/  # TOML policy loading; future persistence/provider adapters
  presentation/    # future API/UI
config/            # versioned illustrative policy configuration
tests/            # unit, integration, evals, fixtures
docs/             # product specs, architecture, decisions, evals
```

Domain modules are focused files rather than a subpackage per entity; the current
size does not justify deeper nesting. No service framework, database or AI SDK is needed.
Infrastructure imports the domain; the domain never imports another architectural layer.
`domain/hypotheses.py` contains the snapshot models; `domain/hypothesis_changes.py`
contains material change functions and audit consistency validation. Configuration
infrastructure only reads TOML and delegates business-policy validation to the domain.

Milestone 0: establish packaging, commands, ignore rules, agent instructions, source
of truth and policy layout. Milestone 1: add immutable models, provenance, ownership,
explicit uncertainty, transition graph, freshness rules, versioned change results and
unit tests. Verify installation, build, tests, formatting, lint and strict typing.

Milestone 2 should first define application use cases and repository ports, then
transactional persistence for snapshots/audit events. Define approved gate requirements
before implementing readiness or prioritization. AI integration is a separate later step.
