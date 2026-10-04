"""Immutable audit records with typed targets and metadata."""

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .common import DomainModel, Owner, ReferenceIds, Text


class ActorKind(StrEnum):
    HUMAN = "human"
    SYSTEM = "system"
    AI = "ai"


class Actor(DomainModel):
    kind: ActorKind
    id: Text
    owner: Owner | None = None

    @model_validator(mode="after")
    def validate_accountability(self) -> "Actor":
        if self.kind == ActorKind.HUMAN and self.owner is None:
            raise ValueError("human actors require accountable ownership")
        return self


class ObjectKind(StrEnum):
    SUBMISSION = "submission"
    HYPOTHESIS = "hypothesis"
    CLAIM = "claim"
    EVIDENCE = "evidence"
    ASSUMPTION = "assumption"
    DECISION = "decision"
    EVIDENCE_ORIGIN = "evidence_origin"
    VALIDATION_ACTIVITY = "validation_activity"
    VALIDATION_RESULT = "validation_result"
    CHALLENGE_ANALYSIS = "challenge_analysis"
    DELIVERY_SELECTION = "delivery_selection"
    DELIVERY_SPEC = "delivery_spec"
    SPEC_PROPOSAL = "spec_proposal"
    DELIVERY_CONTEXT = "delivery_context"
    SPEC_GAP = "spec_gap"
    CLARIFICATION = "clarification"
    SPEC_REVIEW = "spec_review"
    DELIVERY_GATE = "delivery_gate"
    IMPLEMENTATION_AUTHORIZATION = "implementation_authorization"
    IMPLEMENTATION = "implementation"
    RELEASE_OBSERVATION = "release_observation"
    OUTCOME_PLAN = "outcome_plan"
    OUTCOME_BASELINE = "outcome_baseline"
    OUTCOME_OBSERVATION = "outcome_observation"
    OUTCOME_EVALUATION = "outcome_evaluation"
    CAUSAL_INTERPRETATION = "causal_interpretation"
    OUTCOME_REVIEW = "outcome_review"
    FOLLOW_UP_LEARNING = "follow_up_learning"


class AuditTarget(DomainModel):
    kind: ObjectKind
    id: UUID


class EventType(StrEnum):
    OBJECT_CREATED = "object_created"
    MATERIAL_FIELD_CHANGED = "material_field_changed"
    STATUS_CHANGED = "status_changed"
    EVIDENCE_ADDED = "evidence_added"
    EVIDENCE_INVALIDATED = "evidence_invalidated"
    HUMAN_OVERRIDE = "human_override"
    AI_ASSUMPTION_GENERATED = "ai_assumption_generated"
    DECISION_RECORDED = "decision_recorded"
    EVIDENCE_QUALITY_ASSESSED = "evidence_quality_assessed"
    EVIDENCE_FRESHNESS_CHANGED = "evidence_freshness_changed"
    EVIDENCE_ORIGIN_LINKED = "evidence_origin_linked"
    VALIDATION_CREATED = "validation_created"
    VALIDATION_READY = "validation_ready"
    VALIDATION_STARTED = "validation_started"
    VALIDATION_COMPLETED = "validation_completed"
    VALIDATION_CANCELLED = "validation_cancelled"
    VALIDATION_RESULT_RECORDED = "validation_result_recorded"
    VALIDATION_CRITERIA_CHANGED = "validation_criteria_changed"
    ASSUMPTION_RISK_REASSESSED = "assumption_risk_reassessed"
    CHALLENGE_COMPLETED = "challenge_completed"
    DISCOVERY_PRIORITY_ASSESSED = "discovery_priority_assessed"
    DELIVERY_READINESS_ASSESSED = "delivery_readiness_assessed"
    DISCOVERY_GATE_EVALUATED = "discovery_gate_evaluated"
    DISCOVERY_GATE_PASSED = "discovery_gate_passed"
    DISCOVERY_GATE_BLOCKED = "discovery_gate_blocked"
    DISCOVERY_GATE_REVIEW_REQUIRED = "discovery_gate_review_required"
    DISCOVERY_GATE_OVERRIDDEN = "discovery_gate_overridden"
    HYPOTHESIS_PROMOTED = "hypothesis_promoted_to_candidate"
    DELIVERY_SELECTED = "delivery_selected"
    DELIVERY_SELECTION_RECORDED = "delivery_selection_recorded"
    DELIVERY_CONTEXT_RECORDED = "delivery_context_recorded"
    SPEC_DRAFT_GENERATED = "spec_draft_generated"
    SPEC_PROPOSAL_REVIEWED = "spec_proposal_reviewed"
    SPEC_ITEM_ACCEPTED = "spec_item_accepted"
    SPEC_ITEM_REJECTED = "spec_item_rejected"
    SPEC_CREATED = "spec_created"
    SPEC_REVISED = "spec_revised"
    SPEC_SUPERSEDED = "spec_superseded"
    HUMAN_SPEC_ITEM_ADDED = "human_spec_item_added"
    SPEC_COMPLETENESS_ASSESSED = "spec_completeness_assessed"
    SPEC_GAP_DETECTED = "spec_gap_detected"
    SPEC_GAP_REVIEWED = "spec_gap_reviewed"
    CLARIFICATION_CREATED = "clarification_created"
    CLARIFICATION_OWNER_ASSIGNED = "clarification_owner_assigned"
    CLARIFICATION_ANSWERED = "clarification_answered"
    CLARIFICATION_RESOLVED = "clarification_resolved"
    CLARIFICATION_WITHDRAWN = "clarification_withdrawn"
    SPEC_NEEDS_CLARIFICATION = "spec_needs_clarification"
    SPEC_READY_FOR_REVIEW = "spec_ready_for_review"
    SPEC_REVIEW_RECORDED = "spec_review_recorded"
    SPEC_READY_FOR_DELIVERY = "spec_ready_for_delivery"
    DELIVERY_GATE_EVALUATED = "delivery_gate_evaluated"
    DELIVERY_GATE_PASSED = "delivery_gate_passed"
    DELIVERY_GATE_BLOCKED = "delivery_gate_blocked"
    DELIVERY_GATE_REVIEW_REQUIRED = "delivery_gate_review_required"
    IMPLEMENTATION_HANDOFF_AUTHORIZED = "implementation_handoff_authorized"
    IMPLEMENTATION_PLANNED = "implementation_planned"
    IMPLEMENTATION_STARTED = "implementation_started"
    IMPLEMENTATION_COMPLETED = "implementation_completed"
    IMPLEMENTATION_CANCELLED = "implementation_cancelled"
    IMPLEMENTATION_DEVIATION_RECORDED = "implementation_deviation_recorded"
    HYPOTHESIS_IMPLEMENTED = "hypothesis_implemented"
    RELEASE_OBSERVED = "release_observed"
    OUTCOME_PLAN_CREATED = "outcome_plan_created"
    OUTCOME_PLAN_REVISED = "outcome_plan_revised"
    OUTCOME_BASELINE_RECORDED = "outcome_baseline_recorded"
    OUTCOME_TARGET_RECORDED = "outcome_target_recorded"
    OUTCOME_TARGET_REVISED = "outcome_target_revised"
    OUTCOME_OBSERVED = "outcome_observed"
    HYPOTHESIS_MEASURING_OUTCOME = "hypothesis_measuring_outcome"
    OUTCOME_EVALUATED = "outcome_evaluated"
    CAUSAL_INTERPRETATION_RECORDED = "causal_interpretation_recorded"
    OUTCOME_EVIDENCE_ADDED = "outcome_evidence_added"
    OUTCOME_REVIEW_COMPLETED = "outcome_review_completed"
    FOLLOW_UP_LEARNING_LINKED = "follow_up_learning_linked"
    HYPOTHESIS_CLOSED = "hypothesis_closed"


class AuditMetadata(DomainModel):
    previous_version: Annotated[int, Field(ge=1, strict=True)] | None = None
    resulting_version: Annotated[int, Field(ge=1, strict=True)] | None = None
    previous_status: Text | None = None
    resulting_status: Text | None = None
    changed_fields: tuple[Text, ...] = ()
    related_ids: ReferenceIds = ()
    reason: Text | None = None

    @model_validator(mode="after")
    def validate_versions(self) -> "AuditMetadata":
        if self.previous_version is not None:
            if self.resulting_version != self.previous_version + 1:
                raise ValueError("audit version changes must increment exactly once")
        return self


class AuditEvent(DomainModel):
    id: UUID
    actor: Actor
    occurred_at: AwareDatetime
    event_type: EventType
    target: AuditTarget
    metadata: AuditMetadata

    @model_validator(mode="after")
    def validate_override(self) -> "AuditEvent":
        if self.event_type in {EventType.HUMAN_OVERRIDE, EventType.DISCOVERY_GATE_OVERRIDDEN}:
            if self.actor.kind != ActorKind.HUMAN or self.metadata.reason is None:
                raise ValueError("human override requires a human actor and a reason")
        return self
