"""Completion requires bound external reality and cannot be inferred from handoff."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from examples.outcome_feedback import OutcomeScenario
from product_discovery_engine.domain.audit import Actor, ActorKind, EventType
from product_discovery_engine.domain.common import Provenance, SourceReference, SourceType
from product_discovery_engine.domain.hypotheses import Hypothesis
from product_discovery_engine.domain.hypothesis_changes import (
    HypothesisChange,
    transition_hypothesis,
)
from product_discovery_engine.domain.implementation import (
    DeviationKind,
    ImplementationDeviation,
    ImplementationRecord,
    ImplementationStatus,
)
from product_discovery_engine.domain.lifecycle import HypothesisStatus, InvalidTransition
from product_discovery_engine.domain.outcome_lifecycle import OutcomeLifecycleChange
from tests.m7_helpers import ACTOR, AT


def test_explicit_plan_start_and_completion(outcome_scenario: OutcomeScenario) -> None:
    s = outcome_scenario
    auth = s.started.authorization
    planned = s.service.plan_implementation(
        auth,
        auth.current,
        spec_policy=auth.policy,
        owner=s.started.owner,
        actor=ACTOR,
        at=AT,
        summary="Explicit planned work",
    )
    assert planned.status == ImplementationStatus.PLANNED and planned.started_at is None
    started = s.service.start_implementation(
        auth,
        auth.current,
        spec_policy=auth.policy,
        owner=planned.owner,
        actor=ACTOR,
        at=AT,
        summary="Explicit start",
        planned=planned,
    )
    assert started.previous == planned and started.version == 2
    assert started.events[0].event_type == EventType.IMPLEMENTATION_STARTED
    assert auth.current.hypothesis.status == HypothesisStatus.SELECTED_FOR_DELIVERY
    assert s.completed.previous == s.started
    assert s.completed.completed_at is not None
    assert s.completed.release_references == ()
    assert s.implemented.after.status == HypothesisStatus.IMPLEMENTED
    assert s.implemented.before == auth.current.hypothesis


@pytest.mark.parametrize("field", ["hypothesis", "selection", "spec", "current_spec"])
def test_start_rejects_cross_binding(outcome_scenario: OutcomeScenario, field: str) -> None:
    s = outcome_scenario
    auth = s.started.authorization
    item = getattr(auth.current, field)
    wrong = item.model_copy(update={"id": uuid4()})
    current = auth.current.model_copy(update={field: wrong})
    with pytest.raises(ValueError):
        s.service.start_implementation(
            auth,
            current,
            spec_policy=auth.policy,
            owner=s.started.owner,
            actor=ACTOR,
            at=AT,
            summary="Must fail",
        )


@pytest.mark.parametrize("field", ["version", "status"])
def test_start_rejects_wrong_spec_version_or_workflow(
    outcome_scenario: OutcomeScenario, field: str
) -> None:
    s = outcome_scenario
    auth = s.started.authorization
    spec = auth.current.spec.model_copy(update={field: 999 if field == "version" else "draft"})
    with pytest.raises(ValueError):
        s.service.start_implementation(
            auth,
            auth.current.model_copy(update={"spec": spec}),
            spec_policy=auth.policy,
            owner=s.started.owner,
            actor=ACTOR,
            at=AT,
            summary="Must fail",
        )


def test_start_rejects_stale_authorization_and_policy(outcome_scenario: OutcomeScenario) -> None:
    s = outcome_scenario
    auth = s.started.authorization
    with pytest.raises(ValueError, match="stale"):
        s.service.start_implementation(
            auth,
            auth.current,
            spec_policy=auth.policy,
            owner=s.started.owner,
            actor=ACTOR,
            at=auth.gate.expires_at,
            summary="Too late",
        )
    wrong_policy = auth.policy.model_copy(update={"version": "obsolete-policy"})
    with pytest.raises(ValueError, match="policy"):
        s.service.start_implementation(
            auth,
            auth.current,
            spec_policy=wrong_policy,
            owner=s.started.owner,
            actor=ACTOR,
            at=AT,
            summary="Wrong policy",
        )


@pytest.mark.parametrize(
    "field,value", [("authorization", None), ("owner", None), ("started_at", None)]
)
def test_implementation_requires_authorization_owner_and_time(
    outcome_scenario: OutcomeScenario,
    field: str,
    value: None,
) -> None:
    data = outcome_scenario.started.model_dump()
    data[field] = value
    with pytest.raises(ValueError):
        ImplementationRecord.model_validate(data)


@pytest.mark.parametrize("kind", [ActorKind.AI, ActorKind.SYSTEM])
def test_completion_requires_human_accountability(
    outcome_scenario: OutcomeScenario, kind: ActorKind
) -> None:
    s = outcome_scenario
    with pytest.raises(ValueError, match="human"):
        s.service.complete_implementation(
            s.started,
            actor=Actor(kind=kind, id="unaccountable"),
            at=s.completed.recorded_at,
            summary="Invalid completion",
            delivered_scope=("Delivered",),
            delivered_item_ids=s.completed.delivered_item_ids,
        )


def test_cancelled_is_terminal_and_not_implemented(outcome_scenario: OutcomeScenario) -> None:
    s = outcome_scenario
    cancelled = s.service.cancel_implementation(s.started, actor=ACTOR, at=AT, reason="Stopped")
    assert cancelled.status == ImplementationStatus.CANCELLED
    assert cancelled.events[0].event_type == EventType.IMPLEMENTATION_CANCELLED
    auth = s.started.authorization
    planned = s.service.plan_implementation(
        auth,
        auth.current,
        spec_policy=auth.policy,
        owner=s.started.owner,
        actor=ACTOR,
        at=AT,
        summary="Explicit planned work",
    )
    cancelled_plan = s.service.cancel_implementation(
        planned, actor=ACTOR, at=AT, reason="Stopped before start"
    )
    assert cancelled_plan.started_at is None
    with pytest.raises(ValueError, match="unrecorded"):
        ImplementationRecord.model_validate(cancelled_plan.model_copy(update={"started_at": AT}))
    with pytest.raises(ValueError):
        s.service.complete_implementation(
            cancelled,
            actor=ACTOR,
            at=AT,
            summary="Invalid restart",
            delivered_scope=("Delivered",),
            delivered_item_ids=s.completed.delivered_item_ids,
        )
    with pytest.raises(ValueError, match="completed"):
        s.service.mark_implemented(
            cancelled.authorization.current.hypothesis,
            cancelled,
            actor=ACTOR,
            at=AT,
            rationale="Not completed",
        )


def test_completion_requires_actual_scope_and_structural_accounting(
    outcome_scenario: OutcomeScenario,
) -> None:
    s = outcome_scenario
    for scope, item_ids in (((), s.completed.delivered_item_ids), (("Delivered",), ())):
        with pytest.raises(ValueError):
            s.service.complete_implementation(
                s.started,
                actor=ACTOR,
                at=s.completed.recorded_at,
                summary="Missing completion details",
                delivered_scope=scope,
                delivered_item_ids=item_ids,
            )


def test_omission_and_changed_requirements_retained(outcome_scenario: OutcomeScenario) -> None:
    s = outcome_scenario
    spec = s.started.authorization.current.spec
    item = next(i for i in spec.items if i.kind.value == "functional_requirement")
    omission = ImplementationDeviation(
        id=uuid4(),
        kind=DeviationKind.OMITTED,
        spec_item_id=item.id,
        description="Deferred this requirement",
        rationale="Accountable partial delivery",
    )
    complete = s.service.complete_implementation(
        s.started,
        actor=ACTOR,
        at=s.completed.recorded_at,
        summary="Partial completion recorded",
        delivered_scope=("Other requirements delivered",),
        delivered_item_ids=tuple(i.id for i in spec.items if i.id != item.id),
        deviations=(omission,),
        omitted_scope=(
            item.statement if isinstance(item.statement, str) else "Unknown requirement",
        ),
    )
    assert complete.deviations == (omission,)
    assert complete.events[1].event_type == EventType.IMPLEMENTATION_DEVIATION_RECORDED
    assert spec == complete.authorization.current.spec
    assert s.completed.deviations[0].kind == DeviationKind.REDUCED
    with pytest.raises(ValueError):
        s.service.complete_implementation(
            s.started,
            actor=ACTOR,
            at=s.completed.recorded_at,
            summary="Contradictory omission",
            delivered_scope=("Delivered",),
            delivered_item_ids=s.completed.delivered_item_ids,
            deviations=(omission,),
            omitted_scope=("Deferred",),
        )


@pytest.mark.parametrize("record_name", ["started", "completed"])
def test_record_immutable_and_audit_tampering_rejected(
    outcome_scenario: OutcomeScenario, record_name: str
) -> None:
    record = getattr(outcome_scenario, record_name)
    with pytest.raises(ValidationError):
        record.summary = "Rewritten"
    data = record.model_dump()
    data["events"][0]["metadata"]["reason"] = "Rewritten audit"
    with pytest.raises(ValueError, match="audit"):
        ImplementationRecord.model_validate(data)


@pytest.mark.parametrize(
    "target",
    [HypothesisStatus.IMPLEMENTED, HypothesisStatus.MEASURING_OUTCOME, HypothesisStatus.CLOSED],
)
def test_generic_lifecycle_and_status_audit_bypass_rejected(
    outcome_scenario: OutcomeScenario, target: HypothesisStatus
) -> None:
    s = outcome_scenario
    change = {
        HypothesisStatus.IMPLEMENTED: s.implemented,
        HypothesisStatus.MEASURING_OUTCOME: s.measuring,
        HypothesisStatus.CLOSED: s.closed,
    }[target]
    with pytest.raises(InvalidTransition, match="dedicated"):
        transition_hypothesis(
            change.before, target, actor=ACTOR, at=change.after.updated_at, event_id=uuid4()
        )
    event = change.event.model_copy(update={"event_type": EventType.STATUS_CHANGED})
    with pytest.raises(ValueError, match="dedicated"):
        HypothesisChange(before=change.before, after=change.after, event=event)


def test_incomplete_and_stale_hypothesis_cannot_transition(
    outcome_scenario: OutcomeScenario,
) -> None:
    s = outcome_scenario
    with pytest.raises(ValueError, match="completed"):
        s.service.mark_implemented(
            s.implemented.before, s.started, actor=ACTOR, at=AT, rationale="Premature"
        )
    wrong = Hypothesis.model_validate(
        {**s.implemented.before.model_dump(), "version": s.implemented.before.version + 1}
    )
    with pytest.raises(ValueError, match="exact"):
        s.service.mark_implemented(
            wrong, s.completed, actor=ACTOR, at=s.completed.recorded_at, rationale="Stale"
        )
    assert OutcomeLifecycleChange.model_validate(s.implemented) == s.implemented


def test_optional_partial_release_is_external_fact(outcome_scenario: OutcomeScenario) -> None:
    s = outcome_scenario
    source = SourceReference(
        source_type=SourceType.DOCUMENT, reference="synthetic:release-attestation"
    )
    release = s.service.record_release(
        s.completed,
        environment="synthetic-stage",
        audience="Studied customers",
        released_at=s.completed.recorded_at,
        rollout_scope="50% exposure supplied by release owner",
        version_reference="search.v2",
        provenance=Provenance(sources=(source,)),
        actor=ACTOR,
        at=s.completed.recorded_at,
        limitations=("Exposure counts unverified",),
    )
    assert release.rollout_scope.startswith("50%")
    revised = s.service.revise_plan(
        s.plan,
        metrics=s.plan.metrics,
        baselines=s.plan.baselines,
        releases=(release,),
        actor=ACTOR,
        at=s.plan.recorded_at,
        reason="Record supplied partial rollout",
    )
    evaluated = s.service.evaluate(
        revised, revised.metrics[0].id, (), actor=ACTOR, at=revised.window.end
    )
    assert any("50%" in value for value in evaluated.result.limitations)
    assert "Exposure counts unverified" in evaluated.result.limitations
    assert s.plan.releases == ()
