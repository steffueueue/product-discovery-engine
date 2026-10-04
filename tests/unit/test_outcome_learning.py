"""Causal safeguards, appended knowledge, accountable review and closure conditions."""

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from examples.discovery_decisioning import ROOT
from examples.outcome_feedback import OutcomeScenario
from product_discovery_engine.application.evidence_validation import (
    EvidenceReviewInput,
    EvidenceValidationService,
)
from product_discovery_engine.application.outcome_feedback import OutcomeFeedbackService
from product_discovery_engine.domain.audit import Actor, ActorKind
from product_discovery_engine.domain.common import Provenance, SourceReference, SourceType
from product_discovery_engine.domain.evidence import Evidence, EvidenceDirection
from product_discovery_engine.domain.evidence_assessment import EvidenceScope, QualityInput
from product_discovery_engine.domain.evidence_policy import (
    CoverageBasis,
    DirectnessBasis,
    ReliabilityBasis,
)
from product_discovery_engine.domain.hypotheses import Hypothesis
from product_discovery_engine.domain.outcome_causality import (
    CausalInterpretation,
    CausalState,
    StudyDesign,
)
from product_discovery_engine.domain.outcome_evaluation import EvaluationState, OutcomeDisposition
from product_discovery_engine.domain.outcome_feedback import OutcomeEvidenceFeedback
from product_discovery_engine.domain.outcome_lifecycle import OutcomeLifecycleChange
from product_discovery_engine.domain.outcome_measurement import OutcomeMeasurementPlan
from product_discovery_engine.domain.outcome_policy import OutcomeMeasurementPolicy
from product_discovery_engine.domain.outcome_review import FollowUpAction, OutcomeReview
from product_discovery_engine.infrastructure.configuration import load_evidence_policies
from tests.m7_helpers import ACTOR, observation_for


def test_target_met_is_not_causality(outcome_scenario: OutcomeScenario) -> None:
    s = outcome_scenario
    assert s.assessment.evaluations[0].result.state == EvaluationState.MET
    assert s.causal.state == CausalState.INSUFFICIENT_EVIDENCE
    assert s.causal.design == StudyDesign.BEFORE_AFTER
    assert s.causal.confounders == s.plan.confounders
    assert "probability" not in CausalInterpretation.model_fields
    assert "causal_state" not in type(s.observations[0]).model_fields
    data = s.causal.model_dump()
    data["state"] = CausalState.SUPPORTED
    with pytest.raises(ValueError, match="controlled"):
        CausalInterpretation.model_validate(data)


@pytest.mark.parametrize(
    "field,value", [("probability", 0.95), ("confidence_percentage", 90), ("confounders", ())]
)
def test_causal_probability_and_hidden_confounders_rejected(
    outcome_scenario: OutcomeScenario, field: str, value: object
) -> None:
    data = outcome_scenario.causal.model_dump()
    data[field] = value
    with pytest.raises(ValueError):
        CausalInterpretation.model_validate(data)


def controlled_plan(s: OutcomeScenario) -> OutcomeMeasurementPlan:
    return s.service.create_plan(
        s.implemented.after,
        s.completed,
        metrics=s.plan.metrics,
        baselines=s.plan.baselines,
        window=s.plan.window,
        observation_source=s.plan.observation_source,
        analysis_method="Human reviewed controlled comparison",
        owner=s.plan.owner,
        actor=ACTOR,
        at=s.plan.recorded_at,
        reason="Predefine controlled study with supplied instrumentation",
    )


def causal_evidence(s: OutcomeScenario, direction: EvidenceDirection) -> Evidence:
    scope = s.plan.metrics[1].feedback_scope
    source = SourceReference(
        source_type=SourceType.EXPERIMENT, reference=f"synthetic:controlled:{direction.value}"
    )
    return Evidence(
        id=uuid4(),
        hypothesis_id=scope.hypothesis_id,
        statement="Supplied controlled design result",
        source=source,
        collected_on=s.plan.window.end.date(),
        target=scope.target,
        target_assumption_id=scope.assumption_id,
        target_claim_id=scope.claim_id,
        population=scope.population,
        direction=direction,
        methodology_notes="Controlled assignment and instrumentation reviewed",
        provenance=Provenance(sources=(source,)),
    )


def test_controlled_evidence_requires_existing_quality_and_no_unresolved_contradictions(
    outcome_scenario: OutcomeScenario,
) -> None:
    s = outcome_scenario
    plan = controlled_plan(s)
    supporting = causal_evidence(s, EvidenceDirection.SUPPORTS)
    lineage = s.feedback[1].evidence.outcome_provenance
    assert lineage is not None
    supporting = Evidence.model_validate(
        {
            **supporting.model_dump(),
            "outcome_provenance": lineage.model_copy(update={"plan_id": plan.id}),
        }
    )
    policies = load_evidence_policies(ROOT / "config/evidence-policies.v1.toml")
    scope = EvidenceScope.of(supporting)
    quality = (
        EvidenceValidationService(policies)
        .assess(
            scope,
            (supporting,),
            (),
            (
                EvidenceReviewInput(
                    evidence_id=supporting.id,
                    basis=QualityInput(
                        scope=scope,
                        directness=DirectnessBasis.DIRECT_MEASUREMENT,
                        reliability=ReliabilityBasis.REVIEWED_METHOD,
                        coverage=CoverageBasis.BOUNDED_SAMPLE,
                        rationale="Human controlled study review",
                        methodology_basis="Reviewed assignment and instrumentation",
                        population_basis="This cohort",
                    ),
                ),
            ),
            actor=ACTOR,
            at=s.plan.window.end,
        )
        .quality
    )
    supported = s.service.interpret_causality(
        plan,
        plan.metrics[1].feedback_scope,
        claim="Relevance causes reduced abandonment",
        state=CausalState.SUPPORTED,
        design=StudyDesign.CONTROLLED,
        design_basis="Supplied controlled experiment",
        confounders=(),
        limitations=(),
        interpretation="Human reviewed controlled support",
        actor=ACTOR,
        at=s.plan.window.end,
        supporting=(supporting,),
        quality=quality,
        assignment_notes="Randomized assignment reviewed",
        instrumentation_notes="Exposure and tracking verified",
        exposure_population=plan.metrics[1].population,
    )
    assert supported.state == CausalState.SUPPORTED
    with pytest.raises(ValueError, match="outcome episode"):
        unrelated = Evidence.model_validate({**supporting.model_dump(), "outcome_provenance": None})
        CausalInterpretation.model_validate(
            supported.model_copy(update={"supporting_evidence": (unrelated,)})
        )
    with pytest.raises(ValueError, match="quality"):
        CausalInterpretation.model_validate(supported.model_copy(update={"quality": ()}))
    with pytest.raises(ValueError, match="quality"):
        CausalInterpretation.model_validate(
            supported.model_copy(update={"reviewed_at": s.plan.window.end + timedelta(days=365)})
        )
    wrong_lineage = lineage.model_copy(update={"plan_id": plan.id, "metric_id": plan.metrics[0].id})
    unrelated_metric = Evidence.model_validate(
        {**supporting.model_dump(), "outcome_provenance": wrong_lineage}
    )
    with pytest.raises(ValueError, match="outcome episode"):
        CausalInterpretation.model_validate(
            supported.model_copy(update={"supporting_evidence": (unrelated_metric,)})
        )
    with pytest.raises(ValueError, match="controlled"):
        CausalInterpretation.model_validate(
            supported.model_copy(
                update={
                    "contradicting_evidence": (causal_evidence(s, EvidenceDirection.CONTRADICTS),)
                }
            )
        )
    with pytest.raises(ValueError, match="controlled"):
        CausalInterpretation.model_validate(
            supported.model_copy(update={"instrumentation_notes": None})
        )


def test_contradictory_causal_evidence_is_retained(outcome_scenario: OutcomeScenario) -> None:
    s = outcome_scenario
    contradiction = causal_evidence(s, EvidenceDirection.CONTRADICTS)
    interpretation = s.service.interpret_causality(
        s.plan,
        s.plan.metrics[1].feedback_scope,
        claim="Relevance determines abandonment",
        state=CausalState.CONTRADICTED,
        design=StudyDesign.CONTROLLED,
        design_basis="Supplied disconfirming controlled observation",
        confounders=s.plan.confounders,
        limitations=("Only this cohort",),
        interpretation="Human concludes original causal explanation contradicted in study",
        actor=ACTOR,
        at=s.plan.window.end,
        contradicting=(contradiction,),
    )
    assert interpretation.contradicting_evidence == (contradiction,)
    assert interpretation.state == CausalState.CONTRADICTED


def test_feedback_preserves_original_history_and_updates_current_knowledge(
    outcome_scenario: OutcomeScenario,
) -> None:
    s = outcome_scenario
    original = s.feedback[0].prior_evidence
    current = s.feedback[-1].current_evidence
    assert current[: len(original)] == original
    assert len(current) == len(original) + 3
    assert [f.evidence.direction for f in s.feedback] == [
        EvidenceDirection.SUPPORTS,
        EvidenceDirection.CONTRADICTS,
        EvidenceDirection.CONTRADICTS,
    ]
    assert (
        s.knowledge_after.evidence[: len(s.knowledge_before.evidence)]
        == s.knowledge_before.evidence
    )
    assert s.feedback[1].evidence in s.knowledge_after.evidence
    for feedback in s.feedback:
        lineage = feedback.evidence.outcome_provenance
        assert lineage is not None
        assert lineage.implementation_id == s.completed.id
        assert lineage.authorization_id == s.completed.authorization.id
        assert lineage.plan_id == s.plan.id and lineage.plan_version == s.plan.version
        assert lineage.metric_id == feedback.observation.metric_id
        assert lineage.observation_id == feedback.observation.id
        assert feedback.evidence.provenance == feedback.observation.provenance
    assert (
        s.closed.implementation.authorization.current.selection
        == s.started.authorization.current.selection
    )
    assert (
        s.closed.implementation.authorization.current.spec == s.started.authorization.current.spec
    )


@pytest.mark.parametrize(
    "field", ["target_claim_id", "population", "outcome_provenance", "provenance"]
)
def test_feedback_cannot_validate_unrelated_targets_or_rewrite_provenance(
    outcome_scenario: OutcomeScenario, field: str
) -> None:
    feedback = outcome_scenario.feedback[0]
    evidence_data = feedback.evidence.model_dump()
    evidence_data[field] = (
        uuid4()
        if field == "target_claim_id"
        else "Other population"
        if field == "population"
        else None
    )
    with pytest.raises(ValueError):
        evidence = Evidence.model_validate(evidence_data)
        OutcomeEvidenceFeedback.model_validate(feedback.model_copy(update={"evidence": evidence}))


def test_feedback_rejects_dropping_history_and_unknown_directional_claims(
    outcome_scenario: OutcomeScenario,
) -> None:
    s = outcome_scenario
    feedback = s.feedback[0]
    with pytest.raises(ValueError, match="historical"):
        OutcomeEvidenceFeedback.model_validate(feedback.model_copy(update={"prior_evidence": ()}))
    unknown = observation_for(s, s.plan, s.plan.metrics[0].id, None)
    with pytest.raises(ValueError, match="unknown observations"):
        s.service.materialize_evidence(
            s.measuring.after,
            unknown,
            feedback.prior_evidence,
            direction=EvidenceDirection.SUPPORTS,
            rationale="Unknown cannot prove support",
            actor=ACTOR,
            at=s.plan.window.end,
        )
    with pytest.raises(ValidationError):
        feedback.evidence.__setattr__("statement", "Rewrite past evidence")


@pytest.mark.parametrize("kind", [ActorKind.AI, ActorKind.SYSTEM])
def test_review_and_closure_require_accountable_human(
    outcome_scenario: OutcomeScenario, kind: ActorKind
) -> None:
    s = outcome_scenario
    actor = Actor(kind=kind, id="non-human")
    with pytest.raises(ValueError, match="human"):
        s.service.review(
            s.review.hypothesis,
            s.assessment,
            causal_interpretations=(s.causal,),
            evidence=s.review.evidence,
            actor=actor,
            at=s.review.reviewed_at,
            rationale="Unaccountable",
            actions=(FollowUpAction.NO_FURTHER_ACTION,),
            follow_up_learning=(),
            unresolved_questions=(),
            acknowledged_limitations=s.review.acknowledged_limitations,
        )
    with pytest.raises(ValueError, match="human"):
        s.service.close(
            s.review.hypothesis,
            s.completed,
            s.plan,
            s.review,
            actor=actor,
            at=s.review.reviewed_at,
            rationale="Unaccountable",
        )


def test_review_must_cover_limitations_and_all_metrics(outcome_scenario: OutcomeScenario) -> None:
    s = outcome_scenario
    with pytest.raises(ValueError, match="limitations"):
        OutcomeReview.model_validate(s.review.model_copy(update={"acknowledged_limitations": ()}))
    with pytest.raises(ValueError, match="original"):
        OutcomeReview.model_validate(s.review.model_copy(update={"evidence": ()}))
    with pytest.raises(ValueError, match="OutcomeReview"):
        OutcomeLifecycleChange.model_validate(s.closed.model_copy(update={"review": None}))


def test_stale_review_and_wrong_plan_cannot_close(outcome_scenario: OutcomeScenario) -> None:
    s = outcome_scenario
    wrong = Hypothesis.model_validate(
        {**s.review.hypothesis.model_dump(), "version": s.review.hypothesis.version + 1}
    )
    with pytest.raises(ValueError, match="exact current"):
        s.service.close(
            wrong,
            s.completed,
            s.plan,
            s.review,
            actor=ACTOR,
            at=s.review.reviewed_at,
            rationale="Stale review",
        )
    wrong_plan = controlled_plan(s)
    with pytest.raises(ValueError, match="exact current"):
        s.service.close(
            s.review.hypothesis,
            s.completed,
            wrong_plan,
            s.review,
            actor=ACTOR,
            at=s.review.reviewed_at,
            rationale="Wrong plan",
        )
    with pytest.raises(ValueError):
        s.service.begin_measurement(
            s.implemented.after,
            s.started,
            s.plan,
            actor=ACTOR,
            at=s.plan.window.start,
            rationale="Incomplete implementation",
        )


@pytest.mark.parametrize("allowed", [True, False])
def test_inconclusive_closure_requires_explicit_policy_and_review(
    outcome_scenario: OutcomeScenario, allowed: bool
) -> None:
    s = outcome_scenario
    policy = OutcomeMeasurementPolicy(
        version="test-closure.v1", allow_inconclusive_closure=allowed, require_complete_window=True
    )
    service = OutcomeFeedbackService(policy)
    evaluations = tuple(
        service.evaluate(s.plan, m.id, (), actor=ACTOR, at=s.plan.window.end)
        for m in s.plan.metrics
    )
    assessment = service.assess(s.plan, evaluations)
    assert assessment.disposition == OutcomeDisposition.INCONCLUSIVE
    review = service.review(
        s.measuring.after,
        assessment,
        causal_interpretations=(),
        evidence=s.feedback[0].prior_evidence,
        actor=ACTOR,
        at=s.plan.window.end,
        rationale="Explicit inconclusive review; preserve tracking failure",
        actions=(FollowUpAction.FURTHER_MEASUREMENT,),
        follow_up_learning=("Resolve tracking",),
        unresolved_questions=("Actual result unknown",),
        acknowledged_limitations=assessment.limitations,
    )
    if allowed:
        closed = service.close(
            review.hypothesis,
            s.completed,
            s.plan,
            review,
            actor=ACTOR,
            at=s.plan.window.end,
            rationale="Review complete; uncertainty retained",
        )
        assert closed.after.status.value == "closed"
    else:
        with pytest.raises(ValueError, match="not permitted"):
            service.close(
                review.hypothesis,
                s.completed,
                s.plan,
                review,
                actor=ACTOR,
                at=s.plan.window.end,
                rationale="Policy forbids this",
            )


def test_closure_is_episode_end_and_follow_up_is_explicit(
    outcome_scenario: OutcomeScenario,
) -> None:
    s = outcome_scenario
    assert s.closed.after.status.value == "closed"
    assert s.closed.review is not None
    assert s.closed.review.assessment.disposition == OutcomeDisposition.MIXED
    assert s.closed.review.unresolved_questions
    assert s.follow_up.follow_up_hypothesis.id != s.review.hypothesis.id
    assert s.follow_up.outcome_evidence_ids == (s.feedback[1].evidence.id,)
    assert s.follow_up.follow_up_hypothesis.links.evidence_ids == ()
    with pytest.raises(ValueError, match="outcome evidence"):
        s.service.link_follow_up(
            s.review,
            s.follow_up.follow_up_hypothesis,
            (uuid4(),),
            actor=ACTOR,
            at=s.review.reviewed_at,
            rationale="Unrelated provenance",
        )
    with pytest.raises(ValueError, match="distinct"):
        s.service.link_follow_up(
            s.review,
            s.review.hypothesis,
            s.follow_up.outcome_evidence_ids,
            actor=ACTOR,
            at=s.review.reviewed_at,
            rationale="No implicit duplication",
        )


def test_controlled_lifecycle_audit_reconstruction(outcome_scenario: OutcomeScenario) -> None:
    s = outcome_scenario
    for change in (s.implemented, s.measuring, s.closed):
        assert change.after.version == change.before.version + 1
        assert (
            change.after.content == change.before.content
            and change.after.links == change.before.links
        )
        assert change.event.metadata.previous_version == change.before.version
        assert change.event.metadata.resulting_version == change.after.version
    with pytest.raises(ValueError, match="audit"):
        OutcomeLifecycleChange.model_validate(
            s.closed.model_copy(update={"rationale": "Rewritten rationale"})
        )


def test_review_cannot_hide_known_causal_contradictions(outcome_scenario: OutcomeScenario) -> None:
    s = outcome_scenario
    assert s.causal.contradicting_evidence
    hidden = CausalInterpretation.model_validate(
        s.causal.model_copy(
            update={"supporting_evidence": (), "contradicting_evidence": (), "quality": ()}
        )
    )
    with pytest.raises(ValueError, match="hide known scoped"):
        OutcomeReview.model_validate(
            s.review.model_copy(update={"causal_interpretations": (hidden,)})
        )


def test_measurement_transition_requires_plan_and_review_chronology(
    outcome_scenario: OutcomeScenario,
) -> None:
    s = outcome_scenario
    with pytest.raises(ValueError, match="explicit plan"):
        OutcomeLifecycleChange.model_validate(s.measuring.model_copy(update={"plan": None}))
    premature = Hypothesis.model_validate(
        {**s.review.hypothesis.model_dump(), "version": s.plan.hypothesis.version}
    )
    with pytest.raises(ValueError, match="measurement episode"):
        OutcomeReview.model_validate(s.review.model_copy(update={"hypothesis": premature}))


def test_review_cannot_use_future_evidence_snapshot(outcome_scenario: OutcomeScenario) -> None:
    s = outcome_scenario
    evidence = s.review.evidence[0]
    future = Evidence.model_validate(
        {**evidence.model_dump(), "reviewed_on": (s.review.reviewed_at + timedelta(days=1)).date()}
    )
    with pytest.raises(ValueError, match="future evidence"):
        OutcomeReview.model_validate(
            s.review.model_copy(update={"evidence": (future,) + s.review.evidence[1:]})
        )
