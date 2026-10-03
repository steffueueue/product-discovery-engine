"""Versioned validation activities, explicit lifecycle, and append-only results."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .assumptions import Assumption, ValidationState
from .audit import Actor, AuditEvent, AuditMetadata, AuditTarget, EventType, ObjectKind
from .common import DomainModel, Ordinal, Owner, ReferenceIds, Text
from .evidence import Evidence, EvidenceDirection, EvidenceTarget
from .evidence_assessment import require_evidence_time
from .validation_methods import ValidationMethod


class ValidationStatus(StrEnum):
    PLANNED = "planned"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RelativeSpeed(StrEnum):
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"


class RelativeCost(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ValidationConclusion(StrEnum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    INCONCLUSIVE = "inconclusive"
    CONTRADICTED = "contradicted"


class ValidationEffect(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    MIXED = "mixed"
    NEUTRAL = "neutral"


_TRANSITIONS = {
    ValidationStatus.PLANNED: frozenset({ValidationStatus.READY, ValidationStatus.CANCELLED}),
    ValidationStatus.READY: frozenset({ValidationStatus.RUNNING, ValidationStatus.CANCELLED}),
    ValidationStatus.RUNNING: frozenset({ValidationStatus.COMPLETED, ValidationStatus.CANCELLED}),
    ValidationStatus.COMPLETED: frozenset(),
    ValidationStatus.CANCELLED: frozenset(),
}
_STATUS_EVENTS = {
    ValidationStatus.READY: EventType.VALIDATION_READY,
    ValidationStatus.RUNNING: EventType.VALIDATION_STARTED,
    ValidationStatus.COMPLETED: EventType.VALIDATION_COMPLETED,
    ValidationStatus.CANCELLED: EventType.VALIDATION_CANCELLED,
}


class ValidationActivity(DomainModel):
    id: UUID
    hypothesis_id: UUID
    target_assumption_id: UUID
    method: ValidationMethod
    rationale: Text
    required_inputs: tuple[Text, ...]
    success_signal: Text
    failure_signal: Text
    expected_information_gain: Ordinal | None
    relative_cost: RelativeCost
    relative_speed: RelativeSpeed
    owner: Owner
    dependencies: ReferenceIds = ()
    status: ValidationStatus = ValidationStatus.PLANNED
    version: Annotated[int, Field(ge=1, strict=True)] = 1
    criteria_version: Annotated[int, Field(ge=1, strict=True)] = 1
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_activity(self) -> "ValidationActivity":
        if self.updated_at < self.created_at or self.criteria_version > self.version:
            raise ValueError("invalid activity timestamps/versions")
        if self.id in self.dependencies:
            raise ValueError("activity cannot depend on itself")
        if not self.required_inputs or self.success_signal == self.failure_signal:
            raise ValueError(
                "required inputs and distinct predefined success/failure signals required"
            )
        return self


class ValidationChange(DomainModel):
    before: ValidationActivity | None
    after: ValidationActivity
    event: AuditEvent

    @model_validator(mode="after")
    def validate_history(self) -> "ValidationChange":
        event = self.event
        if (
            event.target != AuditTarget(kind=ObjectKind.VALIDATION_ACTIVITY, id=self.after.id)
            or event.occurred_at != self.after.updated_at
            or event.metadata.resulting_version != self.after.version
            or event.metadata.resulting_status != self.after.status.value
        ):
            raise ValueError("validation audit must match resulting snapshot")
        if self.before is None:
            if (
                event.event_type != EventType.VALIDATION_CREATED
                or self.after.version != 1
                or self.after.criteria_version != 1
                or self.after.status != ValidationStatus.PLANNED
                or self.after.created_at != self.after.updated_at
                or event.metadata.previous_version is not None
                or event.metadata.previous_status is not None
                or event.metadata.changed_fields
            ):
                raise ValueError("activity creation must begin planned at version 1")
            return self
        before, after = self.before, self.after
        if (
            before.id != after.id
            or after.version != before.version + 1
            or after.updated_at < before.updated_at
            or event.metadata.previous_version != before.version
            or event.metadata.previous_status != before.status.value
        ):
            raise ValueError("validation history must be consecutive and chronological")
        changed = tuple(
            name
            for name in ValidationActivity.model_fields
            if name not in {"version", "updated_at"}
            and getattr(before, name) != getattr(after, name)
        )
        if (
            set(changed) != set(event.metadata.changed_fields)
            or len(changed) != len(event.metadata.changed_fields)
            or not changed
        ):
            raise ValueError("validation material fields must match audit")
        if event.event_type == EventType.VALIDATION_CRITERIA_CHANGED:
            if (
                not set(changed) <= {"success_signal", "failure_signal", "criteria_version"}
                or not set(changed) & {"success_signal", "failure_signal"}
                or after.criteria_version != before.criteria_version + 1
                or event.metadata.reason is None
            ):
                raise ValueError("criteria revisions preserve old values and require a reason")
            if before.status == ValidationStatus.COMPLETED and not str(
                event.metadata.reason
            ).startswith("Post-hoc criteria revision:"):
                raise ValueError("post-hoc criteria revisions must be explicitly marked")
        else:
            if (
                changed != ("status",)
                or after.status not in _TRANSITIONS[before.status]
                or event.event_type != _STATUS_EVENTS[after.status]
            ):
                raise ValueError("invalid validation transition")
        return self


def create_validation_activity(
    activity: ValidationActivity, *, actor: Actor, event_id: UUID
) -> ValidationChange:
    return ValidationChange(
        before=None,
        after=activity,
        event=AuditEvent(
            id=event_id,
            actor=actor,
            occurred_at=activity.created_at,
            event_type=EventType.VALIDATION_CREATED,
            target=AuditTarget(kind=ObjectKind.VALIDATION_ACTIVITY, id=activity.id),
            metadata=AuditMetadata(resulting_version=1, resulting_status=activity.status.value),
        ),
    )


def _change_activity(
    activity: ValidationActivity,
    after: ValidationActivity,
    *,
    actor: Actor,
    event_id: UUID,
    event_type: EventType,
    reason: str | None = None,
) -> ValidationChange:
    changed = tuple(
        name
        for name in ValidationActivity.model_fields
        if name not in {"version", "updated_at"} and getattr(activity, name) != getattr(after, name)
    )
    return ValidationChange(
        before=activity,
        after=after,
        event=AuditEvent(
            id=event_id,
            actor=actor,
            occurred_at=after.updated_at,
            event_type=event_type,
            target=AuditTarget(kind=ObjectKind.VALIDATION_ACTIVITY, id=activity.id),
            metadata=AuditMetadata(
                previous_version=activity.version,
                resulting_version=after.version,
                previous_status=activity.status.value,
                resulting_status=after.status.value,
                changed_fields=changed,
                reason=reason,
            ),
        ),
    )


def transition_validation_activity(
    activity: ValidationActivity,
    target: ValidationStatus,
    *,
    actor: Actor,
    at: datetime,
    event_id: UUID,
    completed_dependency_ids: tuple[UUID, ...] = (),
) -> ValidationChange:
    if not isinstance(target, ValidationStatus) or target not in _TRANSITIONS[activity.status]:
        raise ValueError("invalid validation transition")
    if target in {ValidationStatus.READY, ValidationStatus.RUNNING}:
        if not set(activity.dependencies) <= set(completed_dependency_ids):
            raise ValueError("validation dependencies must be completed")
    after = ValidationActivity.model_validate(
        {
            **activity.model_dump(),
            "status": target,
            "updated_at": at,
            "version": activity.version + 1,
        }
    )
    return _change_activity(
        activity, after, actor=actor, event_id=event_id, event_type=_STATUS_EVENTS[target]
    )


def revise_validation_criteria(
    activity: ValidationActivity,
    *,
    success_signal: str,
    failure_signal: str,
    reason: str,
    actor: Actor,
    at: datetime,
    event_id: UUID,
) -> ValidationChange:
    if (success_signal, failure_signal) == (activity.success_signal, activity.failure_signal):
        raise ValueError("criteria revision must materially change a signal")
    after = ValidationActivity.model_validate(
        {
            **activity.model_dump(),
            "success_signal": success_signal,
            "failure_signal": failure_signal,
            "criteria_version": activity.criteria_version + 1,
            "version": activity.version + 1,
            "updated_at": at,
        }
    )
    prefix = (
        "Post-hoc criteria revision: "
        if activity.status == ValidationStatus.COMPLETED
        else "Criteria revision: "
    )
    if not reason.strip():
        raise ValueError("criteria changes require an actor and nonempty reason")
    return _change_activity(
        activity,
        after,
        actor=actor,
        event_id=event_id,
        event_type=EventType.VALIDATION_CRITERIA_CHANGED,
        reason=prefix + reason,
    )


class ValidationResult(DomainModel):
    id: UUID
    activity_id: UUID
    tested_assumption_id: UUID
    criteria_version: Annotated[int, Field(ge=1, strict=True)]
    conclusion: ValidationConclusion
    generated_evidence_ids: ReferenceIds
    interpretation: Text
    limitations: tuple[Text, ...]
    effect: ValidationEffect
    owner: Owner
    completed_at: AwareDatetime

    @model_validator(mode="after")
    def validate_effect(self) -> "ValidationResult":
        allowed = {
            ValidationConclusion.SUPPORTED: {ValidationEffect.SUPPORTS},
            ValidationConclusion.PARTIALLY_SUPPORTED: {
                ValidationEffect.SUPPORTS,
                ValidationEffect.MIXED,
            },
            ValidationConclusion.INCONCLUSIVE: {ValidationEffect.NEUTRAL, ValidationEffect.MIXED},
            ValidationConclusion.CONTRADICTED: {ValidationEffect.CONTRADICTS},
        }
        if self.effect not in allowed[self.conclusion]:
            raise ValueError("conclusion and evidence effect disagree")
        if self.conclusion != ValidationConclusion.INCONCLUSIVE and not self.generated_evidence_ids:
            raise ValueError("directional conclusions require new evidence")
        return self


class ValidationRecording(DomainModel):
    activity_change: ValidationChange
    result: ValidationResult
    assumption_before: Assumption
    assumption_after: Assumption
    prior_evidence: tuple[Evidence, ...]
    generated_evidence: tuple[Evidence, ...]
    event: AuditEvent

    @property
    def evidence_history(self) -> tuple[Evidence, ...]:
        return self.prior_evidence + self.generated_evidence

    @model_validator(mode="after")
    def validate_recording(self) -> "ValidationRecording":
        before = self.activity_change.before
        after = self.activity_change.after
        result = self.result
        if (
            before is None
            or before.status != ValidationStatus.RUNNING
            or after.status != ValidationStatus.COMPLETED
            or result.activity_id != after.id
            or result.tested_assumption_id != after.target_assumption_id
            or result.criteria_version != after.criteria_version
            or result.completed_at != after.updated_at
            or self.assumption_before.id != result.tested_assumption_id
        ):
            raise ValueError(
                "result requires a completed activity, tested assumption and criteria snapshot"
            )
        if tuple(e.id for e in self.generated_evidence) != result.generated_evidence_ids:
            raise ValueError("result must identify exactly its generated evidence")
        if set(result.generated_evidence_ids) & set(self.assumption_before.evidence_ids):
            raise ValueError("generated evidence cannot reuse historical assumption evidence IDs")
        if len({e.id for e in self.evidence_history}) != len(self.evidence_history):
            raise ValueError("new evidence must never overwrite historical evidence")
        for evidence in self.generated_evidence:
            require_evidence_time(evidence, result.completed_at)
            if evidence.invalidated_on is not None:
                raise ValueError(
                    "invalidated evidence cannot establish a new validation conclusion"
                )
            if (
                evidence.hypothesis_id != after.hypothesis_id
                or evidence.target != EvidenceTarget.ASSUMPTION
                or evidence.target_assumption_id != result.tested_assumption_id
            ):
                raise ValueError("generated evidence must target the tested assumption")
            if (
                result.effect == ValidationEffect.SUPPORTS
                and evidence.direction != EvidenceDirection.SUPPORTS
            ):
                raise ValueError("support effect requires supporting evidence")
            if (
                result.effect == ValidationEffect.CONTRADICTS
                and evidence.direction != EvidenceDirection.CONTRADICTS
            ):
                raise ValueError("contradict effect requires contradicting evidence")
        if result.effect == ValidationEffect.MIXED and {
            e.direction for e in self.generated_evidence
        } != set(EvidenceDirection):
            raise ValueError("mixed effects retain both supporting and contradicting evidence")
        if self.assumption_after != _updated_assumption(self.assumption_before, result):
            raise ValueError(
                "assumption update must preserve content and all historical evidence links"
            )
        if (
            self.event.event_type != EventType.VALIDATION_RESULT_RECORDED
            or self.event.target != AuditTarget(kind=ObjectKind.VALIDATION_RESULT, id=result.id)
            or self.event.occurred_at != result.completed_at
            or self.event.metadata.related_ids
            != (after.id, result.tested_assumption_id, *result.generated_evidence_ids)
        ):
            raise ValueError("validation result audit must agree with retained knowledge")
        return self


def _updated_assumption(assumption: Assumption, result: ValidationResult) -> Assumption:
    state = {
        ValidationConclusion.SUPPORTED: ValidationState.SUPPORTED,
        ValidationConclusion.PARTIALLY_SUPPORTED: ValidationState.INCONCLUSIVE,
        ValidationConclusion.INCONCLUSIVE: ValidationState.INCONCLUSIVE,
        ValidationConclusion.CONTRADICTED: ValidationState.REFUTED,
    }[result.conclusion]
    return Assumption.model_validate(
        {
            **assumption.model_dump(),
            "validation_state": state,
            "evidence_ids": tuple(
                dict.fromkeys((*assumption.evidence_ids, *result.generated_evidence_ids))
            ),
        }
    )


def record_validation_result(
    activity: ValidationActivity,
    result: ValidationResult,
    assumption: Assumption,
    *,
    prior_evidence: tuple[Evidence, ...],
    generated_evidence: tuple[Evidence, ...],
    actor: Actor,
    completion_event_id: UUID,
    result_event_id: UUID,
) -> ValidationRecording:
    change = transition_validation_activity(
        activity,
        ValidationStatus.COMPLETED,
        actor=actor,
        at=result.completed_at,
        event_id=completion_event_id,
    )
    return ValidationRecording(
        activity_change=change,
        result=result,
        assumption_before=assumption,
        assumption_after=_updated_assumption(assumption, result),
        prior_evidence=prior_evidence,
        generated_evidence=generated_evidence,
        event=AuditEvent(
            id=result_event_id,
            actor=actor,
            occurred_at=result.completed_at,
            event_type=EventType.VALIDATION_RESULT_RECORDED,
            target=AuditTarget(kind=ObjectKind.VALIDATION_RESULT, id=result.id),
            metadata=AuditMetadata(
                related_ids=(activity.id, assumption.id, *result.generated_evidence_ids)
            ),
        ),
    )
