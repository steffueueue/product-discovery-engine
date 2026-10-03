"""Eight offline advisory contracts share checks with opt-in live evaluations."""

import json
import os
from datetime import date
from pathlib import Path

import pytest

from product_discovery_engine.application.challenge_analysis import (
    ChallengeAnalysis,
    ChallengeAnalysisService,
    ChallengeCategory,
    ChallengeInput,
    ChallengeProvenance,
)
from product_discovery_engine.domain.evidence import EvidenceDirection, EvidenceTarget
from product_discovery_engine.domain.triangulation import TriangulationCategory
from product_discovery_engine.domain.validation_methods import ValidationMethod
from product_discovery_engine.infrastructure.openai_analysis import OpenAIAnalysisConfig
from product_discovery_engine.infrastructure.openai_challenge import OpenAIChallengeProvider
from tests.m3_helpers import evidence, knowledge, origin

CASES = json.loads((Path(__file__).parents[1] / "fixtures/challenge_analysis.json").read_text())


def make_request(index: int) -> ChallengeInput:
    case = CASES[index]
    items = tuple(
        evidence(
            spec["number"],
            statement=spec.get("statement"),
            target=EvidenceTarget(spec.get("target", "problem_existence")),
            direction=EvidenceDirection(spec.get("direction", "supports")),
            collected=date.fromisoformat(spec.get("collected", "2026-10-01")),
        )
        for spec in case["evidence"]
    )
    relations = tuple(
        origin(item, spec["family"], ValidationMethod(spec["method"]))
        for item, spec in zip(items, case["evidence"], strict=True)
    )
    return ChallengeInput(hypothesis_statement=case["input"], knowledge=knowledge(items, relations))


class FixtureChallengeProvider:
    provenance = ChallengeProvenance(
        provider="fixture", model="golden-v1", prompt_version="challenge-analysis-v1"
    )

    def __init__(self, result: ChallengeAnalysis) -> None:
        self.result = result

    def analyze_challenges(self, request: ChallengeInput) -> ChallengeAnalysis:
        return self.result


def assert_semantics(name: str, request: ChallengeInput, result: ChallengeAnalysis) -> None:
    categories = {i.category for i in result.items}
    assert result.advisory_only and all(i.ai_generated for i in result.items)
    assert result.disconfirming_evidence_required and result.limitations
    assert set(result.contradicting_evidence_ids) == {
        e.id for e in request.knowledge.evidence if e.direction == EvidenceDirection.CONTRADICTS
    }
    assert all(
        i.unresolved_counterargument and i.additional_evidence_required for i in result.items
    )
    if name == "causality":
        assert ChallengeCategory.FALSE_CAUSALITY in categories
        assert ChallengeCategory.CONFOUNDING in categories
    elif name == "stakeholder":
        assert ChallengeCategory.STAKEHOLDER_BIAS in categories
        assert categories & {ChallengeCategory.SAMPLE_BIAS, ChallengeCategory.SCOPE_LIMITATION}
    elif name == "confirmation_heavy":
        assert ChallengeCategory.CONFIRMATION_BIAS in categories
        assert result.competing_explanations
    elif name == "shared_source":
        assert ChallengeCategory.SHARED_SOURCE in categories
        assert request.knowledge.triangulation.independent_source_group_count == 1
        assert request.knowledge.triangulation.category == TriangulationCategory.SINGLE_SOURCE
    elif name == "old_evidence":
        assert ChallengeCategory.FRESHNESS in categories
        assert "review" in result.source_scope_notes.lower()
        assert "evidence is false" not in result.source_scope_notes.lower()
    elif name == "strong_mixed_methods":
        assert ChallengeCategory.SCOPE_LIMITATION in categories
        assert request.knowledge.triangulation.category == TriangulationCategory.TRIANGULATED
        assert "independent" in result.source_scope_notes.lower()
        assert any(word in result.source_scope_notes.lower() for word in ("causal", "causality"))
        assert "reach" in result.source_scope_notes.lower()
    elif name == "alternative_explanation":
        assert ChallengeCategory.ALTERNATIVE_EXPLANATION in categories
        assert len(result.competing_explanations) >= 2
        text = " ".join(result.competing_explanations).lower()
        assert "price" in text and ("search" in text or "relevance" in text)
    elif name == "solution_first":
        assert ChallengeCategory.SOLUTION_FIRST in categories
        assert any("problem" in i.challenge_statement.lower() for i in result.items)


@pytest.mark.parametrize("index", range(len(CASES)), ids=[c["case"] for c in CASES])
def test_offline_challenge_contract(index: int) -> None:
    request = make_request(index)
    before = request.model_dump_json()
    result = ChallengeAnalysisService(
        FixtureChallengeProvider(ChallengeAnalysis.model_validate(CASES[index]["expected"]))
    ).analyze(request)
    assert_semantics(CASES[index]["case"], request, result)
    assert request.model_dump_json() == before


@pytest.mark.live_ai
@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_AI_EVALS") != "1"
    or not os.environ.get("OPENAI_API_KEY")
    or not os.environ.get("DISCOVERY_ANALYSIS_MODEL"),
    reason="Live AI evaluations explicitly opt in and require configured credentials",
)
@pytest.mark.parametrize("index", range(len(CASES)), ids=[c["case"] for c in CASES])
def test_live_challenge_contract(index: int) -> None:
    request = make_request(index)
    before = request.model_dump_json()
    result = ChallengeAnalysisService(
        OpenAIChallengeProvider(OpenAIAnalysisConfig.from_environment())
    ).analyze(request)
    assert_semantics(CASES[index]["case"], request, result)
    assert request.model_dump_json() == before
