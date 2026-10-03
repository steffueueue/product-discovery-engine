from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from product_discovery_engine.domain.assumptions import ValidationState
from product_discovery_engine.domain.audit import EventType
from product_discovery_engine.domain.common import Ordinal
from product_discovery_engine.domain.evidence import Evidence, EvidenceDirection, EvidenceTarget
from product_discovery_engine.domain.validation import (
    RelativeCost,
    RelativeSpeed,
    ValidationActivity,
    ValidationChange,
    ValidationConclusion,
    ValidationEffect,
    ValidationRecording,
    ValidationResult,
    ValidationStatus,
    create_validation_activity,
    record_validation_result,
    revise_validation_criteria,
    transition_validation_activity,
)
from product_discovery_engine.domain.validation_methods import ValidationMethod
from tests.m3_helpers import ACTOR, ASSUMPTION_ID, AT, HYPOTHESIS_ID, OWNER, assumption, evidence


def activity() -> ValidationActivity:
    return ValidationActivity(
        id=UUID(int=50),
        hypothesis_id=HYPOTHESIS_ID,
        target_assumption_id=ASSUMPTION_ID,
        method=ValidationMethod.CUSTOMER_INTERVIEW,
        rationale="Test problem before building",
        required_inputs=("Recruit ten participants",),
        success_signal="Participants repeatedly fail search",
        failure_signal="Participants consistently succeed unaided",
        expected_information_gain=Ordinal.HIGH,
        relative_cost=RelativeCost.LOW,
        relative_speed=RelativeSpeed.FAST,
        owner=OWNER,
        created_at=AT,
        updated_at=AT,
    )


def running() -> ValidationActivity:
    planned = create_validation_activity(activity(), actor=ACTOR, event_id=uuid4()).after
    ready = transition_validation_activity(
        planned, ValidationStatus.READY, actor=ACTOR, at=AT, event_id=uuid4()
    ).after
    return transition_validation_activity(
        ready, ValidationStatus.RUNNING, actor=ACTOR, at=AT, event_id=uuid4()
    ).after


def result(
    item: Evidence, conclusion: ValidationConclusion = ValidationConclusion.SUPPORTED
) -> ValidationResult:
    return ValidationResult(
        id=uuid4(),
        activity_id=activity().id,
        tested_assumption_id=ASSUMPTION_ID,
        criteria_version=1,
        conclusion=conclusion,
        generated_evidence_ids=(item.id,),
        interpretation="Observed predefined signal",
        limitations=("Sample limited; reach remains unknown",),
        effect=ValidationEffect.CONTRADICTS
        if conclusion == ValidationConclusion.CONTRADICTED
        else ValidationEffect.SUPPORTS,
        owner=OWNER,
        completed_at=AT,
    )


def test_creation_and_normal_lifecycle_emit_specific_audits() -> None:
    created = create_validation_activity(activity(), actor=ACTOR, event_id=uuid4())
    assert created.event.event_type == EventType.VALIDATION_CREATED
    before = created.after
    for status, event in [
        (ValidationStatus.READY, EventType.VALIDATION_READY),
        (ValidationStatus.RUNNING, EventType.VALIDATION_STARTED),
        (ValidationStatus.COMPLETED, EventType.VALIDATION_COMPLETED),
    ]:
        change = transition_validation_activity(
            before, status, actor=ACTOR, at=AT, event_id=uuid4()
        )
        assert change.before == before
        assert change.after.version == before.version + 1
        assert change.event.event_type == event
        before = change.after


VALID_EDGES = {
    (ValidationStatus.PLANNED, ValidationStatus.READY),
    (ValidationStatus.PLANNED, ValidationStatus.CANCELLED),
    (ValidationStatus.READY, ValidationStatus.RUNNING),
    (ValidationStatus.READY, ValidationStatus.CANCELLED),
    (ValidationStatus.RUNNING, ValidationStatus.COMPLETED),
    (ValidationStatus.RUNNING, ValidationStatus.CANCELLED),
}


@pytest.mark.parametrize("start", list(ValidationStatus))
@pytest.mark.parametrize("target", list(ValidationStatus))
def test_transition_graph(start: ValidationStatus, target: ValidationStatus) -> None:
    before = ValidationActivity.model_validate({**activity().model_dump(), "status": start})
    if (start, target) in VALID_EDGES:
        change = transition_validation_activity(
            before, target, actor=ACTOR, at=AT, event_id=uuid4()
        )
        assert change.after.status == target
        if target == ValidationStatus.CANCELLED:
            assert change.event.event_type == EventType.VALIDATION_CANCELLED
    else:
        with pytest.raises(ValueError, match="transition"):
            transition_validation_activity(before, target, actor=ACTOR, at=AT, event_id=uuid4())


def test_dependencies_time_and_no_silent_criteria_mutation() -> None:
    dependency = UUID(int=80)
    planned = ValidationActivity.model_validate(
        {**activity().model_dump(), "dependencies": (dependency,)}
    )
    with pytest.raises(ValueError, match="dependencies"):
        transition_validation_activity(
            planned, ValidationStatus.READY, actor=ACTOR, at=AT, event_id=uuid4()
        )
    ready = transition_validation_activity(
        planned,
        ValidationStatus.READY,
        actor=ACTOR,
        at=AT,
        event_id=uuid4(),
        completed_dependency_ids=(dependency,),
    )
    with pytest.raises(ValueError, match="timestamps|chronological"):
        transition_validation_activity(
            ready.after,
            ValidationStatus.RUNNING,
            actor=ACTOR,
            at=AT - timedelta(days=1),
            event_id=uuid4(),
            completed_dependency_ids=(dependency,),
        )
    with pytest.raises(ValidationError):
        ValidationChange.model_validate(
            {
                **ready.model_dump(),
                "after": {**ready.after.model_dump(), "success_signal": "Moved goalpost"},
            }
        )


def test_result_append_only_and_refuted_assumption_retained() -> None:
    previous = evidence(1, target=EvidenceTarget.ASSUMPTION)
    new = evidence(2, target=EvidenceTarget.ASSUMPTION, direction=EvidenceDirection.CONTRADICTS)
    before = assumption()
    recorded = record_validation_result(
        running(),
        result(new, ValidationConclusion.CONTRADICTED),
        before,
        prior_evidence=(previous,),
        generated_evidence=(new,),
        actor=ACTOR,
        completion_event_id=uuid4(),
        result_event_id=uuid4(),
    )
    assert recorded.evidence_history == (previous, new)
    assert recorded.assumption_before == before
    assert recorded.assumption_before.validation_state == ValidationState.UNTESTED
    assert recorded.assumption_after.validation_state == ValidationState.REFUTED
    assert recorded.assumption_after.statement == before.statement
    assert recorded.assumption_after.evidence_ids == (new.id,)
    assert recorded.event.event_type == EventType.VALIDATION_RESULT_RECORDED
    assert recorded.activity_change.event.event_type == EventType.VALIDATION_COMPLETED
    assert previous.direction == EvidenceDirection.SUPPORTS
    with pytest.raises(ValidationError, match="overwrite"):
        record_validation_result(
            running(),
            result(new),
            before,
            prior_evidence=(new,),
            generated_evidence=(new,),
            actor=ACTOR,
            completion_event_id=uuid4(),
            result_event_id=uuid4(),
        )


@pytest.mark.parametrize(
    "patch",
    [
        {"activity_id": UUID(int=999)},
        {"tested_assumption_id": UUID(int=999)},
        {"criteria_version": 2},
        {"generated_evidence_ids": (UUID(int=999),)},
    ],
)
def test_invalid_result_references_fail(patch: dict[str, object]) -> None:
    item = evidence(target=EvidenceTarget.ASSUMPTION)
    bad = ValidationResult.model_validate({**result(item).model_dump(), **patch})
    with pytest.raises(ValidationError):
        record_validation_result(
            running(),
            bad,
            assumption(),
            prior_evidence=(),
            generated_evidence=(item,),
            actor=ACTOR,
            completion_event_id=uuid4(),
            result_event_id=uuid4(),
        )


def test_result_requires_running_and_same_target_and_effect() -> None:
    item = evidence(target=EvidenceTarget.ASSUMPTION)
    with pytest.raises(ValueError, match="transition"):
        record_validation_result(
            activity(),
            result(item),
            assumption(),
            prior_evidence=(),
            generated_evidence=(item,),
            actor=ACTOR,
            completion_event_id=uuid4(),
            result_event_id=uuid4(),
        )
    wrong = evidence(target=EvidenceTarget.REACH)
    with pytest.raises(ValidationError, match="tested assumption"):
        record_validation_result(
            running(),
            result(wrong),
            assumption(),
            prior_evidence=(),
            generated_evidence=(wrong,),
            actor=ACTOR,
            completion_event_id=uuid4(),
            result_event_id=uuid4(),
        )
    with pytest.raises(ValidationError, match="disagree"):
        ValidationResult.model_validate(
            {**result(item).model_dump(), "conclusion": ValidationConclusion.CONTRADICTED}
        )
    contra = evidence(target=EvidenceTarget.ASSUMPTION, direction=EvidenceDirection.CONTRADICTS)
    with pytest.raises(ValidationError, match="support effect"):
        record_validation_result(
            running(),
            result(contra),
            assumption(),
            prior_evidence=(),
            generated_evidence=(contra,),
            actor=ACTOR,
            completion_event_id=uuid4(),
            result_event_id=uuid4(),
        )


def test_post_hoc_criteria_changes_preserve_original_result_and_old_values() -> None:
    item = evidence(target=EvidenceTarget.ASSUMPTION)
    recorded = record_validation_result(
        running(),
        result(item),
        assumption(),
        prior_evidence=(),
        generated_evidence=(item,),
        actor=ACTOR,
        completion_event_id=uuid4(),
        result_event_id=uuid4(),
    )
    after = recorded.activity_change.after
    change = revise_validation_criteria(
        after,
        success_signal="Different threshold",
        failure_signal=after.failure_signal,
        reason="Correct wording for a follow-up; original conclusion retained",
        actor=ACTOR,
        at=AT + timedelta(days=1),
        event_id=uuid4(),
    )
    assert change.before == after
    assert change.after.criteria_version == 2
    assert change.event.event_type == EventType.VALIDATION_CRITERIA_CHANGED
    assert change.event.actor == ACTOR
    assert "Post-hoc" in str(change.event.metadata.reason)
    assert recorded.result.criteria_version == 1
    assert recorded.activity_change.after.success_signal == activity().success_signal
    assert recorded.result.conclusion == ValidationConclusion.SUPPORTED
    with pytest.raises(ValueError, match="reason"):
        revise_validation_criteria(
            after,
            success_signal="Different",
            failure_signal=after.failure_signal,
            reason=" ",
            actor=ACTOR,
            at=AT,
            event_id=uuid4(),
        )
    with pytest.raises(ValueError, match="materially"):
        revise_validation_criteria(
            after,
            success_signal=after.success_signal,
            failure_signal=after.failure_signal,
            reason="No change",
            actor=ACTOR,
            at=AT,
            event_id=uuid4(),
        )


def test_inconclusive_and_partial_results_do_not_declare_full_support() -> None:
    supported = evidence(1, target=EvidenceTarget.ASSUMPTION)
    contradicted = evidence(
        2, target=EvidenceTarget.ASSUMPTION, direction=EvidenceDirection.CONTRADICTS
    )
    partial = ValidationResult.model_validate(
        {
            **result(supported).model_dump(),
            "generated_evidence_ids": (supported.id, contradicted.id),
            "conclusion": ValidationConclusion.PARTIALLY_SUPPORTED,
            "effect": ValidationEffect.MIXED,
        }
    )
    record = record_validation_result(
        running(),
        partial,
        assumption(),
        prior_evidence=(),
        generated_evidence=(supported, contradicted),
        actor=ACTOR,
        completion_event_id=uuid4(),
        result_event_id=uuid4(),
    )
    assert record.assumption_after.validation_state == ValidationState.INCONCLUSIVE
    inconclusive = ValidationResult.model_validate(
        {
            **partial.model_dump(),
            "conclusion": ValidationConclusion.INCONCLUSIVE,
            "effect": ValidationEffect.NEUTRAL,
            "generated_evidence_ids": (),
        }
    )
    record = record_validation_result(
        running(),
        inconclusive,
        assumption(),
        prior_evidence=(),
        generated_evidence=(),
        actor=ACTOR,
        completion_event_id=uuid4(),
        result_event_id=uuid4(),
    )
    assert record.assumption_after.validation_state == ValidationState.INCONCLUSIVE
    with pytest.raises(ValidationError):
        ValidationRecording.model_validate(
            {
                **record.model_dump(),
                "assumption_after": {
                    **record.assumption_after.model_dump(),
                    "statement": "Silently rewritten",
                },
            }
        )


@pytest.mark.parametrize(
    "patch",
    [
        {"required_inputs": ()},
        {"success_signal": " "},
        {"expected_information_gain": 0.87},
        {"method": "invented"},
        {"dependencies": (UUID(int=50),)},
        {"criteria_version": 2},
        {"owner": None},
    ],
)
def test_activity_invalid_states(patch: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ValidationActivity.model_validate({**activity().model_dump(), **patch})


def test_invalidated_generated_evidence_cannot_support_a_validation() -> None:
    item = evidence(target=EvidenceTarget.ASSUMPTION)
    invalid = Evidence.model_validate(
        {
            **item.model_dump(),
            "invalidated_on": AT.date(),
            "invalidation_reason": "Source measurements invalid",
        }
    )
    with pytest.raises(ValidationError, match="invalidated evidence"):
        record_validation_result(
            running(),
            result(invalid),
            assumption(),
            prior_evidence=(),
            generated_evidence=(invalid,),
            actor=ACTOR,
            completion_event_id=uuid4(),
            result_event_id=uuid4(),
        )


def test_criteria_version_only_changes_and_unmarked_post_hoc_revisions_fail() -> None:
    planned = activity()
    revised = revise_validation_criteria(
        planned,
        success_signal="Updated criterion",
        failure_signal=planned.failure_signal,
        reason="Improve preregistration",
        actor=ACTOR,
        at=AT,
        event_id=uuid4(),
    )
    data = revised.model_dump()
    data["after"]["success_signal"] = planned.success_signal
    data["event"]["metadata"]["changed_fields"] = ("criteria_version",)
    with pytest.raises(ValidationError, match="criteria revisions"):
        ValidationChange.model_validate(data)
    item = evidence(target=EvidenceTarget.ASSUMPTION)
    completed = record_validation_result(
        running(),
        result(item),
        assumption(),
        prior_evidence=(),
        generated_evidence=(item,),
        actor=ACTOR,
        completion_event_id=uuid4(),
        result_event_id=uuid4(),
    ).activity_change.after
    revised = revise_validation_criteria(
        completed,
        success_signal="Updated criterion",
        failure_signal=completed.failure_signal,
        reason="Explain correction",
        actor=ACTOR,
        at=AT,
        event_id=uuid4(),
    )
    data = revised.model_dump()
    data["event"]["metadata"]["reason"] = "Unmarked correction"
    with pytest.raises(ValidationError, match="post-hoc"):
        ValidationChange.model_validate(data)
