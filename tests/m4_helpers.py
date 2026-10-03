"""Reviewed synthetic decision inputs shared by offline decisioning tests."""

from datetime import datetime
from uuid import uuid4

from examples.discovery_decisioning import ACTOR, AT, Scenario, build_scenario
from product_discovery_engine.domain.decisioning_inputs import ReadinessInput
from product_discovery_engine.domain.decisioning_policy import (
    DecisioningPolicies,
    ReadinessDimension,
)
from product_discovery_engine.domain.delivery_readiness import (
    DeliveryReadinessAssessment,
    DimensionState,
    assess_delivery_readiness,
)
from product_discovery_engine.domain.discovery_gate import (
    DiscoveryGateEvaluation,
    evaluate_discovery_gate,
)
from product_discovery_engine.domain.hypotheses import Hypothesis


def readiness(
    inputs: ReadinessInput,
    policies: DecisioningPolicies,
    *,
    at: datetime = AT,
) -> DeliveryReadinessAssessment:
    return assess_delivery_readiness(
        inputs,
        policy=policies.readiness,
        actor=ACTOR,
        at=at,
        assessment_id=uuid4(),
        event_id=uuid4(),
    )


def gate(
    hypothesis: Hypothesis,
    assessment: DeliveryReadinessAssessment | None,
    policies: DecisioningPolicies,
    *,
    at: datetime = AT,
) -> DiscoveryGateEvaluation:
    return evaluate_discovery_gate(
        hypothesis,
        assessment,
        policies=policies,
        actor=ACTOR,
        at=at,
        gate_id=uuid4(),
        evaluation_event_id=uuid4(),
        outcome_event_id=uuid4(),
    )


def dimension(record: DeliveryReadinessAssessment, name: ReadinessDimension) -> DimensionState:
    return next(d.state for d in record.result.dimensions if d.dimension == name)


__all__ = ["ACTOR", "AT", "Scenario", "build_scenario", "dimension", "gate", "readiness"]
