"""OpenAI Responses structured-output adapter; SDK retries transient failures only."""

import os

from openai import APIError, OpenAI
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from product_discovery_engine.ai.prompts import (
    PROMPT_VERSION,
    SYSTEM_INSTRUCTIONS,
    task_instructions,
)
from product_discovery_engine.application.analysis_models import DiscoveryAnalysis
from product_discovery_engine.application.discovery_analysis import (
    AnalysisConfigurationError,
    AnalysisInput,
    InvalidAnalysis,
    ProviderUnavailable,
)
from product_discovery_engine.domain.common import Text

from .openai_errors import safe_api_failure


class OpenAIAnalysisConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    api_key: SecretStr
    model: Text

    @classmethod
    def from_environment(cls) -> "OpenAIAnalysisConfig":
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        model = os.environ.get("DISCOVERY_ANALYSIS_MODEL", "").strip()
        if not key or not model:
            raise AnalysisConfigurationError("Set OPENAI_API_KEY and DISCOVERY_ANALYSIS_MODEL")
        return cls(api_key=SecretStr(key), model=model)


class OpenAIAnalysisProvider:
    prompt_version = PROMPT_VERSION

    def __init__(self, config: OpenAIAnalysisConfig) -> None:
        if not config.api_key.get_secret_value().strip():
            raise AnalysisConfigurationError("OpenAI API key is missing")
        self.config = config
        self.client = OpenAI(api_key=config.api_key.get_secret_value(), timeout=60.0, max_retries=2)

    def analyze(self, request: AnalysisInput) -> DiscoveryAnalysis:
        try:
            response = self.client.responses.parse(
                model=self.config.model,
                input=[
                    {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                    {"role": "user", "content": task_instructions(request)},
                ],
                text_format=DiscoveryAnalysis,
                store=False,
            )
            if response.status != "completed" or response.output_parsed is None:
                raise InvalidAnalysis("Provider returned incomplete or refused analysis")
            return DiscoveryAnalysis.model_validate(response.output_parsed)
        except ValidationError:
            raise InvalidAnalysis("Provider returned invalid structured output") from None
        except APIError as error:
            raise ProviderUnavailable(
                f"OpenAI analysis request failed ({safe_api_failure(error)})"
            ) from None
