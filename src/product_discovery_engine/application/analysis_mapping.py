"""Explicit assumption mapping; facts/evidence require a separate human review workflow."""

from uuid import UUID

from product_discovery_engine.domain.assumptions import Assumption
from product_discovery_engine.domain.common import Provenance, SourceType

from .analysis_models import AssumptionProposal
from .discovery_analysis import AnalysisInput, InvalidAnalysis


def map_assumption(proposal: AssumptionProposal, request: AnalysisInput, *, id: UUID) -> Assumption:
    """Caller supplies identity; mapping never persists, links or changes lifecycle."""
    proposal = AssumptionProposal.model_validate(proposal)
    request = AnalysisInput.model_validate(request)
    sources = [request.submission.source]
    for citation in proposal.citations:
        if citation.source_id == "submission":
            if citation.quote not in request.submission.original_text:
                raise InvalidAnalysis("Invalid assumption citation")
        else:
            evidence = next((e for e in request.evidence if str(e.id) == citation.source_id), None)
            fact = next((f for f in request.facts if str(f.id) == citation.source_id), None)
            if evidence is not None and citation.quote in evidence.statement:
                sources.extend(evidence.provenance.sources)
            elif (
                fact is not None
                and citation.quote in fact.statement
                and fact.provenance is not None
            ):
                sources.extend(fact.provenance.sources)
            else:
                raise InvalidAnalysis("Invalid assumption citation")
    if all(source.source_type == SourceType.AI_SUMMARY for source in sources):
        raise InvalidAnalysis("Underlying sources required for domain assumption mapping")
    return Assumption(
        id=id,
        statement=proposal.statement,
        category=proposal.category,
        importance=proposal.importance,
        uncertainty=proposal.uncertainty,
        provenance=Provenance(
            sources=tuple(dict.fromkeys(sources)),
            submission_ids=(request.submission.id,),
            ai_generated=True,
            interpretation_notes=proposal.rationale + " " + proposal.decision_relevance,
        ),
    )
