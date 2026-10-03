"""Dedicated structured capability using the existing OpenAI configuration convention."""

from openai import APIError, OpenAI
from pydantic import ValidationError

from product_discovery_engine.ai.challenge_prompts import (
    CHALLENGE_INSTRUCTIONS,
    CHALLENGE_PROMPT_VERSION,
    challenge_task,
)
from product_discovery_engine.application.challenge_analysis import (
    ChallengeAnalysis,
    ChallengeInput,
    ChallengeProvenance,
)
from product_discovery_engine.application.discovery_analysis import (
    AnalysisConfigurationError,
    InvalidAnalysis,
    ProviderUnavailable,
)

from .openai_analysis import OpenAIAnalysisConfig


class OpenAIChallengeProvider:
    def __init__(self, config: OpenAIAnalysisConfig) -> None:
        if not config.api_key.get_secret_value().strip():
            raise AnalysisConfigurationError("OpenAI API key is missing")
        self.config = config
        self.provenance = ChallengeProvenance(
            provider="openai",
            model=config.model,
            prompt_version=CHALLENGE_PROMPT_VERSION,
        )
        self.client = OpenAI(api_key=config.api_key.get_secret_value(), timeout=60.0, max_retries=2)

    def analyze_challenges(self, request: ChallengeInput) -> ChallengeAnalysis:
        try:
            response = self.client.responses.parse(
                model=self.config.model,
                input=[
                    {"role": "system", "content": CHALLENGE_INSTRUCTIONS},
                    {"role": "user", "content": challenge_task(request, self.provenance)},
                ],
                text_format=ChallengeAnalysis,
                store=False,
            )
            if response.status != "completed" or response.output_parsed is None:
                raise InvalidAnalysis("Provider returned incomplete or refused challenge analysis")
            return ChallengeAnalysis.model_validate(response.output_parsed)
        except ValidationError:
            raise InvalidAnalysis("Provider returned invalid structured challenge output") from None
        except APIError:
            raise ProviderUnavailable("OpenAI challenge request failed") from None
