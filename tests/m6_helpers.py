"""Shared offline specification and human-reviewed handoff snapshots."""

from dataclasses import dataclass
from uuid import uuid4

from examples.spec_delivery import SearchSpecification, resolve_interface, search_specification
from product_discovery_engine.domain.delivery_gate import DeliveryGateInput
from product_discovery_engine.domain.delivery_specification import DeliverySpecChange
from product_discovery_engine.domain.spec_clarification import (
    ClarificationActionType,
    ClarificationAnswer,
    ClarificationQuestion,
)
from product_discovery_engine.domain.spec_completeness import SpecCompletenessAssessment
from product_discovery_engine.domain.spec_completeness_policy import GapClassification
from product_discovery_engine.domain.spec_content import DeliverySpecStatus
from product_discovery_engine.domain.spec_review import ReviewDisposition
from tests.m5_helpers import ACTOR as ACTOR
from tests.m5_helpers import AT as AT


@dataclass(frozen=True)
class DeliveryScenario:
    scenario: SearchSpecification
    initial_assessment: SpecCompletenessAssessment
    answered: ClarificationQuestion
    revision: DeliverySpecChange
    resolved: ClarificationQuestion
    inputs: DeliveryGateInput


def delivery_scenario() -> DeliveryScenario:
    scenario = search_specification()
    service, draft = scenario.delivery, scenario.draft
    assessment = service.assess(draft, actor=ACTOR, at=AT, applicability=scenario.applicability)
    gap = next(g for g in assessment.gaps if g.classification == GapClassification.BLOCKING)
    question = service.question(
        assessment,
        gap,
        actor=ACTOR,
        at=AT,
        owner=ACTOR.owner,
        rationale="Request supplied search contract and owner",
    )
    answer = ClarificationAnswer(
        id=uuid4(),
        question_id=question.id,
        answer="Use the supplied catalogue query contract owned by Search",
        answered_by=ACTOR,
        answered_at=AT,
        source_references=("synthetic:contract-review",),
        human_decision=True,
    )
    answered = service.act_on_question(
        question,
        draft,
        kind=ClarificationActionType.ANSWER,
        actor=ACTOR,
        at=AT,
        rationale="Record answer only",
        answer=answer,
    )
    revision, updated, resolved = resolve_interface(scenario, draft, assessment, answered, answer)
    reviewable = service.transition(
        revision.after,
        updated,
        DeliverySpecStatus.READY_FOR_REVIEW,
        actor=ACTOR,
        at=AT,
        rationale="Required information supplied",
        clarifications=(resolved,),
    )
    review = service.review(
        reviewable,
        updated,
        actor=ACTOR,
        at=AT,
        disposition=ReviewDisposition.APPROVED,
        rationale="Approve exact v2",
    )
    ready = service.transition(
        reviewable,
        updated,
        DeliverySpecStatus.READY_FOR_DELIVERY,
        actor=ACTOR,
        at=AT,
        rationale="Reviewed v2 eligible for gate",
        review=review,
        clarifications=(resolved,),
    )
    inputs = DeliveryGateInput(
        spec=ready,
        current_spec=ready,
        hypothesis=ready.context.hypothesis,
        selection=ready.context.selection,
        assessment=updated,
        review=review,
        clarifications=(resolved,),
    )
    return DeliveryScenario(scenario, assessment, answered, revision, resolved, inputs)
