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

## Final review and synchronization

Merged latest `origin/main` (`e1014b0`) into the existing analysis branch without
rebasing or resolving a merge conflict. Main had added the identical live-evaluation
workflow at the nested path `.github/workflows/.github/workflows/live-ai-evals.yml`.
Removed that duplicate; `.github/workflows/live-ai-evals.yml` remains unchanged.
All existing Milestone 2 application code, tests, dependencies and the correctly
located workflow remain intact. No domain or application source fixes were required.

Final offline verification on the synchronized tree:

- `env -u OPENAI_API_KEY -u RUN_LIVE_AI_EVALS .venv/bin/python -m pytest`:
  409 passed, 10 opt-in live evaluations skipped.
- `.venv/bin/ruff check .`: passed.
- `.venv/bin/ruff format --check .`: passed; 47 files already formatted.
- `.venv/bin/mypy src tests`: passed; 33 source files.
- `.venv/bin/python -m pip wheel . --no-deps --no-build-isolation --wheel-dir dist`:
  built `product_discovery_engine-0.1.0-py3-none-any.whl` successfully.
- `.venv/bin/python -m pip check`: no broken requirements.
- `git diff --check`: passed.

The final specification review confirmed provider-independent domain/application
boundaries, separate knowledge categories, rejection of unsupported numeric evidence,
explicit AI assumption provenance, missing-strategy guards, contradiction representation
with competing explanations, and schema validation. Correlation/causation separation is
covered by prompt instructions and evaluation examples; semantic correctness still
requires human review and is not certified by structural validation.

The project owner confirmed that live AI evaluations already passed in GitHub Actions;
they were not rerun. The Actions run listing available during this task exposed only
Python quality runs, so no independent live-run URL was available for this report.
Residual risks above remain unchanged. Milestone 3 remains explicitly deferred.
