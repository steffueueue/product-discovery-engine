"""Synthetic selected discovery and fake drafting inputs; no paid model calls."""

from uuid import uuid4

from product_discovery_engine.application.delivery_specification import DeliverySpecificationService
from product_discovery_engine.application.discovery_decisioning import (
    DiscoveryDecisioningService,
    decision_knowledge,
)
from product_discovery_engine.domain.common import Unknown
from product_discovery_engine.domain.delivery_context import (
    ContextFact,
    DeliverySpecContext,
    ReferenceKind,
)
from product_discovery_engine.domain.discovery_promotion import CandidatePromotion
from product_discovery_engine.domain.spec_items import (
    ContentOrigin,
    SpecItem,
    SpecItemType,
    SpecStatement,
)
from product_discovery_engine.domain.spec_proposals import (
    DeliverySpecDraftProposal,
    DraftingProvenance,
    ItemDisposition,
    ItemReview,
    SpecProposalReview,
)
from tests.m4_helpers import ACTOR as ACTOR
from tests.m4_helpers import AT as AT
from tests.m4_helpers import build_scenario


def candidate(solution: str | None = None) -> CandidatePromotion:
    scenario = build_scenario()
    if solution is not None:
        from examples.discovery_decisioning import assess_knowledge, synthetic_evidence
        from product_discovery_engine.domain.decisioning_inputs import ReadinessInput
        from product_discovery_engine.domain.evidence import EvidenceTarget

        knowledge = assess_knowledge(
            tuple(
                synthetic_evidence(
                    EvidenceTarget.SOLUTION, scenario.final.hypothesis.links.claim_ids[0], n
                )
                for n in (5, 6)
            ),
            scenario.evidence_policies,
        )
        data = scenario.final.model_dump()
        data["hypothesis"]["content"]["solution_hypothesis"] = solution
        data["hypothesis"]["links"]["evidence_ids"] += tuple(e.id for e in knowledge.evidence)
        data["knowledge"] += (decision_knowledge(knowledge, scenario.evidence_policies),)
        data["target_scopes"] += (knowledge.scope,)
        inputs = ReadinessInput.model_validate(data)
    else:
        inputs = scenario.final
    service = DiscoveryDecisioningService(scenario.policies)
    assessment = service.readiness(
        inputs, actor=ACTOR, at=AT, challenge_record=scenario.final_challenge
    )
    gate = service.gate(inputs.hypothesis, assessment, actor=ACTOR, at=AT)
    return service.promote(inputs.hypothesis, gate, actor=ACTOR, at=AT)


def context(promotion: CandidatePromotion | None = None) -> DeliverySpecContext:
    promotion = promotion or candidate()
    service = DeliverySpecificationService()
    selection = service.select(
        promotion.after,
        promotion,
        actor=ACTOR,
        at=AT,
        rationale="Accountable choice to explore delivery scope",
    )
    return service.context(selection.after, selection, actor=ACTOR, at=AT)


def fact(
    context: DeliverySpecContext, statement: str, kind: ReferenceKind = ReferenceKind.HUMAN_DECISION
) -> ContextFact:
    return ContextFact(
        id=uuid4(),
        kind=kind,
        hypothesis_id=context.hypothesis.id,
        statement=statement,
        source_artifact="synthetic:review-notes",
        recorded_by=ACTOR,
        recorded_at=AT,
        rationale="Explicit synthetic delivery decision",
    )


def source_item(
    context: DeliverySpecContext,
    kind: SpecItemType = SpecItemType.PROBLEM,
    field: str = "problem_statement",
) -> SpecItem:
    source = next(s for s in context.sources() if s.reference.field == field)
    return SpecItem(
        id=uuid4(),
        kind=kind,
        statement=source.statement,
        origin=ContentOrigin.UNKNOWN
        if isinstance(source.statement, Unknown)
        else ContentOrigin.SOURCE_BACKED,
        references=(source.reference,),
    )


def unknown_item(kind: SpecItemType = SpecItemType.INTERFACE) -> SpecItem:
    return SpecItem(
        id=uuid4(),
        kind=kind,
        statement=Unknown(reason="Details not supplied"),
        origin=ContentOrigin.UNKNOWN,
        references=(),
    )


class FakeDraftingProvider:
    provenance = DraftingProvenance(
        provider="synthetic", model="offline", prompt_version="delivery-specification.v1"
    )

    def __init__(self, items: tuple[SpecItem, ...] | None = None) -> None:
        self.items = items

    def draft_specification(self, context: DeliverySpecContext) -> DeliverySpecDraftProposal:
        items = (
            self.items
            if self.items is not None
            else (
                source_item(context),
                source_item(context, SpecItemType.OUTCOME, "desired_outcome"),
                source_item(context, SpecItemType.SOLUTION, "solution_hypothesis"),
                unknown_item(),
                unknown_item(SpecItemType.QUALITY_REQUIREMENT),
                SpecItem(
                    id=uuid4(),
                    kind=SpecItemType.FUNCTIONAL_REQUIREMENT,
                    statement="Use vector embeddings",
                    origin=ContentOrigin.AI_PROPOSAL,
                    references=(),
                ),
            )
        )
        return DeliverySpecDraftProposal(context_id=context.id, items=items, ai_generated=True)


def reviewed(
    context: DeliverySpecContext, provider: FakeDraftingProvider | None = None
) -> SpecProposalReview:
    service = DeliverySpecificationService(provider or FakeDraftingProvider())
    record = service.draft(context, at=AT)
    items = tuple(
        ItemReview(
            item_id=i.id,
            disposition=ItemDisposition.REJECTED
            if i.origin == ContentOrigin.AI_PROPOSAL
            else ItemDisposition.ACCEPTED,
            rationale="Reject unsupported architecture"
            if i.origin == ContentOrigin.AI_PROPOSAL
            else "Preserve source and explicit unknowns",
        )
        for i in record.proposal.items
    )
    return service.review(record, items, actor=ACTOR, at=AT)


def proposed_statement(value: str | Unknown) -> SpecStatement:
    return SpecStatement(
        statement=value,
        origin=ContentOrigin.UNKNOWN if isinstance(value, Unknown) else ContentOrigin.AI_PROPOSAL,
        references=(),
    )
