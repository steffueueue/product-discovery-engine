"""Draft binding, provenance preservation, human review and immutable revision contracts."""

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from product_discovery_engine.application.delivery_specification import DeliverySpecificationService
from product_discovery_engine.application.discovery_analysis import (
    InvalidAnalysis,
    ProviderUnavailable,
)
from product_discovery_engine.domain.audit import Actor, ActorKind, EventType
from product_discovery_engine.domain.common import Unknown
from product_discovery_engine.domain.delivery_context import (
    DeliverySpecContext,
    ReferenceKind,
    SpecReference,
)
from product_discovery_engine.domain.delivery_specification import (
    DeliverySpec,
    DeliverySpecChange,
    DeliverySpecStatus,
)
from product_discovery_engine.domain.spec_items import (
    AcceptanceCriterion,
    ContentOrigin,
    SpecItem,
    SpecItemType,
)
from product_discovery_engine.domain.spec_proposals import (
    DeliverySpecDraftProposal,
    ItemDisposition,
    ItemReview,
    SpecProposalRecord,
    SpecProposalReview,
)
from tests.m5_helpers import (
    ACTOR,
    AT,
    FakeDraftingProvider,
    context,
    fact,
    proposed_statement,
    reviewed,
    source_item,
    unknown_item,
)


@pytest.fixture
def inputs() -> DeliverySpecContext:
    return context()


def test_manual_incomplete_draft_needs_no_ai(inputs: DeliverySpecContext) -> None:
    items = (source_item(inputs), unknown_item())
    change = DeliverySpecificationService().create(inputs, actor=ACTOR, at=AT, manual_items=items)
    assert change.after.status == DeliverySpecStatus.DRAFT
    assert change.after.version == 1
    assert change.after.hypothesis_id == inputs.hypothesis.id
    assert change.after.hypothesis_version == inputs.hypothesis.version
    assert change.after.selection_id == inputs.selection.id
    assert change.after.items == items
    assert isinstance(change.after.items[1].statement, Unknown)
    assert change.events[0].event_type == EventType.SPEC_CREATED
    assert DeliverySpecChange.model_validate_json(change.model_dump_json()) == change
    empty = DeliverySpecificationService().create(inputs, actor=ACTOR, at=AT)
    assert empty.after.items == ()  # Incompleteness is valid, no completeness gate.


def test_reviewed_draft_preserves_rejected_proposal_and_unknowns(
    inputs: DeliverySpecContext,
) -> None:
    review = reviewed(inputs)
    change = DeliverySpecificationService().create(inputs, actor=ACTOR, at=AT, reviews=(review,))
    assert len(change.after.items) == 5
    assert len(change.after.proposal_reviews[0].record.proposal.items) == 6
    assert all(i.statement != "Use vector embeddings" for i in change.after.items)
    assert change.after.proposal_reviews == (review,)
    assert sum(e.event_type == EventType.SPEC_ITEM_REJECTED for e in review.item_events) == 1
    assert sum(isinstance(i.statement, Unknown) for i in change.after.items) == 3
    assert SpecProposalReview.model_validate_json(review.model_dump_json()) == review


def test_human_acceptance_never_rewrites_ai_origin(inputs: DeliverySpecContext) -> None:
    criterion = SpecItem(
        id=uuid4(),
        kind=SpecItemType.ACCEPTANCE_CRITERION,
        statement="Observe whether customers find suitable products",
        origin=ContentOrigin.AI_PROPOSAL,
        references=(),
        acceptance_criterion=AcceptanceCriterion(
            given=proposed_statement("A studied customer"),
            when=proposed_statement("They use search"),
            then=proposed_statement(Unknown(reason="Success measure needs a decision")),
        ),
    )
    service = DeliverySpecificationService(FakeDraftingProvider((criterion,)))
    record = service.draft(inputs, at=AT)
    review = service.review(
        record,
        (
            ItemReview(
                item_id=criterion.id,
                disposition=ItemDisposition.ACCEPTED,
                rationale="Accept proposed criterion wording",
            ),
        ),
        actor=ACTOR,
        at=AT,
    )
    spec = service.create(inputs, actor=ACTOR, at=AT, reviews=(review,)).after
    assert spec.items == (criterion,)
    assert spec.items[0].origin == ContentOrigin.AI_PROPOSAL
    assert spec.proposal_reviews[0].record.proposal.ai_generated is True
    data = spec.model_dump()
    data["items"][0]["origin"] = ContentOrigin.SOURCE_BACKED
    with pytest.raises(ValidationError):
        DeliverySpec.model_validate(data)


def test_explicit_human_decision_and_constraint(inputs: DeliverySpecContext) -> None:
    decision = fact(inputs, "Provide a manual relevance review tool")
    constraint = fact(inputs, "Support the existing web platform", ReferenceKind.CONSTRAINT)
    service = DeliverySpecificationService()
    ctx = service.context(
        inputs.hypothesis, inputs.selection, actor=ACTOR, at=AT, facts=(decision, constraint)
    )
    items = (
        SpecItem(
            id=uuid4(),
            kind=SpecItemType.FUNCTIONAL_REQUIREMENT,
            statement=decision.statement,
            origin=ContentOrigin.HUMAN_DECISION,
            references=(decision.reference,),
        ),
        SpecItem(
            id=uuid4(),
            kind=SpecItemType.CONSTRAINT,
            statement=constraint.statement,
            origin=ContentOrigin.SOURCE_BACKED,
            references=(constraint.reference,),
        ),
    )
    spec = service.create(ctx, actor=ACTOR, at=AT, manual_items=items).after
    assert spec.items[0].origin == ContentOrigin.HUMAN_DECISION
    assert spec.items[1].references == (constraint.reference,)
    assert ctx.event.metadata.related_ids[-2:] == (decision.id, constraint.id)


@pytest.mark.parametrize(
    "reference",
    [
        SpecReference(kind=ReferenceKind.EVIDENCE, id=str(uuid4())),
        SpecReference(
            kind=ReferenceKind.HYPOTHESIS, id=str(uuid4()), version=1, field="problem_statement"
        ),
    ],
)
def test_invented_cross_hypothesis_refs_rejected(
    inputs: DeliverySpecContext, reference: SpecReference
) -> None:
    item = SpecItem(
        id=uuid4(),
        kind=SpecItemType.RISK,
        statement="Possible risk",
        origin=ContentOrigin.AI_PROPOSAL,
        references=(reference,),
    )
    with pytest.raises(InvalidAnalysis, match="ungrounded"):
        DeliverySpecificationService(FakeDraftingProvider((item,))).draft(inputs, at=AT)
    with pytest.raises(ValidationError, match="invented or cross-hypothesis"):
        DeliverySpecificationService().create(inputs, actor=ACTOR, at=AT, manual_items=(item,))


@pytest.mark.parametrize("field", ["id", "version", "status"])
def test_context_requires_exact_selected_snapshot(inputs: DeliverySpecContext, field: str) -> None:
    data = inputs.model_dump()
    data["hypothesis"][field] = {
        "id": uuid4(),
        "version": 99,
        "status": "candidate_for_delivery_prioritization",
    }[field]
    with pytest.raises(ValidationError, match="exact selected"):
        DeliverySpecContext.model_validate(data)


def test_context_rejects_other_selection_and_wrong_fact(inputs: DeliverySpecContext) -> None:
    other = context()
    with pytest.raises(ValidationError, match="context audit"):
        DeliverySpecContext.model_validate({**inputs.model_dump(), "selection": other.selection})
    wrong = fact(inputs, "Wrong context").model_dump()
    wrong["hypothesis_id"] = uuid4()
    with pytest.raises(ValidationError, match="another hypothesis"):
        DeliverySpecContext.model_validate({**inputs.model_dump(), "delivery_facts": (wrong,)})


@pytest.mark.parametrize(
    "kind",
    [
        SpecItemType.FUNCTIONAL_REQUIREMENT,
        SpecItemType.QUALITY_REQUIREMENT,
        SpecItemType.INTERFACE,
        SpecItemType.ACCEPTANCE_CRITERION,
    ],
)
def test_evidence_cannot_become_solution_requirement(
    inputs: DeliverySpecContext, kind: SpecItemType
) -> None:
    source = next(s for s in inputs.sources() if s.reference.kind == ReferenceKind.EVIDENCE)
    item = SpecItem(
        id=uuid4(),
        kind=kind,
        statement=source.statement,
        origin=ContentOrigin.SOURCE_BACKED,
        references=(source.reference,),
    )
    with pytest.raises(ValidationError, match="does not automatically"):
        DeliverySpecificationService().create(inputs, actor=ACTOR, at=AT, manual_items=(item,))


@pytest.mark.parametrize(
    "statement,kind",
    [
        ("Search responds within 200 ms", SpecItemType.QUALITY_REQUIREMENT),
        ("POST /api/v1/search/semantic", SpecItemType.INTERFACE),
        ("Use vector embeddings", SpecItemType.FUNCTIONAL_REQUIREMENT),
    ],
)
def test_unsupported_details_cannot_claim_grounding(
    inputs: DeliverySpecContext,
    statement: str,
    kind: SpecItemType,
) -> None:
    source = source_item(inputs)
    item = SpecItem(
        id=uuid4(),
        kind=kind,
        statement=statement,
        origin=ContentOrigin.SOURCE_BACKED,
        references=source.references,
    )
    with pytest.raises(InvalidAnalysis):
        DeliverySpecificationService(FakeDraftingProvider((item,))).draft(inputs, at=AT)


def test_problem_only_has_unknown_solution(inputs: DeliverySpecContext) -> None:
    item = source_item(inputs, SpecItemType.SOLUTION, "solution_hypothesis")
    assert isinstance(item.statement, Unknown)
    assert item.origin == ContentOrigin.UNKNOWN
    spec = (
        DeliverySpecificationService()
        .create(inputs, actor=ACTOR, at=AT, manual_items=(item,))
        .after
    )
    assert spec.context.hypothesis.content.solution_hypothesis is None


def test_material_revision_keeps_history_and_proposals(inputs: DeliverySpecContext) -> None:
    service = DeliverySpecificationService()
    review = reviewed(inputs)
    v1 = service.create(inputs, actor=ACTOR, at=AT, reviews=(review,)).after
    snapshot = v1.model_dump_json()
    decision = fact(inputs, "Include manual relevance review in scope")
    ctx = service.context(
        inputs.hypothesis, inputs.selection, actor=ACTOR, at=AT, facts=(decision,)
    )
    new_item = SpecItem(
        id=uuid4(),
        kind=SpecItemType.SCOPE,
        statement=decision.statement,
        origin=ContentOrigin.HUMAN_DECISION,
        references=(decision.reference,),
    )
    change = service.revise(
        v1,
        ctx,
        v1.items + (new_item,),
        actor=ACTOR,
        at=AT + timedelta(minutes=1),
        reason="Bound scope explicitly",
    )
    assert v1.model_dump_json() == snapshot
    assert change.after.version == 2
    assert change.after.previous_version is not None
    assert change.after.previous_version.version == 1
    assert change.after.proposal_reviews == (review,)
    assert change.after.revision is not None
    assert change.after.revision.changed_item_ids == (new_item.id,)
    assert [e.event_type for e in change.events] == [
        EventType.SPEC_REVISED,
        EventType.SPEC_SUPERSEDED,
        EventType.HUMAN_SPEC_ITEM_ADDED,
    ]
    assert DeliverySpecChange.model_validate_json(change.model_dump_json()) == change
    assert v1.status == DeliverySpecStatus.DRAFT  # Supersession recorded, old snapshot unchanged.


@pytest.mark.parametrize("failure", ["noop", "reason", "actor", "backdate", "same_id"])
def test_invalid_material_revision(inputs: DeliverySpecContext, failure: str) -> None:
    service = DeliverySpecificationService()
    v1 = service.create(inputs, actor=ACTOR, at=AT, manual_items=(unknown_item(),)).after
    item = unknown_item(SpecItemType.QUALITY_REQUIREMENT)
    items = v1.items + (item,)
    reason = "Add explicit unknown"
    actor = ACTOR
    at = AT
    if failure == "noop":
        items = v1.items
    elif failure == "reason":
        reason = " "
    elif failure == "actor":
        actor = Actor(kind=ActorKind.AI, id="model")
    elif failure == "backdate":
        at = AT - timedelta(seconds=1)
    else:
        item = SpecItem.model_validate(
            {**v1.items[0].model_dump(), "statement": Unknown(reason="Different wording")}
        )
        items = (item,)
    with pytest.raises(ValueError):
        service.revise(v1, inputs, items, actor=actor, at=at, reason=reason)


@pytest.mark.parametrize("status", [s for s in DeliverySpecStatus if s != DeliverySpecStatus.DRAFT])
def test_generic_status_mutation_cannot_bypass_authority(
    inputs: DeliverySpecContext, status: DeliverySpecStatus
) -> None:
    spec = DeliverySpecificationService().create(inputs, actor=ACTOR, at=AT).after
    with pytest.raises(ValidationError, match="requires exact assessment/review authority"):
        DeliverySpec.model_validate({**spec.model_dump(), "status": status})


def test_ai_output_alone_cannot_materialize(inputs: DeliverySpecContext) -> None:
    proposal = FakeDraftingProvider().draft_specification(inputs)
    with pytest.raises(ValidationError, match="AI output alone"):
        DeliverySpecificationService().create(
            inputs, actor=ACTOR, at=AT, manual_items=proposal.items
        )
    with pytest.raises(ValidationError, match="accountable human"):
        DeliverySpecificationService().create(
            inputs, actor=Actor(kind=ActorKind.AI, id="model"), at=AT
        )


def test_review_must_cover_all_items_and_require_human(inputs: DeliverySpecContext) -> None:
    service = DeliverySpecificationService(FakeDraftingProvider())
    record = service.draft(inputs, at=AT)
    with pytest.raises(ValidationError, match="every proposal item"):
        service.review(record, (), actor=ACTOR, at=AT)
    items = tuple(
        ItemReview(item_id=i.id, disposition=ItemDisposition.ACCEPTED, rationale="Review")
        for i in record.proposal.items
    )
    with pytest.raises(ValidationError, match="accountable human"):
        service.review(record, items, actor=Actor(kind=ActorKind.AI, id="model"), at=AT)
    with pytest.raises(ValidationError, match="precede proposal"):
        service.review(record, items, actor=ACTOR, at=AT - timedelta(seconds=1))


def test_rejected_item_cannot_be_materialized(inputs: DeliverySpecContext) -> None:
    review = reviewed(inputs)
    rejected = review.record.proposal.items[-1]
    with pytest.raises(ValidationError, match="human accepted"):
        DeliverySpecificationService().create(
            inputs, actor=ACTOR, at=AT, reviews=(review,), manual_items=(rejected,)
        )


def test_proposal_binding_marker_and_nested_revalidation(inputs: DeliverySpecContext) -> None:
    service = DeliverySpecificationService(FakeDraftingProvider())
    record = service.draft(inputs, at=AT)
    for patch in ({"context_id": uuid4()}, {"ai_generated": False}, {"ai_generated": 1}):
        data = record.model_dump()
        data["proposal"].update(patch)
        with pytest.raises(ValidationError):
            SpecProposalRecord.model_validate(data)
    bad_item = record.proposal.items[0].model_copy(update={"origin": ContentOrigin.AI_PROPOSAL})
    bad = record.model_copy(
        update={"proposal": record.proposal.model_copy(update={"items": (bad_item,)})}
    )
    assert SpecProposalRecord.model_validate(bad).proposal.items == (bad_item,)
    # Tampered audit is still rejected even from unchecked nested instances.
    bad = record.model_copy(
        update={"event": record.event.model_copy(update={"event_type": EventType.SPEC_CREATED})}
    )
    with pytest.raises(ValidationError, match="proposal audit"):
        SpecProposalRecord.model_validate(bad)


def test_tampered_spec_audit_and_review_rejected(inputs: DeliverySpecContext) -> None:
    service = DeliverySpecificationService()
    review = reviewed(inputs)
    change = service.create(inputs, actor=ACTOR, at=AT, reviews=(review,))
    data = change.model_dump()
    data["events"][0]["metadata"]["resulting_version"] = 2
    with pytest.raises(ValidationError, match="audit does not reconstruct"):
        DeliverySpecChange.model_validate(data)
    review_data = review.model_dump()
    review_data["items"][0]["rationale"] = "Different decision"
    with pytest.raises(ValidationError, match="audit must match"):
        SpecProposalReview.model_validate(review_data)
    for field in ("version",):
        with pytest.raises(ValidationError, match="frozen"):
            setattr(change.after, field, 2)


def test_item_type_unknown_and_criterion_validation() -> None:
    with pytest.raises(ValidationError):
        SpecItem.model_validate(
            {
                "id": uuid4(),
                "kind": "made-up",
                "statement": "Text",
                "origin": ContentOrigin.AI_PROPOSAL,
                "references": (),
            }
        )
    with pytest.raises(ValidationError, match="explicitly Unknown"):
        SpecItem(
            id=uuid4(),
            kind=SpecItemType.INTERFACE,
            statement="UNKNOWN",
            origin=ContentOrigin.UNKNOWN,
            references=(),
        )
    with pytest.raises(ValidationError, match="criterion item type"):
        SpecItem(
            id=uuid4(),
            kind=SpecItemType.INTERFACE,
            statement="Proposed",
            origin=ContentOrigin.AI_PROPOSAL,
            references=(),
            acceptance_criterion=AcceptanceCriterion(
                given=proposed_statement("Given"),
                when=proposed_statement("When"),
                then=proposed_statement("Then"),
            ),
        )


def test_provider_optional_and_failure_sanitization(inputs: DeliverySpecContext) -> None:
    with pytest.raises(ProviderUnavailable, match="No specification"):
        DeliverySpecificationService().draft(inputs, at=AT)

    class BrokenProvider(FakeDraftingProvider):
        def draft_specification(self, context: DeliverySpecContext) -> DeliverySpecDraftProposal:
            raise RuntimeError("sensitive-provider-error")

    with pytest.raises(ProviderUnavailable, match="provider failed") as error:
        DeliverySpecificationService(BrokenProvider()).draft(inputs, at=AT)
    assert "sensitive" not in str(error.value)


@pytest.mark.parametrize(
    "kind,wording",
    [
        (SpecItemType.QUALITY_REQUIREMENT, "Search responds within 200 ms"),
        (SpecItemType.INTERFACE, "POST /api/v1/search/semantic"),
        (SpecItemType.SOLUTION, "Use vector embeddings"),
    ],
)
def test_ai_cannot_manufacture_missing_concrete_details(
    inputs: DeliverySpecContext,
    kind: SpecItemType,
    wording: str,
) -> None:
    item = SpecItem(
        id=uuid4(), kind=kind, statement=wording, origin=ContentOrigin.AI_PROPOSAL, references=()
    )
    with pytest.raises(InvalidAnalysis):
        DeliverySpecificationService(FakeDraftingProvider((item,))).draft(inputs, at=AT)


def test_human_decision_origin_survives_ai_organization(inputs: DeliverySpecContext) -> None:
    decision = fact(inputs, "Provide manual relevance review")
    ctx = DeliverySpecificationService().context(
        inputs.hypothesis, inputs.selection, actor=ACTOR, at=AT, facts=(decision,)
    )
    item = SpecItem(
        id=uuid4(),
        kind=SpecItemType.FUNCTIONAL_REQUIREMENT,
        statement=decision.statement,
        origin=ContentOrigin.HUMAN_DECISION,
        references=(decision.reference,),
    )
    service = DeliverySpecificationService(FakeDraftingProvider((item,)))
    record = service.draft(ctx, at=AT)
    review = service.review(
        record,
        (
            ItemReview(
                item_id=item.id,
                disposition=ItemDisposition.ACCEPTED,
                rationale="Preserve existing decision",
            ),
        ),
        actor=ACTOR,
        at=AT,
    )
    spec = service.create(ctx, actor=ACTOR, at=AT, reviews=(review,)).after
    assert spec.items[0].origin == ContentOrigin.HUMAN_DECISION
    assert spec.proposal_reviews[0].record.proposal.ai_generated is True


def test_numeric_structured_criterion_cannot_hide_in_proposal(inputs: DeliverySpecContext) -> None:
    item = SpecItem(
        id=uuid4(),
        kind=SpecItemType.ACCEPTANCE_CRITERION,
        statement="Fast search",
        origin=ContentOrigin.AI_PROPOSAL,
        references=(),
        acceptance_criterion=AcceptanceCriterion(
            given=proposed_statement("A customer"),
            when=proposed_statement("They search"),
            then=proposed_statement("Respond within 200 ms"),
        ),
    )
    with pytest.raises(InvalidAnalysis):
        DeliverySpecificationService(FakeDraftingProvider((item,))).draft(inputs, at=AT)


def test_unknown_summary_cannot_hide_unreviewed_ai_criterion(inputs: DeliverySpecContext) -> None:
    item = SpecItem(
        id=uuid4(),
        kind=SpecItemType.ACCEPTANCE_CRITERION,
        statement=Unknown(reason="Summary unresolved"),
        origin=ContentOrigin.UNKNOWN,
        references=(),
        acceptance_criterion=AcceptanceCriterion(
            given=proposed_statement("A customer"),
            when=proposed_statement("They search"),
            then=proposed_statement("They find a product"),
        ),
    )
    with pytest.raises(ValidationError, match="AI output alone"):
        DeliverySpecificationService().create(inputs, actor=ACTOR, at=AT, manual_items=(item,))


def test_structured_source_backed_criteria_with_clause_provenance(
    inputs: DeliverySpecContext,
) -> None:
    from product_discovery_engine.domain.spec_items import SpecStatement

    values = (
        "Catalogue search acceptance",
        "A catalogue customer",
        "They search the catalogue",
        "An existing catalogue result is returned",
    )
    facts = tuple(fact(inputs, value, ReferenceKind.SYSTEM_FACT) for value in values)
    service = DeliverySpecificationService()
    ctx = service.context(inputs.hypothesis, inputs.selection, actor=ACTOR, at=AT, facts=facts)
    clauses = tuple(
        SpecStatement(
            statement=f.statement, origin=ContentOrigin.SOURCE_BACKED, references=(f.reference,)
        )
        for f in facts
    )
    item = SpecItem(
        id=uuid4(),
        kind=SpecItemType.ACCEPTANCE_CRITERION,
        statement=clauses[0].statement,
        origin=clauses[0].origin,
        references=clauses[0].references,
        acceptance_criterion=AcceptanceCriterion(
            given=clauses[1], when=clauses[2], then=clauses[3]
        ),
    )
    spec = service.create(ctx, actor=ACTOR, at=AT, manual_items=(item,)).after
    assert spec.items[0].acceptance_criterion == item.acceptance_criterion
    tampered = item.model_dump()
    tampered["acceptance_criterion"]["then"]["statement"] = "Search responds within 200 ms"
    with pytest.raises(ValidationError, match="exactly preserve"):
        service.create(ctx, actor=ACTOR, at=AT, manual_items=(SpecItem.model_validate(tampered),))


def test_materialization_requires_exact_reviewed_input_context(inputs: DeliverySpecContext) -> None:
    review = reviewed(inputs)
    service = DeliverySpecificationService()
    new_context = service.context(
        inputs.hypothesis,
        inputs.selection,
        actor=ACTOR,
        at=AT,
        facts=(fact(inputs, "An additional delivery decision"),),
    )
    with pytest.raises(ValidationError, match="exact reviewed context"):
        service.create(new_context, actor=ACTOR, at=AT, reviews=(review,))
    v1 = service.create(inputs, actor=ACTOR, at=AT, reviews=(review,)).after
    new_review = reviewed(inputs)
    with pytest.raises(ValidationError, match="exact reviewed context"):
        service.revise(
            v1,
            new_context,
            v1.items,
            actor=ACTOR,
            at=AT,
            reason="Consume a new proposal",
            reviews=(new_review,),
        )


def test_other_selection_review_cannot_create_spec(inputs: DeliverySpecContext) -> None:
    other_review = reviewed(context())
    with pytest.raises(ValidationError):
        DeliverySpecificationService().create(inputs, actor=ACTOR, at=AT, reviews=(other_review,))


def test_unsupplied_linked_claim_reference_rejected(inputs: DeliverySpecContext) -> None:
    item = SpecItem(
        id=uuid4(),
        kind=SpecItemType.RISK,
        statement="Possible risk",
        origin=ContentOrigin.AI_PROPOSAL,
        references=(
            SpecReference(kind=ReferenceKind.CLAIM, id=str(inputs.hypothesis.links.claim_ids[0])),
        ),
    )
    with pytest.raises(InvalidAnalysis):
        DeliverySpecificationService(FakeDraftingProvider((item,))).draft(inputs, at=AT)


def test_explicit_constraint_addition_has_human_audit(inputs: DeliverySpecContext) -> None:
    constraint = fact(inputs, "Use the existing platform", ReferenceKind.CONSTRAINT)
    service = DeliverySpecificationService()
    ctx = service.context(
        inputs.hypothesis, inputs.selection, actor=ACTOR, at=AT, facts=(constraint,)
    )
    item = SpecItem(
        id=uuid4(),
        kind=SpecItemType.CONSTRAINT,
        statement=constraint.statement,
        origin=ContentOrigin.SOURCE_BACKED,
        references=(constraint.reference,),
    )
    change = service.create(ctx, actor=ACTOR, at=AT, manual_items=(item,))
    assert change.events[-1].event_type == EventType.HUMAN_SPEC_ITEM_ADDED
    assert change.events[-1].actor == ACTOR


def test_revision_tampering_and_removed_review_history_rejected(
    inputs: DeliverySpecContext,
) -> None:
    service = DeliverySpecificationService()
    review = reviewed(inputs)
    v1 = service.create(inputs, actor=ACTOR, at=AT, reviews=(review,)).after
    change = service.revise(
        v1,
        inputs,
        v1.items + (unknown_item(SpecItemType.DATA_REQUIREMENT),),
        actor=ACTOR,
        at=AT,
        reason="Retain missing data rules",
    )
    for field in ("version", "proposal_reviews", "revision"):
        data = change.model_dump()
        if field == "version":
            data["after"][field] = 3
        elif field == "proposal_reviews":
            data["after"][field] = ()
        else:
            data["after"][field]["changed_item_ids"] = (uuid4(),)
        with pytest.raises(ValidationError):
            DeliverySpecChange.model_validate(data)
