"""Real SDK failure classification without credentials, prompts or payload exposure."""

from unittest.mock import patch

import httpx
import pytest
from openai import APIConnectionError, APIError, APITimeoutError, OpenAI
from pydantic import SecretStr

from product_discovery_engine.application.discovery_analysis import ProviderUnavailable
from product_discovery_engine.infrastructure.openai_analysis import (
    OpenAIAnalysisConfig,
    OpenAIAnalysisProvider,
)
from product_discovery_engine.infrastructure.openai_challenge import OpenAIChallengeProvider
from product_discovery_engine.infrastructure.openai_errors import safe_api_failure
from tests.evals.test_challenge_golden import make_request
from tests.unit.test_discovery_analysis import request


@pytest.mark.parametrize("capability", ["analysis", "challenge"])
@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "invalid_api_key"),
        (403, "permission_denied"),
        (400, "invalid_json_schema"),
        (404, "model_not_found"),
        (429, "insufficient_quota"),
        (500, "private-code-must-not-escape"),
    ],
)
def test_status_diagnostics_remain_safe(capability: str, status: int, code: str) -> None:
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(
            status,
            json={
                "error": {"message": "private provider payload", "code": code, "type": "api_error"}
            },
        )

    client = OpenAI(
        api_key="offline-placeholder",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    config = OpenAIAnalysisConfig(api_key=SecretStr("offline-placeholder"), model="test-model")
    module = "product_discovery_engine.infrastructure.openai_" + capability + ".OpenAI"
    with patch(module, return_value=client), client:
        with pytest.raises(ProviderUnavailable) as caught:
            if capability == "analysis":
                OpenAIAnalysisProvider(config).analyze(request())
            else:
                OpenAIChallengeProvider(config).analyze_challenges(make_request(0))
        message = str(caught.value)
        assert f"HTTP {status}" in message
        if status != 500:
            assert code in message
        assert "private" not in message
        assert "offline-placeholder" not in message
        assert caught.value.__suppress_context__
    assert len(calls) == 1


def test_connection_timeout_and_generic_errors_never_expose_raw_messages() -> None:
    req = httpx.Request("POST", "https://api.openai.com/v1/responses")
    assert safe_api_failure(APITimeoutError(request=req)) == "timeout"
    assert (
        safe_api_failure(APIConnectionError(message="private connection payload", request=req))
        == "connection failure"
    )
    assert (
        safe_api_failure(APIError("private generic payload", request=req, body=None))
        == "provider failure"
    )
