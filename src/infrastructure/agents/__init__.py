from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from src.config import settings


def get_model(
    model_name: str | None = None,
) -> OpenAIChatModel:
    return OpenAIChatModel(
        model_name or settings.openai.default_model,
        provider=OpenAIProvider(),
    )


# NOTE: referenced by src/infrastructure/agents, not by domain
AGENT_MODELS: dict[str, str] = {
    "orchestrator": "gpt-4.1-mini",
    "manual_add": "gpt-4.1-mini",
    "microscope": "o4-mini",
    "telescope": "o4-mini",
    "preference": "gpt-4.1-mini",
}
