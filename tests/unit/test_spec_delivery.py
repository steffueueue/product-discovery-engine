"""Clarification, exact human review, Delivery Gate and handoff fail-safe contracts."""

from datetime import timedelta
from uuid import uuid4

import pytest

from product_discovery_engine.domain.audit import Actor, ActorKind, EventType
from product_discovery_engine.domain.delivery_gate import (
    DeliveryGate,
    DeliveryGateInput,
    DeliveryGateState,
    ImplementationAuthorization,
)
from product_discovery_engine.domain.delivery_specification import DeliverySpec
from product_discovery_engine.domain.hypotheses import Hypothesis
from product_discovery_engine.domain.lifecycle import HypothesisStatus
from product_discovery_engine.domain.spec_clarification import (
    ClarificationActionType,
    ClarificationAnswer,
    ClarificationQuestion,
    ClarificationResolution,
    ClarificationStatus,
)
from product_discovery_engine.domain.spec_completeness_policy import (
    DeliveryCondition,
    GapClassification,
    SpecCompletenessPolicy,
    SpecDimension,
)
from product_discovery_engine.domain.spec_content import DeliverySpecStatus
from product_discovery_engine.domain.spec_gaps import GapType
from product_discovery_engine.domain.spec_items import SpecItemType
from product_discovery_engine.domain.spec_review import ReviewDisposition, SpecReview
from tests.m5_helpers import unknown_item
from tests.m6_helpers import ACTOR, AT, DeliveryScenario, delivery_scenario


@pytest.fixture(scope="module")
def delivery() -> DeliveryScenario:
    return delivery_scenario()


def test_answer_does_not_resolve_or_mutate_spec(delivery: DeliveryScenario) -> None:
    assert delivery.answered.status == ClarificationStatus.ANSWERED
    assert delivery.resolved.status == ClarificationStatus.RESOLVED
    assert delivery.scenario.draft.version == 1
    assert delivery.revision.after.version == 2
    assert delivery.revision.before == delivery.scenario.draft
    assert delivery.initial_assessment.result.blocking_gaps
    assert delivery.inputs.assessment is not None
    assert not delivery.inputs.assessment.result.blocking_gaps
    assert (
        ClarificationQuestion.model_validate_json(delivery.resolved.model_dump_json())
        == delivery.resolved
    )
    answer = delivery.answered.actions[-1].answer
    assert answer is not None
    assert ClarificationAnswer.model_validate_json(answer.model_dump_json()) == answer


def test_blocking_owner_and_targeted_question(delivery: DeliveryScenario) -> None:
    gap = delivery.answered.source_gap
    service = delivery.scenario.delivery
    with pytest.raises(ValueError, match="owner"):
        service.question(
            delivery.initial_assessment,
            gap,
            actor=ACTOR,
            at=AT,
            owner=None,
            rationale="Cannot leave blocking decision unowned",
        )
    question = service.question(
        delivery.initial_assessment,
        gap,
        actor=ACTOR,
        at=AT,
        owner=ACTOR.owner,
        rationale="Explicit ownership",
    )
    assert "contract" in question.question and "owns" in question.question
    assert not any(token in question.question for token in ("200", "/api", "POST"))
    with pytest.raises(ValueError, match="duplicate"):
        service.question(
            delivery.initial_assessment,
            gap,
            actor=ACTOR,
            at=AT,
            owner=ACTOR.owner,
            rationale="Duplicate",
            existing=(question,),
        )
    assigned = service.act_on_question(
        question,
        delivery.scenario.draft,
        kind=ClarificationActionType.ASSIGN_OWNER,
        actor=ACTOR,
        at=AT,
        rationale="Explicit team assignment",
        owner=ACTOR.owner,
    )
    assert assigned.owner == ACTOR.owner and assigned.status == ClarificationStatus.OPEN
    assert assigned.actions[-1].event.event_type == EventType.CLARIFICATION_OWNER_ASSIGNED
    with pytest.raises(ValueError, match="targeted"):
        ClarificationQuestion.model_validate(
            {**question.model_dump(), "question": "Can you clarify the requirements?"}
        )


@pytest.mark.parametrize(
    "failure",
    ["no_provenance", "wrong_question", "ai_answer", "future_answer", "false_human_marker"],
)
def test_answer_integrity(delivery: DeliveryScenario, failure: str) -> None:
    answer = delivery.answered.actions[-1].answer
    assert answer is not None
    data = answer.model_dump()
    if failure == "no_provenance":
        data["source_references"] = ()
    elif failure == "wrong_question":
        data["question_id"] = uuid4()
    elif failure == "ai_answer":
        data["answered_by"] = Actor(kind=ActorKind.AI, id="fake")
    elif failure == "future_answer":
        data["answered_at"] = AT + timedelta(hours=1)
    else:
        data["human_decision"] = "true"
    with pytest.raises(ValueError):
        candidate = ClarificationAnswer.model_validate(data)
        question = ClarificationQuestion.model_validate(
            {**delivery.answered.model_dump(), "actions": ()}
        )
        delivery.scenario.delivery.act_on_question(
            question,
            delivery.scenario.draft,
            kind=ClarificationActionType.ANSWER,
            actor=ACTOR,
            at=AT,
            rationale="Attempt invalid answer",
            answer=candidate,
        )


def test_inadequate_resolution_and_missing_revision(delivery: DeliveryScenario) -> None:
    resolution = delivery.resolved.actions[-1].resolution
    assert resolution is not None
    with pytest.raises(ValueError, match="material resolution requires"):
        invalid = ClarificationResolution.model_validate(
            {**resolution.model_dump(), "revision": None}
        )
        delivery.scenario.delivery.act_on_question(
            delivery.answered,
            delivery.revision.after,
            kind=ClarificationActionType.RESOLVE,
            actor=ACTOR,
            at=AT,
            rationale="Cannot claim materialization without revision",
            resolution=invalid,
        )
    with pytest.raises(ValueError, match="resulting material revision"):
        ClarificationResolution.model_validate(
            {**resolution.model_dump(), "resulting_assessment": delivery.initial_assessment}
        )
    data = delivery.resolved.model_dump()
    data["actions"][0]["answer"]["limitations"] = ("Contract authority is not confirmed",)
    with pytest.raises(ValueError, match="limitations"):
        ClarificationQuestion.model_validate(data)
    with pytest.raises(ValueError):
        delivery.scenario.delivery.act_on_question(
            delivery.resolved,
            delivery.revision.after,
            kind=ClarificationActionType.ANSWER,
            actor=ACTOR,
            at=AT,
            rationale="Terminal questions cannot be answered again",
            answer=delivery.answered.actions[-1].answer,
        )


def test_stale_question_requires_explicit_withdrawal(delivery: DeliveryScenario) -> None:
    service = delivery.scenario.delivery
    assert not delivery.answered.applies_to(delivery.revision.after)
    with pytest.raises(ValueError, match="stale question"):
        service.act_on_question(
            delivery.answered,
            delivery.revision.after,
            kind=ClarificationActionType.ASSIGN_OWNER,
            actor=ACTOR,
            at=AT,
            rationale="Cannot silently carry unresolved question forward",
            owner=ACTOR.owner,
        )
    withdrawn = service.act_on_question(
        delivery.answered,
        delivery.revision.after,
        kind=ClarificationActionType.WITHDRAW,
        actor=ACTOR,
        at=AT,
        rationale="Question superseded by explicitly reviewed current contract",
    )
    assert withdrawn.status == ClarificationStatus.WITHDRAWN
    assert withdrawn.applies_to(delivery.revision.after)
    assert delivery.answered.status == ClarificationStatus.ANSWERED


def test_cross_gap_question_rejected(delivery: DeliveryScenario) -> None:
    assert delivery.inputs.assessment is not None
    with pytest.raises(ValueError, match="exact authoritative"):
        ClarificationQuestion.model_validate(
            {**delivery.answered.model_dump(), "source_gap": delivery.inputs.assessment.gaps[0]}
        )


def test_status_flow_and_superseded_history(delivery: DeliveryScenario) -> None:
    service = delivery.scenario.delivery
    waiting = service.transition(
        delivery.scenario.draft,
        delivery.initial_assessment,
        DeliverySpecStatus.NEEDS_CLARIFICATION,
        actor=ACTOR,
        at=AT,
        rationale="Unresolved interface requires clarification",
    )
    assert waiting.status == DeliverySpecStatus.NEEDS_CLARIFICATION
    assert waiting.status_history[-1].assessment.result.blocking_gaps
    returned = service.transition(
        waiting,
        delivery.initial_assessment,
        DeliverySpecStatus.DRAFT,
        actor=ACTOR,
        at=AT,
        rationale="Return to authoring",
    )
    assert returned.status == DeliverySpecStatus.DRAFT
    assert delivery.inputs.spec.status == DeliverySpecStatus.READY_FOR_DELIVERY
    assert (
        DeliverySpec.model_validate_json(delivery.inputs.spec.model_dump_json())
        == delivery.inputs.spec
    )
    superseded = service.superseded(delivery.revision)
    assert superseded.status == DeliverySpecStatus.SUPERSEDED
    assert delivery.scenario.draft.status == DeliverySpecStatus.DRAFT
    assert superseded.supersession is not None
    assert superseded.supersession.replacement.version == 2
    assert DeliverySpec.model_validate_json(superseded.model_dump_json()) == superseded
    with pytest.raises(ValueError, match="superseded"):
        delivery.scenario.drafting.revise(
            superseded,
            superseded.context,
            superseded.items + (unknown_item(SpecItemType.RISK),),
            actor=ACTOR,
            at=AT,
            reason="Cannot revise terminal historical view",
        )


def test_required_clarification_prevents_ready_states(delivery: DeliveryScenario) -> None:
    assessment = delivery.inputs.assessment
    assert assessment is not None
    with pytest.raises(ValueError, match="explicitly resolved"):
        delivery.scenario.delivery.transition(
            delivery.revision.after,
            assessment,
            DeliverySpecStatus.READY_FOR_REVIEW,
            actor=ACTOR,
            at=AT,
            rationale="Cannot skip required resolution",
            clarifications=(delivery.answered,),
        )
    with pytest.raises(ValueError, match="sufficient information"):
        delivery.scenario.delivery.transition(
            delivery.scenario.draft,
            delivery.initial_assessment,
            DeliverySpecStatus.READY_FOR_REVIEW,
            actor=ACTOR,
            at=AT,
            rationale="Cannot skip blocking information",
        )


@pytest.mark.parametrize(
    "failure",
    [
        "no_review",
        "changes_requested",
        "concerns",
        "ai_reviewer",
        "stale_assessment",
        "bad_transition",
    ],
)
def test_ready_for_delivery_requires_exact_accountable_approval(
    delivery: DeliveryScenario, failure: str
) -> None:
    service = delivery.scenario.delivery
    assessment = delivery.inputs.assessment
    assert assessment is not None
    reviewable = service.transition(
        delivery.revision.after,
        assessment,
        DeliverySpecStatus.READY_FOR_REVIEW,
        actor=ACTOR,
        at=AT,
        rationale="Prepare accountable review",
    )
    review = delivery.inputs.review
    actor = ACTOR
    target = DeliverySpecStatus.READY_FOR_DELIVERY
    selected_assessment = assessment
    with pytest.raises(ValueError):
        if failure == "no_review":
            review = None
        elif failure == "changes_requested":
            review = service.review(
                reviewable,
                assessment,
                actor=ACTOR,
                at=AT,
                disposition=ReviewDisposition.CHANGES_REQUESTED,
                rationale="More work required",
            )
        elif failure == "concerns":
            review = service.review(
                reviewable,
                assessment,
                actor=ACTOR,
                at=AT,
                disposition=ReviewDisposition.REVIEW_WITH_CONCERNS,
                rationale="Outstanding review concerns",
            )
        elif failure == "ai_reviewer":
            review = service.review(
                reviewable,
                assessment,
                actor=Actor(kind=ActorKind.AI, id="fake"),
                at=AT,
                disposition=ReviewDisposition.APPROVED,
                rationale="AI cannot approve",
            )
        elif failure == "stale_assessment":
            selected_assessment = delivery.initial_assessment
        else:
            target = DeliverySpecStatus.READY_FOR_REVIEW
        service.transition(
            reviewable,
            selected_assessment,
            target,
            actor=actor,
            at=AT,
            rationale="Attempt unauthorized readiness",
            review=review,
        )


def test_changes_requested_review_is_retained_and_returns_to_draft(
    delivery: DeliveryScenario,
) -> None:
    service = delivery.scenario.delivery
    assessment = delivery.inputs.assessment
    assert assessment is not None
    reviewable = service.transition(
        delivery.revision.after,
        assessment,
        DeliverySpecStatus.READY_FOR_REVIEW,
        actor=ACTOR,
        at=AT,
        rationale="Ready for review",
    )
    review = service.review(
        reviewable,
        assessment,
        actor=ACTOR,
        at=AT,
        disposition=ReviewDisposition.CHANGES_REQUESTED,
        rationale="Revisit scope",
    )
    returned = service.transition(
        reviewable,
        assessment,
        DeliverySpecStatus.DRAFT,
        actor=ACTOR,
        at=AT,
        rationale="Act on change request",
        review=review,
    )
    assert returned.status_history[-1].review == review
    assert SpecReview.model_validate_json(review.model_dump_json()) == review


def test_pass_gate_and_handoff_are_separate_and_do_not_implement(
    delivery: DeliveryScenario,
) -> None:
    service = delivery.scenario.delivery
    gate = service.gate(delivery.inputs, actor=ACTOR, at=AT)
    assert gate.result.state == DeliveryGateState.PASSED
    assert not gate.result.failed_conditions and not gate.result.unknown_conditions
    assert gate.events[-1].event_type == EventType.DELIVERY_GATE_PASSED
    assert DeliveryGate.model_validate_json(gate.model_dump_json()) == gate
    authorization = service.authorize(
        gate, delivery.inputs, actor=ACTOR, at=AT, rationale="Explicit accountable handoff"
    )
    assert authorization.current.spec == delivery.inputs.spec
    assert authorization.current.hypothesis.status == HypothesisStatus.SELECTED_FOR_DELIVERY
    assert authorization.event.event_type == EventType.IMPLEMENTATION_HANDOFF_AUTHORIZED
    assert (
        ImplementationAuthorization.model_validate_json(authorization.model_dump_json())
        == authorization
    )


@pytest.mark.parametrize(
    "failure,condition",
    [
        ("missing_assessment", DeliveryCondition.COMPLETENESS),
        ("missing_review", DeliveryCondition.APPROVED_REVIEW),
        ("draft_status", DeliveryCondition.READY_STATUS),
        ("wrong_id", DeliveryCondition.CURRENT_SPEC),
        ("wrong_version", DeliveryCondition.CURRENT_SPEC),
        ("wrong_hypothesis", DeliveryCondition.SELECTION),
        ("wrong_selection", DeliveryCondition.SELECTION),
        ("old_assessment", DeliveryCondition.CURRENT_SPEC),
        ("unresolved_question", DeliveryCondition.CLARIFICATIONS),
        ("policy_mismatch", DeliveryCondition.CURRENT_POLICY),
        ("expired_assessment", DeliveryCondition.FRESH_RECORDS),
    ],
)
def test_delivery_gate_blocks_invalid_or_unknown_inputs(
    delivery: DeliveryScenario, failure: str, condition: DeliveryCondition
) -> None:
    service = delivery.scenario.delivery
    data = delivery.inputs.model_dump()
    at = AT
    if failure == "missing_assessment":
        data["assessment"] = None
    elif failure == "missing_review":
        data["review"] = None
    elif failure == "draft_status":
        data["spec"] = delivery.revision.after
    elif failure == "wrong_id":
        data["current_spec"] = delivery.scenario.drafting.create(
            delivery.inputs.spec.context, actor=ACTOR, at=AT
        ).after
    elif failure == "wrong_version":
        data["current_spec"] = delivery.scenario.draft
    elif failure == "wrong_hypothesis":
        data["hypothesis"] = Hypothesis.model_validate(
            {**delivery.inputs.hypothesis.model_dump(), "id": uuid4()}
        )
    elif failure == "wrong_selection":
        # A different selection identity is valid internally but does not bind this spec.
        selection = delivery.inputs.selection.model_dump()
        selection["id"] = uuid4()
        selection["event"]["target"]["id"] = selection["id"]
        selection["lifecycle_event"]["metadata"]["related_ids"] = (
            selection["id"],
            selection["candidacy"]["decision_event"]["id"],
        )
        data["selection"] = selection
    elif failure == "old_assessment":
        data["assessment"] = delivery.initial_assessment
    elif failure == "unresolved_question":
        data["clarifications"] = (delivery.answered,)
    elif failure == "policy_mismatch":
        from product_discovery_engine.application.spec_delivery import SpecDeliveryService

        policy = SpecCompletenessPolicy.model_validate(
            {**service.policy.model_dump(), "version": "spec-completeness.v2"}
        )
        service = SpecDeliveryService(policy)
    else:
        at = AT + timedelta(hours=24)
    inputs = DeliveryGateInput.model_validate(data)
    gate = service.gate(inputs, actor=ACTOR, at=at)
    assert gate.result.state == DeliveryGateState.BLOCKED
    assert condition in gate.result.failed_conditions + gate.result.unknown_conditions
    assert gate.events[-1].event_type == EventType.DELIVERY_GATE_BLOCKED
    with pytest.raises(ValueError, match="PASS"):
        service.authorize(
            gate, inputs, actor=ACTOR, at=at, rationale="Blocked gate cannot hand off"
        )


def test_gate_needs_review_for_current_semantic_concern(delivery: DeliveryScenario) -> None:
    service = delivery.scenario.delivery
    spec = delivery.inputs.spec
    gap = service.materialize_semantic_gap(
        spec,
        dimension=SpecDimension.FUNCTIONAL,
        gap_type=GapType.AMBIGUOUS,
        statement="Possible ambiguous result meaning",
        rationale="Human identifies decision concern",
        source_basis="human:review",
        classification=GapClassification.REVIEW_REQUIRED,
        actor=ACTOR,
        at=AT,
    )
    assessment = service.assess(
        spec,
        actor=ACTOR,
        at=AT,
        applicability=delivery.scenario.applicability,
        semantic_gaps=(gap,),
    )
    from product_discovery_engine.domain.audit import ObjectKind
    from product_discovery_engine.domain.spec_gaps import spec_event

    id = uuid4()
    review = SpecReview(
        id=id,
        assessment=assessment,
        reviewer=ACTOR,
        reviewed_at=AT,
        reviewed_gaps=tuple(g.id for g in assessment.gaps),
        disposition=ReviewDisposition.REVIEW_WITH_CONCERNS,
        rationale="Semantic concern needs review",
        event=spec_event(
            EventType.SPEC_REVIEW_RECORDED,
            ObjectKind.SPEC_REVIEW,
            id,
            ACTOR,
            AT,
            uuid4(),
            (assessment.id, spec.id),
            "Semantic concern needs review",
            spec.version,
        ),
    )
    inputs = DeliveryGateInput.model_validate(
        {**delivery.inputs.model_dump(), "assessment": assessment, "review": review}
    )
    gate = service.gate(inputs, actor=ACTOR, at=AT)
    assert gate.result.state == DeliveryGateState.NEEDS_REVIEW
    assert DeliveryCondition.COMPLETENESS in gate.result.review_required_conditions
    assert gate.events[-1].event_type == EventType.DELIVERY_GATE_REVIEW_REQUIRED


@pytest.mark.parametrize(
    "failure",
    [
        "expired",
        "new_version",
        "new_policy",
        "missing_actor",
        "missing_reason",
        "ai_actor",
        "changed_question_state",
    ],
)
def test_authorization_rejects_stale_or_unaccountable_gate(
    delivery: DeliveryScenario, failure: str
) -> None:
    service = delivery.scenario.delivery
    gate = service.gate(delivery.inputs, actor=ACTOR, at=AT)
    current, at, actor, rationale = delivery.inputs, AT, ACTOR, "Accountable handoff"
    if failure == "expired":
        at = AT + timedelta(hours=24)
    elif failure == "new_version":
        current = DeliveryGateInput.model_validate(
            {**current.model_dump(), "current_spec": delivery.scenario.draft}
        )
    elif failure == "new_policy":
        from product_discovery_engine.application.spec_delivery import SpecDeliveryService

        service = SpecDeliveryService(
            SpecCompletenessPolicy.model_validate(
                {**service.policy.model_dump(), "version": "new-policy"}
            )
        )
    elif failure == "missing_actor":
        actor = Actor(kind=ActorKind.SYSTEM, id="unaccountable")
    elif failure == "missing_reason":
        rationale = " "
    elif failure == "ai_actor":
        actor = Actor(kind=ActorKind.AI, id="fake")
    else:
        current = DeliveryGateInput.model_validate(
            {**current.model_dump(), "clarifications": (delivery.answered,)}
        )
    with pytest.raises(ValueError):
        service.authorize(gate, current, actor=actor, at=at, rationale=rationale)


def test_gate_and_status_tampering_rejected(delivery: DeliveryScenario) -> None:
    gate = delivery.scenario.delivery.gate(delivery.inputs, actor=ACTOR, at=AT)
    for field in ("result", "expires_at", "events"):
        data = gate.model_dump()
        if field == "result":
            data["result"]["state"] = DeliveryGateState.BLOCKED
        elif field == "expires_at":
            data[field] = AT + timedelta(days=5)
        else:
            data[field][0]["actor"] = Actor(kind=ActorKind.AI, id="fake")
        with pytest.raises(ValueError):
            DeliveryGate.model_validate(data)
    data = delivery.inputs.spec.model_dump()
    data["status_history"] = ()
    with pytest.raises(ValueError, match="requires exact"):
        DeliverySpec.model_validate(data)
    data = delivery.inputs.spec.model_dump()
    data["status_history"][-1]["review"] = None
    with pytest.raises(ValueError, match="approved human review"):
        DeliverySpec.model_validate(data)
    with pytest.raises(ValueError, match="AI"):
        delivery.scenario.delivery.gate(
            delivery.inputs, actor=Actor(kind=ActorKind.AI, id="fake"), at=AT
        )


def test_material_revision_discards_old_status_authority(delivery: DeliveryScenario) -> None:
    ready = delivery.inputs.spec
    changed = delivery.scenario.drafting.revise(
        ready,
        ready.context,
        ready.items + (unknown_item(SpecItemType.RISK),),
        actor=ACTOR,
        at=AT,
        reason="New material uncertainty",
    )
    assert changed.after.status == DeliverySpecStatus.DRAFT
    assert changed.after.status_history == ()
    assert ready.status == DeliverySpecStatus.READY_FOR_DELIVERY
    assert delivery.inputs.assessment is not None
    with pytest.raises(ValueError):
        delivery.scenario.delivery.transition(
            changed.after,
            delivery.inputs.assessment,
            DeliverySpecStatus.READY_FOR_REVIEW,
            actor=ACTOR,
            at=AT,
            rationale="Obsolete assessment cannot authorize newer spec",
        )


def test_unrelated_answer_cannot_claim_resolution(delivery: DeliveryScenario) -> None:
    data = delivery.resolved.model_dump()
    data["actions"][0]["answer"]["answer"] = "A different unresolved contract decision"
    with pytest.raises(ValueError, match="exact reviewed answer"):
        ClarificationQuestion.model_validate(data)


@pytest.mark.parametrize(
    "dimension,condition",
    [
        (SpecDimension.INTERFACES, DeliveryCondition.INTERFACES),
        (SpecDimension.DATA, DeliveryCondition.DATA),
        (SpecDimension.QUALITY, DeliveryCondition.QUALITY),
        (SpecDimension.DEPENDENCIES, DeliveryCondition.DEPENDENCIES),
    ],
)
def test_applicable_required_information_blocks_gate_when_missing(
    delivery: DeliveryScenario, dimension: SpecDimension, condition: DeliveryCondition
) -> None:
    from product_discovery_engine.domain.spec_completeness import ApplicabilityDecision

    decisions = tuple(
        ApplicabilityDecision.model_validate({**a.model_dump(), "applicable": True})
        if a.dimension == dimension
        else a
        for a in delivery.scenario.applicability
    )
    draft = delivery.scenario.draft
    assessment = delivery.scenario.delivery.assess(
        draft, actor=ACTOR, at=AT, applicability=decisions
    )
    inputs = DeliveryGateInput(
        spec=draft,
        current_spec=draft,
        hypothesis=draft.context.hypothesis,
        selection=draft.context.selection,
        assessment=assessment,
        review=None,
    )
    gate = delivery.scenario.delivery.gate(inputs, actor=ACTOR, at=AT)
    assert gate.result.state == DeliveryGateState.BLOCKED
    assert condition in gate.result.failed_conditions + gate.result.unknown_conditions
    assert dimension in assessment.result.missing_requirements


def test_unknown_conditions_are_explicit_and_cannot_pass(delivery: DeliveryScenario) -> None:
    inputs = DeliveryGateInput.model_validate({**delivery.inputs.model_dump(), "assessment": None})
    gate = delivery.scenario.delivery.gate(inputs, actor=ACTOR, at=AT)
    assert gate.result.state == DeliveryGateState.BLOCKED
    assert DeliveryCondition.COMPLETENESS in gate.result.unknown_conditions
    assert DeliveryCondition.ACCEPTANCE in gate.result.unknown_conditions
    assert DeliveryCondition.CURRENT_POLICY in gate.result.unknown_conditions


def test_new_blocking_semantic_gap_blocks_existing_ready_spec(delivery: DeliveryScenario) -> None:
    spec = delivery.inputs.spec
    service = delivery.scenario.delivery
    gap = service.materialize_semantic_gap(
        spec,
        dimension=SpecDimension.FUNCTIONAL,
        gap_type=GapType.CONFLICTING,
        statement="Conflicting acceptance interpretations",
        rationale="Explicit human concern",
        source_basis="human:review",
        classification=GapClassification.BLOCKING,
        actor=ACTOR,
        at=AT,
    )
    assessment = service.assess(
        spec,
        actor=ACTOR,
        at=AT,
        applicability=delivery.scenario.applicability,
        semantic_gaps=(gap,),
    )
    inputs = DeliveryGateInput.model_validate(
        {**delivery.inputs.model_dump(), "assessment": assessment}
    )
    gate = service.gate(inputs, actor=ACTOR, at=AT)
    assert gate.result.state == DeliveryGateState.BLOCKED
    assert DeliveryCondition.NO_BLOCKING_GAPS in gate.result.failed_conditions
    assert DeliveryCondition.APPROVED_REVIEW in gate.result.failed_conditions


def test_same_policy_version_cannot_hide_changed_configuration(delivery: DeliveryScenario) -> None:
    assert delivery.inputs.assessment is not None
    policy = SpecCompletenessPolicy.model_validate(
        {**delivery.scenario.delivery.policy.model_dump(), "validity_hours": 12}
    )
    with pytest.raises(ValueError, match="full policy"):
        delivery.inputs.assessment.require_current(delivery.inputs.spec, policy, AT)


def test_owner_omission_and_unchecked_copy_do_not_bypass_scope(delivery: DeliveryScenario) -> None:
    hypothesis = delivery.inputs.hypothesis
    unowned = hypothesis.model_copy(
        update={"content": hypothesis.content.model_copy(update={"owner": None})}
    )
    spec = delivery.inputs.spec
    unsafe = spec.model_copy(
        update={"context": spec.context.model_copy(update={"hypothesis": unowned})}
    )
    inputs = delivery.inputs.model_copy(update={"spec": unsafe})
    with pytest.raises(ValueError, match="exact selected"):
        delivery.scenario.delivery.gate(inputs, actor=ACTOR, at=AT)


def test_missing_acceptance_fails_gate(delivery: DeliveryScenario) -> None:
    original = delivery.scenario.draft
    changed = delivery.scenario.drafting.revise(
        original,
        original.context,
        tuple(i for i in original.items if i.kind != SpecItemType.ACCEPTANCE_CRITERION),
        actor=ACTOR,
        at=AT,
        reason="Acceptance not yet specified",
    )
    assessment = delivery.scenario.delivery.assess(
        changed.after, actor=ACTOR, at=AT, applicability=delivery.scenario.applicability
    )
    inputs = DeliveryGateInput.model_validate(
        {
            **delivery.inputs.model_dump(),
            "spec": changed.after,
            "current_spec": changed.after,
            "assessment": assessment,
        }
    )
    gate = delivery.scenario.delivery.gate(inputs, actor=ACTOR, at=AT)
    assert gate.result.state == DeliveryGateState.BLOCKED
    assert DeliveryCondition.ACCEPTANCE in gate.result.failed_conditions


def test_resolution_without_material_change_requires_reviewed_semantic_state(
    delivery: DeliveryScenario,
) -> None:
    from product_discovery_engine.domain.spec_gaps import GapStatus

    spec, service = delivery.revision.after, delivery.scenario.delivery
    gap = service.materialize_semantic_gap(
        spec,
        dimension=SpecDimension.FUNCTIONAL,
        gap_type=GapType.AMBIGUOUS,
        statement="Interpretation of catalogue results",
        rationale="Need an explicit interpretation",
        source_basis="human:review",
        classification=GapClassification.BLOCKING,
        actor=ACTOR,
        at=AT,
    )
    assessment = service.assess(
        spec,
        actor=ACTOR,
        at=AT,
        applicability=delivery.scenario.applicability,
        semantic_gaps=(gap,),
    )
    question = service.question(
        assessment,
        gap,
        actor=ACTOR,
        at=AT,
        owner=ACTOR.owner,
        rationale="Request explicit interpretation",
    )
    answer = ClarificationAnswer(
        id=uuid4(),
        question_id=question.id,
        answer="The existing wording already identifies catalogue results",
        answered_by=ACTOR,
        answered_at=AT,
        human_decision=False,
        source_references=("synthetic:interpretation-review",),
    )
    answered = service.act_on_question(
        question,
        spec,
        kind=ClarificationActionType.ANSWER,
        actor=ACTOR,
        at=AT,
        rationale="Record interpretation",
        answer=answer,
    )
    reviewed_gap = service.review_gap(
        gap,
        actor=ACTOR,
        at=AT,
        rationale="Exact requirement already specifies behavior",
        classification=GapClassification.NON_BLOCKING,
        status=GapStatus.RESOLVED,
        resolution_references=(answer.id, spec.items[0].id),
    )
    updated = service.assess(
        spec,
        actor=ACTOR,
        at=AT,
        applicability=delivery.scenario.applicability,
        semantic_gaps=(reviewed_gap,),
    )
    resolution = ClarificationResolution(
        answer_id=answer.id,
        reviewed_by=ACTOR,
        resolved_at=AT,
        rationale="Reviewed existing wording is sufficient",
        resulting_assessment=updated,
        resolution_references=(answer.id, spec.items[0].id),
    )
    resolved = service.act_on_question(
        answered,
        spec,
        kind=ClarificationActionType.RESOLVE,
        actor=ACTOR,
        at=AT,
        rationale=resolution.rationale,
        resolution=resolution,
    )
    assert resolved.status == ClarificationStatus.RESOLVED and resolved.spec.version == spec.version
    assert gap.status == GapStatus.OPEN
