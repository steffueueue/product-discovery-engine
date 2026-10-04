# ADR 0005: AI proposes; accountable humans create DeliverySpec versions

Status: Accepted for Milestone 5.

## Context

Discovery knowledge maturity does not determine which initiative to build or what software
requirements to accept. A Discovery Gate PASS establishes candidacy only. Converting
observations directly into architecture, metrics or authoritative requirements would
conceal uncertainty and merge three independent product decisions.

Specification drafting benefits from AI organization and proposed wording. It also adds
semantic risks: unsupported numeric targets, invented interfaces/references, problem-to-
solution leaps and lost provenance after human acceptance. The existing architecture
already separates advisory AI interpretation from deterministic domain mutations.

## Decision

Record explicit accountable human DeliverySelection against exact retained candidacy.
Require that dedicated operation for `selected_for_delivery`; block generic transitions.

AI returns immutable, schema-validated, context-bound DeliverySpec proposals. Provider,
model and prompt provenance and full input/output remain retained. Human review explicitly
accepts or rejects every item with actor, timestamp and rationale. Separate deterministic
human materialization produces authoritative DRAFT versions. AI cannot select delivery work,
accept requirements, mutate specs, declare completeness or authorize implementation.

Typed specification items distinguish exact source-backed restatements, explicit human
decisions, AI proposals and unknowns. Every reference must exist in supplied context.
Evidence informs problems; it does not establish solution requirements. Accepted AI wording
retains AI origin and original proposal/review history. New human decisions are separately
recorded rather than disguised as discovered facts. Conservative grounding and numeric/
interface safeguards live in code, not solely prompts.

Allow deliberately incomplete drafts. Preserve absent solution, unknown endpoint, latency,
retention and other unresolved delivery details explicitly. Material changes produce
consecutive immutable versions with before/after snapshots, reasons, actors, changed item
IDs and supersession audits. Existing item identities cannot be silently reworded.

Completeness, gap classification, targeted clarifications, delivery readiness and Delivery
Gate are separate Milestone 6 capabilities. Enum compatibility does not authorize them.
No completeness logic or implementation authorization is added in Milestone 5.

## Alternatives

- **Direct AI-to-spec mutation:** rejected because generation would imply acceptance and
  silently elevate ungrounded proposals. It would hide who selected and accepted work.
- **Generic lifecycle promotion:** rejected because it bypasses exact candidacy and human
  accountability even if the historical stage graph has a selection edge.
- **One untyped requirements dictionary:** rejected because it loses item type, scope,
  provenance, unknowns and review traceability.
- **Require a complete spec before creation:** rejected because it encourages fabricated
  values and conflates drafting with the deferred completeness/Delivery Gate workflow.
- **Event sourcing or durable storage now:** rejected as unnecessary for reconstructable
  immutable snapshots. Transactional current-state enforcement remains a future boundary.

## Consequences

Manual drafting remains provider-free. The optional adapter follows existing OpenAI
configuration and structured-output conventions; credential-free CI uses fakes/mock
transport, and existing opt-in live tests are preserved. Paid semantic verification remains
unverified and intentionally deferred, with new future checks documented.

Human review and record retention are required. Exact source restatement and lexical guards
are conservative and may reject useful paraphrases/numeric identifiers; human decisions can
supply explicit intended content. They do not prove source truth or arbitrary semantic
entailment. Full records may grow and contain sensitive text; future storage must implement
retention/access controls, unique IDs, atomic version checks and concurrency protection.
