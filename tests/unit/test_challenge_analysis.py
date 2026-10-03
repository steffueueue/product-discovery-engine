from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from product_discovery_engine.application.challenge_analysis import (
    ChallengeAnalysis,
    ChallengeAnalysisService,
    ChallengeCategory,
    ChallengeInput,
)
from product_discovery_engine.application.discovery_analysis import (
    InvalidAnalysis,
    ProviderUnavailable,
)
from product_discovery_engine.domain.audit import EventType
from product_discovery_engine.infrastructure.openai_analysis import OpenAIAnalysisConfig
from product_discovery_engine.infrastructure.openai_challenge import OpenAIChallengeProvider
from tests.evals.test_challenge_golden import (
    CASES,
    FixtureChallengeProvider,
    assert_semantics,
    make_request,
)
from tests.m3_helpers import ACTOR, AT


def analysis(index: int = 6) -> ChallengeAnalysis:
    return ChallengeAnalysis.model_validate(CASES[index]["expected"])


def test_challenge_record_preserves_context_audit_and_advisory_marker() -> None:
    request = make_request(6)
    record = ChallengeAnalysisService(FixtureChallengeProvider(analysis())).analyze_record(
        request, actor=ACTOR, at=AT, record_id=uuid4(), event_id=uuid4()
    )
    assert record.request == request
    assert record.event.event_type == EventType.CHALLENGE_COMPLETED
    assert record.result.advisory_only
    assert record.result.contradicting_evidence_ids
    assert record.provenance == record.result.items[0].provenance


@pytest.mark.parametrize(
    "patch", [{"contradicting_evidence_ids": ()}, {"contradicting_evidence_ids": (uuid4(),)}]
)
def test_challenges_cannot_hide_or_invent_contradictions(patch: dict[str, object]) -> None:
    result = ChallengeAnalysis.model_validate({**analysis().model_dump(), **patch})
    with pytest.raises(InvalidAnalysis, match="every contradictory"):
        ChallengeAnalysisService(FixtureChallengeProvider(result)).analyze(make_request(6))


def test_challenges_cannot_invent_references_or_provenance() -> None:
    for patch in (
        {"relevant_evidence_ids": (uuid4(),)},
        {"provenance": {"provider": "invented", "model": "fake", "prompt_version": "x"}},
    ):
        data = analysis().model_dump()
        data["items"][0].update(patch)
        result = ChallengeAnalysis.model_validate(data)
        with pytest.raises(InvalidAnalysis):
            ChallengeAnalysisService(FixtureChallengeProvider(result)).analyze(make_request(6))


@pytest.mark.parametrize(
    "patch",
    [
        {"final_decision": "pursue"},
        {"evidence_quality": "high"},
        {"freshness": "current"},
        {"triangulation": "triangulated"},
        {"advisory_only": False},
        {"disconfirming_evidence_required": ()},
        {"limitations": ()},
        {"items": ()},
    ],
)
def test_ai_cannot_emit_authoritative_states_or_skip_safeguards(patch: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ChallengeAnalysis.model_validate({**analysis().model_dump(), **patch})


def test_provider_error_is_sanitized_and_invalid_payload_revalidated() -> None:
    class FailingProvider(FixtureChallengeProvider):
        def analyze_challenges(self, request: ChallengeInput) -> ChallengeAnalysis:
            raise RuntimeError("Sensitive provider payload")

    with pytest.raises(ProviderUnavailable, match="Challenge provider failed") as error:
        ChallengeAnalysisService(FailingProvider(analysis())).analyze(make_request(6))
    assert "Sensitive" not in str(error.value)
    invalid = analysis().model_copy(update={"items": ()})
    with pytest.raises(InvalidAnalysis, match="structured"):
        ChallengeAnalysisService(FixtureChallengeProvider(invalid)).analyze(make_request(6))


def test_semantic_contract_rejects_generic_challenge_that_misses_causality() -> None:
    data = analysis(0).model_dump()
    for item in data["items"]:
        item["category"] = ChallengeCategory.OVERLOOKED_RISK
    with pytest.raises(AssertionError):
        assert_semantics("causality", make_request(0), ChallengeAnalysis.model_validate(data))


def test_openai_adapter_uses_structured_output_and_retains_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenAIChallengeProvider(
        OpenAIAnalysisConfig(api_key=SecretStr("offline-placeholder"), model="test-model")
    )
    data = analysis().model_dump()
    for item in data["items"]:
        item["provenance"] = provider.provenance.model_dump()
    result = ChallengeAnalysis.model_validate(data)
    calls: list[dict[str, object]] = []

    class FakeResponses:
        def parse(self, **kwargs: object) -> SimpleNamespace:
            calls.append(kwargs)
            return SimpleNamespace(status="completed", output_parsed=result)

    monkeypatch.setattr(provider.client, "responses", FakeResponses())
    output = ChallengeAnalysisService(provider).analyze(make_request(6))
    assert output == result
    assert calls[0]["text_format"] is ChallengeAnalysis
    assert calls[0]["store"] is False
    assert "test-model" in str(calls[0]["input"])


@pytest.mark.parametrize("status", ["incomplete", "failed", "completed"])
def test_adapter_rejects_incomplete_or_missing_output(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    provider = OpenAIChallengeProvider(
        OpenAIAnalysisConfig(api_key=SecretStr("offline-placeholder"), model="test-model")
    )

    class FakeResponses:
        def parse(self, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(status=status, output_parsed=None)

    monkeypatch.setattr(provider.client, "responses", FakeResponses())
    with pytest.raises(InvalidAnalysis):
        provider.analyze_challenges(make_request(6))


def test_markers_reject_numeric_truth_and_challenge_cannot_precede_knowledge() -> None:
    from datetime import timedelta

    data = analysis().model_dump()
    data["advisory_only"] = 1
    with pytest.raises(ValidationError, match="boolean true"):
        ChallengeAnalysis.model_validate(data)
    data = analysis().model_dump()
    data["items"][0]["ai_generated"] = 1
    with pytest.raises(ValidationError, match="boolean true"):
        ChallengeAnalysis.model_validate(data)
    with pytest.raises(ValidationError, match="cannot precede"):
        ChallengeAnalysisService(FixtureChallengeProvider(analysis())).analyze_record(
            make_request(6),
            actor=ACTOR,
            at=AT - timedelta(days=1),
            record_id=uuid4(),
            event_id=uuid4(),
        )
