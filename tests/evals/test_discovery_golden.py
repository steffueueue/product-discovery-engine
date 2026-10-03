"""Offline contracts and optional live behavior checks share semantic expectations."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from product_discovery_engine.application.analysis_models import DiscoveryAnalysis
from product_discovery_engine.application.discovery_analysis import (
    AnalysisInput,
    DiscoveryAnalysisService,
)
from product_discovery_engine.domain.common import SourceReference, SourceType
from product_discovery_engine.domain.submissions import Submission
from product_discovery_engine.infrastructure.openai_analysis import (
    OpenAIAnalysisConfig,
    OpenAIAnalysisProvider,
)

CASES = json.loads((Path(__file__).parents[1] / "fixtures/discovery_analysis.json").read_text())


def make_request(text: str) -> AnalysisInput:
    return AnalysisInput(
        submission=Submission(
            id=uuid4(),
            original_text=text,
            source=SourceReference(source_type=SourceType.STAKEHOLDER, reference="fixture"),
            submitter=None,
            created_at=datetime.now(UTC),
        )
    )


class FixtureProvider:
    def __init__(self, result: DiscoveryAnalysis) -> None:
        self.result = result

    def analyze(self, request: AnalysisInput) -> DiscoveryAnalysis:
        return self.result


def assert_semantics(case: str, result: DiscoveryAnalysis) -> None:
    assert not result.facts and not result.evidence
    assert result.strategic_fit.status == "insufficient_strategy_context"
    assert result.assumptions and all(a.agent_generated for a in result.assumptions)
    assert result.validation_recommendation is not None
    assert result.riskiest_assumption is not None
    assert (
        result.validation_recommendation.target_assumption_id
        == result.riskiest_assumption.assumption_id
    )
    if case == "feature_request":
        assert result.intake_classification in {"feature_request", "solution_idea"}
        assert result.normalized_problem.status == "unknown"
    if case == "mixed":
        assert result.normalized_problem.status == "hypothesis"
        assert result.solution_hypothesis.status == "hypothesis"
        assert result.normalized_problem.statement != result.solution_hypothesis.statement
    if case == "conflicting":
        assert result.contradictory_signals
    if case == "explicit_unknown":
        assert result.unknowns
    if case == "causality":
        assert result.inferences and result.assumptions
    if case == "validation":
        assert result.validation_recommendation.method in {
            "customer_interview",
            "contextual_inquiry",
            "support_ticket_analysis",
            "survey",
            "behavioral_analytics",
        }


@pytest.mark.parametrize("index", range(len(CASES)), ids=[c["case"] for c in CASES])
def test_offline_golden_contract(index: int) -> None:
    case = CASES[index]
    request = make_request(case["input"])
    original = request.submission.model_dump_json()
    result = DiscoveryAnalysisService(
        FixtureProvider(DiscoveryAnalysis.model_validate(case["expected"]))
    ).analyze(request)
    assert_semantics(case["case"], result)
    assert request.submission.model_dump_json() == original


@pytest.mark.live_ai
@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_AI_EVALS") != "1"
    or not os.environ.get("OPENAI_API_KEY")
    or not os.environ.get("DISCOVERY_ANALYSIS_MODEL"),
    reason="Live AI evaluations explicitly opt in and require configured credentials",
)
@pytest.mark.parametrize("index", range(len(CASES)), ids=[c["case"] for c in CASES])
def test_live_golden_contract(index: int) -> None:
    case = CASES[index]
    result = DiscoveryAnalysisService(
        OpenAIAnalysisProvider(OpenAIAnalysisConfig.from_environment())
    ).analyze(make_request(case["input"]))
    assert_semantics(case["case"], result)
