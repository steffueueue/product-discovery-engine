# ADR 0002: Review proposals behind a replaceable structured provider

Accepted for Milestone 2.

Keep AI interpretation in application DTOs rather than changing domain knowledge objects
or implementing autonomous lifecycle mutations. The application protocol returns a typed
DiscoveryAnalysis; orchestration revalidates it and checks input-source/category/strategy
references. OpenAI Responses structured output and configuration live in infrastructure;
versioned prompt instructions live in AI. The domain is unchanged.

Free-text claims cannot certify facts/evidence. Existing same-category domain sources can
be restated exactly; semantic interpretation remains explicitly generated and reviewable.
This deliberately favors incompleteness over unverified certainty, at the cost of requiring
review/source ingestion before text-only measurements become established knowledge.

No automatic persistence or evidence acceptance is added. Immutable AnalysisRecord retains
request/result and provenance metadata for future storage; explicit assumption mapping
preserves source history without implementing a new audited mutation workflow.
