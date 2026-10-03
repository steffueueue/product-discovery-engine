from uuid import uuid4

import pytest

from product_discovery_engine.domain.assumption_risk import assess_assumption_risk
from product_discovery_engine.domain.audit import EventType
from product_discovery_engine.domain.common import Ordinal
from product_discovery_engine.domain.evidence import EvidenceDirection, EvidenceTarget
from product_discovery_engine.domain.evidence_assessment import EvidenceScope
from tests.m3_helpers import ACTOR, AT, assumption, evidence, policies


@pytest.mark.parametrize("impact", list(Ordinal))
@pytest.mark.parametrize("uncertainty", list(Ordinal))
def test_explicit_risk_matrix(impact: Ordinal, uncertainty: Ordinal) -> None:
    item = evidence(target=EvidenceTarget.ASSUMPTION)
    assessed = assess_assumption_risk(
        assumption(),
        EvidenceScope.of(item),
        (item,),
        decision_impact=impact,
        uncertainty=uncertainty,
        rationale="Failure changes proposed investment",
        evidence_gaps=("Representative segment data",),
        policy=policies().assumption_risk,
        actor=ACTOR,
        at=AT,
        assessment_id=uuid4(),
        event_id=uuid4(),
    )
    assert assessed.risk == policies().assumption_risk.assess(impact, uncertainty)
    assert assessed.supporting_evidence_ids == (item.id,)
    assert assessed.event.event_type == EventType.ASSUMPTION_RISK_REASSESSED
    assert assessed.policy_version


def test_impact_matters_more_than_evidence_count_and_both_directions_retained() -> None:
    a = evidence(1, target=EvidenceTarget.ASSUMPTION)
    b = evidence(2, target=EvidenceTarget.ASSUMPTION, direction=EvidenceDirection.CONTRADICTS)
    scope = EvidenceScope.of(a)
    low = assess_assumption_risk(
        assumption(),
        scope,
        (),
        decision_impact=Ordinal.VERY_LOW,
        uncertainty=Ordinal.VERY_HIGH,
        rationale="Failure barely changes decision",
        evidence_gaps=("All evidence missing",),
        policy=policies().assumption_risk,
        actor=ACTOR,
        at=AT,
        assessment_id=uuid4(),
        event_id=uuid4(),
    )
    high = assess_assumption_risk(
        assumption(),
        scope,
        (a, b),
        decision_impact=Ordinal.VERY_HIGH,
        uncertainty=Ordinal.HIGH,
        rationale="Mixed evidence; failure reverses investment",
        evidence_gaps=("Resolve competing explanation",),
        policy=policies().assumption_risk,
        actor=ACTOR,
        at=AT,
        assessment_id=uuid4(),
        event_id=uuid4(),
    )
    assert low.risk == Ordinal.LOW
    assert high.risk == Ordinal.VERY_HIGH
    assert high.supporting_evidence_ids == (a.id,)
    assert high.contradicting_evidence_ids == (b.id,)
    unknown = assess_assumption_risk(
        assumption(),
        scope,
        (),
        decision_impact=None,
        uncertainty=None,
        rationale="Decision impact not specified",
        evidence_gaps=("Impact unknown",),
        policy=policies().assumption_risk,
        actor=ACTOR,
        at=AT,
        assessment_id=uuid4(),
        event_id=uuid4(),
    )
    assert unknown.risk is None


def test_wrong_assumption_scope_fails() -> None:
    scope = EvidenceScope.of(evidence())
    with pytest.raises(ValueError, match="explicit assumption"):
        assess_assumption_risk(
            assumption(),
            scope,
            (),
            decision_impact=Ordinal.HIGH,
            uncertainty=Ordinal.HIGH,
            rationale="Wrong target",
            evidence_gaps=(),
            policy=policies().assumption_risk,
            actor=ACTOR,
            at=AT,
            assessment_id=uuid4(),
            event_id=uuid4(),
        )
