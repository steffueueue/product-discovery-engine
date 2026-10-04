"""Credential-free selection → proposal → reviewed DRAFT v1 → immutable DRAFT v2."""

from datetime import timedelta
from uuid import uuid4

from discovery_decisioning import ACTOR, AT, build_scenario

from product_discovery_engine.application.delivery_specification import DeliverySpecificationService
from product_discovery_engine.application.discovery_decisioning import DiscoveryDecisioningService
from product_discovery_engine.domain.common import Unknown
from product_discovery_engine.domain.delivery_context import (
    ContextFact,
    DeliverySpecContext,
    ReferenceKind,
)
from product_discovery_engine.domain.delivery_specification import DeliverySpecStatus
from product_discovery_engine.domain.lifecycle import HypothesisStatus
from product_discovery_engine.domain.spec_items import ContentOrigin, SpecItem, SpecItemType
from product_discovery_engine.domain.spec_proposals import (
    DeliverySpecDraftProposal,
    DraftingProvenance,
    ItemDisposition,
    ItemReview,
)


class SyntheticSpecificationProvider:
    """Hand-authored offline proposal; no network client or credentials."""

    provenance = DraftingProvenance(
        provider="synthetic", model="offline", prompt_version="delivery-specification.v1"
    )

    def draft_specification(self, context: DeliverySpecContext) -> DeliverySpecDraftProposal:
        items: list[SpecItem] = []
        for kind, field in (
            (SpecItemType.PROBLEM, "problem_statement"),
            (SpecItemType.OUTCOME, "desired_outcome"),
            (SpecItemType.SOLUTION, "solution_hypothesis"),
        ):
            source = next(s for s in context.sources() if s.reference.field == field)
            items.append(
                SpecItem(
                    id=uuid4(),
                    kind=kind,
                    statement=source.statement,
                    origin=ContentOrigin.UNKNOWN
                    if isinstance(source.statement, Unknown)
                    else ContentOrigin.SOURCE_BACKED,
                    references=(source.reference,),
                )
            )
        for kind, reason in (
            (SpecItemType.INTERFACE, "Existing interface details not supplied"),
            (SpecItemType.QUALITY_REQUIREMENT, "Latency target not supplied"),
        ):
            items.append(
                SpecItem(
                    id=uuid4(),
                    kind=kind,
                    statement=Unknown(reason=reason),
                    origin=ContentOrigin.UNKNOWN,
                    references=(),
                )
            )
        items.append(
            SpecItem(
                id=uuid4(),
                kind=SpecItemType.FUNCTIONAL_REQUIREMENT,
                statement="Use vector embeddings",
                origin=ContentOrigin.AI_PROPOSAL,
                references=(),
            )
        )
        return DeliverySpecDraftProposal(
            context_id=context.id, items=tuple(items), ai_generated=True
        )


def main() -> None:
    scenario = build_scenario()
    discovery = DiscoveryDecisioningService(scenario.policies)
    readiness = discovery.readiness(
        scenario.final, actor=ACTOR, at=AT, challenge_record=scenario.final_challenge
    )
    gate = discovery.gate(scenario.final.hypothesis, readiness, actor=ACTOR, at=AT)
    assert scenario.final.hypothesis.status == HypothesisStatus.EVIDENCE_UPDATED
    promotion = discovery.promote(scenario.final.hypothesis, gate, actor=ACTOR, at=AT)
    assert promotion.after.status == HypothesisStatus.CANDIDATE_FOR_DELIVERY_PRIORITIZATION
    print("Discovery Gate:", gate.result.state.value, "— no delivery selection")
    print("Candidacy:", promotion.after.status.value)
    service = DeliverySpecificationService(SyntheticSpecificationProvider())
    selection = service.select(
        promotion.after,
        promotion,
        actor=ACTOR,
        at=AT,
        rationale="Accountable product choice to draft delivery scope; solution remains undecided",
    )
    print("Explicit human selection:", selection.after.status.value)
    context = service.context(selection.after, selection, actor=ACTOR, at=AT)
    proposal = service.draft(context, at=AT)
    print("Allowed context retains evidence, refuted assumption, validation and human reviews")
    decisions = tuple(
        ItemReview(
            item_id=i.id,
            disposition=ItemDisposition.REJECTED
            if i.origin == ContentOrigin.AI_PROPOSAL
            else ItemDisposition.ACCEPTED,
            rationale="No selected technical solution supports vector embeddings"
            if i.origin == ContentOrigin.AI_PROPOSAL
            else "Preserve sourced content and unknowns",
        )
        for i in proposal.proposal.items
    )
    review = service.review(proposal, decisions, actor=ACTOR, at=AT)
    creation = service.create(context, actor=ACTOR, at=AT, reviews=(review,))
    v1 = creation.after
    assert v1.status == DeliverySpecStatus.DRAFT
    assert all(i.statement != "Use vector embeddings" for i in v1.items)
    assert sum(isinstance(i.statement, Unknown) for i in v1.items) == 3
    print("Rejected unsupported embedding proposal; rejection and AI origin retained")
    print("Solution, interface and latency details remain explicitly unknown")
    print("DeliverySpec v1:", v1.status.value, "— problem/outcome references preserved")
    preserved = v1.model_dump_json()
    decision = ContextFact(
        id=uuid4(),
        kind=ReferenceKind.HUMAN_DECISION,
        hypothesis_id=selection.after.id,
        statement="Keep ranking architecture outside this draft scope",
        source_artifact="synthetic:product-review",
        recorded_by=ACTOR,
        recorded_at=AT + timedelta(minutes=1),
        rationale="Explicitly bound the proposed scope",
    )
    revised_context = service.context(
        selection.after, selection, actor=ACTOR, at=AT + timedelta(minutes=1), facts=(decision,)
    )
    non_goal = SpecItem(
        id=uuid4(),
        kind=SpecItemType.NON_GOAL,
        statement=decision.statement,
        origin=ContentOrigin.HUMAN_DECISION,
        references=(decision.reference,),
    )
    revision = service.revise(
        v1,
        revised_context,
        v1.items + (non_goal,),
        actor=ACTOR,
        at=AT + timedelta(minutes=1),
        reason="Record human scope boundary",
    )
    assert revision.after.version == 2
    assert revision.before == v1 and v1.model_dump_json() == preserved
    assert revision.after.proposal_reviews == v1.proposal_reviews
    print("DeliverySpec v2:", revision.after.status.value, "— human scope decision added")
    print(
        "v1 unchanged; supersession linked and audited; no completeness analysis or Delivery Gate"
    )


if __name__ == "__main__":
    main()
