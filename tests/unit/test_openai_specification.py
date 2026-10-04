"""Exercise the real structured-output SDK exclusively through local mock transport."""

import json
from unittest.mock import patch

import httpx
import pytest
from openai import OpenAI
from pydantic import SecretStr

from product_discovery_engine.ai.specification_prompts import PROMPT_VERSION, specification_input
from product_discovery_engine.application.delivery_specification import DeliverySpecificationService
from product_discovery_engine.application.discovery_analysis import (
    InvalidAnalysis,
    ProviderUnavailable,
)
from product_discovery_engine.infrastructure.openai_analysis import OpenAIAnalysisConfig
from product_discovery_engine.infrastructure.openai_specification import (
    OpenAISpecificationDraftingProvider,
)
from tests.m5_helpers import AT, FakeDraftingProvider, context


@pytest.mark.parametrize(
    "mode", ["valid", "invalid", "refusal", "incomplete", "auth", "rate_limit"]
)
def test_actual_sdk_structured_specification_offline(mode: str) -> None:
    inputs = context()
    expected = FakeDraftingProvider().draft_specification(inputs)
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        body = json.loads(req.content)
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["text"]["format"]["strict"] is True
        assert body["store"] is False
        assert body["model"] == "configured-model"
        data = json.loads(body["input"][1]["content"])
        assert data["context"]["id"] == str(inputs.id)
        assert len(data["allowed_sources"]) == len(inputs.sources())
        if mode in {"auth", "rate_limit"}:
            return httpx.Response(
                401 if mode == "auth" else 429,
                json={"error": {"message": "sensitive-provider-error", "type": "api_error"}},
            )
        content = {"type": "output_text", "text": expected.model_dump_json(), "annotations": []}
        if mode == "invalid":
            content["text"] = '{"unexpected":true}'
        elif mode == "refusal":
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
        "product_discovery_engine.infrastructure.openai_specification.OpenAI", return_value=client
    ):
        provider = OpenAISpecificationDraftingProvider(
            OpenAIAnalysisConfig(api_key=SecretStr("test-only"), model="configured-model")
        )
    with client:
        if mode == "valid":
            record = DeliverySpecificationService(provider).draft(inputs, at=AT)
            assert record.proposal == expected
            assert record.provenance.prompt_version == PROMPT_VERSION
            assert record.provenance.model == "configured-model"
        else:
            error = ProviderUnavailable if mode in {"auth", "rate_limit"} else InvalidAnalysis
            with pytest.raises(error) as caught:
                DeliverySpecificationService(provider).draft(inputs, at=AT)
            assert "sensitive-provider-error" not in str(caught.value)
    assert len(calls) == 1


def test_prompt_encodes_sources_as_data() -> None:
    inputs = context()
    data = json.loads(specification_input(inputs))
    assert data["context"] == inputs.model_dump(mode="json")
    assert data["allowed_sources"] == [s.model_dump(mode="json") for s in inputs.sources()]
