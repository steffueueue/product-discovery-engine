# Milestones 0–1 validation

Validated locally with Python 3.12.14 and the versions in `requirements-dev.lock`.

- Pytest: 367 passed, no skipped tests. Includes 196 lifecycle pairs, immutable
  submissions/snapshots, claim categories, provenance, ownership, freshness boundaries,
  invalid models, qualitative assumptions, version changes and immutable audit records.
- Integration checks load the actual TOML policy example and reject falsely configured
  deferred scoring. Domain import checks guard the architectural boundary.
- Ruff lint and formatting checks passed.
- Strict Mypy passed across 26 Python source/test files.
- Editable installation, wheel and source-distribution builds, and `pip check` passed.
- Rebuilding a wheel from the source distribution yielded identical wheel file contents,
  including the typing marker.
- Installed the wheel with pinned dependencies in a fresh virtual environment;
  all 367 tests passed against that installed artifact as well.
- Repeated the saved cloud installation script successfully.

The GitHub Actions workflow contains the corresponding checks; remote execution
has not been observed. AI evaluations are unimplemented and were not run.
No external AI call, API credential, persistence service or UI is involved.

The lifecycle graph is provisional and does not enforce readiness gates. Snapshots
and events are returned to callers; durable retention, atomic transactions, cross-object
referential integrity, optimistic concurrency and override authorization remain future
work. Freshness thresholds in the example are illustrative. No production strategy,
scoring or delivery policy is claimed to be configured.

The deliberate structural adjustment is to use focused domain modules under one
package rather than nesting a package for every entity. Milestone 2 is not implemented.
Critical reviews added 108 behavior/regression cases to the original 259 tests.
Review against the product specification and AGENTS.md identified and fixed:

- Missing evidence UUIDs in evidence-addition audit records.
- Inconsistent snapshot/audit payloads and falsely reported material field changes.
- Naive datetime comparison errors and retroactive links to future evidence snapshots.
- Missing explicit classification/validation of AI summaries as non-primary sources.
- Missing AI-origin information incorrectly defaulting to non-AI authorship.
- Duplicate references and coercion of non-integer values into version counters.
- Missing configuration file, malformed TOML and invalid-policy regression checks.

Reduced unnecessary complexity by replacing the inherited wildcard timestamp validator,
removing unused mutation parameters/manual changed-field metadata, sharing reference
uniqueness validation and separating snapshot models from audited change operations.
The infrastructure adapter contains only TOML I/O and delegates policy rules to the domain;
no business logic leak was found. The import guard now checks nested domain packages,
permits domain absolute imports and rejects storage/network/framework dependencies.

The latest review added 17 focused cases and sealed unsupported mutation event labels,
checked assumption-target associations, rejected exact duplicate provenance entries and
non-string original text, and made invalid lifecycle input errors explicit. A serialized
multi-step history test verifies material reconstruction using retained typed snapshots.
Read [the ten-area domain review](milestone-0-1-domain-review.md) for detailed assessments,
test-quality analysis and remaining architectural risks.

Recommended next task: application repository ports and transactional persistence of
versioned hypothesis snapshots and audit events, with approved gate requirements.
