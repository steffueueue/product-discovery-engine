"""Owned exact-version questions, immutable answers and explicit human resolution."""

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .audit import Actor, AuditEvent, EventType, ObjectKind
from .common import DomainModel, Owner, ReferenceIds, Text
from .delivery_context import ReferenceKind
from .delivery_selection import require_human
from .delivery_specification import DeliverySpecChange
from .spec_completeness import SpecCompletenessAssessment, dimension_acceptable
from .spec_completeness_policy import GapClassification
from .spec_content import DeliverySpecBody, spec_body
from .spec_gaps import GapStatus, SpecGap, spec_event


class ClarificationStatus(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"
    RESOLVED = "resolved"
    WITHDRAWN = "withdrawn"


class ClarificationAnswer(DomainModel):
    id: UUID
    question_id: UUID
    answer: Text
    answered_by: Actor
    answered_at: AwareDatetime
    source_references: tuple[Text, ...]
    supporting_artifacts: tuple[Text, ...] = ()
    limitations: tuple[Text, ...] = ()
    human_decision: bool = Field(strict=True)

    @model_validator(mode="after")
    def require_sources(self) -> "ClarificationAnswer":
        require_human(self.answered_by)
        if not self.source_references or len(set(self.source_references)) != len(
            self.source_references
        ):
            raise ValueError("answer requires unique explicit provenance/source references")
        return self


class ClarificationResolution(DomainModel):
    answer_id: UUID
    reviewed_by: Actor
    resolved_at: AwareDatetime
    rationale: Text
    resulting_assessment: SpecCompletenessAssessment
    revision: DeliverySpecChange | None = None
    resolution_references: ReferenceIds

    @model_validator(mode="after")
    def accountable_resolution(self) -> "ClarificationResolution":
        require_human(self.reviewed_by)
        if not self.resolution_references:
            raise ValueError("resolution requires authoritative resulting references")
        self.resulting_assessment.require_current(
            self.resulting_assessment.spec, self.resulting_assessment.policy, self.resolved_at
        )
        if (
            self.revision is not None
            and spec_body(self.revision.after) != self.resulting_assessment.spec
        ):
            raise ValueError("resolution must consume exact resulting material revision")
        return self


class ClarificationActionType(StrEnum):
    ASSIGN_OWNER = "assign_owner"
    ANSWER = "answer"
    RESOLVE = "resolve"
    WITHDRAW = "withdraw"


class ClarificationAction(DomainModel):
    kind: ClarificationActionType
    actor: Actor
    at: AwareDatetime
    rationale: Text
    current_spec: DeliverySpecBody
    owner: Owner | None = None
    answer: ClarificationAnswer | None = None
    resolution: ClarificationResolution | None = None
    event: AuditEvent

    @model_validator(mode="after")
    def human_action(self) -> "ClarificationAction":
        require_human(self.actor)
        if (self.kind == ClarificationActionType.ASSIGN_OWNER) != (self.owner is not None):
            raise ValueError("owner is supplied only for assignment")
        if (self.kind == ClarificationActionType.ANSWER) != (self.answer is not None):
            raise ValueError("answer is supplied only for answering")
        if (self.kind == ClarificationActionType.RESOLVE) != (self.resolution is not None):
            raise ValueError("resolution is supplied only for resolving")
        return self


class ClarificationQuestion(DomainModel):
    id: UUID
    assessment: SpecCompletenessAssessment
    source_gap: SpecGap
    question: Text
    rationale: Text
    requested_information: Text
    initial_owner: Owner | None
    created_by: Actor
    created_at: AwareDatetime
    due_at: AwareDatetime | None = None
    event: AuditEvent
    actions: tuple[ClarificationAction, ...] = ()

    @model_validator(mode="after")
    def reconstruct(self) -> "ClarificationQuestion":
        require_human(self.created_by)
        self.assessment.require_current(
            self.assessment.spec, self.assessment.policy, self.created_at
        )
        if self.source_gap not in self.assessment.gaps or self.source_gap.status != GapStatus.OPEN:
            raise ValueError("question must reference an exact authoritative unresolved gap")
        rule = self.assessment.policy.requirement(self.source_gap.dimension)
        # v1 deliberately uses reviewed deterministic templates, avoiding invented facts.
        if (
            self.question != rule.question
            or self.requested_information != rule.requested_information
        ):
            raise ValueError("question must use the targeted supplied-policy template")
        if (
            self.source_gap.classification == GapClassification.BLOCKING
            and self.assessment.policy.require_blocking_question_owner
            and self.initial_owner is None
        ):
            raise ValueError("active blocking clarification requires explicit accountable owner")
        if self.due_at is not None and self.due_at < self.created_at:
            raise ValueError("due date cannot precede creation")
        if self.event != spec_event(
            EventType.CLARIFICATION_CREATED,
            ObjectKind.CLARIFICATION,
            self.id,
            self.created_by,
            self.created_at,
            self.event.id,
            (self.source_gap.id, self.assessment.id),
            self.rationale,
            self.spec.version,
        ):
            raise ValueError("question creation audit must reconstruct")
        status = ClarificationStatus.OPEN
        last_at = self.created_at
        latest_answer: ClarificationAnswer | None = None
        answer_ids: set[UUID] = set()
        event_ids = {self.event.id}
        for action in self.actions:
            if (
                status in {ClarificationStatus.RESOLVED, ClarificationStatus.WITHDRAWN}
                or action.at < last_at
            ):
                raise ValueError("terminal clarification or backward action timestamp")
            if action.event.id in event_ids:
                raise ValueError("clarification audit IDs must be distinct")
            event_ids.add(action.event.id)
            last_at = action.at
            if (
                action.current_spec.id != self.spec.id
                or action.current_spec.context.selection != self.spec.context.selection
            ):
                raise ValueError("clarification action must bind current spec/selection")
            if (
                action.kind
                in {ClarificationActionType.ANSWER, ClarificationActionType.ASSIGN_OWNER}
                and action.current_spec != self.spec
            ):
                raise ValueError("stale clarification requires explicit resolution or withdrawal")
            material_at = (
                action.current_spec.revision.at
                if action.current_spec.revision
                else action.current_spec.created_at
            )
            if action.at < material_at:
                raise ValueError("clarification action cannot precede current specification")
            related: tuple[UUID, ...] = ()
            if action.kind == ClarificationActionType.ASSIGN_OWNER:
                kind = EventType.CLARIFICATION_OWNER_ASSIGNED
            elif action.kind == ClarificationActionType.ANSWER:
                answer = action.answer
                assert answer is not None
                if (
                    answer.question_id != self.id
                    or answer.answered_by != action.actor
                    or answer.answered_at != action.at
                    or answer.id in answer_ids
                ):
                    raise ValueError("answer must bind question, unique ID, actor and timestamp")
                answer_ids.add(answer.id)
                latest_answer = answer
                status, kind, related = (
                    ClarificationStatus.ANSWERED,
                    EventType.CLARIFICATION_ANSWERED,
                    (answer.id,),
                )
            elif action.kind == ClarificationActionType.RESOLVE:
                resolution = action.resolution
                assert resolution is not None
                if (
                    status != ClarificationStatus.ANSWERED
                    or latest_answer is None
                    or resolution.answer_id != latest_answer.id
                ):
                    raise ValueError("resolution requires review of the current recorded answer")
                if resolution.reviewed_by != action.actor or resolution.resolved_at != action.at:
                    raise ValueError("resolution review must bind actor/time")
                result = resolution.resulting_assessment
                if action.current_spec != result.spec:
                    raise ValueError("resolution must bind current resulting specification")
                if (
                    result.policy != self.assessment.policy
                    or result.spec.id != self.spec.id
                    or result.spec.context.selection != self.spec.context.selection
                ):
                    raise ValueError("resolution must preserve spec, selection and policy")
                if resolution.revision is None:
                    if result.spec != self.spec:
                        raise ValueError("material resolution requires a retained spec revision")
                    if self.source_gap.id not in {
                        g.id for g in result.gaps if g.status != GapStatus.OPEN
                    }:
                        raise ValueError(
                            "same-version resolution requires explicit semantic gap disposition"
                        )
                else:
                    revision = resolution.revision
                    if (
                        revision.before is None
                        or spec_body(revision.before) != self.spec
                        or revision.after.version != self.spec.version + 1
                    ):
                        raise ValueError(
                            "resolution revision requires exact question version predecessor"
                        )
                    assert revision.after.revision is not None
                    if revision.after.revision.at < latest_answer.answered_at:
                        raise ValueError("materialization cannot precede answer")
                    original_facts = set(self.spec.context.delivery_facts)
                    accepted_facts = tuple(
                        f
                        for f in result.spec.context.delivery_facts
                        if f not in original_facts
                        and f.statement == latest_answer.answer
                        and f.recorded_at >= latest_answer.answered_at
                        and f.source_artifact
                        in latest_answer.source_references + latest_answer.supporting_artifacts
                        and f.kind
                        == (
                            ReferenceKind.HUMAN_DECISION
                            if latest_answer.human_decision
                            else ReferenceKind.SYSTEM_FACT
                        )
                    )
                    materialized_items = tuple(
                        item
                        for item in result.spec.items
                        if item.id not in {i.id for i in self.spec.items}
                        and any(
                            statement.statement == latest_answer.answer
                            and any(f.reference in statement.references for f in accepted_facts)
                            for statement in item.statements()
                        )
                    )
                    if (
                        not accepted_facts
                        or not materialized_items
                        or not (
                            {f.id for f in accepted_facts} & set(resolution.resolution_references)
                            and {i.id for i in materialized_items}
                            & set(resolution.resolution_references)
                        )
                    ):
                        raise ValueError(
                            "resolution must materialize this exact reviewed answer with provenance"
                        )
                dimension = next(
                    r for r in result.result.dimensions if r.dimension == self.source_gap.dimension
                )
                if not dimension_acceptable(dimension, result.policy) or any(
                    g.dimension == self.source_gap.dimension
                    and g.status == GapStatus.OPEN
                    and g.classification != GapClassification.NON_BLOCKING
                    for g in result.gaps
                ):
                    raise ValueError(
                        "answer remains unresolved in resulting authoritative specification"
                    )
                if latest_answer.limitations:
                    raise ValueError(
                        "answer limitations require a new adequate answer before resolution"
                    )
                status, kind = ClarificationStatus.RESOLVED, EventType.CLARIFICATION_RESOLVED
                related = (latest_answer.id, result.id)
            else:
                status, kind = ClarificationStatus.WITHDRAWN, EventType.CLARIFICATION_WITHDRAWN
            if action.event != spec_event(
                kind,
                ObjectKind.CLARIFICATION,
                self.id,
                action.actor,
                action.at,
                action.event.id,
                related,
                action.rationale,
                self.spec.version,
            ):
                raise ValueError("clarification action audit must reconstruct")
        return self

    @property
    def spec(self) -> DeliverySpecBody:
        return self.assessment.spec

    @property
    def status(self) -> ClarificationStatus:
        if not self.actions:
            return ClarificationStatus.OPEN
        for action in reversed(self.actions):
            if action.kind != ClarificationActionType.ASSIGN_OWNER:
                return {
                    ClarificationActionType.ANSWER: ClarificationStatus.ANSWERED,
                    ClarificationActionType.RESOLVE: ClarificationStatus.RESOLVED,
                    ClarificationActionType.WITHDRAW: ClarificationStatus.WITHDRAWN,
                }[action.kind]
        return ClarificationStatus.OPEN

    @property
    def owner(self) -> Owner | None:
        return next(
            (a.owner for a in reversed(self.actions) if a.owner is not None), self.initial_owner
        )

    def applies_to(self, current: DeliverySpecBody) -> bool:
        if self.status == ClarificationStatus.RESOLVED:
            resolution = next(a.resolution for a in reversed(self.actions) if a.resolution)
            return resolution.resulting_assessment.spec == spec_body(current)
        if self.status == ClarificationStatus.WITHDRAWN:
            return self.actions[-1].current_spec == spec_body(current)
        return self.spec == spec_body(current)
