"""Retained candidacy transition with ordinary and human-override paths distinguished."""

from datetime import datetime
from uuid import UUID

from pydantic import model_validator

from .audit import Actor, ActorKind, AuditEvent, AuditMetadata, AuditTarget, EventType, ObjectKind
from .common import DomainModel
from .decisioning_policy import DecisioningPolicies
from .discovery_gate import DiscoveryGateEvaluation, DiscoveryGateOverride, GateState
from .hypotheses import Hypothesis
from .lifecycle import HypothesisStatus


def require_promotion_authority(
    hypothesis: Hypothesis,
    gate: DiscoveryGateEvaluation,
    policies: DecisioningPolicies,
    actor: Actor,
    at: datetime,
    override: DiscoveryGateOverride | None,
) -> None:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("promotion timestamp requires a timezone")
    if actor.kind != ActorKind.HUMAN:
        raise ValueError("candidacy promotion requires accountable human action")
    if hypothesis != gate.hypothesis:
        raise ValueError("gate belongs to a different or obsolete material hypothesis snapshot")
    if gate.policies != policies:
        raise ValueError("gate policies are outdated or mismatched")
    if not gate.evaluated_at <= at < gate.expires_at:
        raise ValueError("gate is expired or promotion precedes evaluation")
    if hypothesis.status != HypothesisStatus.EVIDENCE_UPDATED:
        raise ValueError("promotion must start at evidence_updated")
    if override is None:
        if gate.result.state != GateState.PASSED:
            raise ValueError("ordinary promotion requires an ordinary Discovery Gate PASS")
    elif override.original_gate != gate or override.actor != actor or override.overridden_at > at:
        raise ValueError("override must explicitly authorize this gate and human actor")


class CandidatePromotion(DomainModel):
    before: Hypothesis
    after: Hypothesis
    gate: DiscoveryGateEvaluation
    active_policies: DecisioningPolicies
    override: DiscoveryGateOverride | None
    lifecycle_event: AuditEvent
    decision_event: AuditEvent

    @model_validator(mode="after")
    def reconstruct(self) -> "CandidatePromotion":
        at = self.after.updated_at
        actor = self.lifecycle_event.actor
        require_promotion_authority(
            self.before, self.gate, self.active_policies, actor, at, self.override
        )
        expected = Hypothesis.model_validate(
            {
                **self.before.model_dump(),
                "status": HypothesisStatus.CANDIDATE_FOR_DELIVERY_PRIORITIZATION,
                "version": self.before.version + 1,
                "updated_at": at,
            }
        )
        related = (self.gate.id,) + ((self.override.id,) if self.override else ())
        reason = (
            "Explicit human override authorizes candidacy"
            if self.override
            else "Ordinary Discovery Gate PASS"
        )
        if self.after != expected:
            raise ValueError("promotion must only change candidacy status and consecutive version")
        if (
            self.lifecycle_event.target
            != AuditTarget(kind=ObjectKind.HYPOTHESIS, id=self.before.id)
            or self.lifecycle_event.event_type != EventType.HYPOTHESIS_PROMOTED
            or self.lifecycle_event.occurred_at != at
            or self.lifecycle_event.metadata
            != AuditMetadata(
                previous_version=self.before.version,
                resulting_version=self.after.version,
                previous_status=self.before.status.value,
                resulting_status=self.after.status.value,
                changed_fields=("status",),
                related_ids=related,
                reason=reason,
            )
        ):
            raise ValueError(
                "lifecycle audit must preserve candidacy authorization and snapshot versions"
            )
        if (
            self.decision_event.target != AuditTarget(kind=ObjectKind.DECISION, id=self.gate.id)
            or self.decision_event.event_type != EventType.DECISION_RECORDED
            or self.decision_event.occurred_at != at
            or self.decision_event.actor != actor
            or self.decision_event.metadata
            != AuditMetadata(
                related_ids=(self.before.id,) + ((self.override.id,) if self.override else ()),
                reason=reason,
            )
            or self.lifecycle_event.id == self.decision_event.id
        ):
            raise ValueError("promotion decision audit must identify gate, hypothesis and override")
        return self


def promote_candidate(
    hypothesis: Hypothesis,
    gate: DiscoveryGateEvaluation,
    *,
    policies: DecisioningPolicies,
    actor: Actor,
    at: datetime,
    lifecycle_event_id: UUID,
    decision_event_id: UUID,
    override: DiscoveryGateOverride | None = None,
) -> CandidatePromotion:
    hypothesis = Hypothesis.model_validate(hypothesis)
    gate = DiscoveryGateEvaluation.model_validate(gate)
    policies = DecisioningPolicies.model_validate(policies)
    override = DiscoveryGateOverride.model_validate(override) if override else None
    require_promotion_authority(hypothesis, gate, policies, actor, at, override)
    after = Hypothesis.model_validate(
        {
            **hypothesis.model_dump(),
            "status": HypothesisStatus.CANDIDATE_FOR_DELIVERY_PRIORITIZATION,
            "version": hypothesis.version + 1,
            "updated_at": at,
        }
    )
    related = (gate.id,) + ((override.id,) if override else ())
    reason = (
        "Explicit human override authorizes candidacy"
        if override
        else "Ordinary Discovery Gate PASS"
    )
    return CandidatePromotion(
        before=hypothesis,
        after=after,
        gate=gate,
        active_policies=policies,
        override=override,
        lifecycle_event=AuditEvent(
            id=lifecycle_event_id,
            actor=actor,
            occurred_at=at,
            event_type=EventType.HYPOTHESIS_PROMOTED,
            target=AuditTarget(kind=ObjectKind.HYPOTHESIS, id=hypothesis.id),
            metadata=AuditMetadata(
                previous_version=hypothesis.version,
                resulting_version=after.version,
                previous_status=hypothesis.status.value,
                resulting_status=after.status.value,
                changed_fields=("status",),
                related_ids=related,
                reason=reason,
            ),
        ),
        decision_event=AuditEvent(
            id=decision_event_id,
            actor=actor,
            occurred_at=at,
            event_type=EventType.DECISION_RECORDED,
            target=AuditTarget(kind=ObjectKind.DECISION, id=gate.id),
            metadata=AuditMetadata(
                related_ids=(hypothesis.id,) + ((override.id,) if override else ()), reason=reason
            ),
        ),
    )
