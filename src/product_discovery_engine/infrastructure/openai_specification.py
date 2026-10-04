"""Optional structured drafting adapter; construction and execution are explicitly opt-in."""

from openai import APIError, OpenAI
from pydantic import ValidationError

from product_discovery_engine.ai.specification_prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    specification_input,
)
from product_discovery_engine.application.discovery_analysis import (
    AnalysisConfigurationError,
    InvalidAnalysis,
    ProviderUnavailable,
)
from product_discovery_engine.domain.delivery_context import DeliverySpecContext
from product_discovery_engine.domain.spec_proposals import (
    DeliverySpecDraftProposal,
    DraftingProvenance,
)

from .openai_analysis import OpenAIAnalysisConfig
from .openai_errors import safe_api_failure


class OpenAISpecificationDraftingProvider:
    def __init__(self, config: OpenAIAnalysisConfig) -> None:
        if not config.api_key.get_secret_value().strip():
            raise AnalysisConfigurationError("OpenAI API key is missing")
        self.config = config
        self.provenance = DraftingProvenance(
            provider="openai", model=config.model, prompt_version=PROMPT_VERSION
        )
        self.client = OpenAI(api_key=config.api_key.get_secret_value(), timeout=60.0, max_retries=2)

    def draft_specification(self, context: DeliverySpecContext) -> DeliverySpecDraftProposal:
        try:
            response = self.client.responses.parse(
                model=self.config.model,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": specification_input(context)},
                ],
                text_format=DeliverySpecDraftProposal,
                store=False,
            )
            if response.status != "completed" or response.output_parsed is None:
                raise InvalidAnalysis("Provider returned incomplete or refused specification draft")
            return DeliverySpecDraftProposal.model_validate(response.output_parsed)
        except ValidationError:
            raise InvalidAnalysis(
                "Provider returned invalid structured specification output"
            ) from None
        except APIError as error:
            raise ProviderUnavailable(
                f"OpenAI specification request failed ({safe_api_failure(error)})"
            ) from None
