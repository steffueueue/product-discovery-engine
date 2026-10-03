"""Credential-free orchestration, translating existing knowledge/advisory artifacts."""

from datetime import datetime
from uuid import uuid4

from product_discovery_engine.domain.audit import Actor
from product_discovery_engine.domain.decisioning_inputs import (
    ChallengeCompletion,
    DecisionKnowledge,
    ReadinessInput,
)
from product_discovery_engine.domain.decisioning_policy import DecisioningPolicies
from product_discovery_engine.domain.delivery_readiness import (
    DeliveryReadinessAssessment,
    assess_delivery_readiness,
)
from product_discovery_engine.domain.discovery_gate import (
    DiscoveryGateEvaluation,
    DiscoveryGateOverride,
    evaluate_discovery_gate,
    override_discovery_gate,
)
from product_discovery_engine.domain.discovery_priority import (
    DiscoveryPriorityAssessment,
    LearningInput,
    assess_discovery_priority,
)
from product_discovery_engine.domain.discovery_promotion import (
    CandidatePromotion,
    promote_candidate,
)
from product_discovery_engine.domain.evidence_policy import EvidencePolicies
from product_discovery_engine.domain.hypotheses import Hypothesis

from .challenge_analysis import ChallengeRecord
from .evidence_validation import KnowledgeState


def decision_knowledge(state: KnowledgeState, policies: EvidencePolicies) -> DecisionKnowledge:
    """No classification or quality invention: retain and reconstruct Milestone 3 records."""
    return DecisionKnowledge.model_validate({**state.model_dump(), "policies": policies})


def challenge_completion(record: ChallengeRecord) -> ChallengeCompletion:
    record = ChallengeRecord.model_validate(record)
    return ChallengeCompletion(
        record_id=record.id,
        hypothesis_id=record.request.knowledge.scope.hypothesis_id,
        analyzed_at=record.analyzed_at,
        evidence_ids=tuple(e.id for e in record.request.knowledge.evidence),
        item_ids=tuple(i.id for i in record.result.items),
    )


def require_challenge_record(inputs: ReadinessInput, record: ChallengeRecord | None) -> None:
    if inputs.challenge is None:
        if record is not None:
            raise ValueError("advisory record requires explicit Challenge Mode review input")
        return
    if record is None or inputs.challenge.completion != challenge_completion(record):
        raise ValueError("Challenge Mode completion must preserve actual retained advisory record")
    packet = next((k for k in inputs.knowledge if k.scope == record.request.knowledge.scope), None)
    if (
        packet is None
        or packet.evidence != record.request.knowledge.evidence
        or packet.quality != record.request.knowledge.quality
        or record.request.hypothesis_statement != inputs.hypothesis.content.problem_statement
    ):
        raise ValueError(
            "Challenge Mode must address current statement and exact knowledge snapshot"
        )


class DiscoveryDecisioningService:
    def __init__(self, policies: DecisioningPolicies) -> None:
        self.policies = DecisioningPolicies.model_validate(policies)

    def priority(
        self, inputs: LearningInput, *, actor: Actor, at: datetime
    ) -> DiscoveryPriorityAssessment:
        return assess_discovery_priority(
            inputs,
            policy=self.policies.priority,
            actor=actor,
            at=at,
            assessment_id=uuid4(),
            event_id=uuid4(),
        )

    def readiness(
        self,
        inputs: ReadinessInput,
        *,
        actor: Actor,
        at: datetime,
        challenge_record: ChallengeRecord | None = None,
    ) -> DeliveryReadinessAssessment:
        inputs = ReadinessInput.model_validate(inputs)
        require_challenge_record(inputs, challenge_record)
        return assess_delivery_readiness(
            inputs,
            policy=self.policies.readiness,
            actor=actor,
            at=at,
            assessment_id=uuid4(),
            event_id=uuid4(),
        )

    def gate(
        self,
        hypothesis: Hypothesis,
        readiness: DeliveryReadinessAssessment | None,
        *,
        actor: Actor,
        at: datetime,
    ) -> DiscoveryGateEvaluation:
        return evaluate_discovery_gate(
            hypothesis,
            readiness,
            policies=self.policies,
            actor=actor,
            at=at,
            gate_id=uuid4(),
            evaluation_event_id=uuid4(),
            outcome_event_id=uuid4(),
        )

    def override(
        self,
        gate: DiscoveryGateEvaluation,
        *,
        actor: Actor,
        reason: str,
        at: datetime,
    ) -> DiscoveryGateOverride:
        if gate.policies != self.policies:
            raise ValueError("cannot override an obsolete gate policy")
        return override_discovery_gate(
            gate, actor=actor, reason=reason, at=at, override_id=uuid4(), event_id=uuid4()
        )

    def promote(
        self,
        hypothesis: Hypothesis,
        gate: DiscoveryGateEvaluation,
        *,
        actor: Actor,
        at: datetime,
        override: DiscoveryGateOverride | None = None,
    ) -> CandidatePromotion:
        return promote_candidate(
            hypothesis,
            gate,
            policies=self.policies,
            actor=actor,
            at=at,
            lifecycle_event_id=uuid4(),
            decision_event_id=uuid4(),
            override=override,
        )
