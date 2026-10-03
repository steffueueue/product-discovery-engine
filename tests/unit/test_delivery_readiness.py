"""Readiness target boundaries, quality/freshness, source origins and human review."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from examples.discovery_decisioning import assess_knowledge, synthetic_evidence
from product_discovery_engine.application.discovery_decisioning import decision_knowledge
from product_discovery_engine.application.evidence_validation import (
    EvidenceReviewInput,
    EvidenceValidationService,
)
from product_discovery_engine.domain.assumption_risk import assess_assumption_risk
from product_discovery_engine.domain.common import Ordinal, Unknown
from product_discovery_engine.domain.decisioning_inputs import (
    ChallengeDisposition,
    ContradictionDisposition,
    DecisionKnowledge,
    ReadinessInput,
    ReviewedAssumption,
)
from product_discovery_engine.domain.decisioning_policy import (
    DecisioningPolicies,
    ReadinessDimension,
)
from product_discovery_engine.domain.delivery_readiness import (
    DeliveryReadinessAssessment,
    DimensionState,
)
from product_discovery_engine.domain.evidence import Evidence, EvidenceTarget, Freshness
from product_discovery_engine.domain.evidence_assessment import EvidenceScope, QualityInput
from product_discovery_engine.domain.evidence_origins import EvidenceOrigin, OriginRelationship
from product_discovery_engine.domain.evidence_policy import ReliabilityBasis
from tests.m4_helpers import ACTOR, AT, Scenario, build_scenario, dimension, readiness


@pytest.fixture(scope="module")
def scenario() -> Scenario:
    return build_scenario()


def amend(inputs: ReadinessInput, **patch: object) -> ReadinessInput:
    return ReadinessInput.model_validate({**inputs.model_dump(), **patch})


def rebuild(
    packet: DecisionKnowledge,
    *,
    evidence: tuple[Evidence, ...] | None = None,
    relationships: tuple[OriginRelationship, ...] | None = None,
    basis_patch: dict[str, object] | None = None,
) -> DecisionKnowledge:
    items = evidence if evidence is not None else packet.evidence
    reviews = tuple(
        EvidenceReviewInput(
            evidence_id=e.id,
            basis=QualityInput.model_validate(
                {
                    **packet.quality[min(index, len(packet.quality) - 1)].input_basis.model_dump(),
                    "scope": EvidenceScope.of(e),
                    **(basis_patch or {}),
                }
            ),
        )
        for index, e in enumerate(items)
    )
    state = EvidenceValidationService(packet.policies).assess(
        EvidenceScope.of(items[0]),
        items,
        relationships if relationships is not None else packet.origin_relationships,
        reviews,
        actor=ACTOR,
        at=AT,
    )
    return decision_knowledge(state, packet.policies)


def replace_packet(
    inputs: ReadinessInput, packet: DecisionKnowledge, index: int = 0
) -> ReadinessInput:
    knowledge = tuple(packet if i == index else k for i, k in enumerate(inputs.knowledge))
    hypothesis = {
        **inputs.hypothesis.model_dump(),
        "links": {
            **inputs.hypothesis.links.model_dump(),
            "evidence_ids": tuple(e.id for k in knowledge for e in k.evidence),
        },
    }
    return amend(inputs, hypothesis=hypothesis, knowledge=knowledge)


def with_required(scenario: Scenario, *dimensions: ReadinessDimension) -> DecisioningPolicies:
    data = scenario.policies.model_dump()
    data["readiness"]["required_dimensions"] += dimensions
    return DecisioningPolicies.model_validate(data)


def test_problem_support_does_not_infer_other_targets(scenario: Scenario) -> None:
    assessment = readiness(scenario.final, scenario.policies)
    assert dimension(assessment, ReadinessDimension.PROBLEM_EVIDENCE) == DimensionState.SUFFICIENT
    for target in (
        ReadinessDimension.REACH,
        ReadinessDimension.VIABILITY,
        ReadinessDimension.CAUSAL_MECHANISM,
        ReadinessDimension.BUSINESS_IMPACT,
    ):
        assert dimension(assessment, target) == DimensionState.UNKNOWN
        policy = with_required(scenario, target)
        assert readiness(scenario.final, policy).result.state.value == "not_ready"


def test_nonrepresentative_interviews_do_not_establish_reach(scenario: Scenario) -> None:
    items = (
        synthetic_evidence(EvidenceTarget.REACH, UUID(int=32), 5),
        synthetic_evidence(EvidenceTarget.REACH, UUID(int=32), 6),
    )
    packet = decision_knowledge(
        assess_knowledge(items, scenario.evidence_policies), scenario.evidence_policies
    )
    assert all(q.coverage == Ordinal.LOW for q in packet.quality)
    data = scenario.final.model_dump()
    data["hypothesis"]["links"]["claim_ids"] += (UUID(int=32),)
    data["hypothesis"]["links"]["evidence_ids"] += tuple(e.id for e in items)
    data["knowledge"] += (packet,)
    data["target_scopes"] += (packet.scope,)
    assessment = readiness(
        ReadinessInput.model_validate(data), with_required(scenario, ReadinessDimension.REACH)
    )
    assert dimension(assessment, ReadinessDimension.REACH) == DimensionState.INSUFFICIENT
    assert dimension(assessment, ReadinessDimension.PROBLEM_EVIDENCE) == DimensionState.SUFFICIENT


def test_same_origin_reports_cannot_satisfy_independence(scenario: Scenario) -> None:
    packet = scenario.final.knowledge[0]
    relationships = []
    for relationship in packet.origin_relationships:
        origins = tuple(
            EvidenceOrigin.model_validate({**o.model_dump(), "family_key": "same-dataset"})
            for o in relationship.origins
        )
        relationships.append(
            OriginRelationship.model_validate({**relationship.model_dump(), "origins": origins})
        )
    changed = rebuild(packet, relationships=tuple(relationships))
    assert changed.triangulation.independent_source_group_count == 1
    assessment = readiness(replace_packet(scenario.final, changed), scenario.policies)
    assert dimension(assessment, ReadinessDimension.TRIANGULATION) == DimensionState.INSUFFICIENT
    assert assessment.result.state.value == "not_ready"


def test_independent_mixed_methods_can_satisfy_configured_claim(scenario: Scenario) -> None:
    assessment = readiness(scenario.final, scenario.policies)
    packet = scenario.final.knowledge[0]
    assert packet.triangulation.independent_source_group_count == 2
    assert packet.triangulation.independent_method_diversity == 2
    assert dimension(assessment, ReadinessDimension.TRIANGULATION) == DimensionState.SUFFICIENT
    assert assessment.result.state.value == "ready"


@pytest.mark.parametrize(
    "days, expected",
    [
        (0, DimensionState.SUFFICIENT),
        (90, DimensionState.PARTIAL),
        (365, DimensionState.INSUFFICIENT),
    ],
)
def test_freshness_keeps_historical_items_visible(
    scenario: Scenario,
    days: int,
    expected: DimensionState,
) -> None:
    packet = scenario.final.knowledge[0]
    items = tuple(
        Evidence.model_validate(
            {**e.model_dump(), "collected_on": (AT - timedelta(days=days)).date()}
        )
        for e in packet.evidence
    )
    changed = rebuild(packet, evidence=items)
    assessment = readiness(replace_packet(scenario.final, changed), scenario.policies)
    assert dimension(assessment, ReadinessDimension.EVIDENCE_FRESHNESS) == expected
    assert assessment.inputs.knowledge[0].evidence == items
    if days:
        assert set(e.id for e in items) <= set(assessment.result.freshness_concerns)


def test_invalidated_evidence_cannot_satisfy_readiness(scenario: Scenario) -> None:
    packet = scenario.final.knowledge[0]
    items = tuple(
        Evidence.model_validate(
            {
                **e.model_dump(),
                "invalidated_on": AT.date(),
                "invalidation_reason": "Measurement invalid",
            }
        )
        for e in packet.evidence
    )
    changed = rebuild(packet, evidence=items)
    assessment = readiness(replace_packet(scenario.final, changed), scenario.policies)
    assert all(q.freshness.state == Freshness.INVALIDATED for q in changed.quality)
    assert dimension(assessment, ReadinessDimension.PROBLEM_EVIDENCE) == DimensionState.INSUFFICIENT
    assert len(assessment.inputs.knowledge[0].evidence) == len(items)


def test_unknown_quality_cannot_be_replaced_by_evidence_count(scenario: Scenario) -> None:
    packet = rebuild(scenario.final.knowledge[0], basis_patch={"reliability": None})
    assessment = readiness(replace_packet(scenario.final, packet), scenario.policies)
    assert dimension(assessment, ReadinessDimension.EVIDENCE_QUALITY) == DimensionState.UNKNOWN
    assert assessment.result.state.value == "not_ready"


def test_unresolved_critical_assumption_blocks_despite_good_problem_evidence(
    scenario: Scenario,
) -> None:
    assessment = readiness(scenario.initial, scenario.policies)
    assert dimension(assessment, ReadinessDimension.PROBLEM_EVIDENCE) == DimensionState.SUFFICIENT
    assert dimension(assessment, ReadinessDimension.ASSUMPTION_RISK) == DimensionState.INSUFFICIENT
    assert assessment.result.unresolved_high_risk_assumptions == (
        scenario.initial.assumptions[0].assumption.id,
    )


def test_low_impact_uncertainty_need_not_block(scenario: Scenario) -> None:
    item = scenario.initial.assumptions[0]
    assert item.risk is not None
    risk = assess_assumption_risk(
        item.assumption,
        item.risk.scope,
        (),
        decision_impact=Ordinal.LOW,
        uncertainty=Ordinal.VERY_HIGH,
        rationale="Low-impact unresolved detail",
        evidence_gaps=("Detail unknown",),
        policy=scenario.evidence_policies.assumption_risk,
        actor=ACTOR,
        at=AT,
        assessment_id=uuid4(),
        event_id=uuid4(),
    )
    inputs = amend(
        scenario.initial,
        assumptions=(
            ReviewedAssumption(
                assumption=item.assumption,
                risk=risk,
                risk_policy=scenario.evidence_policies.assumption_risk,
            ),
        ),
    )
    assessment = readiness(inputs, scenario.policies)
    assert dimension(assessment, ReadinessDimension.ASSUMPTION_RISK) == DimensionState.SUFFICIENT


def test_missing_risk_is_unknown(scenario: Scenario) -> None:
    item = scenario.final.assumptions[0]
    inputs = amend(
        scenario.final, assumptions=(ReviewedAssumption(assumption=item.assumption, risk=None),)
    )
    assert (
        dimension(readiness(inputs, scenario.policies), ReadinessDimension.ASSUMPTION_RISK)
        == DimensionState.UNKNOWN
    )


@pytest.mark.parametrize(
    "disposition, expected",
    [
        (ContradictionDisposition.HEALTHY_MIXED, DimensionState.PARTIAL),
        (ContradictionDisposition.UNRESOLVED_MATERIAL, DimensionState.INSUFFICIENT),
        (ContradictionDisposition.INVALIDATES_CRITICAL, DimensionState.INSUFFICIENT),
        (ContradictionDisposition.INVESTIGATED_ACCEPTED, DimensionState.SUFFICIENT),
    ],
)
def test_contradiction_treatment_is_explicit_human_input(
    scenario: Scenario,
    disposition: ContradictionDisposition,
    expected: DimensionState,
) -> None:
    review = {**scenario.final.contradictions[0].model_dump(), "disposition": disposition}
    assessment = readiness(amend(scenario.final, contradictions=(review,)), scenario.policies)
    assert dimension(assessment, ReadinessDimension.CONTRADICTIONS) == expected
    assert assessment.inputs.knowledge[-1].evidence[0].direction.value == "contradicts"


def test_missing_contradiction_review_is_unknown(scenario: Scenario) -> None:
    assessment = readiness(amend(scenario.final, contradictions=()), scenario.policies)
    assert dimension(assessment, ReadinessDimension.CONTRADICTIONS) == DimensionState.UNKNOWN
    assert assessment.result.unresolved_contradictions


@pytest.mark.parametrize("field", ["owner", "strategy", "desired_outcome", "target_segment"])
def test_missing_required_context_never_passes(scenario: Scenario, field: str) -> None:
    content = {
        **scenario.final.hypothesis.content.model_dump(),
        field: None if field in {"owner", "strategy"} else Unknown(reason="Unknown"),
    }
    hypothesis = {**scenario.final.hypothesis.model_dump(), "content": content}
    inputs = amend(
        scenario.final,
        hypothesis=hypothesis,
        strategy_context=None if field == "strategy" else scenario.final.strategy_context,
        strategy_acknowledgement=None
        if field == "strategy"
        else scenario.final.strategy_acknowledgement,
    )
    assert readiness(inputs, scenario.policies).result.state.value == "not_ready"


@pytest.mark.parametrize(
    "solution, expected",
    [
        (None, DimensionState.NOT_APPLICABLE),
        (Unknown(reason="Solution context missing"), DimensionState.UNKNOWN),
        ("Improve ranking", DimensionState.UNKNOWN),
    ],
)
def test_solution_specific_requirements_only_apply_when_solution_exists(
    scenario: Scenario,
    solution: str | Unknown | None,
    expected: DimensionState,
) -> None:
    hypothesis = {
        **scenario.final.hypothesis.model_dump(),
        "content": {
            **scenario.final.hypothesis.content.model_dump(),
            "solution_hypothesis": solution,
        },
    }
    assessment = readiness(amend(scenario.final, hypothesis=hypothesis), scenario.policies)
    assert dimension(assessment, ReadinessDimension.SOLUTION_EFFECTIVENESS) == expected


@pytest.mark.parametrize(
    "severity, disposition, expected",
    [
        (Ordinal.HIGH, ChallengeDisposition.UNRESOLVED, DimensionState.INSUFFICIENT),
        (Ordinal.LOW, ChallengeDisposition.UNRESOLVED, DimensionState.SUFFICIENT),
        (None, ChallengeDisposition.UNRESOLVED, DimensionState.UNKNOWN),
        (Ordinal.HIGH, ChallengeDisposition.ACCEPTED, DimensionState.SUFFICIENT),
    ],
)
def test_human_severity_and_treatment_control_challenge_concerns(
    scenario: Scenario,
    severity: Ordinal | None,
    disposition: ChallengeDisposition,
    expected: DimensionState,
) -> None:
    assert scenario.final.challenge is not None
    challenge = scenario.final.challenge.model_dump()
    challenge["items"][0]["human_severity"] = severity
    challenge["items"][0]["disposition"] = disposition
    assessment = readiness(amend(scenario.final, challenge=challenge), scenario.policies)
    assert dimension(assessment, ReadinessDimension.CHALLENGE) == expected
    # Synthetic AI severity remains VERY_HIGH even when human-reviewed severity is LOW.
    assert scenario.final_challenge.result.items[0].severity == Ordinal.VERY_HIGH


def test_readiness_audit_reconstruction_and_tamper_rejection(scenario: Scenario) -> None:
    record = readiness(scenario.final, scenario.policies)
    assert DeliveryReadinessAssessment.model_validate_json(record.model_dump_json()) == record
    data = record.model_dump()
    data["result"]["state"] = "not_ready"
    with pytest.raises(ValidationError, match="reconstruct"):
        DeliveryReadinessAssessment.model_validate(data)
    with pytest.raises(ValidationError, match="frozen"):
        immutable_field = "state"
        setattr(record.result, immutable_field, record.result.state)


@pytest.mark.parametrize("missing", ["assumptions", "validations", "knowledge"])
def test_linked_knowledge_cannot_disappear_from_readiness(scenario: Scenario, missing: str) -> None:
    with pytest.raises(ValidationError, match="all linked|every linked"):
        amend(scenario.final, **{missing: ()})


def test_assessment_requires_freshness_for_the_current_day(scenario: Scenario) -> None:
    with pytest.raises(ValueError, match="same-day"):
        readiness(scenario.final, scenario.policies, at=AT + timedelta(days=1))


def test_invalid_target_or_population_never_cross_validates(scenario: Scenario) -> None:
    scopes = tuple(
        EvidenceScope.model_validate({**s.model_dump(), "population": "Other population"})
        for s in scenario.final.target_scopes
    )
    assessment = readiness(amend(scenario.final, target_scopes=scopes), scenario.policies)
    assert dimension(assessment, ReadinessDimension.PROBLEM_EVIDENCE) == DimensionState.UNKNOWN


def test_quality_rating_cannot_be_tampered_inside_decision_packet(scenario: Scenario) -> None:
    data = scenario.final.knowledge[0].model_dump()
    data["quality"][0]["reliability"] = Ordinal.VERY_HIGH
    # Aggregate stays MEDIUM: reconstructing the reviewer basis catches the changed rating.
    with pytest.raises(ValidationError, match="reconstruct"):
        DecisionKnowledge.model_validate(data)


@pytest.mark.parametrize(
    "reliability", [ReliabilityBasis.KNOWN_MAJOR_ERRORS, ReliabilityBasis.UNDOCUMENTED_METHOD]
)
def test_more_items_do_not_increase_quality(
    scenario: Scenario, reliability: ReliabilityBasis
) -> None:
    changed = rebuild(scenario.final.knowledge[0], basis_patch={"reliability": reliability})
    assessment = readiness(replace_packet(scenario.final, changed), scenario.policies)
    assert dimension(assessment, ReadinessDimension.EVIDENCE_QUALITY) == DimensionState.INSUFFICIENT


@pytest.mark.parametrize("duplicates", [1, 2, 5])
def test_duplicate_same_origin_evidence_never_improves_independence_or_quality(
    scenario: Scenario,
    duplicates: int,
) -> None:
    from product_discovery_engine.domain.common import ORDINAL_ORDER
    from product_discovery_engine.domain.evidence_origins import link_origins

    packet = scenario.final.knowledge[0]
    original = packet.evidence[0]
    items = packet.evidence + tuple(
        Evidence.model_validate({**original.model_dump(), "id": uuid4()}) for _ in range(duplicates)
    )
    extra = tuple(
        link_origins(
            e,
            packet.origin_relationships[0].origins,
            rationale="Report reuses existing dataset",
            actor=ACTOR,
            at=AT,
            event_id=uuid4(),
        )
        for e in items[len(packet.evidence) :]
    )
    changed = rebuild(packet, evidence=items, relationships=packet.origin_relationships + extra)
    assert (
        changed.triangulation.independent_source_group_count
        == packet.triangulation.independent_source_group_count
    )
    assert (
        changed.triangulation.independent_method_diversity
        == packet.triangulation.independent_method_diversity
    )
    for before, after in zip(packet.quality, changed.quality, strict=False):
        assert before.aggregate is not None and after.aggregate is not None
        assert ORDINAL_ORDER.index(after.aggregate) <= ORDINAL_ORDER.index(before.aggregate)
    assessment = readiness(replace_packet(scenario.final, changed), scenario.policies)
    assert assessment.result.state.value != "ready"


def test_filtering_stale_bridge_cannot_create_artificial_source_independence(
    scenario: Scenario,
) -> None:
    from product_discovery_engine.domain.common import Provenance
    from product_discovery_engine.domain.evidence_origins import link_origins

    packet = scenario.final.knowledge[0]
    bridge = synthetic_evidence(EvidenceTarget.PROBLEM_EXISTENCE, UUID(int=30), 7)
    bridge = Evidence.model_validate(
        {
            **bridge.model_dump(),
            "collected_on": (AT - timedelta(days=365)).date(),
            "provenance": Provenance(sources=(bridge.source, *(e.source for e in packet.evidence))),
        }
    )
    relationship = link_origins(
        bridge,
        packet.origin_relationships[0].origins + packet.origin_relationships[1].origins,
        rationale="Derived report bridges both datasets",
        actor=ACTOR,
        at=AT,
        event_id=uuid4(),
    )
    changed = rebuild(
        packet,
        evidence=packet.evidence + (bridge,),
        relationships=packet.origin_relationships + (relationship,),
    )
    data = scenario.policies.model_dump()
    data["readiness"]["evidence_requirements"][0]["minimum_quality"] = "low"
    policy = DecisioningPolicies.model_validate(data)
    assessment = readiness(replace_packet(scenario.final, changed), policy)
    assert dimension(assessment, ReadinessDimension.TRIANGULATION) == DimensionState.INSUFFICIENT
    assert changed.triangulation.independent_source_group_count == 1


@pytest.mark.parametrize("invalidated", [False, True])
def test_completed_validation_with_stale_or_invalidated_dependency_cannot_satisfy_gate(
    scenario: Scenario,
    invalidated: bool,
) -> None:
    from tests.m4_helpers import gate

    packet = scenario.final.knowledge[-1]
    observation = Evidence.model_validate(
        {
            **packet.evidence[0].model_dump(),
            "collected_on": (AT - timedelta(days=365)).date(),
            **(
                {"invalidated_on": AT.date(), "invalidation_reason": "Comparison instrument broken"}
                if invalidated
                else {}
            ),
        }
    )
    changed = rebuild(packet, evidence=(observation,))
    data = (
        replace_packet(scenario.final, changed, index=2).model_dump()
        if not invalidated
        else scenario.final.model_dump()
    )
    if invalidated:
        data["knowledge"] = scenario.final.knowledge[:-1] + (changed,)
        data["contradictions"] = ()
        item = scenario.final.assumptions[0]
        assert item.risk is not None and item.treatment is not None
        risk = assess_assumption_risk(
            item.assumption,
            item.risk.scope,
            (observation,),
            decision_impact=item.risk.decision_impact,
            uncertainty=item.risk.uncertainty,
            rationale="Invalidation retained; explicit treatment still needed",
            evidence_gaps=("Recheck comparison",),
            policy=scenario.evidence_policies.assumption_risk,
            actor=ACTOR,
            at=AT,
            assessment_id=uuid4(),
            event_id=uuid4(),
        )
        data["assumptions"][0]["risk"] = risk
        data["assumptions"][0]["treatment"]["risk_assessment_id"] = risk.id
    inputs = ReadinessInput.model_validate(data)
    assessment = readiness(inputs, scenario.policies)
    assert dimension(assessment, ReadinessDimension.VALIDATION) == DimensionState.INSUFFICIENT
    evaluation = gate(inputs.hypothesis, assessment, scenario.policies)
    assert evaluation.result.state.value == "blocked"
    assert "validation" in evaluation.result.failed_conditions


def test_risk_policy_reconstructs_and_rejects_tampered_risk(scenario: Scenario) -> None:
    data = scenario.final.assumptions[0].model_dump()
    data["risk"]["risk"] = "very_high"
    with pytest.raises(ValidationError, match="reconstruct"):
        ReviewedAssumption.model_validate(data)


@pytest.mark.parametrize("context", ["missing", "unknown_objective"])
def test_strategy_reference_alone_is_not_sufficient_context(
    scenario: Scenario, context: str
) -> None:
    data = scenario.final.model_dump()
    data["strategy_acknowledgement"] = None
    if context == "missing":
        data["strategy_context"] = None
    else:
        data["strategy_context"]["objective"] = Unknown(reason="insufficient_strategy_context")
    assessment = readiness(ReadinessInput.model_validate(data), scenario.policies)
    assert dimension(assessment, ReadinessDimension.STRATEGY) == DimensionState.UNKNOWN
    assert assessment.result.state.value == "not_ready"


def test_completed_validation_directions_cannot_be_relabeled(scenario: Scenario) -> None:
    data = scenario.final.model_dump()
    data["validation_results"][0]["conclusion"] = "supported"
    data["validation_results"][0]["effect"] = "supports"
    with pytest.raises(ValidationError, match="original evidence directions"):
        ReadinessInput.model_validate(data)
