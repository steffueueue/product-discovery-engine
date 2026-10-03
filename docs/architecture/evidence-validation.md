# Milestone 3: evidence and validation

Milestone 3 adds a deterministic knowledge layer and advisory Challenge Mode to the
existing modular monolith. It does not decide whether to pursue or deliver a product.
The public entry points are `EvidenceValidationService`, the domain validation
functions, `assess_assumption_risk`, and `ChallengeAnalysisService`.

## Boundaries and retained records

- **Domain:** immutable evidence scopes, source origins, policy models, five-dimension
  quality, freshness assessments, source/method triangulation, assumption risk,
  validation snapshots/results and matching audits. No SDK, storage or environment I/O.
- **Application:** assembles a scoped `KnowledgeState` from explicit reviewer inputs;
  coordinates advisory challenge providers and checks references and provenance.
- **AI:** versioned challenge instructions. No evidence rubric or lifecycle policy.
- **Infrastructure:** validated TOML loading and a dedicated OpenAI Responses challenge
  adapter using existing `OPENAI_API_KEY` / `DISCOVERY_ANALYSIS_MODEL` conventions.
- **Presentation/storage:** remain deferred. Callers must retain complete returned
  records, previous knowledge states, referenced source artifacts and policy versions.

Changes produce immutable records rather than mutate objects. Invalidation retains
both evidence snapshots. Validation changes retain before/after activity snapshots;
recording a result retains the activity/criteria snapshot, prior/generated evidence,
before/after assumption and separate completion/result audits. Freshness records retain
previous/current assessments. Quality, risk and challenges are append-only assessments
with audit references. These records support reconstruction when persisted together;
this milestone does not supply a database or guarantee transactions across callers.
Unchecked Pydantic `model_copy`/`model_construct` are not approved mutation APIs.

## Quantity and quality

The versioned rubric is `config/evidence-policies.v1.toml`. TOML matches the existing
configuration architecture and adds no dependencies. Tables load into immutable typed
fields, require complete definitions and reject extra entries, missing versions,
invalid thresholds, nonmonotonic risk/quality rules and prevalence caps above LOW.

Ratings are VERY_LOW, LOW, MEDIUM, HIGH, VERY_HIGH. They are ordered categories,
not probabilities or numerical measurements. Unavailable directness, reliability or
coverage is `None`; aggregate quality then remains unknown, with an explanation.

| Dimension | Reviewer input / deterministic basis | Meaning |
| --- | --- | --- |
| Directness | belief, indirect proxy, reported experience, direct observation, direct measurement | Relationship to **this specific claim and target**, not an intrinsic source rank |
| Reliability | major errors, undocumented method, documented limitations, reviewed method, rigorous checked method | Methodology, instrumentation, sampling design, integrity and limitations |
| Coverage | single account, convenience sample, bounded sample, representative segment/population | Representation of the **named population** |
| Recency | CURRENT / REVIEW_DUE / STALE / INVALIDATED | Applicability and review status from deterministic freshness policy |
| Independence | unknown, shared family, traceable origin, distinct family | Explicit underlying-source relationships in the relevant scoped context |

The initial directness/reliability/coverage ladders map to the five ordinal levels in
order. Recency maps to VERY_HIGH/MEDIUM/LOW/VERY_LOW. Independence maps to
VERY_LOW/LOW/MEDIUM/HIGH. The aggregate is the **weakest dimension**; no count bonus,
weighted average, decimal score or fake probability is computed. This deliberately
conservative assessment exposes every dimension and its input rationale. It is not a
truth verdict. Adding duplicate reports can reveal lower independence; it cannot raise
quality. Adding verified distinct source families can change independence because of
new provenance information, never merely because the item count increased.

Reliability never depends on `SourceType`. A rigorously conducted qualitative interview
study can have VERY_HIGH reliability. Poor analytics instrumentation can have VERY_LOW
reliability. High reliability does not resolve weak coverage or indirectness.

Reviewer basis is an accountable assertion, not automatic semantic certification. A
causal target requires a causally informative method; simply labeling observational
correlation "direct measurement" does not make it causal proof. Keep this limitation
visible during review. The application accepts explicit review inputs, not automatic
acceptance of Milestone 2 AI proposals.

## Targets and population safeguards

A Milestone 3 `EvidenceScope` requires a hypothesis plus an explicit claim or assumption
reference, exact target and population (unknown population is `None`). Targets include
problem existence, segment, frequency, severity, reach, desirability, user value,
behavior, usability, feasibility, viability, economics, business impact and causal
mechanism. Existing Milestone 1 target values remain compatible; there are no automatic
aliases or promotions. Legacy evidence needs an explicit claim association before using
this assessment layer. Existing Milestone 1 freshness and Milestone 2 behavior are retained.

Every aggregation matches the entire scope exactly. Evidence about existence does not
establish reach, economics, causality or solution suitability. Different claims or
populations never cross-validate. Assumption evidence requires that specific assumption.
Nonrepresentative single/convenience/bounded samples are capped at LOW coverage for
reach/frequency claims even if methodology is rigorous. Seven of ten participants can
support a problem in the studied sample; it does not imply that 70% of all customers
experience the problem. No population percentage is calculated.

## Freshness

The four states are CURRENT, REVIEW_DUE, STALE, INVALIDATED. Default v1 thresholds are
90 elapsed whole days for review and 365 for staleness, inclusive, measured from the
last review or collection. Named contexts can override thresholds. The `historical`
context asks for review after 180 days and never automatically marks historical evidence
STALE; it is retained as REVIEW_DUE even after its 730-day threshold.

`collected_on` is the existing collection date. `valid_from` prevents evaluation before
applicability; it does not reset collection age. `review_after` can trigger an earlier
review, unless an explicit review occurred on or after that date. Explicit invalidation
takes precedence, including over future applicability metadata. Future snapshots and
naive timestamps are rejected; comparisons use UTC calendar days. Reasons explain the
threshold, review date or invalidation. Stale evidence is retained; age does not make a
historical observation false. Each initial assessment/state transition produces a
freshness audit; same-state reassessments retain before/after records without a duplicate
state-change event. Calling `invalidate_evidence` emits a separate invalidation audit.

## Source independence and triangulation

`EvidenceOrigin` identifies an underlying dataset, experiment, research/interview study,
ticket corpus, survey or source artifact. Its stable `family_key` is the canonical
underlying-source identity; its reference, kind and constrained method are retained.
`link_origins` records actor, reason, timestamp and origins in an audited relationship.

Grouping merges shared family keys, shared underlying references, overlapping non-AI
provenance and transitive overlaps. Changing report labels, source types or source owners
cannot make a reused dataset independent. A derived artifact combining two origins
bridges their groups conservatively. Unmapped evidence remains visible but does not
certify independence. Conflicting snapshots of the same origin ID and duplicate
relationship/evidence IDs fail. Reviewers remain responsible for canonical origin
identity: the system cannot discover undeclared overlap in external artifacts.

Triangulation reports relevant item count, traceable independent groups, methods,
supporting/contradicting groups and invalidated references. Distinct methods must match
to distinct groups; multiple methods applied to one corpus cannot inflate diversity.
The initial policy requires three independent groups and three distinct methods for
TRIANGULATED. Other categories are NO_EVIDENCE, UNRESOLVED_ORIGINS, SINGLE_SOURCE,
MULTIPLE_SOURCES and MIXED_UNRESOLVED. Mixed active evidence never forces a winner;
a group containing both directions appears in both lists. Pure disconfirmation can also
have independent triangulation; direction does not privilege support. Invalidated items
remain in the knowledge state and explicit history, but cannot provide active confirmation.
Structural triangulation does not calculate a combined quality score or certify truth,
causality, economic impact or a product decision. Stale items remain visible with low
recency; structural diversity must be read alongside their quality and freshness.

Reassessment rejects dropping earlier evidence, changing its statement/provenance under
the same ID, reversing invalidation or moving review dates backwards. Referenced object
existence and authorization remain future repository/application responsibilities.

## Assumption risk

Decision impact and unresolved uncertainty use the same five ordinal levels; unknown
inputs give unknown risk. Risk comes from an explicit, validated monotonic 5×5 policy
lookup, not multiplication of probabilities. Reviewer rationale describes how assumption
failure would change the decision. Relevant support, contradiction, invalidation history
and evidence gaps are retained. Uncertainty is an explicit accountable assessment; it is
not inferred from item count. A barely consequential assumption with no evidence can be
LOW risk while a consequential, still-uncertain assumption with several evidence items
is VERY_HIGH risk. Costs do not determine risk or expected information gain.

## Validation activities and results

Activities store hypothesis/assumption, constrained method (the existing eighteen
Milestone 2 methods), rationale, required inputs, predefined distinct success/failure
signals, ordinal expected information gain, relative cost/speed, accountable owner,
dependencies, status, timestamps, snapshot version and criteria version.

| Status | Allowed next statuses |
| --- | --- |
| PLANNED | READY, CANCELLED |
| READY | RUNNING, CANCELLED |
| RUNNING | COMPLETED, CANCELLED |
| COMPLETED / CANCELLED | none |

READY/RUNNING require completed dependency references supplied by the application.
No self, skipped, reverse or terminal transitions are valid. Readiness is a validation
activity state only; it does not implement Delivery Readiness or any discovery gate.

`record_validation_result` completes a running activity and binds the result to the
exact tested assumption and criteria version. Conclusions are SUPPORTED,
PARTIALLY_SUPPORTED, INCONCLUSIVE and CONTRADICTED. Effects are support, contradiction,
mixed or neutral; incompatible conclusions/effects and wrong evidence targets fail.
Mixed effects retain evidence in both directions. Directional conclusions require new
evidence; inconclusive results can record learning without new directional evidence.
Generated IDs must be distinct from all prior evidence. Original evidence is appended
alongside new observations, never deleted or rewritten. Assumption content and earlier
links remain intact. A contradicted assumption is retained as REFUTED. Partial support
maps conservatively to INCONCLUSIVE in the existing Milestone 1 validation-state enum.
This per-test conclusion does not erase historical mixed evidence or establish global
consensus. The returned recording must be saved atomically by a future persistence layer.

Criteria must be stored before running/interpreting results. Revisions require actor
and nonempty reason, increment material and criteria versions, retain old/new signals
and emit an audit. Revisions after completion explicitly say "Post-hoc". An earlier
result retains the criteria snapshot/version that it actually tested. It cannot be
silently reinterpreted against revised criteria or recorded again on a terminal activity.

## Challenge Mode and confirmation-bias safeguards

Challenge Mode asks: **What credible evidence or alternative explanation suggests that
we should NOT pursue this opportunity?** The provider may propose alternative
explanations, contradictory evidence, selection/survivorship/sample bias, measurement
error, confounding, false causality, novelty bias, sunk costs, stakeholder bias,
solution-first framing and overlooked risks. Explicit additional categories cover shared
sources, freshness, scope limits and confirmation bias.

Each typed `ChallengeItem` contains statement, rationale, relevant evidence references,
unresolved counterargument, required additional evidence, ordinal severity, a constrained
validation recommendation, an AI marker and provider/model/prompt provenance. The result
also preserves contradictions, competing explanations, disconfirming evidence needs,
source/scope notes and limitations. A completed record retains full input/output,
provenance and an audit. References must be from supplied knowledge and every
contradictory item, even invalidated history, must remain visible. Provider failures are
sanitized. Prompts treat input/source content as data, including embedded instructions.

AI does not set evidence ratings, freshness, triangulation, accepted knowledge,
validation states or final product decisions. Those fields are absent/rejected by the
challenge schema; `advisory_only` must be true. Severity and recommended validation are
advisory interpretation. They are not assumption-risk policy output. No autonomous
agents, orchestration, RAG, vector database, microservice or decision gate is introduced.

The safeguards therefore include both directions in knowledge, dedicated disconfirmation
search, contradictory results, retained refuted assumptions and rejected evidence
removal. Semantic truth still requires accountable review; structural checks cannot prove
that an AI explanation is credible or stop all subtle bias in prose.

## End-to-end search example

Run the credential-free synthetic example:

```sh
.venv/bin/python examples/evidence_validation.py
```

1. A scoped study records seven of ten participants struggling to find relevant products.
   Reliability may be strong; coverage is bounded, and causal/reach targets remain unknown.
   One traceable source is SINGLE_SOURCE, not triangulated.
2. Two more reports from the same study would still be one source family. The shared-source
   tests demonstrate this explicitly; they add no independent confirmation or quality bonus.
3. Separate interviews, behavioral observations and support collections add verified
   independent families/methods. The example becomes TRIANGULATED for scoped problem
   existence; per-item quality remains MEDIUM because coverage is still bounded.
4. The assumption "relevance is the principal cause of abandonment" remains unresolved.
   Problem-existence evidence does not enter its causal risk assessment. The configured
   HIGH impact/HIGH uncertainty combination is HIGH risk, with an explicit causal gap.
5. A controlled comparison is planned with success/failure signals before it runs. A
   synthetic result favors price and contradicts that assumption. It appends evidence,
   completes the activity, retains the old assumption and records REFUTED plus audits.
6. Challenge Mode can review this scoped knowledge through its provider boundary. Offline
   case G preserves price/relevance as competing explanations; case F recognizes structural
   triangulation while retaining reach/causality limitations. No final decision follows.

## Verification and limits

Unit tests cover policies, dimensions, targets, time, origins, method matching, both
evidence directions, risk, lifecycle, criteria history and result integrity. Eight
challenge golden cases cover causality/confounding, stakeholder anecdotes, confirmation,
shared-source pseudo-triangulation, old evidence, strong mixed methods, competing price
explanations and solution-first framing. The same expectations are used for opt-in live
runs. Offline fixture checks verify contracts, not actual model quality; semantic checks
are representative categories/content checks, not a factual reliability certificate.

Use `RUN_LIVE_AI_EVALS=0` for the full offline suite. Standard CI explicitly sets that
flag and needs no credentials. The existing manual `live-ai-evals.yml` already runs all
`tests/evals` live-marked cases, including the new Challenge Mode cases; there is no
second workflow. Live model choice and API key remain secret/environment configuration.
The new adapter is tested with fake Responses calls and no real key.
Paid live verification is intentionally deferred by project decision to a later final
phase and is not required for milestone completion or merge. The 18 live tests remain
unchanged and opt-in; their HTTP 429 attempt results do not establish semantic quality.
See the [project checklist](../evals/deferred-live-verification.md) for later execution.

Known risks: imperfect reviewer basis and origin identity; conservative source-overlap
merging; manual dependency completion attestations; no storage, scheduling, authorization,
transaction or source-authenticity guarantee; and potentially incomplete AI counterarguments.
Future persistence must retain snapshots and audits together. Keep policy versions with
records when changing a rubric. Freshness contexts are explicit reviewer configuration,
not automatic semantic detection. Large-scale performance is not assessed here.

Milestone 4 explicitly remains deferred: **Discovery Priority, Delivery Readiness,
Discovery Gate**. Portfolio selection, specification generation, delivery gates,
implementation records and outcome measurement also remain deferred.
