"""Synthetic, credential-free discovery loop; run python examples/discovery_decisioning.py."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from product_discovery_engine.application.challenge_analysis import (
    ChallengeAnalysis,
    ChallengeAnalysisService,
    ChallengeCategory,
    ChallengeInput,
    ChallengeItem,
    ChallengeProvenance,
    ChallengeRecord,
    ChallengeValidation,
)
from product_discovery_engine.application.discovery_decisioning import (
    DiscoveryDecisioningService,
    challenge_completion,
    decision_knowledge,
)
from product_discovery_engine.application.evidence_validation import (
    EvidenceReviewInput,
    EvidenceValidationService,
    KnowledgeState,
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
    StrategyReference,
)
from product_discovery_engine.domain.decisioning_inputs import (
    AssumptionTreatment,
    ChallengeDisposition,
    ChallengeItemReview,
    ChallengeReview,
    ContradictionDisposition,
    ContradictionReview,
    HumanReview,
    ReadinessInput,
    ReviewedAssumption,
    StrategyAcknowledgement,
)
from product_discovery_engine.domain.decisioning_policy import DecisioningPolicies
from product_discovery_engine.domain.discovery_priority import LearningInput, LearningTargetKind
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
    EvidencePolicies,
    ReliabilityBasis,
)
from product_discovery_engine.domain.hypotheses import (
    Hypothesis,
    HypothesisContent,
    HypothesisLinks,
)
from product_discovery_engine.domain.hypothesis_changes import (
    create_hypothesis,
    link_evidence,
    transition_hypothesis,
)
from product_discovery_engine.domain.lifecycle import HypothesisStatus
from product_discovery_engine.domain.policies import StrategyPolicy
from product_discovery_engine.domain.validation import (
    RelativeCost,
    RelativeSpeed,
    ValidationActivity,
    ValidationConclusion,
    ValidationEffect,
    ValidationResult,
    ValidationStatus,
    record_validation_result,
    transition_validation_activity,
)
from product_discovery_engine.domain.validation_methods import ValidationMethod
from product_discovery_engine.infrastructure.configuration import (
    load_decisioning_policies,
    load_evidence_policies,
)

AT = datetime(2026, 10, 3, 10, tzinfo=UTC)
OWNER = Owner(id=UUID(int=1), display_name="Synthetic research owner")
ACTOR = Actor(kind=ActorKind.HUMAN, id="synthetic-reviewer", owner=OWNER)
ROOT = Path(__file__).resolve().parents[1]


class SyntheticChallengeProvider:
    """Hand-authored advisory output for demonstration, never a live model call."""

    provenance = ChallengeProvenance(
        provider="synthetic", model="offline", prompt_version="demo.v1"
    )

    def analyze_challenges(self, request: ChallengeInput) -> ChallengeAnalysis:
        return ChallengeAnalysis(
            items=(
                ChallengeItem(
                    id="causal-scope",
                    category=ChallengeCategory.FALSE_CAUSALITY,
                    challenge_statement="Problem existence does not prove relevance causes exits",
                    rationale="Price remains a competing explanation",
                    relevant_evidence_ids=tuple(e.id for e in request.knowledge.evidence),
                    unresolved_counterargument="A relevance solution still needs causal evidence",
                    additional_evidence_required=("Controlled comparison",),
                    severity=Ordinal.VERY_HIGH,
                    recommended_validation=ChallengeValidation(
                        method=ValidationMethod.CONTROLLED_EXPERIMENT,
                        rationale="Separate price/relevance",
                    ),
                    ai_generated=True,
                    provenance=self.provenance,
                ),
            ),
            contradicting_evidence_ids=tuple(
                e.id
                for e in request.knowledge.evidence
                if e.direction == EvidenceDirection.CONTRADICTS
            ),
            competing_explanations=("Price rather than relevance",),
            disconfirming_evidence_required=("Price/relevance comparison",),
            source_scope_notes="Bounded sample, no population prevalence inference",
            limitations=("Synthetic advisory output; semantic quality unverified",),
            advisory_only=True,
        )


def review(hypothesis: Hypothesis, reason: str) -> HumanReview:
    return HumanReview(
        hypothesis_id=hypothesis.id,
        hypothesis_version=hypothesis.version,
        actor=ACTOR,
        reason=reason,
        reviewed_at=AT,
    )


def synthetic_evidence(
    target: EvidenceTarget,
    claim_id: UUID | None,
    number: int,
    direction: EvidenceDirection = EvidenceDirection.SUPPORTS,
) -> Evidence:
    source = SourceReference(
        source_type=SourceType.DOCUMENT, reference=f"synthetic:source:{number}"
    )
    return Evidence(
        id=UUID(int=100 + number),
        hypothesis_id=UUID(int=10),
        statement=f"Synthetic {target.value} observation {number}",
        source=source,
        collected_on=AT.date(),
        target=target,
        target_claim_id=claim_id,
        target_assumption_id=UUID(int=20) if target == EvidenceTarget.ASSUMPTION else None,
        population="Studied customers",
        direction=direction,
        methodology_notes="Synthetic bounded sample",
        provenance=Provenance(sources=(source,), ai_generated=False),
    )


def assess_knowledge(items: tuple[Evidence, ...], policies: EvidencePolicies) -> KnowledgeState:
    relationships = tuple(
        link_origins(
            e,
            (
                EvidenceOrigin(
                    id=uuid4(),
                    kind=OriginKind.RESEARCH_STUDY,
                    family_key=e.source.reference,
                    source_reference=e.source.reference,
                    method=(
                        ValidationMethod.CUSTOMER_INTERVIEW
                        if index % 2 == 0
                        else ValidationMethod.BEHAVIORAL_ANALYTICS
                    ),
                ),
            ),
            rationale="Synthetic independent underlying collection",
            actor=ACTOR,
            at=AT,
            event_id=uuid4(),
        )
        for index, e in enumerate(items)
    )
    reviews = tuple(
        EvidenceReviewInput(
            evidence_id=e.id,
            basis=QualityInput(
                scope=EvidenceScope.of(e),
                directness=DirectnessBasis.DIRECT_OBSERVATION,
                reliability=ReliabilityBasis.REVIEWED_METHOD,
                coverage=CoverageBasis.BOUNDED_SAMPLE,
                rationale="Problem observations, not causal or population proof",
                methodology_basis="Synthetic reviewed observation",
                population_basis="Bounded studied customers",
            ),
        )
        for e in items
    )
    return EvidenceValidationService(policies).assess(
        EvidenceScope.of(items[0]), items, relationships, reviews, actor=ACTOR, at=AT
    )


@dataclass(frozen=True)
class Scenario:
    policies: DecisioningPolicies
    evidence_policies: EvidencePolicies
    initial: ReadinessInput
    final: ReadinessInput
    initial_challenge: ChallengeRecord
    final_challenge: ChallengeRecord
    learning: LearningInput


def build_scenario() -> Scenario:
    policies = load_decisioning_policies(ROOT / "config/discovery-decisioning.v1.toml")
    evidence_policies = load_evidence_policies(ROOT / "config/evidence-policies.v1.toml")
    assumption_source = SourceReference(
        source_type=SourceType.STAKEHOLDER, reference="synthetic:causal-assumption"
    )
    assumption = Assumption(
        id=UUID(int=20),
        statement="Relevance is the principal cause of abandonment",
        category=AssumptionCategory.DESIRABILITY,
        importance=Importance.HIGH,
        uncertainty=Uncertainty.HIGH,
        owner=OWNER,
        provenance=Provenance(sources=(assumption_source,), ai_generated=False),
    )
    activity = ValidationActivity(
        id=UUID(int=40),
        hypothesis_id=UUID(int=10),
        target_assumption_id=assumption.id,
        method=ValidationMethod.CONTROLLED_EXPERIMENT,
        rationale="Separate relevance from price",
        required_inputs=("Controlled comparison",),
        success_signal="Relevance changes completion",
        failure_signal="Price changes completion; relevance does not",
        expected_information_gain=Ordinal.HIGH,
        relative_cost=RelativeCost.MEDIUM,
        relative_speed=RelativeSpeed.MEDIUM,
        owner=OWNER,
        created_at=AT,
        updated_at=AT,
    )
    strategy = StrategyPolicy(
        reference=StrategyReference(id="customer-experience", version=1),
        objective="Reduce customer difficulty finding suitable products",
    )
    hypothesis = create_hypothesis(
        id=UUID(int=10),
        content=HypothesisContent(
            title="Understand search difficulty",
            owner=OWNER,
            problem_statement="Customers struggle to find relevant products in search",
            target_segment="Studied customers",
            desired_outcome="Customers find suitable products",
            strategy=strategy.reference,
        ),
        links=HypothesisLinks(
            submission_ids=(UUID(int=2),),
            claim_ids=(UUID(int=30), UUID(int=31)),
            assumption_ids=(assumption.id,),
            validation_ids=(activity.id,),
        ),
        actor=ACTOR,
        at=AT,
        event_id=uuid4(),
    ).after
    for status in (
        HypothesisStatus.STRUCTURED,
        HypothesisStatus.READY_TO_VALIDATE,
        HypothesisStatus.VALIDATING,
        HypothesisStatus.EVIDENCE_UPDATED,
    ):
        hypothesis = transition_hypothesis(
            hypothesis, status, actor=ACTOR, at=AT, event_id=uuid4()
        ).after
    problem = assess_knowledge(
        (
            synthetic_evidence(EvidenceTarget.PROBLEM_EXISTENCE, UUID(int=30), 1),
            synthetic_evidence(EvidenceTarget.PROBLEM_EXISTENCE, UUID(int=30), 2),
        ),
        evidence_policies,
    )
    segment = assess_knowledge(
        (synthetic_evidence(EvidenceTarget.TARGET_SEGMENT, UUID(int=31), 3),), evidence_policies
    )
    for evidence in problem.evidence + segment.evidence:
        hypothesis = link_evidence(hypothesis, evidence, actor=ACTOR, at=AT, event_id=uuid4()).after
    causal_scope = EvidenceScope(
        hypothesis_id=hypothesis.id,
        target=EvidenceTarget.ASSUMPTION,
        assumption_id=assumption.id,
        population="Studied customers",
    )
    risk = assess_assumption_risk(
        assumption,
        causal_scope,
        (),
        decision_impact=Ordinal.VERY_HIGH,
        uncertainty=Ordinal.HIGH,
        rationale="A wrong causal explanation changes the proposed intervention",
        evidence_gaps=("Price/relevance confounding unresolved",),
        policy=evidence_policies.assumption_risk,
        actor=ACTOR,
        at=AT,
        assessment_id=uuid4(),
        event_id=uuid4(),
    )
    learning = LearningInput(
        hypothesis=hypothesis,
        target_id=assumption.id,
        target_kind=LearningTargetKind.ASSUMPTION,
        target_description=assumption.statement,
        assumption=assumption,
        risk_assessment=risk,
        decision_impact=risk.decision_impact,
        unresolved_uncertainty=risk.uncertainty,
        evidence_gaps=risk.evidence_gaps,
        expected_information_gain=activity.expected_information_gain,
        relative_cost=activity.relative_cost,
        relative_speed=activity.relative_speed,
        validations=(activity,),
        proposed_validation_id=activity.id,
    )
    challenge_service = ChallengeAnalysisService(SyntheticChallengeProvider())

    def challenge_for(
        current: Hypothesis, knowledge: KnowledgeState, item: Assumption, resolved: bool
    ) -> tuple[ChallengeRecord, ChallengeReview]:
        record = challenge_service.analyze_record(
            ChallengeInput(
                hypothesis_statement=str(current.content.problem_statement),
                knowledge=knowledge,
                assumptions=(item,),
            ),
            actor=ACTOR,
            at=AT,
            record_id=uuid4(),
            event_id=uuid4(),
        )
        human = ChallengeReview(
            completion=challenge_completion(record),
            items=(
                ChallengeItemReview(
                    item_id="causal-scope",
                    human_severity=Ordinal.HIGH,
                    disposition=ChallengeDisposition.ADDRESSED
                    if resolved
                    else ChallengeDisposition.UNRESOLVED,
                    rationale="Comparison completed; candidate is problem-only"
                    if resolved
                    else "Run comparison",
                ),
            ),
            review=review(current, "Advisory AI severity independently reviewed by a human"),
        )
        return record, human

    initial_challenge, challenge_review = challenge_for(hypothesis, problem, assumption, False)
    assert hypothesis.content.strategy is not None
    initial = ReadinessInput(
        hypothesis=hypothesis,
        target_scopes=(problem.scope, segment.scope),
        knowledge=(
            decision_knowledge(problem, evidence_policies),
            decision_knowledge(segment, evidence_policies),
        ),
        assumptions=(
            ReviewedAssumption(
                assumption=assumption, risk=risk, risk_policy=evidence_policies.assumption_risk
            ),
        ),
        validations=(activity,),
        required_validation_ids=(activity.id,),
        challenge=challenge_review,
        strategy_context=strategy,
        strategy_acknowledgement=StrategyAcknowledgement(
            strategy=strategy,
            review=review(
                hypothesis, "Explicit customer-experience objective, no inferred alignment"
            ),
        ),
    )
    for validation_status in (ValidationStatus.READY, ValidationStatus.RUNNING):
        activity = transition_validation_activity(
            activity, validation_status, actor=ACTOR, at=AT, event_id=uuid4()
        ).after
    observation = synthetic_evidence(
        EvidenceTarget.ASSUMPTION, None, 4, EvidenceDirection.CONTRADICTS
    )
    result = ValidationResult(
        id=uuid4(),
        activity_id=activity.id,
        tested_assumption_id=assumption.id,
        criteria_version=activity.criteria_version,
        conclusion=ValidationConclusion.CONTRADICTED,
        generated_evidence_ids=(observation.id,),
        interpretation="Synthetic failure signal observed",
        limitations=("No population prevalence or economics inferred",),
        effect=ValidationEffect.CONTRADICTS,
        owner=OWNER,
        completed_at=AT,
    )
    recording = record_validation_result(
        activity,
        result,
        assumption,
        prior_evidence=problem.evidence + segment.evidence,
        generated_evidence=(observation,),
        actor=ACTOR,
        completion_event_id=uuid4(),
        result_event_id=uuid4(),
    )
    hypothesis = link_evidence(hypothesis, observation, actor=ACTOR, at=AT, event_id=uuid4()).after
    assumption = recording.assumption_after
    causal_knowledge = assess_knowledge((observation,), evidence_policies)
    new_risk = assess_assumption_risk(
        assumption,
        causal_scope,
        (observation,),
        decision_impact=Ordinal.VERY_HIGH,
        uncertainty=Ordinal.LOW,
        rationale="Comparison refuted causal assumption; reframe rather than confirmation-seek",
        evidence_gaps=(),
        policy=evidence_policies.assumption_risk,
        actor=ACTOR,
        at=AT,
        assessment_id=uuid4(),
        event_id=uuid4(),
    )
    final_challenge, final_review = challenge_for(hypothesis, problem, assumption, True)
    assert hypothesis.content.strategy is not None
    final = ReadinessInput(
        hypothesis=hypothesis,
        target_scopes=(problem.scope, segment.scope),
        knowledge=initial.knowledge + (decision_knowledge(causal_knowledge, evidence_policies),),
        assumptions=(
            ReviewedAssumption(
                assumption=assumption,
                risk=new_risk,
                risk_policy=evidence_policies.assumption_risk,
                treatment=AssumptionTreatment(
                    risk_assessment_id=new_risk.id,
                    review=review(
                        hypothesis, "Refuted relevance assumption retained and explicitly treated"
                    ),
                    action="Reframe as problem-only candidacy; no relevance solution endorsed",
                ),
            ),
        ),
        validations=(recording.activity_change.after,),
        validation_results=(recording.result,),
        required_validation_ids=(activity.id,),
        contradictions=(
            ContradictionReview(
                scope=causal_scope,
                contradicting_evidence_ids=(observation.id,),
                disposition=ContradictionDisposition.INVESTIGATED_ACCEPTED,
                review=review(
                    hypothesis, "Controlled comparison accepted; causal claim remains refuted"
                ),
            ),
        ),
        challenge=final_review,
        strategy_context=strategy,
        strategy_acknowledgement=StrategyAcknowledgement(
            strategy=strategy,
            review=review(hypothesis, "Acknowledged versioned customer-experience strategy"),
        ),
    )
    return Scenario(
        policies, evidence_policies, initial, final, initial_challenge, final_challenge, learning
    )


def main() -> None:
    scenario = build_scenario()
    service = DiscoveryDecisioningService(scenario.policies)
    priority = service.priority(scenario.learning, actor=ACTOR, at=AT)
    first = service.readiness(
        scenario.initial, actor=ACTOR, at=AT, challenge_record=scenario.initial_challenge
    )
    first_gate = service.gate(scenario.initial.hypothesis, first, actor=ACTOR, at=AT)
    final = service.readiness(
        scenario.final, actor=ACTOR, at=AT, challenge_record=scenario.final_challenge
    )
    final_gate = service.gate(scenario.final.hypothesis, final, actor=ACTOR, at=AT)
    promotion = service.promote(scenario.final.hypothesis, final_gate, actor=ACTOR, at=AT)
    print("Evidence: independent scoped problem observations; reach/causality not inferred")
    print("Next learning:", priority.result.priority.value, priority.result.action.value)
    print("Initially:", first.result.state.value, first_gate.result.state.value)
    print("New validation: refuted causal assumption retained, explicitly treated by human")
    print("After validation and reviews:", final.result.state.value, final_gate.result.state.value)
    print("Historical contradictions retained:", len(scenario.final.contradictions))
    print("Lifecycle:", promotion.after.status.value)
    print("No delivery selection; optional reach/viability/business impact remain unknown")


if __name__ == "__main__":
    main()
