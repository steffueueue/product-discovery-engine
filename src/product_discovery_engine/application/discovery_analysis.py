"""Provider-neutral orchestration and deterministic provenance checks."""

from typing import Protocol

from pydantic import AwareDatetime, ValidationError, model_validator

from product_discovery_engine.domain.claims import Claim, ClaimKind
from product_discovery_engine.domain.common import DomainModel, Text, Unknown
from product_discovery_engine.domain.evidence import Evidence
from product_discovery_engine.domain.policies import StrategyPolicy
from product_discovery_engine.domain.submissions import Submission

from .analysis_models import AssumptionProposal, ClaimProposal, DiscoveryAnalysis


class AnalysisError(Exception):
    """Safe application error; provider payloads must not escape this boundary."""


class InvalidAnalysis(AnalysisError):
    pass


class ProviderUnavailable(AnalysisError):
    pass


class AnalysisConfigurationError(AnalysisError):
    pass


class AnalysisInput(DomainModel):
    submission: Submission
    strategy: StrategyPolicy | None = None
    evidence: tuple[Evidence, ...] = ()
    facts: tuple[Claim, ...] = ()

    @model_validator(mode="after")
    def validate_sources(self) -> "AnalysisInput":
        if any(f.kind != ClaimKind.FACT for f in self.facts):
            raise ValueError("fact context requires existing FACT claims")
        ids = [e.id for e in self.evidence] + [f.id for f in self.facts]
        if len(ids) != len(set(ids)):
            raise ValueError("context source IDs must be unique")
        return self


class AnalysisProvider(Protocol):
    def analyze(self, request: AnalysisInput) -> DiscoveryAnalysis: ...


class AnalysisRecord(DomainModel):
    request: AnalysisInput
    analyzed_at: AwareDatetime
    provider: Text
    model: Text
    prompt_version: Text
    result: DiscoveryAnalysis


class DiscoveryAnalysisService:
    def __init__(self, provider: AnalysisProvider) -> None:
        self.provider = provider

    def analyze(self, request: AnalysisInput) -> DiscoveryAnalysis:
        try:
            request = AnalysisInput.model_validate(request)
        except ValidationError:
            raise InvalidAnalysis("Malformed analysis input") from None
        try:
            result = DiscoveryAnalysis.model_validate(self.provider.analyze(request))
        except AnalysisError:
            raise
        except ValidationError:
            raise InvalidAnalysis("Invalid structured analysis") from None
        except Exception:
            raise ProviderUnavailable("Analysis provider failed") from None
        validate_context(request, result)
        return result

    def analyze_record(
        self,
        request: AnalysisInput,
        *,
        analyzed_at: AwareDatetime,
        provider: str,
        model: str,
        prompt_version: str,
    ) -> AnalysisRecord:
        """Caller retains the full immutable record; metadata must identify the adapter used."""
        return AnalysisRecord(
            request=request,
            analyzed_at=analyzed_at,
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            result=self.analyze(request),
        )


def validate_context(request: AnalysisInput, result: DiscoveryAnalysis) -> None:
    """Source anchoring is a structural guard, not a factual truth certificate."""
    sources = {"submission": request.submission.original_text}
    established = {str(e.id): e.statement for e in request.evidence if e.invalidated_on is None}
    existing_facts = {str(f.id): f.statement for f in request.facts}
    sources.update({str(e.id): e.statement for e in request.evidence})
    sources.update(existing_facts)
    claims = result.facts + result.evidence + result.inferences + result.unknowns
    items: tuple[ClaimProposal | AssumptionProposal, ...] = (*claims, *result.assumptions)
    for item in items:
        for citation in item.citations:
            if (
                citation.source_id not in sources
                or citation.quote not in sources[citation.source_id]
            ):
                raise InvalidAnalysis("Citation does not match supplied source")
    # Preserve supplied knowledge categories; neither submissions nor evidence become facts.
    for group, allowed in ((result.facts, existing_facts), (result.evidence, established)):
        for claim in group:
            if not claim.citations or not any(
                c.source_id in allowed and claim.statement == allowed[c.source_id]
                for c in claim.citations
            ):
                raise InvalidAnalysis(
                    "Facts/evidence require existing domain evidence or same-kind claims"
                )
    fit = result.strategic_fit
    strategy = request.strategy
    if strategy is None or isinstance(strategy.objective, Unknown):
        if (
            fit.status != "insufficient_strategy_context"
            or fit.objective_ids
            or fit.potential_alignment
            or fit.potential_conflicts
        ):
            raise InvalidAnalysis("Strategy context is unavailable")
    elif fit.status == "preliminary":
        if fit.objective_ids != (strategy.reference.id,):
            raise InvalidAnalysis("Strategy references must match configured strategy")
    elif fit.objective_ids or fit.potential_alignment or fit.potential_conflicts:
        raise InvalidAnalysis("Insufficient strategy cannot assert alignment")
