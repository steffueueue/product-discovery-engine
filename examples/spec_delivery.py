"""Offline search: unknown interface → owned clarification → v2 → authorized handoff."""

import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples.discovery_decisioning import ACTOR, AT, build_scenario
from product_discovery_engine.application.delivery_specification import DeliverySpecificationService
from product_discovery_engine.application.discovery_decisioning import DiscoveryDecisioningService
from product_discovery_engine.application.spec_delivery import SpecDeliveryService
from product_discovery_engine.domain.common import Unknown
from product_discovery_engine.domain.delivery_context import ContextFact, ReferenceKind
from product_discovery_engine.domain.delivery_gate import (
    DeliveryGateInput,
    DeliveryGateState,
    ImplementationAuthorization,
)
from product_discovery_engine.domain.delivery_specification import DeliverySpec, DeliverySpecChange
from product_discovery_engine.domain.lifecycle import HypothesisStatus
from product_discovery_engine.domain.spec_clarification import (
    ClarificationActionType,
    ClarificationAnswer,
    ClarificationQuestion,
    ClarificationResolution,
    ClarificationStatus,
)
from product_discovery_engine.domain.spec_completeness import (
    ApplicabilityDecision,
    SpecCompletenessAssessment,
)
from product_discovery_engine.domain.spec_completeness_policy import (
    ApplicabilityRule,
    GapClassification,
    SpecDimension,
)
from product_discovery_engine.domain.spec_content import DeliverySpecStatus
from product_discovery_engine.domain.spec_items import ContentOrigin, SpecItem, SpecItemType
from product_discovery_engine.domain.spec_review import ReviewDisposition
from product_discovery_engine.infrastructure.configuration import load_spec_completeness_policy


@dataclass(frozen=True)
class SearchSpecification:
    drafting: DeliverySpecificationService
    delivery: SpecDeliveryService
    draft: DeliverySpec
    applicability: tuple[ApplicabilityDecision, ...]


def search_specification() -> SearchSpecification:
    scenario = build_scenario()
    discovery = DiscoveryDecisioningService(scenario.policies)
    readiness = discovery.readiness(
        scenario.final, actor=ACTOR, at=AT, challenge_record=scenario.final_challenge
    )
    gate = discovery.gate(scenario.final.hypothesis, readiness, actor=ACTOR, at=AT)
    candidate = discovery.promote(scenario.final.hypothesis, gate, actor=ACTOR, at=AT)
    drafting = DeliverySpecificationService()
    selection = drafting.select(
        candidate.after,
        candidate,
        actor=ACTOR,
        at=AT,
        rationale="Explore search delivery scope; this is not implementation",
    )
    policy = load_spec_completeness_policy(
        Path(__file__).resolve().parents[1] / "config/spec-completeness.v1.toml"
    )
    delivery = SpecDeliveryService(policy)
    facts: list[ContextFact] = []
    decisions: list[ApplicabilityDecision] = []
    for rule in policy.dimensions:
        if rule.applicability != ApplicabilityRule.EXPLICIT_CONTEXT:
            continue
        applicable = rule.dimension == SpecDimension.INTERFACES
        fact = ContextFact(
            id=uuid4(),
            kind=ReferenceKind.HUMAN_DECISION,
            hypothesis_id=selection.after.id,
            statement=f"{rule.dimension.value} applicability: {applicable}",
            recorded_by=ACTOR,
            recorded_at=AT,
            source_artifact="synthetic:scope-review",
            rationale="Explicit synthetic scoped applicability decision",
        )
        facts.append(fact)
        decisions.append(
            ApplicabilityDecision(
                dimension=rule.dimension,
                applicable=applicable,
                context_fact_id=fact.id,
                actor=ACTOR,
                at=AT,
                rationale=fact.rationale,
            )
        )
    items: list[SpecItem] = []
    for kind, wording in (
        (SpecItemType.SUMMARY, "Deliver a bounded catalogue-search behavior"),
        (SpecItemType.SCOPE, "Include catalogue search through the existing interface"),
        (SpecItemType.NON_GOAL, "Exclude replacement of ranking architecture"),
        (SpecItemType.FUNCTIONAL_REQUIREMENT, "Return existing catalogue results for a query"),
        (SpecItemType.ACCEPTANCE_CRITERION, "A catalogue query returns existing catalogue results"),
    ):
        fact = ContextFact(
            id=uuid4(),
            kind=ReferenceKind.HUMAN_DECISION,
            hypothesis_id=selection.after.id,
            statement=wording,
            recorded_by=ACTOR,
            recorded_at=AT,
            source_artifact="synthetic:product-review",
            rationale="Explicit human delivery requirement",
        )
        facts.append(fact)
        items.append(
            SpecItem(
                id=uuid4(),
                kind=kind,
                statement=wording,
                origin=ContentOrigin.HUMAN_DECISION,
                references=(fact.reference,),
            )
        )
    context = drafting.context(selection.after, selection, actor=ACTOR, at=AT, facts=tuple(facts))
    for kind, field in (
        (SpecItemType.PROBLEM, "problem_statement"),
        (SpecItemType.SEGMENT, "target_segment"),
        (SpecItemType.OUTCOME, "desired_outcome"),
    ):
        source = next(s for s in context.sources() if s.reference.field == field)
        items.append(
            SpecItem(
                id=uuid4(),
                kind=kind,
                statement=source.statement,
                origin=ContentOrigin.SOURCE_BACKED,
                references=(source.reference,),
            )
        )
    for kind in (SpecItemType.INTERFACE, SpecItemType.ANALYTICS):
        items.append(
            SpecItem(
                id=uuid4(),
                kind=kind,
                statement=Unknown(reason="Details not supplied"),
                origin=ContentOrigin.UNKNOWN,
                references=(),
            )
        )
    draft = drafting.create(context, actor=ACTOR, at=AT, manual_items=tuple(items)).after
    return SearchSpecification(drafting, delivery, draft, tuple(decisions))


def resolve_interface(
    scenario: SearchSpecification,
    spec: DeliverySpec,
    assessment: SpecCompletenessAssessment,
    question: ClarificationQuestion,
    answer: ClarificationAnswer,
) -> tuple[DeliverySpecChange, SpecCompletenessAssessment, ClarificationQuestion]:
    fact = ContextFact(
        id=uuid4(),
        kind=ReferenceKind.HUMAN_DECISION,
        hypothesis_id=spec.hypothesis_id,
        statement=answer.answer,
        recorded_by=ACTOR,
        recorded_at=AT,
        source_artifact=answer.source_references[0],
        rationale="Materialize reviewed interface answer",
    )
    ctx = scenario.drafting.context(
        spec.context.hypothesis,
        spec.context.selection,
        actor=ACTOR,
        at=AT,
        facts=spec.context.delivery_facts + (fact,),
    )
    item = SpecItem(
        id=uuid4(),
        kind=SpecItemType.INTERFACE,
        statement=fact.statement,
        origin=ContentOrigin.HUMAN_DECISION,
        references=(fact.reference,),
    )
    revision = scenario.drafting.revise(
        spec,
        ctx,
        tuple(i for i in spec.items if i.kind != SpecItemType.INTERFACE) + (item,),
        actor=ACTOR,
        at=AT,
        reason="Reviewed answer specifies existing search interface",
    )
    updated = scenario.delivery.assess(
        revision.after, actor=ACTOR, at=AT, applicability=scenario.applicability
    )
    resolution = ClarificationResolution(
        answer_id=answer.id,
        reviewed_by=ACTOR,
        resolved_at=AT,
        rationale="Supplied contract and owner now recorded explicitly",
        revision=revision,
        resulting_assessment=updated,
        resolution_references=(fact.id, item.id),
    )
    resolved = scenario.delivery.act_on_question(
        question,
        revision.after,
        kind=ClarificationActionType.RESOLVE,
        actor=ACTOR,
        at=AT,
        rationale=resolution.rationale,
        resolution=resolution,
    )
    return revision, updated, resolved


def authorized_search() -> ImplementationAuthorization:
    scenario = search_specification()
    service = scenario.delivery
    v1 = scenario.draft
    preserved = v1.model_dump_json()
    assessment = service.assess(v1, actor=ACTOR, at=AT, applicability=scenario.applicability)
    assert len(assessment.result.blocking_gaps) == 1
    assert len(assessment.result.non_blocking_gaps) == 1
    assert {g.dimension for g in assessment.gaps} == {
        SpecDimension.INTERFACES,
        SpecDimension.ANALYTICS,
    }
    blocking = next(g for g in assessment.gaps if g.classification == GapClassification.BLOCKING)
    waiting = service.transition(
        v1,
        assessment,
        DeliverySpecStatus.NEEDS_CLARIFICATION,
        actor=ACTOR,
        at=AT,
        rationale="Existing search contract is required but unknown",
    )
    question = service.question(
        assessment,
        blocking,
        actor=ACTOR,
        at=AT,
        owner=ACTOR.owner,
        rationale="Request the existing contract and its explicit owner",
    )
    print("v1:", waiting.status.value, "— blocking interface unknown; analytics non-blocking")
    print("Owned question:", question.question)
    answer = ClarificationAnswer(
        id=uuid4(),
        question_id=question.id,
        answer="Use the supplied catalogue query contract owned by the assigned Search team",
        answered_by=ACTOR,
        answered_at=AT,
        source_references=("synthetic:search-contract-review",),
        human_decision=True,
    )
    answered = service.act_on_question(
        question,
        waiting,
        kind=ClarificationActionType.ANSWER,
        actor=ACTOR,
        at=AT,
        rationale="Record supplied contract decision without mutating the spec",
        answer=answer,
    )
    assert answered.status == ClarificationStatus.ANSWERED
    assert v1.model_dump_json() == preserved
    print("Answer recorded:", answered.status.value, "— gap remains unresolved")
    revision, reassessment, resolved = resolve_interface(
        scenario, waiting, assessment, answered, answer
    )
    assert resolved.status == ClarificationStatus.RESOLVED
    assert not reassessment.result.blocking_gaps and v1.model_dump_json() == preserved
    v2 = service.transition(
        revision.after,
        reassessment,
        DeliverySpecStatus.READY_FOR_REVIEW,
        actor=ACTOR,
        at=AT,
        rationale="Blocking contract gap resolved in immutable v2",
        clarifications=(resolved,),
    )
    review = service.review(
        v2,
        reassessment,
        actor=ACTOR,
        at=AT,
        disposition=ReviewDisposition.APPROVED,
        rationale="Approve exact v2 with analytics detail retained as non-blocking",
    )
    ready = service.transition(
        v2,
        reassessment,
        DeliverySpecStatus.READY_FOR_DELIVERY,
        actor=ACTOR,
        at=AT,
        rationale="Exact human review permits gate evaluation",
        review=review,
        clarifications=(resolved,),
    )
    inputs = DeliveryGateInput(
        spec=ready,
        current_spec=ready,
        hypothesis=ready.context.hypothesis,
        selection=ready.context.selection,
        assessment=reassessment,
        review=review,
        clarifications=(resolved,),
    )
    gate = service.gate(inputs, actor=ACTOR, at=AT)
    assert gate.result.state == DeliveryGateState.PASSED
    authorization = service.authorize(
        gate,
        inputs,
        actor=ACTOR,
        at=AT,
        rationale="Accountable handoff of the reviewed catalogue-search specification",
    )
    assert authorization.current.hypothesis.status == HypothesisStatus.SELECTED_FOR_DELIVERY
    print("v2:", ready.status.value, "— exact accountable review retained; v1 unchanged")
    print("Delivery Gate:", gate.result.state.value)
    print("Implementation Authorization:", authorization.spec_version, "— handoff only")
    print(
        "Hypothesis:",
        inputs.hypothesis.status.value,
        "— implementation and outcomes remain deferred",
    )

    return authorization


def main() -> None:
    authorized_search()


if __name__ == "__main__":
    main()
