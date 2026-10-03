"""Reject unsupported knowledge and exercise the actual SDK without network calls."""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from openai import OpenAI
from pydantic import SecretStr, ValidationError

from product_discovery_engine.ai.prompts import task_instructions
from product_discovery_engine.application.analysis_mapping import map_assumption
from product_discovery_engine.application.analysis_models import DiscoveryAnalysis
from product_discovery_engine.application.discovery_analysis import (
    AnalysisConfigurationError,
    AnalysisInput,
    DiscoveryAnalysisService,
    InvalidAnalysis,
    ProviderUnavailable,
)
from product_discovery_engine.domain.common import (
    Provenance,
    SourceReference,
    SourceType,
    StrategyReference,
    Unknown,
)
from product_discovery_engine.domain.evidence import Evidence, EvidenceDirection, EvidenceTarget
from product_discovery_engine.domain.policies import StrategyPolicy
from product_discovery_engine.domain.submissions import Submission
from product_discovery_engine.infrastructure.openai_analysis import (
    OpenAIAnalysisConfig,
    OpenAIAnalysisProvider,
)

GOLDEN = json.loads((Path(__file__).parents[1] / "fixtures/discovery_analysis.json").read_text())


def request() -> AnalysisInput:
    return AnalysisInput(
        submission=Submission(
            id=uuid4(),
            original_text="Probably 40% struggle.",
            source=SourceReference(source_type=SourceType.STAKEHOLDER, reference="stakeholder:1"),
            submitter=None,
            created_at=datetime.now(UTC),
        )
    )


def result() -> DiscoveryAnalysis:
    return DiscoveryAnalysis.model_validate(GOLDEN[0]["expected"])


class FakeProvider:
    def __init__(self, output: DiscoveryAnalysis) -> None:
        self.output = output

    def analyze(self, request: AnalysisInput) -> DiscoveryAnalysis:
        return self.output


def run(output: DiscoveryAnalysis, context: AnalysisInput | None = None) -> DiscoveryAnalysis:
    return DiscoveryAnalysisService(FakeProvider(output)).analyze(context or request())


def test_assumption_maps_with_ai_provenance_and_preserves_category() -> None:
    context = request()
    proposal = result().assumptions[0]
    mapped = map_assumption(proposal, context, id=uuid4())
    assert mapped.ai_generated is True
    assert mapped.category == proposal.category
    assert mapped.provenance.submission_ids == (context.submission.id,)
    assert mapped.provenance.sources == (context.submission.source,)
    assert mapped.evidence_ids == ()


@pytest.mark.parametrize("field,value", [("agent_generated", False), ("uncertainty", "95%")])
def test_assumptions_cannot_claim_observed_origin_or_probability(field: str, value: object) -> None:
    payload = result().model_dump(mode="json")
    payload["assumptions"][0][field] = value
    with pytest.raises(ValidationError):
        DiscoveryAnalysis.model_validate(payload)


@pytest.mark.parametrize("group,kind", [("facts", "fact"), ("evidence", "evidence")])
def test_submission_number_cannot_become_established_knowledge(group: str, kind: str) -> None:
    payload = result().model_dump(mode="json")
    payload[group] = [
        {
            "id": "f1",
            "kind": kind,
            "statement": "40% struggle.",
            "citations": [{"source_id": "submission", "quote": "40%"}],
            "rationale": "Unsupported number",
            "agent_generated": True,
        }
    ]
    with pytest.raises(InvalidAnalysis, match="existing domain evidence"):
        run(DiscoveryAnalysis.model_validate(payload))


@pytest.mark.parametrize("source,quote", [("invented", "40%"), ("submission", "99%")])
def test_fabricated_citation_rejected(source: str, quote: str) -> None:
    payload = result().model_dump(mode="json")
    payload["assumptions"][0]["citations"] = [{"source_id": source, "quote": quote}]
    with pytest.raises(InvalidAnalysis, match="Citation"):
        run(DiscoveryAnalysis.model_validate(payload))


def test_existing_evidence_can_be_preserved_but_not_rewritten() -> None:
    context = request()
    source = SourceReference(source_type=SourceType.ANALYTICS, reference="report:september")
    evidence = Evidence(
        id=uuid4(),
        hypothesis_id=uuid4(),
        statement="Reformulation was 31%.",
        source=source,
        collected_on=datetime.now(UTC).date(),
        target=EvidenceTarget.PROBLEM,
        direction=EvidenceDirection.CONTRADICTS,
        methodology_notes="Measured sample.",
        provenance=Provenance(sources=(source,), ai_generated=False),
    )
    context = AnalysisInput(submission=context.submission, evidence=(evidence,))
    payload = result().model_dump(mode="json")
    payload["evidence"] = [
        {
            "id": "f1",
            "kind": "evidence",
            "statement": evidence.statement,
            "citations": [{"source_id": str(evidence.id), "quote": evidence.statement}],
            "rationale": "Existing measurement; no causal conclusion.",
            "agent_generated": True,
        }
    ]
    assert run(DiscoveryAnalysis.model_validate(payload), context).evidence
    payload["evidence"][0]["statement"] = "All customers cannot find products."
    with pytest.raises(InvalidAnalysis):
        run(DiscoveryAnalysis.model_validate(payload), context)


@pytest.mark.parametrize("objective", [None, Unknown(reason="Not configured")])
def test_missing_strategy_rejects_invented_alignment(objective: Unknown | None) -> None:
    context = request()
    if objective is not None:
        context = AnalysisInput(
            submission=context.submission,
            strategy=StrategyPolicy(
                reference=StrategyReference(id="strategy", version=1), objective=objective
            ),
        )
    payload = result().model_dump(mode="json")
    payload["strategic_fit"]["potential_alignment"] = ["Invented priority"]
    with pytest.raises(InvalidAnalysis, match="unavailable"):
        run(DiscoveryAnalysis.model_validate(payload), context)


def test_configured_strategy_rejects_other_objective() -> None:
    context = AnalysisInput(
        submission=request().submission,
        strategy=StrategyPolicy(
            reference=StrategyReference(id="strategy", version=2), objective="Improve discovery"
        ),
    )
    payload = result().model_dump(mode="json")
    payload["strategic_fit"].update(status="preliminary", objective_ids=["strategy"])
    assert (
        run(DiscoveryAnalysis.model_validate(payload), context).strategic_fit.status
        == "preliminary"
    )
    payload["strategic_fit"]["objective_ids"] = ["invented"]
    with pytest.raises(InvalidAnalysis):
        run(DiscoveryAnalysis.model_validate(payload), context)


@pytest.mark.parametrize(
    "mutation", ["taxonomy", "target", "duplicate", "contradiction", "missing"]
)
def test_structural_integrity(mutation: str) -> None:
    payload = result().model_dump(mode="json")
    if mutation == "taxonomy":
        payload["unknowns"][0]["kind"] = "fact"
    elif mutation == "target":
        payload["validation_recommendation"]["target_assumption_id"] = "missing"
    elif mutation == "duplicate":
        payload["assumptions"][0]["id"] = "u1"
    elif mutation == "contradiction":
        payload["contradictory_signals"] = [
            {
                "claim_ids": ["missing"],
                "competing_explanations": ["A", "B"],
                "explanation": "Unresolved.",
            }
        ]
    else:
        del payload["validation_recommendation"]["failure_signal"]
    with pytest.raises(ValidationError):
        DiscoveryAnalysis.model_validate(payload)


def test_error_boundary_hides_unexpected_exception() -> None:
    class BrokenProvider:
        def analyze(self, request: AnalysisInput) -> DiscoveryAnalysis:
            raise RuntimeError("sensitive provider payload")

    with pytest.raises(ProviderUnavailable) as caught:
        DiscoveryAnalysisService(BrokenProvider()).analyze(request())
    assert "sensitive" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_unchecked_nested_result_is_revalidated() -> None:
    bad = result().model_copy(update={"riskiest_assumption": None})
    with pytest.raises(InvalidAnalysis):
        run(bad)


def test_configuration_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DISCOVERY_ANALYSIS_MODEL", raising=False)
    with pytest.raises(AnalysisConfigurationError):
        OpenAIAnalysisConfig.from_environment()
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    with pytest.raises(AnalysisConfigurationError):
        OpenAIAnalysisConfig.from_environment()
    monkeypatch.setenv("DISCOVERY_ANALYSIS_MODEL", "configured-model")
    assert "test-only" not in repr(OpenAIAnalysisConfig.from_environment())


@pytest.mark.parametrize(
    "mode", ["valid", "invalid", "refusal", "incomplete", "auth", "rate_limit"]
)
def test_actual_sdk_structured_response_without_network(mode: str) -> None:
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        body = json.loads(req.content)
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["text"]["format"]["strict"] is True
        assert body["store"] is False
        if mode in {"auth", "rate_limit"}:
            return httpx.Response(
                401 if mode == "auth" else 429,
                json={"error": {"message": "private provider error", "type": "api_error"}},
            )
        content = {"type": "output_text", "text": result().model_dump_json(), "annotations": []}
        if mode == "invalid":
            content["text"] = '{"unexpected":true}'
        if mode == "refusal":
            content = {"type": "refusal", "refusal": "Cannot comply"}
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 1,
                "model": "configured-model",
                "status": "incomplete" if mode == "incomplete" else "completed",
                "incomplete_details": {"reason": "max_output_tokens"}
                if mode == "incomplete"
                else None,
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [content],
                    }
                ],
            },
        )

    client = OpenAI(
        api_key="test-only",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with patch(
        "product_discovery_engine.infrastructure.openai_analysis.OpenAI", return_value=client
    ):
        provider = OpenAIAnalysisProvider(
            OpenAIAnalysisConfig(api_key=SecretStr("test-only"), model="configured-model")
        )
    with client:
        if mode == "valid":
            assert provider.analyze(request()) == result()
        else:
            expected = ProviderUnavailable if mode in {"auth", "rate_limit"} else InvalidAnalysis
            with pytest.raises(expected) as caught:
                provider.analyze(request())
            assert "private provider error" not in str(caught.value)
    assert len(calls) == 1


def test_original_text_is_encoded_as_data() -> None:
    context = request()
    assert (
        json.loads(task_instructions(context).split("\n", 1)[1])["submission"]["original_text"]
        == context.submission.original_text
    )


def test_existing_fact_keeps_category_and_source() -> None:
    from product_discovery_engine.domain.claims import Claim, ClaimKind

    context = request()
    fact = Claim(
        id=uuid4(),
        kind=ClaimKind.FACT,
        statement="Sample contained 12 interviews.",
        provenance=Provenance(sources=(context.submission.source,), ai_generated=False),
    )
    context = AnalysisInput(submission=context.submission, facts=(fact,))
    payload = result().model_dump(mode="json")
    payload["facts"] = [
        {
            "id": "f1",
            "kind": "fact",
            "statement": fact.statement,
            "citations": [{"source_id": str(fact.id), "quote": fact.statement}],
            "rationale": "Preserve supplied fact without extrapolation.",
            "agent_generated": True,
        }
    ]
    assert (
        run(DiscoveryAnalysis.model_validate(payload), context).facts[0].statement == fact.statement
    )
    payload["evidence"] = [{**payload["facts"][0], "id": "e1", "kind": "evidence"}]
    with pytest.raises(InvalidAnalysis):
        run(DiscoveryAnalysis.model_validate(payload), context)


def test_ai_summary_cannot_supply_underlying_assumption_provenance() -> None:
    context = request()
    submission = Submission(
        id=context.submission.id,
        original_text=context.submission.original_text,
        source=SourceReference(source_type=SourceType.AI_SUMMARY, reference="ai-summary"),
        submitter=None,
        created_at=context.submission.created_at,
    )
    with pytest.raises(InvalidAnalysis, match="Underlying sources"):
        map_assumption(result().assumptions[0], AnalysisInput(submission=submission), id=uuid4())


def test_analysis_record_retains_input_and_version_metadata() -> None:
    context = request()
    record = DiscoveryAnalysisService(FakeProvider(result())).analyze_record(
        context,
        analyzed_at=datetime.now(UTC),
        provider="fixture",
        model="fixture-v1",
        prompt_version="v1",
    )
    assert record.request == context
    assert record.prompt_version == "v1"
    assert record.result == result()
    assert DiscoveryAnalysis.model_validate_json(record.result.model_dump_json()) == result()


def test_malformed_input_rejected() -> None:
    context = request()
    malformed = context.model_copy(update={"submission": {"original_text": " "}})
    with pytest.raises(InvalidAnalysis, match="Malformed"):
        run(result(), malformed)


def test_application_has_no_provider_specific_imports() -> None:
    import ast

    root = Path(__file__).parents[2] / "src/product_discovery_engine/application"
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert all("openai" not in name and "infrastructure" not in name for name in names)


def test_assumption_can_cite_existing_fact_and_preserve_underlying_source() -> None:
    from product_discovery_engine.application.analysis_models import AssumptionProposal
    from product_discovery_engine.domain.claims import Claim, ClaimKind

    context = request()
    source = SourceReference(source_type=SourceType.DOCUMENT, reference="research-report")
    fact = Claim(
        id=uuid4(),
        kind=ClaimKind.FACT,
        statement="Sample contained 12 interviews.",
        provenance=Provenance(sources=(source,), ai_generated=False),
    )
    context = AnalysisInput(submission=context.submission, facts=(fact,))
    payload = result().assumptions[0].model_dump(mode="json")
    payload["citations"] = [{"source_id": str(fact.id), "quote": fact.statement}]
    mapped = map_assumption(AssumptionProposal.model_validate(payload), context, id=uuid4())
    assert source in mapped.provenance.sources
    assert mapped.ai_generated is True
    with pytest.raises(ValidationError):
        AnalysisInput(submission=context.submission, facts=(fact, fact))
