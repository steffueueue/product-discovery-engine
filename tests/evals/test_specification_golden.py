"""Ten hand-authored offline proposal contracts; these do not establish live semantics."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import TypeAdapter

from product_discovery_engine.application.delivery_specification import DeliverySpecificationService
from product_discovery_engine.application.discovery_analysis import InvalidAnalysis
from product_discovery_engine.domain.claims import Claim, ClaimKind
from product_discovery_engine.domain.common import DomainModel, Unknown
from product_discovery_engine.domain.delivery_context import ReferenceKind, SpecReference
from product_discovery_engine.domain.spec_items import (
    AcceptanceCriterion,
    ContentOrigin,
    SpecItem,
    SpecItemType,
)
from product_discovery_engine.domain.spec_proposals import ItemDisposition, ItemReview
from tests.m5_helpers import (
    ACTOR,
    AT,
    FakeDraftingProvider,
    candidate,
    context,
    fact,
    proposed_statement,
)


class GoldenCase(DomainModel):
    case: str
    name: str
    kind: SpecItemType
    statement: str | None
    origin: ContentOrigin
    field: str | None
    expected: str


CASES = TypeAdapter(tuple[GoldenCase, ...]).validate_python(
    json.loads((Path(__file__).parents[1] / "fixtures/specification_drafting.json").read_text())
)


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c.case}-{c.name}")
def test_offline_specification_contract(case: GoldenCase) -> None:
    promotion = candidate(case.statement if case.case == "B" else None)
    service = DeliverySpecificationService()
    ctx = context(promotion)
    refs: tuple[SpecReference, ...] = ()
    if case.field:
        refs = (next(s.reference for s in ctx.sources() if s.reference.field == case.field),)
    if case.case in {"D", "F", "J"}:
        value = {
            "D": "Search integrates with the existing catalogue",
            "F": "Support the existing web platform",
            "J": "Offer a manual relevance review tool",
        }[case.case]
        explicit = fact(
            ctx,
            value,
            {
                "D": ReferenceKind.SYSTEM_FACT,
                "F": ReferenceKind.CONSTRAINT,
                "J": ReferenceKind.HUMAN_DECISION,
            }[case.case],
        )
        ctx = service.context(ctx.hypothesis, ctx.selection, actor=ACTOR, at=AT, facts=(explicit,))
        refs = (explicit.reference,)
    if case.case == "E":
        evidence = ctx.selection.candidacy.gate.readiness
        assert evidence is not None
        source = evidence.inputs.knowledge[0].evidence[0]
        claim = Claim(
            id=ctx.hypothesis.links.claim_ids[0],
            kind=ClaimKind.EVIDENCE,
            statement="Users frequently reformulate queries",
            provenance=source.provenance,
            evidence_ids=(source.id,),
        )
        ctx = service.context(ctx.hypothesis, ctx.selection, actor=ACTOR, at=AT, claims=(claim,))
        refs = (SpecReference(kind=ReferenceKind.CLAIM, id=str(claim.id)),)
    if case.case == "G":
        refs = tuple(
            s.reference
            for s in ctx.sources()
            if s.reference.kind in {ReferenceKind.EVIDENCE, ReferenceKind.ASSUMPTION}
        )
    if case.case == "H":
        refs = (SpecReference(kind=ReferenceKind.EVIDENCE, id=str(uuid4())),)
    item = SpecItem(
        id=uuid4(),
        kind=case.kind,
        origin=case.origin,
        statement=case.statement if case.statement is not None else Unknown(reason="Not supplied"),
        references=refs,
        acceptance_criterion=AcceptanceCriterion(
            given=proposed_statement("A studied customer"),
            when=proposed_statement("They search"),
            then=proposed_statement(Unknown(reason="Measure not yet decided")),
        )
        if case.case == "I"
        else None,
    )
    if case.case == "J":
        spec = service.create(ctx, actor=ACTOR, at=AT, manual_items=(item,)).after
    else:
        service = DeliverySpecificationService(FakeDraftingProvider((item,)))
        if case.expected == "reject":
            with pytest.raises(InvalidAnalysis):
                service.draft(ctx, at=AT)
            return
        record = service.draft(ctx, at=AT)
        review = service.review(
            record,
            (
                ItemReview(
                    item_id=item.id,
                    disposition=ItemDisposition.ACCEPTED,
                    rationale="Reviewed synthetic contract",
                ),
            ),
            actor=ACTOR,
            at=AT,
        )
        spec = service.create(ctx, actor=ACTOR, at=AT, reviews=(review,)).after
    assert spec.items[0].origin.value == case.expected
    assert spec.items[0] == item
    if case.expected == "unknown":
        assert isinstance(spec.items[0].statement, Unknown)
    assert spec.status.value == "draft"
