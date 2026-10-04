"""Complete credential-free search outcome loop with mixed learning and retained history."""

from examples.outcome_feedback import OutcomeScenario
from product_discovery_engine.domain.lifecycle import HypothesisStatus


def test_complete_offline_search_outcome_episode(outcome_scenario: OutcomeScenario) -> None:
    s = outcome_scenario
    assert (
        s.started.authorization.current.hypothesis.status == HypothesisStatus.SELECTED_FOR_DELIVERY
    )
    assert s.implemented.after.status == HypothesisStatus.IMPLEMENTED
    assert s.measuring.after.status == HypothesisStatus.MEASURING_OUTCOME
    assert s.closed.after.status == HypothesisStatus.CLOSED
    assert s.assessment.disposition.value == "mixed"
    assert s.causal.state.value == "insufficient_evidence"
    assert s.knowledge_before.evidence[0] in s.knowledge_after.evidence
    assert len(s.knowledge_after.evidence) == len(s.knowledge_before.evidence) + 1
    assert (
        len(s.closed.after.links.evidence_ids) == len(s.implemented.before.links.evidence_ids) + 3
    )
    assert s.completed.deviations and s.review.reviewer.kind.value == "human"
