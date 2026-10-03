"""Stable, credential-free inputs shared by Milestone 3 tests and evaluations."""

from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

from product_discovery_engine.application.evidence_validation import (
    EvidenceReviewInput,
    EvidenceValidationService,
    KnowledgeState,
)
from product_discovery_engine.domain.assumptions import (
    Assumption,
    AssumptionCategory,
    Importance,
    Uncertainty,
)
from product_discovery_engine.domain.audit import Actor, ActorKind
from product_discovery_engine.domain.common import Owner, Provenance, SourceReference, SourceType
from product_discovery_engine.domain.evidence import Evidence, EvidenceDirection, EvidenceTarget
from product_discovery_engine.domain.evidence_assessment import EvidenceScope, QualityInput
from product_discovery_engine.domain.evidence_origins import (
    EvidenceOrigin,
    OriginKind,
    OriginRelationship,
    link_origins,
)
from product_discovery_engine.domain.evidence_policy import (
    CoverageBasis,
    DirectnessBasis,
    EvidencePolicies,
    ReliabilityBasis,
)
from product_discovery_engine.domain.validation_methods import ValidationMethod
from product_discovery_engine.infrastructure.configuration import load_evidence_policies

AT = datetime(2026, 10, 3, tzinfo=UTC)
OWNER = Owner(id=UUID(int=1), display_name="Research owner")
ACTOR = Actor(kind=ActorKind.HUMAN, id="researcher", owner=OWNER)
HYPOTHESIS_ID = UUID(int=10)
ASSUMPTION_ID = UUID(int=20)
CLAIM_ID = UUID(int=30)


def policies() -> EvidencePolicies:
    return load_evidence_policies(Path(__file__).parents[1] / "config/evidence-policies.v1.toml")


def evidence(
    number: int = 1,
    *,
    target: EvidenceTarget = EvidenceTarget.PROBLEM_EXISTENCE,
    direction: EvidenceDirection = EvidenceDirection.SUPPORTS,
    reference: str | None = None,
    source_type: SourceType = SourceType.INTERVIEW,
    collected: date = date(2026, 10, 1),
    statement: str | None = None,
    population: str | None = "Study participants",
    claim_id: UUID | None = CLAIM_ID,
) -> Evidence:
    source = SourceReference(
        source_type=source_type, reference=reference or f"study:{number}", owner=OWNER
    )
    return Evidence(
        id=UUID(int=100 + number),
        hypothesis_id=HYPOTHESIS_ID,
        statement=statement
        or (
            "7 of 10 research participants struggled with product search"
            if direction == EvidenceDirection.SUPPORTS
            else "Research participants completed search successfully without assistance"
        ),
        source=source,
        collected_on=collected,
        target=target,
        target_claim_id=claim_id,
        target_assumption_id=ASSUMPTION_ID if target == EvidenceTarget.ASSUMPTION else None,
        population=population,
        direction=direction,
        methodology_notes="Moderated task study; convenience sample, no population estimate",
        provenance=Provenance(sources=(source,), ai_generated=False),
    )


def origin(
    item: Evidence,
    family: str | None = None,
    method: ValidationMethod = ValidationMethod.CUSTOMER_INTERVIEW,
) -> OriginRelationship:
    return link_origins(
        item,
        (
            EvidenceOrigin(
                id=uuid4(),
                kind=OriginKind.RESEARCH_STUDY,
                family_key=family or item.source.reference,
                source_reference=item.source.reference,
                method=method,
            ),
        ),
        rationale="Verified underlying source",
        actor=ACTOR,
        at=AT,
        event_id=uuid4(),
    )


def basis(item: Evidence) -> QualityInput:
    return QualityInput(
        scope=EvidenceScope.of(item),
        directness=DirectnessBasis.DIRECT_OBSERVATION,
        reliability=ReliabilityBasis.RIGOROUS_CHECKED_METHOD,
        coverage=CoverageBasis.BOUNDED_SAMPLE,
        rationale="Supports existence in this sample, not full-customer prevalence",
        methodology_basis="Reviewed observations, known convenience-sampling limitation",
        population_basis="Ten participants only; recruitment does not establish representativeness",
    )


def knowledge(
    items: tuple[Evidence, ...] = (),
    relationships: tuple[OriginRelationship, ...] = (),
    *,
    at: datetime = AT,
    previous: KnowledgeState | None = None,
    scope: EvidenceScope | None = None,
) -> KnowledgeState:
    scope = scope or (
        EvidenceScope.of(items[0])
        if items
        else EvidenceScope(
            hypothesis_id=HYPOTHESIS_ID,
            target=EvidenceTarget.PROBLEM_EXISTENCE,
            claim_id=CLAIM_ID,
            population="Study participants",
        )
    )
    return EvidenceValidationService(policies()).assess(
        scope,
        items,
        relationships,
        tuple(
            EvidenceReviewInput(evidence_id=e.id, basis=basis(e)) for e in items if scope.matches(e)
        ),
        actor=ACTOR,
        at=at,
        previous=previous,
    )


def assumption() -> Assumption:
    source = SourceReference(source_type=SourceType.STAKEHOLDER, reference="hypothesis:search")
    return Assumption(
        id=ASSUMPTION_ID,
        statement="Improving relevance changes the decision",
        category=AssumptionCategory.DESIRABILITY,
        importance=Importance.HIGH,
        uncertainty=Uncertainty.HIGH,
        owner=OWNER,
        provenance=Provenance(sources=(source,)),
    )
