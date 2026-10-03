"""Synthetic example: run `python examples/evidence_validation.py`; no network calls."""

from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

from product_discovery_engine.application.evidence_validation import (
    EvidenceReviewInput,
    EvidenceValidationService,
)
from product_discovery_engine.domain.assumption_risk import assess_assumption_risk
from product_discovery_engine.domain.assumptions import (
    Assumption,
    AssumptionCategory,
    Importance,
    Uncertainty,
)
from product_discovery_engine.domain.audit import Actor, ActorKind
from product_discovery_engine.domain.common import (
    Ordinal,
    Owner,
    Provenance,
    SourceReference,
    SourceType,
)
from product_discovery_engine.domain.evidence import Evidence, EvidenceDirection, EvidenceTarget
from product_discovery_engine.domain.evidence_assessment import EvidenceScope, QualityInput
from product_discovery_engine.domain.evidence_origins import (
    EvidenceOrigin,
    OriginKind,
    link_origins,
)
from product_discovery_engine.domain.evidence_policy import (
    CoverageBasis,
    DirectnessBasis,
    ReliabilityBasis,
)
from product_discovery_engine.domain.validation import (
    RelativeCost,
    RelativeSpeed,
    ValidationActivity,
    ValidationConclusion,
    ValidationEffect,
    ValidationResult,
    ValidationStatus,
    create_validation_activity,
    record_validation_result,
    transition_validation_activity,
)
from product_discovery_engine.domain.validation_methods import ValidationMethod
from product_discovery_engine.infrastructure.configuration import load_evidence_policies


def main() -> None:
    at = datetime(2026, 10, 3, tzinfo=UTC)
    owner = Owner(id=UUID(int=1), display_name="Example research owner")
    actor = Actor(kind=ActorKind.HUMAN, id="example-reviewer", owner=owner)
    policies = load_evidence_policies(
        Path(__file__).parents[1] / "config/evidence-policies.v1.toml"
    )
    service = EvidenceValidationService(policies)
    items = []
    relationships = []
    reviews = []
    for number, source_type, method, statement in (
        (
            1,
            SourceType.INTERVIEW,
            ValidationMethod.CUSTOMER_INTERVIEW,
            "7 of 10 study participants struggled to find relevant products",
        ),
        (
            2,
            SourceType.ANALYTICS,
            ValidationMethod.BEHAVIORAL_ANALYTICS,
            "Observed sample sessions include repeated query reformulations and exits",
        ),
        (
            3,
            SourceType.SUPPORT,
            ValidationMethod.SUPPORT_TICKET_ANALYSIS,
            "Reviewed support cases describe difficulty finding relevant products",
        ),
    ):
        source = SourceReference(
            source_type=source_type, reference=f"example:source:{number}", owner=owner
        )
        item = Evidence(
            id=UUID(int=100 + number),
            hypothesis_id=UUID(int=10),
            statement=statement,
            source=source,
            collected_on=date(2026, 10, 1),
            target=EvidenceTarget.PROBLEM_EXISTENCE,
            target_claim_id=UUID(int=30),
            population="Studied customers",
            direction=EvidenceDirection.SUPPORTS,
            methodology_notes="Synthetic bounded sample",
            provenance=Provenance(sources=(source,), ai_generated=False),
        )
        items.append(item)
        relationships.append(
            link_origins(
                item,
                (
                    EvidenceOrigin(
                        id=uuid4(),
                        kind=OriginKind.DATASET,
                        family_key=f"independent-example:{number}",
                        source_reference=source.reference,
                        method=method,
                    ),
                ),
                rationale="Separate underlying collection confirmed for this example",
                actor=actor,
                at=at,
                event_id=uuid4(),
            )
        )
        reviews.append(
            EvidenceReviewInput(
                evidence_id=item.id,
                basis=QualityInput(
                    scope=EvidenceScope.of(item),
                    directness=DirectnessBasis.DIRECT_OBSERVATION,
                    reliability=ReliabilityBasis.REVIEWED_METHOD,
                    coverage=CoverageBasis.BOUNDED_SAMPLE,
                    rationale="Problem existence in the studied sample only",
                    methodology_basis="Reviewed methodology with documented selection limits",
                    population_basis="No representative population sampling",
                ),
            )
        )
    scope = EvidenceScope.of(items[0])
    first = service.assess(
        scope, (items[0],), (relationships[0],), (reviews[0],), actor=actor, at=at
    )
    combined = service.assess(
        scope,
        tuple(items),
        tuple(relationships),
        tuple(reviews),
        actor=actor,
        at=at,
        previous=first,
    )
    print("One source:", first.triangulation.category.value)
    print("Independent mixed methods:", combined.triangulation.category.value)
    print(
        "Per-item quality:",
        [q.aggregate.value if q.aggregate else "unknown" for q in combined.quality],
    )
    print("Population reach and causality: unknown; the scope is problem existence only")

    assumption_source = SourceReference(
        source_type=SourceType.STAKEHOLDER, reference="example:causal-claim"
    )
    assumption = Assumption(
        id=UUID(int=20),
        statement="Relevance is the principal cause of abandonment",
        category=AssumptionCategory.DESIRABILITY,
        importance=Importance.HIGH,
        uncertainty=Uncertainty.HIGH,
        owner=owner,
        provenance=Provenance(sources=(assumption_source,), ai_generated=False),
    )
    assumption_scope = EvidenceScope(
        hypothesis_id=UUID(int=10),
        target=EvidenceTarget.ASSUMPTION,
        assumption_id=assumption.id,
        population="Studied customers",
    )
    risk = assess_assumption_risk(
        assumption,
        assumption_scope,
        tuple(items),
        decision_impact=Ordinal.HIGH,
        uncertainty=Ordinal.HIGH,
        rationale="A false causal explanation would change the proposed investment",
        evidence_gaps=("Problem observations do not isolate relevance from price",),
        policy=policies.assumption_risk,
        actor=actor,
        at=at,
        assessment_id=uuid4(),
        event_id=uuid4(),
    )
    print("Causal assumption risk:", risk.risk.value if risk.risk else "unknown")
    activity = ValidationActivity(
        id=uuid4(),
        hypothesis_id=UUID(int=10),
        target_assumption_id=assumption.id,
        method=ValidationMethod.CONTROLLED_EXPERIMENT,
        rationale="Isolate relevance from the competing price explanation",
        required_inputs=("Controlled comparison and checked instrumentation",),
        success_signal="Relevance intervention changes completion with price held stable",
        failure_signal="Price intervention changes completion; relevance intervention does not",
        expected_information_gain=Ordinal.HIGH,
        relative_cost=RelativeCost.MEDIUM,
        relative_speed=RelativeSpeed.MEDIUM,
        owner=owner,
        created_at=at,
        updated_at=at,
    )
    created = create_validation_activity(activity, actor=actor, event_id=uuid4())
    ready = transition_validation_activity(
        created.after, ValidationStatus.READY, actor=actor, at=at, event_id=uuid4()
    )
    running = transition_validation_activity(
        ready.after, ValidationStatus.RUNNING, actor=actor, at=at, event_id=uuid4()
    )
    experiment_source = SourceReference(
        source_type=SourceType.EXPERIMENT, reference="example:synthetic-experiment"
    )
    new_evidence = Evidence(
        id=uuid4(),
        hypothesis_id=UUID(int=10),
        statement="Synthetic controlled comparison favors the price explanation",
        source=experiment_source,
        collected_on=at.date(),
        target=EvidenceTarget.ASSUMPTION,
        target_assumption_id=assumption.id,
        population="Studied customers",
        direction=EvidenceDirection.CONTRADICTS,
        methodology_notes="Synthetic example; no real experiment performed",
        provenance=Provenance(sources=(experiment_source,), ai_generated=False),
    )
    result = ValidationResult(
        id=uuid4(),
        activity_id=activity.id,
        tested_assumption_id=assumption.id,
        criteria_version=activity.criteria_version,
        conclusion=ValidationConclusion.CONTRADICTED,
        generated_evidence_ids=(new_evidence.id,),
        interpretation="Predefined failure signal observed in synthetic data",
        limitations=("Synthetic example, scoped comparison; no population economic estimate",),
        effect=ValidationEffect.CONTRADICTS,
        owner=owner,
        completed_at=at,
    )
    recorded = record_validation_result(
        running.after,
        result,
        assumption,
        prior_evidence=tuple(items),
        generated_evidence=(new_evidence,),
        actor=actor,
        completion_event_id=uuid4(),
        result_event_id=uuid4(),
    )
    print("Validation conclusion:", recorded.result.conclusion.value)
    print("Assumption retained:", recorded.assumption_after.validation_state.value)
    print("Evidence items retained:", len(recorded.evidence_history))
    print("No delivery or pursuit decision is made")


if __name__ == "__main__":
    main()
