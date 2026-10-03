# Milestone 2 verification and critical review

Implemented on `feat/discovery-analysis` from fetched remote main `60b9c0f`.

## Verification

- Complete offline suite: 409 passed; 10 explicitly opt-in live evaluations skipped.
- Ruff lint and formatting checks: passed.
- Strict mypy on src and tests: passed (33 source files).
- Wheel build without dependency resolution/build isolation: passed.
- pip dependency compatibility and git whitespace checks: passed.
- No Milestone 0–1 domain source changes.

## Critical review

The application has no provider-specific imports; domain import guards remain green.
OpenAI SDK use and configuration stay in infrastructure. Prompts describe interpretation
without implementing lifecycle, score, freshness or gate algorithms.

Review exposed a category-promotion risk: restating existing Evidence as FACT. The final
boundary accepts FACT only from supplied existing FACT claims, and EVIDENCE only from
supplied non-invalidated Evidence; exact source statements/citations are required. Raw
submission numbers and AI assumptions cannot enter these categories. No automatic
persistence or facts/evidence mapping exists. Assumption mapping always preserves
AI-generation provenance and rejects AI-summary-only sources.

Missing strategy rejects alignment/conflicts; available strategy references are checked
against configuration. Semantic alignment still requires human review. Assumption
recommendations remain qualitative and unscored.

Ten golden cases test public review contracts, not exact prose. Separate negative tests
exercise unsupported categories/numbers, citations, strategy invention, invalid references,
malformed input and structured output. SDK tests use real Responses parsing against mock
transport. Live reliability has not been measured in this environment; offline examples
cannot prove prompt quality or factual reasoning.

Residual risks: upstream FACT/source authenticity is caller-owned; quote matching does not
prove semantic entailment. Models can omit contradictions, make poor recommendations or
misinterpret strategy. Prompt injection resistance is an instruction, not a security proof.
Callers must retain records with accurate adapter metadata; storage/access policy and
context-budget management are deferred. Human review is essential.

Milestone 3 validation execution, evidence aggregation, readiness gates and new workflows
remain deferred. No Milestone 3–7 functionality was implemented.
