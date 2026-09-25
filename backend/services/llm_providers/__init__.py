"""Provider adapters for Alfred. Batch A placeholder: default is Gemini.

Batch B replaces get_default_adapter() with real per-user selection.
"""

from config import get_settings

from .anthropic_adapter import AnthropicAdapter
from .base import (
    LLMNotConfiguredError,
    LLMLimitError,
    LLMProviderAdapter,
    LLMResponse,
    LLMServiceError,
    ProviderCapabilities,
    ToolCall,
)
from .capabilities import get_capabilities
from .gemini import GeminiAdapter
from .openai_compatible import OpenAICompatibleAdapter


def get_default_adapter() -> LLMProviderAdapter:
    """Hardcoded Gemini default (Batch A). Batch B: per-user selection."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise LLMNotConfiguredError(
            "GEMINI_API_KEY is not set. Set it in Railway before using Alfred."
        )
    return GeminiAdapter(api_key=settings.gemini_api_key, model=settings.gemini_model)


__all__ = [
    "AnthropicAdapter",
    "GeminiAdapter",
    "LLMNotConfiguredError",
    "LLMLimitError",
    "LLMProviderAdapter",
    "LLMResponse",
    "LLMServiceError",
    "OpenAICompatibleAdapter",
    "ProviderCapabilities",
    "ToolCall",
    "get_capabilities",
    "get_default_adapter",
]
