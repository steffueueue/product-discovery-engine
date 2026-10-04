"""Selection and drafting orchestration; provider output never mutates authoritative state."""

from datetime import datetime
from typing import Protocol
from uuid import uuid4

from pydantic import ValidationError

from product_discovery_engine.domain.audit import (
    Actor,
    ActorKind,
    AuditEvent,
    AuditMetadata,
    AuditTarget,
    EventType,
    ObjectKind,
)
from product_discovery_engine.domain.claims import Claim
from product_discovery_engine.domain.delivery_context import ContextFact, DeliverySpecContext
from product_discovery_engine.domain.delivery_selection import (
    DeliverySelection,
    select_for_delivery,
)
from product_discovery_engine.domain.delivery_specification import (
    DeliverySpec,
    DeliverySpecChange,
    create_delivery_spec,
    revise_delivery_spec,
)
from product_discovery_engine.domain.discovery_promotion import CandidatePromotion
from product_discovery_engine.domain.hypotheses import Hypothesis
from product_discovery_engine.domain.spec_items import SpecItem
from product_discovery_engine.domain.spec_proposals import (
    DeliverySpecDraftProposal,
    DraftingProvenance,
    ItemReview,
    SpecProposalRecord,
    SpecProposalReview,
    item_review_event,
)

from .discovery_analysis import AnalysisError, InvalidAnalysis, ProviderUnavailable


class SpecificationDraftingProvider(Protocol):
    provenance: DraftingProvenance

    def draft_specification(self, context: DeliverySpecContext) -> DeliverySpecDraftProposal: ...


class DeliverySpecificationService:
    def __init__(self, provider: SpecificationDraftingProvider | None = None) -> None:
        self.provider = provider

    def select(
        self,
        current: Hypothesis,
        candidacy: CandidatePromotion,
        *,
        actor: Actor,
        rationale: str,
        at: datetime,
        decision_context: tuple[str, ...] = (),
    ) -> DeliverySelection:
        return select_for_delivery(
            current,
            candidacy,
            selection_id=uuid4(),
            actor=actor,
            rationale=rationale,
            at=at,
            decision_context=decision_context,
            lifecycle_event_id=uuid4(),
            event_id=uuid4(),
        )

    def context(
        self,
        current: Hypothesis,
        selection: DeliverySelection,
        *,
        actor: Actor,
        at: datetime,
        claims: tuple[Claim, ...] = (),
        facts: tuple[ContextFact, ...] = (),
    ) -> DeliverySpecContext:
        context_id = uuid4()
        return DeliverySpecContext(
            id=context_id,
            hypothesis=current,
            selection=selection,
            accepted_claims=claims,
            delivery_facts=facts,
            assembled_by=actor,
            assembled_at=at,
            event=AuditEvent(
                id=uuid4(),
                actor=actor,
                occurred_at=at,
                event_type=EventType.DELIVERY_CONTEXT_RECORDED,
                target=AuditTarget(kind=ObjectKind.DELIVERY_CONTEXT, id=context_id),
                metadata=AuditMetadata(
                    related_ids=(current.id, selection.id) + tuple(f.id for f in facts),
                    reason="Explicit allowed drafting context; human assertions retained",
                ),
            ),
        )

    def draft(self, context: DeliverySpecContext, *, at: datetime) -> SpecProposalRecord:
        context = DeliverySpecContext.model_validate(context)
        if self.provider is None:
            raise ProviderUnavailable("No specification drafting provider configured")
        if at.tzinfo is None or at.utcoffset() is None or at < context.assembled_at:
            raise InvalidAnalysis(
                "Draft generation requires aware time at or after context assembly"
            )
        record_id = uuid4()
        provenance = DraftingProvenance.model_validate(self.provider.provenance)
        try:
            result = DeliverySpecDraftProposal.model_validate(
                self.provider.draft_specification(context)
            )
            return SpecProposalRecord(
                id=record_id,
                context=context,
                proposal=result,
                provenance=provenance,
                generated_at=at,
                event=AuditEvent(
                    id=uuid4(),
                    actor=Actor(kind=ActorKind.AI, id=provenance.provider),
                    occurred_at=at,
                    event_type=EventType.SPEC_DRAFT_GENERATED,
                    target=AuditTarget(kind=ObjectKind.SPEC_PROPOSAL, id=record_id),
                    metadata=AuditMetadata(related_ids=(context.id,)),
                ),
            )
        except AnalysisError:
            raise
        except ValidationError:
            raise InvalidAnalysis("Invalid or ungrounded specification proposal") from None
        except Exception:
            raise ProviderUnavailable("Specification drafting provider failed") from None

    def review(
        self,
        record: SpecProposalRecord,
        items: tuple[ItemReview, ...],
        *,
        actor: Actor,
        at: datetime,
    ) -> SpecProposalReview:
        return SpecProposalReview(
            record=record,
            actor=actor,
            reviewed_at=at,
            items=items,
            event=AuditEvent(
                id=uuid4(),
                actor=actor,
                occurred_at=at,
                event_type=EventType.SPEC_PROPOSAL_REVIEWED,
                target=AuditTarget(kind=ObjectKind.SPEC_PROPOSAL, id=record.id),
                metadata=AuditMetadata(related_ids=(record.context.id,)),
            ),
            item_events=tuple(item_review_event(record.id, i, actor, at, uuid4()) for i in items),
        )

    def create(
        self,
        context: DeliverySpecContext,
        *,
        actor: Actor,
        at: datetime,
        manual_items: tuple[SpecItem, ...] = (),
        reviews: tuple[SpecProposalReview, ...] = (),
    ) -> DeliverySpecChange:
        items = manual_items + tuple(i for r in reviews for i in r.accepted_items())
        return create_delivery_spec(
            context,
            items,
            spec_id=uuid4(),
            actor=actor,
            at=at,
            reviews=reviews,
            event_ids=tuple(uuid4() for _ in range(1 + len(items))),
        )

    def revise(
        self,
        before: DeliverySpec,
        context: DeliverySpecContext,
        items: tuple[SpecItem, ...],
        *,
        actor: Actor,
        at: datetime,
        reason: str,
        reviews: tuple[SpecProposalReview, ...] = (),
    ) -> DeliverySpecChange:
        items = items + tuple(i for r in reviews for i in r.accepted_items())
        new_ids = {i.id for i in items} - {i.id for i in before.items}
        return revise_delivery_spec(
            before,
            context,
            items,
            actor=actor,
            at=at,
            reason=reason,
            reviews=reviews,
            event_ids=tuple(uuid4() for _ in range(2 + len(new_ids))),
        )
