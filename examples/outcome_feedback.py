"""Offline search implementation → mixed metrics → append-only learning → human closure."""

import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples.discovery_decisioning import ACTOR, AT, ROOT
from examples.spec_delivery import authorized_search
from product_discovery_engine.application.evidence_validation import (
    EvidenceReviewInput,
    EvidenceValidationService,
    KnowledgeState,
)
from product_discovery_engine.application.outcome_feedback import OutcomeFeedbackService
from product_discovery_engine.domain.common import Provenance, SourceReference, SourceType
from product_discovery_engine.domain.evidence import Evidence, EvidenceDirection, EvidenceTarget
from product_discovery_engine.domain.evidence_assessment import EvidenceScope, QualityInput
from product_discovery_engine.domain.evidence_policy import (
    CoverageBasis,
    DirectnessBasis,
    ReliabilityBasis,
)
from product_discovery_engine.domain.hypotheses import HypothesisLinks
from product_discovery_engine.domain.hypothesis_changes import (
    create_hypothesis,
    transition_hypothesis,
)
from product_discovery_engine.domain.implementation import (
    DeviationKind,
    ImplementationDeviation,
    ImplementationRecord,
)
from product_discovery_engine.domain.lifecycle import HypothesisStatus, InvalidTransition
from product_discovery_engine.domain.outcome_causality import (
    CausalInterpretation,
    CausalState,
    StudyDesign,
)
from product_discovery_engine.domain.outcome_evaluation import OutcomeAssessment, OutcomeDisposition
from product_discovery_engine.domain.outcome_feedback import OutcomeEvidenceFeedback
from product_discovery_engine.domain.outcome_lifecycle import OutcomeLifecycleChange
from product_discovery_engine.domain.outcome_measurement import (
    Comparator,
    ImprovementDirection,
    MeasurementWindow,
    MetricRole,
    OutcomeMeasurementPlan,
    OutcomeMetricDefinition,
    OutcomeObservation,
    OutcomeTarget,
    TargetKind,
)
from product_discovery_engine.domain.outcome_review import (
    FollowUpAction,
    FollowUpLearning,
    OutcomeReview,
)
from product_discovery_engine.domain.spec_items import SpecItemType
from product_discovery_engine.infrastructure.configuration import (
    load_evidence_policies,
    load_outcome_measurement_policy,
)


@dataclass(frozen=True)
class OutcomeScenario:
    service: OutcomeFeedbackService
    started: ImplementationRecord
    completed: ImplementationRecord
    implemented: OutcomeLifecycleChange
    plan: OutcomeMeasurementPlan
    measuring: OutcomeLifecycleChange
    observations: tuple[OutcomeObservation, ...]
    assessment: OutcomeAssessment
    causal: CausalInterpretation
    feedback: tuple[OutcomeEvidenceFeedback, ...]
    knowledge_before: KnowledgeState
    knowledge_after: KnowledgeState
    review: OutcomeReview
    follow_up: FollowUpLearning
    closed: OutcomeLifecycleChange


def build_outcome_scenario() -> OutcomeScenario:
    authorization = authorized_search()
    inputs = authorization.current
    service = OutcomeFeedbackService(
        load_outcome_measurement_policy(ROOT / "config/outcome-measurement.v1.toml")
    )
    original_spec = inputs.spec.model_dump_json()
    original_hypothesis = inputs.hypothesis.model_dump_json()
    assert inputs.hypothesis.status == HypothesisStatus.SELECTED_FOR_DELIVERY
    try:
        transition_hypothesis(
            inputs.hypothesis, HypothesisStatus.IMPLEMENTED, actor=ACTOR, at=AT, event_id=uuid4()
        )
    except InvalidTransition:
        pass
    else:
        raise AssertionError("authorization alone must not permit implementation transition")
    assert ACTOR.owner is not None
    started = service.start_implementation(
        authorization,
        inputs,
        spec_policy=authorization.policy,
        owner=ACTOR.owner,
        actor=ACTOR,
        at=AT,
        summary="Begin bounded catalogue search delivery",
    )
    scope_item = next(i for i in inputs.spec.items if i.kind == SpecItemType.SCOPE)
    deviation = ImplementationDeviation(
        id=uuid4(),
        kind=DeviationKind.REDUCED,
        spec_item_id=scope_item.id,
        description="Initial behavior limited to signed-in catalogue audience",
        rationale="Accountable supplied scope reduction; no global release claimed",
    )
    completed = service.complete_implementation(
        started,
        actor=ACTOR,
        at=AT + timedelta(days=1),
        summary="Catalogue search behavior completed for the bounded audience",
        delivered_scope=("Catalogue query behavior through existing search interface",),
        delivered_item_ids=tuple(i.id for i in inputs.spec.items),
        deviations=(deviation,),
        artifact_references=("synthetic:delivery-review",),
        limitations=("Actual production exposure not independently verified",),
    )
    implemented = service.mark_implemented(
        inputs.hypothesis,
        completed,
        actor=ACTOR,
        at=AT + timedelta(days=1),
        rationale="Human accepts supplied completed implementation record",
    )
    period = MeasurementWindow(start=AT + timedelta(days=2), end=AT + timedelta(days=16))
    baseline_period = MeasurementWindow(start=AT - timedelta(days=14), end=AT)
    population = "Studied customers"
    source = SourceReference(
        source_type=SourceType.ANALYTICS,
        reference="synthetic:search-measurement",
        owner=ACTOR.owner,
    )
    provenance = Provenance(
        sources=(source,),
        ai_generated=False,
        interpretation_notes="Hand-authored synthetic data, no analytics connector",
    )
    definitions: list[OutcomeMetricDefinition] = []
    for name, role, unit, direction, aggregation, target, scope in (
        (
            "Search success",
            MetricRole.PRIMARY,
            "fraction",
            ImprovementDirection.INCREASE,
            "Sessions with a found item / all eligible query sessions in the study cohort",
            OutcomeTarget(
                kind=TargetKind.NUMERIC,
                definition="Search success at least 0.70",
                value=0.70,
                comparator=Comparator.AT_LEAST,
            ),
            EvidenceScope(
                hypothesis_id=inputs.hypothesis.id,
                target=EvidenceTarget.OUTCOME,
                claim_id=inputs.hypothesis.links.claim_ids[0],
                population=population,
            ),
        ),
        (
            "Abandonment",
            MetricRole.SECONDARY,
            "fraction",
            ImprovementDirection.DECREASE,
            "Sessions ending without further catalogue interaction / all eligible query sessions",
            OutcomeTarget(
                kind=TargetKind.DIRECTIONAL,
                definition="Reduce abandonment from the explicit baseline",
            ),
            EvidenceScope(
                hypothesis_id=inputs.hypothesis.id,
                target=EvidenceTarget.ASSUMPTION,
                assumption_id=inputs.hypothesis.links.assumption_ids[0],
                population=population,
            ),
        ),
        (
            "Search latency",
            MetricRole.GUARDRAIL,
            "milliseconds",
            ImprovementDirection.DECREASE,
            "p95 observed query response duration over eligible query sessions",
            OutcomeTarget(
                kind=TargetKind.THRESHOLD,
                definition="p95 latency at most 250 milliseconds",
                value=250.0,
                comparator=Comparator.AT_MOST,
            ),
            EvidenceScope(
                hypothesis_id=inputs.hypothesis.id,
                target=EvidenceTarget.SOLUTION,
                claim_id=inputs.hypothesis.links.claim_ids[0],
                population=population,
            ),
        ),
    ):
        definitions.append(
            OutcomeMetricDefinition(
                id=uuid4(),
                name=name,
                role=role,
                unit=unit,
                direction=direction,
                aggregation=aggregation,
                description=f"Explicit synthetic {name} observation",
                population=population,
                observation_source=source,
                baseline_definition="Same cohort and instrumentation before implementation",
                baseline_period=baseline_period,
                outcome_period=period,
                target=target,
                feedback_scope=scope,
            )
        )
    metrics = tuple(definitions)
    baselines = tuple(
        service.baseline(
            completed.id,
            m.id,
            value=value,
            period=baseline_period,
            population=population,
            source=source,
            methodology=m.aggregation,
            provenance=provenance,
            actor=ACTOR,
            at=AT,
        )
        for m, value in zip(metrics, (0.60, 0.30, 180.0), strict=True)
    )
    plan = service.create_plan(
        implemented.after,
        completed,
        metrics=metrics,
        baselines=baselines,
        window=period,
        observation_source=source.reference,
        analysis_method="Descriptive full-window target comparison; no causal inference",
        owner=ACTOR.owner,
        actor=ACTOR,
        at=AT + timedelta(days=1),
        reason="Define criteria before outcome observations",
        confounders=("Concurrent campaigns and price changes were not controlled",),
        interpretation_risks=("Bounded study population; do not infer full rollout",),
    )
    measuring = service.begin_measurement(
        implemented.after,
        completed,
        plan,
        actor=ACTOR,
        at=period.start,
        rationale="Explicit measurement plan ready for the supplied implementation",
    )
    observations = tuple(
        service.observe(
            plan,
            m.id,
            value=value,
            period=period,
            population=population,
            source=source,
            methodology=m.aggregation,
            provenance=provenance,
            actor=ACTOR,
            at=period.end,
            limitations=("Observational synthetic study; no randomized assignment",),
        )
        for m, value in zip(metrics, (0.74, 0.30, 290.0), strict=True)
    )
    evaluations = tuple(
        service.evaluate(plan, m.id, (o,), actor=ACTOR, at=period.end)
        for m, o in zip(metrics, observations, strict=True)
    )
    assessment = service.assess(plan, evaluations)
    causal = service.interpret_causality(
        plan,
        metrics[1].feedback_scope,
        claim="Catalogue relevance changes reduce abandonment",
        state=CausalState.INSUFFICIENT_EVIDENCE,
        design=StudyDesign.BEFORE_AFTER,
        design_basis="Before/after cohort observation with no control",
        confounders=plan.confounders,
        limitations=("No causal design; actual exposure unverified",),
        interpretation="Primary target met but abandonment unchanged; causality remains unresolved",
        actor=ACTOR,
        at=period.end,
    )
    readiness = inputs.selection.candidacy.gate.readiness
    assert readiness is not None
    by_id = {e.id: e for k in readiness.inputs.knowledge for e in k.evidence}
    evidence = tuple(by_id[eid] for eid in inputs.hypothesis.links.evidence_ids)
    original_evidence = tuple(e.model_dump_json() for e in evidence)
    current = measuring.after
    feedback: list[OutcomeEvidenceFeedback] = []
    for observation, evidence_direction, reason in zip(
        observations,
        (EvidenceDirection.SUPPORTS, EvidenceDirection.CONTRADICTS, EvidenceDirection.CONTRADICTS),
        (
            "Observed search proxy improved in this cohort",
            "Unchanged abandonment challenges expected causal/business learning",
            "Latency guardrail regression remains visible",
        ),
        strict=True,
    ):
        added = service.materialize_evidence(
            current,
            observation,
            evidence,
            direction=evidence_direction,
            rationale=reason,
            actor=ACTOR,
            at=period.end,
        )
        feedback.append(added)
        current, evidence = added.change.after, added.current_evidence
    # The existing Milestone 3 service consumes outcome evidence with explicit quality input.
    old_knowledge = next(
        k for k in readiness.inputs.knowledge if k.scope.target == EvidenceTarget.ASSUMPTION
    )
    policies = load_evidence_policies(ROOT / "config/evidence-policies.v1.toml")
    knowledge_service = EvidenceValidationService(policies)
    old_scope = old_knowledge.scope

    def reviews(
        items: tuple[Evidence, ...], scope: EvidenceScope
    ) -> tuple[EvidenceReviewInput, ...]:
        return tuple(
            EvidenceReviewInput(
                evidence_id=e.id,
                basis=QualityInput(
                    scope=scope,
                    directness=DirectnessBasis.INDIRECT_PROXY,
                    reliability=ReliabilityBasis.DOCUMENTED_LIMITATIONS,
                    coverage=CoverageBasis.BOUNDED_SAMPLE,
                    rationale="Human review of scoped observational limits",
                    methodology_basis="Descriptive cohort, no causal assignment",
                    population_basis="Only the named cohort",
                ),
            )
            for e in items
        )

    knowledge_before = knowledge_service.assess(
        old_scope,
        old_knowledge.evidence,
        old_knowledge.origin_relationships,
        reviews(old_knowledge.evidence, old_scope),
        actor=ACTOR,
        at=period.end,
    )
    feedback_scope = metrics[1].feedback_scope
    relevant = tuple(e for e in evidence if feedback_scope.matches(e))
    knowledge_after = knowledge_service.assess(
        feedback_scope,
        relevant,
        old_knowledge.origin_relationships,
        reviews(relevant, feedback_scope),
        actor=ACTOR,
        at=period.end,
        previous=knowledge_before,
    )
    causal = service.interpret_causality(
        plan,
        metrics[1].feedback_scope,
        claim="Catalogue relevance changes reduce abandonment",
        state=CausalState.INSUFFICIENT_EVIDENCE,
        design=StudyDesign.BEFORE_AFTER,
        design_basis="Before/after cohort observation with no control",
        confounders=plan.confounders,
        limitations=("No causal design; actual exposure unverified",),
        interpretation="Primary target met but abandonment unchanged; causality remains unresolved",
        actor=ACTOR,
        at=period.end,
        supporting=tuple(
            e
            for e in evidence
            if metrics[1].feedback_scope.matches(e)
            and e.direction == EvidenceDirection.SUPPORTS
            and e.invalidated_on is None
        ),
        contradicting=tuple(
            e
            for e in evidence
            if metrics[1].feedback_scope.matches(e)
            and e.direction == EvidenceDirection.CONTRADICTS
            and e.invalidated_on is None
        ),
    )
    acknowledged = tuple(
        dict.fromkeys(assessment.limitations + causal.limitations + causal.confounders)
    )
    review = service.review(
        current,
        assessment,
        causal_interpretations=(causal,),
        evidence=evidence,
        actor=ACTOR,
        at=period.end,
        rationale=(
            "Close reviewed mixed episode; retain unresolved causal learning and latency issue"
        ),
        actions=(FollowUpAction.INVESTIGATE_GUARDRAIL, FollowUpAction.ADDITIONAL_VALIDATION),
        follow_up_learning=(
            "Investigate latency before extending exposure",
            "Separate relevance from pricing explanations",
        ),
        unresolved_questions=("Which explanation determines abandonment?",),
        acknowledged_limitations=acknowledged,
    )
    follow_up = create_hypothesis(
        id=uuid4(),
        content=current.content,
        links=HypothesisLinks(submission_ids=current.links.submission_ids),
        actor=ACTOR,
        at=period.end,
        event_id=uuid4(),
    ).after
    learning = service.link_follow_up(
        review,
        follow_up,
        (feedback[1].evidence.id,),
        actor=ACTOR,
        at=period.end,
        rationale="Explicit human-created follow-up to test competing explanations",
    )
    closed = service.close(
        current,
        completed,
        plan,
        review,
        actor=ACTOR,
        at=period.end,
        rationale="Current measurement episode reviewed and closed; no proof of correctness",
    )
    assert assessment.disposition == OutcomeDisposition.MIXED
    assert inputs.spec.model_dump_json() == original_spec
    assert inputs.hypothesis.model_dump_json() == original_hypothesis
    assert (
        tuple(e.model_dump_json() for e in evidence[: len(original_evidence)]) == original_evidence
    )
    return OutcomeScenario(
        service,
        started,
        completed,
        implemented,
        plan,
        measuring,
        observations,
        assessment,
        causal,
        tuple(feedback),
        knowledge_before,
        knowledge_after,
        review,
        learning,
        closed,
    )


def main() -> None:
    scenario = build_outcome_scenario()
    print("Implementation:", scenario.started.status.value, "→", scenario.completed.status.value)
    print("Deviation:", scenario.completed.deviations[0].description)
    print("Release:", "unknown; completion is not global deployment")
    print(
        "Lifecycle:",
        scenario.implemented.after.status.value,
        "→",
        scenario.measuring.after.status.value,
    )
    for evaluation in scenario.assessment.evaluations:
        print(
            evaluation.plan.metric(evaluation.metric_id).name + ":", evaluation.result.state.value
        )
    print("Assessment:", scenario.assessment.disposition.value, "— metrics are not averaged")
    print("Causality:", scenario.causal.state.value)
    print("Feedback evidence appended:", len(scenario.feedback), "— original history retained")
    print("Human review:", scenario.review.reviewer.id, "— follow-up learning explicitly linked")
    print(
        "Lifecycle:", scenario.closed.after.status.value, "— episode closed, hypothesis not proven"
    )


if __name__ == "__main__":
    main()
