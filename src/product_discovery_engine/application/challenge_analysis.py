"""Advisory challenge interpretation, isolated from deterministic evidence policy."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import AwareDatetime, BeforeValidator, ValidationError, model_validator

from product_discovery_engine.domain.assumptions import Assumption
from product_discovery_engine.domain.audit import (
    Actor,
    AuditEvent,
    AuditMetadata,
    AuditTarget,
    EventType,
    ObjectKind,
)
from product_discovery_engine.domain.common import DomainModel, Ordinal, ReferenceIds, Text
from product_discovery_engine.domain.evidence import EvidenceDirection
from product_discovery_engine.domain.validation_methods import ValidationMethod

from .discovery_analysis import AnalysisError, InvalidAnalysis, ProviderUnavailable
from .evidence_validation import KnowledgeState


def _require_true(value: object) -> Literal[True]:
    if value is not True:
        raise ValueError("AI/advisory markers must be the explicit boolean true")
    return True


TrueMarker = Annotated[Literal[True], BeforeValidator(_require_true)]


class ChallengeCategory(StrEnum):
    ALTERNATIVE_EXPLANATION = "alternative_explanation"
    CONTRADICTORY_EVIDENCE = "contradictory_evidence"
    SELECTION_BIAS = "selection_bias"
    SURVIVORSHIP_BIAS = "survivorship_bias"
    SAMPLE_BIAS = "sample_bias"
    MEASUREMENT_ERROR = "measurement_error"
    CONFOUNDING = "confounding"
    FALSE_CAUSALITY = "false_causality"
    NOVELTY_BIAS = "novelty_bias"
    SUNK_COST = "sunk_cost"
    STAKEHOLDER_BIAS = "stakeholder_bias"
    SOLUTION_FIRST = "solution_first"
    OVERLOOKED_RISK = "overlooked_risk"
    SHARED_SOURCE = "shared_source"
    FRESHNESS = "freshness"
    SCOPE_LIMITATION = "scope_limitation"
    CONFIRMATION_BIAS = "confirmation_bias"


class ChallengeProvenance(DomainModel):
    provider: Text
    model: Text
    prompt_version: Text


class ChallengeValidation(DomainModel):
    method: ValidationMethod
    rationale: Text


class ChallengeItem(DomainModel):
    id: Text
    category: ChallengeCategory
    challenge_statement: Text
    rationale: Text
    relevant_evidence_ids: ReferenceIds
    unresolved_counterargument: Text
    additional_evidence_required: tuple[Text, ...]
    severity: Ordinal
    recommended_validation: ChallengeValidation
    ai_generated: TrueMarker
    provenance: ChallengeProvenance


class ChallengeAnalysis(DomainModel):
    items: tuple[ChallengeItem, ...]
    contradicting_evidence_ids: ReferenceIds
    competing_explanations: tuple[Text, ...]
    disconfirming_evidence_required: tuple[Text, ...]
    source_scope_notes: Text
    limitations: tuple[Text, ...]
    advisory_only: TrueMarker

    @model_validator(mode="after")
    def validate_challenges(self) -> "ChallengeAnalysis":
        if not self.items or len({i.id for i in self.items}) != len(self.items):
            raise ValueError("challenge items must be present and uniquely identified")
        if not self.disconfirming_evidence_required or not self.limitations:
            raise ValueError("challenge mode must seek disconfirmation and expose limitations")
        return self


class ChallengeInput(DomainModel):
    hypothesis_statement: Text
    knowledge: KnowledgeState
    assumptions: tuple[Assumption, ...] = ()

    @model_validator(mode="after")
    def validate_assumptions(self) -> "ChallengeInput":
        if len({a.id for a in self.assumptions}) != len(self.assumptions):
            raise ValueError("challenge assumptions must be unique")
        return self


class ChallengeProvider(Protocol):
    provenance: ChallengeProvenance

    def analyze_challenges(self, request: ChallengeInput) -> ChallengeAnalysis: ...


class ChallengeRecord(DomainModel):
    id: UUID
    request: ChallengeInput
    result: ChallengeAnalysis
    analyzed_at: AwareDatetime
    provenance: ChallengeProvenance
    event: AuditEvent

    @model_validator(mode="after")
    def validate_record(self) -> "ChallengeRecord":
        validate_challenge_context(self.request, self.result, self.provenance)
        if any(q.assessed_at > self.analyzed_at for q in self.request.knowledge.quality):
            raise ValueError("challenge cannot precede the supplied knowledge assessment")
        if (
            self.event.event_type != EventType.CHALLENGE_COMPLETED
            or self.event.target != AuditTarget(kind=ObjectKind.CHALLENGE_ANALYSIS, id=self.id)
            or self.event.occurred_at != self.analyzed_at
            or self.event.metadata.related_ids != (self.request.knowledge.scope.hypothesis_id,)
        ):
            raise ValueError("challenge record must match audit")
        return self


def validate_challenge_context(
    request: ChallengeInput,
    result: ChallengeAnalysis,
    provenance: ChallengeProvenance,
) -> None:
    evidence_ids = {e.id for e in request.knowledge.evidence}
    contradicting = {
        e.id for e in request.knowledge.evidence if e.direction == EvidenceDirection.CONTRADICTS
    }
    if set(result.contradicting_evidence_ids) != contradicting:
        raise InvalidAnalysis("Challenge output must retain every contradictory evidence reference")
    for item in result.items:
        if not set(item.relevant_evidence_ids) <= evidence_ids:
            raise InvalidAnalysis("Challenge evidence references must come from supplied knowledge")
        if item.provenance != provenance:
            raise InvalidAnalysis(
                "Challenge provenance must identify the actual configured provider"
            )


class ChallengeAnalysisService:
    def __init__(self, provider: ChallengeProvider) -> None:
        self.provider = provider

    def analyze(self, request: ChallengeInput) -> ChallengeAnalysis:
        try:
            request = ChallengeInput.model_validate(request)
        except ValidationError:
            raise InvalidAnalysis("Malformed challenge input") from None
        try:
            result = ChallengeAnalysis.model_validate(self.provider.analyze_challenges(request))
        except AnalysisError:
            raise
        except ValidationError:
            raise InvalidAnalysis("Invalid structured challenge output") from None
        except Exception:
            raise ProviderUnavailable("Challenge provider failed") from None
        validate_challenge_context(request, result, self.provider.provenance)
        return result

    def analyze_record(
        self,
        request: ChallengeInput,
        *,
        actor: Actor,
        at: datetime,
        record_id: UUID,
        event_id: UUID,
    ) -> ChallengeRecord:
        return ChallengeRecord(
            id=record_id,
            request=request,
            result=self.analyze(request),
            analyzed_at=at,
            provenance=self.provider.provenance,
            event=AuditEvent(
                id=event_id,
                actor=actor,
                occurred_at=at,
                event_type=EventType.CHALLENGE_COMPLETED,
                target=AuditTarget(kind=ObjectKind.CHALLENGE_ANALYSIS, id=record_id),
                metadata=AuditMetadata(related_ids=(request.knowledge.scope.hypothesis_id,)),
            ),
        )
