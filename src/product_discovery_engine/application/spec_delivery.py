"""Focused Milestone 6 orchestration; provider-free and credential-free."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from product_discovery_engine.domain.audit import Actor, EventType, ObjectKind
from product_discovery_engine.domain.common import Owner
from product_discovery_engine.domain.delivery_gate import (
    DeliveryGate,
    DeliveryGateInput,
    DeliveryGateState,
    ImplementationAuthorization,
    evaluate_delivery_conditions,
)
from product_discovery_engine.domain.delivery_specification import DeliverySpec, DeliverySpecChange
from product_discovery_engine.domain.spec_clarification import (
    ClarificationAction,
    ClarificationActionType,
    ClarificationAnswer,
    ClarificationQuestion,
    ClarificationResolution,
)
from product_discovery_engine.domain.spec_completeness import (
    ApplicabilityDecision,
    SpecCompletenessAssessment,
    completeness_result,
    structural_gaps,
    structural_results,
)
from product_discovery_engine.domain.spec_completeness_policy import (
    GapClassification,
    SpecCompletenessPolicy,
    SpecDimension,
)
from product_discovery_engine.domain.spec_content import (
    DeliverySpecStatus,
    SpecVersionReference,
    spec_body,
)
from product_discovery_engine.domain.spec_gaps import (
    GapBasis,
    GapReview,
    GapStatus,
    GapType,
    SpecGap,
    spec_event,
)
from product_discovery_engine.domain.spec_review import (
    ReviewDisposition,
    SpecReview,
    SpecStatusRecord,
    SpecSupersession,
)


class SpecDeliveryService:
    def __init__(self, policy: SpecCompletenessPolicy) -> None:
        self.policy = SpecCompletenessPolicy.model_validate(policy)

    def assess(
        self,
        spec: DeliverySpec,
        *,
        actor: Actor,
        at: datetime,
        applicability: tuple[ApplicabilityDecision, ...] = (),
        semantic_gaps: tuple[SpecGap, ...] = (),
    ) -> SpecCompletenessAssessment:
        body = spec_body(DeliverySpec.model_validate(spec))
        dimensions = structural_results(body, self.policy, applicability)
        gaps = structural_gaps(body, self.policy, dimensions, actor, at) + semantic_gaps
        id = uuid4()
        return SpecCompletenessAssessment(
            id=id,
            spec=body,
            policy=self.policy,
            applicability=applicability,
            semantic_gaps=semantic_gaps,
            assessed_by=actor,
            assessed_at=at,
            gaps=gaps,
            result=completeness_result(dimensions, gaps, self.policy),
            event=spec_event(
                EventType.SPEC_COMPLETENESS_ASSESSED,
                ObjectKind.DELIVERY_SPEC,
                body.id,
                actor,
                at,
                uuid4(),
                (id,),
                self.policy.version,
                body.version,
            ),
        )

    def materialize_semantic_gap(
        self,
        spec: DeliverySpec,
        *,
        dimension: SpecDimension,
        gap_type: GapType,
        statement: str,
        rationale: str,
        source_basis: str,
        classification: GapClassification,
        actor: Actor,
        at: datetime,
        item_ids: tuple[UUID, ...] = (),
    ) -> SpecGap:
        # No proposal provider is added in v1. A supplied concern is authoritative
        # only through this explicit accountable human operation.

        if any(not isinstance(id, UUID) for id in item_ids):
            raise ValueError("affected item references require UUIDs")
        body = spec_body(DeliverySpec.model_validate(spec))
        id = uuid4()
        gap = SpecGap(
            id=id,
            spec=SpecVersionReference(id=body.id, version=body.version),
            dimension=dimension,
            gap_type=gap_type,
            affected_item_ids=tuple(UUID(str(i)) for i in item_ids),
            statement=statement,
            rationale=rationale,
            source_basis=source_basis,
            basis=GapBasis.HUMAN_REVIEW,
            classification=classification,
            detected_classification=classification,
            detected_by=actor,
            detected_at=at,
            event=spec_event(
                EventType.SPEC_GAP_DETECTED,
                ObjectKind.SPEC_GAP,
                id,
                actor,
                at,
                uuid4(),
                (body.id,),
                rationale,
                body.version,
            ),
        )
        gap.require_scope(body)
        material_at = body.revision.at if body.revision else body.created_at
        if at < material_at:
            raise ValueError("gap cannot precede material specification")
        return gap

    def review_gap(
        self,
        gap: SpecGap,
        *,
        actor: Actor,
        at: datetime,
        rationale: str,
        classification: GapClassification,
        status: GapStatus = GapStatus.OPEN,
        resolution_references: tuple[UUID, ...] = (),
    ) -> SpecGap:

        gap = SpecGap.model_validate(gap)
        if any(not isinstance(id, UUID) for id in resolution_references):
            raise ValueError("resolution references require UUIDs")
        refs = tuple(UUID(str(i)) for i in resolution_references)
        review = GapReview(
            actor=actor,
            at=at,
            rationale=rationale,
            previous_classification=gap.classification,
            previous_status=gap.status,
            resulting_classification=classification,
            resulting_status=status,
            resolution_references=refs,
            event=spec_event(
                EventType.SPEC_GAP_REVIEWED,
                ObjectKind.SPEC_GAP,
                gap.id,
                actor,
                at,
                uuid4(),
                refs,
                rationale,
                gap.spec.version,
            ),
        )
        return SpecGap.model_validate(
            {
                **gap.model_dump(),
                "classification": classification,
                "status": status,
                "reviews": gap.reviews + (review,),
            }
        )

    def question(
        self,
        assessment: SpecCompletenessAssessment,
        gap: SpecGap,
        *,
        actor: Actor,
        at: datetime,
        owner: Owner | None,
        rationale: str,
        existing: tuple[ClarificationQuestion, ...] = (),
    ) -> ClarificationQuestion:
        from product_discovery_engine.domain.spec_clarification import ClarificationStatus

        assessment = SpecCompletenessAssessment.model_validate(assessment)
        if any(
            q.source_gap.id == gap.id and q.status != ClarificationStatus.WITHDRAWN
            for q in existing
        ):
            raise ValueError("duplicate clarification for the same authoritative gap")
        id = uuid4()
        rule = self.policy.requirement(gap.dimension)
        if self.policy != assessment.policy:
            raise ValueError("question requires current assessment policy")
        return ClarificationQuestion(
            id=id,
            assessment=assessment,
            source_gap=gap,
            question=rule.question,
            rationale=rationale,
            requested_information=rule.requested_information,
            initial_owner=owner,
            created_by=actor,
            created_at=at,
            event=spec_event(
                EventType.CLARIFICATION_CREATED,
                ObjectKind.CLARIFICATION,
                id,
                actor,
                at,
                uuid4(),
                (gap.id, assessment.id),
                rationale,
                assessment.spec.version,
            ),
        )

    def act_on_question(
        self,
        question: ClarificationQuestion,
        current_spec: DeliverySpec,
        *,
        kind: ClarificationActionType,
        actor: Actor,
        at: datetime,
        rationale: str,
        owner: Owner | None = None,
        answer: ClarificationAnswer | None = None,
        resolution: ClarificationResolution | None = None,
    ) -> ClarificationQuestion:
        question = ClarificationQuestion.model_validate(question)
        current_spec = DeliverySpec.model_validate(current_spec)
        if kind != ClarificationActionType.WITHDRAW:
            expected = resolution.resulting_assessment.spec if resolution else question.spec
            if expected != spec_body(current_spec):
                raise ValueError("stale question cannot act on an incompatible current version")
        elif (
            current_spec.id != question.spec.id
            or current_spec.context.selection != question.spec.context.selection
        ):
            raise ValueError("withdrawal must preserve spec and selection linkage")
        kind_event = {
            ClarificationActionType.ASSIGN_OWNER: EventType.CLARIFICATION_OWNER_ASSIGNED,
            ClarificationActionType.ANSWER: EventType.CLARIFICATION_ANSWERED,
            ClarificationActionType.RESOLVE: EventType.CLARIFICATION_RESOLVED,
            ClarificationActionType.WITHDRAW: EventType.CLARIFICATION_WITHDRAWN,
        }[kind]
        related = (
            (answer.id,)
            if answer
            else (resolution.answer_id, resolution.resulting_assessment.id)
            if resolution
            else ()
        )
        action = ClarificationAction(
            kind=kind,
            current_spec=spec_body(current_spec),
            actor=actor,
            at=at,
            rationale=rationale,
            owner=owner,
            answer=answer,
            resolution=resolution,
            event=spec_event(
                kind_event,
                ObjectKind.CLARIFICATION,
                question.id,
                actor,
                at,
                uuid4(),
                related,
                rationale,
                question.spec.version,
            ),
        )
        return ClarificationQuestion.model_validate(
            {**question.model_dump(), "actions": question.actions + (action,)}
        )

    def review(
        self,
        spec: DeliverySpec,
        assessment: SpecCompletenessAssessment,
        *,
        actor: Actor,
        at: datetime,
        disposition: ReviewDisposition,
        rationale: str,
        concerns: tuple[str, ...] = (),
    ) -> SpecReview:
        spec = DeliverySpec.model_validate(spec)
        if spec.status != DeliverySpecStatus.READY_FOR_REVIEW:
            raise ValueError("spec review requires controlled READY_FOR_REVIEW")
        assessment = SpecCompletenessAssessment.model_validate(assessment)
        assessment.require_current(spec, self.policy, at)
        id = uuid4()
        return SpecReview(
            id=id,
            assessment=assessment,
            reviewer=actor,
            reviewed_at=at,
            reviewed_gaps=tuple(g.id for g in assessment.gaps),
            disposition=disposition,
            rationale=rationale,
            concerns=concerns,
            event=spec_event(
                EventType.SPEC_REVIEW_RECORDED,
                ObjectKind.SPEC_REVIEW,
                id,
                actor,
                at,
                uuid4(),
                (assessment.id, spec.id),
                rationale,
                spec.version,
            ),
        )

    def transition(
        self,
        spec: DeliverySpec,
        assessment: SpecCompletenessAssessment,
        target: DeliverySpecStatus,
        *,
        actor: Actor,
        at: datetime,
        rationale: str,
        review: SpecReview | None = None,
        clarifications: tuple[ClarificationQuestion, ...] = (),
    ) -> DeliverySpec:
        from product_discovery_engine.domain.spec_clarification import ClarificationStatus

        spec = DeliverySpec.model_validate(spec)
        assessment = SpecCompletenessAssessment.model_validate(assessment)
        assessment.require_current(spec, self.policy, at)
        if target in {DeliverySpecStatus.READY_FOR_REVIEW, DeliverySpecStatus.READY_FOR_DELIVERY}:
            for supplied in clarifications:
                question = ClarificationQuestion.model_validate(supplied)
                if question.source_gap.classification != GapClassification.NON_BLOCKING and (
                    not question.applies_to(spec)
                    or question.status
                    not in {ClarificationStatus.RESOLVED, ClarificationStatus.WITHDRAWN}
                ):
                    raise ValueError(
                        "required clarifications must be explicitly resolved for current spec"
                    )
        kind = {
            DeliverySpecStatus.NEEDS_CLARIFICATION: EventType.SPEC_NEEDS_CLARIFICATION,
            DeliverySpecStatus.READY_FOR_REVIEW: EventType.SPEC_READY_FOR_REVIEW,
            DeliverySpecStatus.READY_FOR_DELIVERY: EventType.SPEC_READY_FOR_DELIVERY,
            DeliverySpecStatus.DRAFT: EventType.STATUS_CHANGED,
        }.get(target)
        if kind is None:
            raise ValueError(
                "supersession is retained by material revision, not arbitrary status mutation"
            )
        record = SpecStatusRecord(
            before=spec.status,
            after=target,
            assessment=assessment,
            review=review,
            actor=actor,
            at=at,
            rationale=rationale,
            event=spec_event(
                kind,
                ObjectKind.DELIVERY_SPEC,
                spec.id,
                actor,
                at,
                uuid4(),
                (assessment.id,) + ((review.id,) if review else ()),
                rationale,
                spec.version,
                previous_status=spec.status.value,
                resulting_status=target.value,
            ),
        )
        return DeliverySpec.model_validate(
            {
                **spec.model_dump(),
                "status": target,
                "status_history": spec.status_history + (record,),
            }
        )

    def gate(self, inputs: DeliveryGateInput, *, actor: Actor, at: datetime) -> DeliveryGate:
        inputs = DeliveryGateInput.model_validate(inputs)
        id = uuid4()
        result = evaluate_delivery_conditions(inputs, self.policy, at)
        expiry = at + timedelta(hours=self.policy.validity_hours)
        if inputs.assessment is not None:
            expiry = min(
                expiry, inputs.assessment.assessed_at + timedelta(hours=self.policy.validity_hours)
            )
        outcome = {
            DeliveryGateState.PASSED: EventType.DELIVERY_GATE_PASSED,
            DeliveryGateState.BLOCKED: EventType.DELIVERY_GATE_BLOCKED,
            DeliveryGateState.NEEDS_REVIEW: EventType.DELIVERY_GATE_REVIEW_REQUIRED,
        }[result.state]
        return DeliveryGate(
            id=id,
            inputs=inputs,
            policy=self.policy,
            evaluated_by=actor,
            evaluated_at=at,
            expires_at=expiry,
            result=result,
            events=tuple(
                spec_event(
                    k,
                    ObjectKind.DELIVERY_GATE,
                    id,
                    actor,
                    at,
                    uuid4(),
                    (inputs.spec.id, inputs.selection.id),
                    self.policy.version,
                    inputs.spec.version,
                )
                for k in (EventType.DELIVERY_GATE_EVALUATED, outcome)
            ),
        )

    def authorize(
        self,
        gate: DeliveryGate,
        current: DeliveryGateInput,
        *,
        actor: Actor,
        at: datetime,
        rationale: str,
        conditions: tuple[str, ...] = (),
    ) -> ImplementationAuthorization:
        id = uuid4()
        return ImplementationAuthorization(
            id=id,
            gate=gate,
            current=current,
            policy=self.policy,
            authorizing_human=actor,
            authorized_at=at,
            rationale=rationale,
            conditions=conditions,
            event=spec_event(
                EventType.IMPLEMENTATION_HANDOFF_AUTHORIZED,
                ObjectKind.IMPLEMENTATION_AUTHORIZATION,
                id,
                actor,
                at,
                uuid4(),
                (gate.id, current.spec.id, current.selection.id, current.hypothesis.id),
                rationale,
                current.spec.version,
            ),
        )

    def superseded(self, change: DeliverySpecChange) -> DeliverySpec:
        """Create a superseded historical view; the retained old snapshot stays unchanged."""
        change = DeliverySpecChange.model_validate(change)
        if change.before is None:
            raise ValueError("creation cannot supersede a previous specification")
        supersession = SpecSupersession(
            previous=spec_body(change.before),
            replacement=spec_body(change.after),
            event=change.events[1],
        )
        return DeliverySpec.model_validate(
            {
                **change.before.model_dump(),
                "status": DeliverySpecStatus.SUPERSEDED,
                "supersession": supersession,
            }
        )
