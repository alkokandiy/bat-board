"""Backwards-compatible entry point. Delegates to the default adapter.

Tests patch llm_provider.generate / llm_provider.get_settings directly —
both names keep working. New code should use services.llm_providers.
"""

from typing import List

from config import get_settings  # noqa: F401 — patched by tests as llm_provider.get_settings

from services.llm_providers.base import (
    LLMNotConfiguredError,
    LLMLimitError,
    LLMResponse,
    LLMServiceError,
    ToolCall,
    extract_system_instruction,
)

__all__ = [
    "LLMNotConfiguredError",
    "LLMLimitError",
    "LLMResponse",
    "LLMServiceError",
    "ToolCall",
    "generate",
    "get_settings",
]


async def generate(messages: List[dict], tools: List[dict]) -> LLMResponse:
    """Default provider: Gemini. Fail-closed when GEMINI_API_KEY is unset."""
    from services.llm_providers.gemini import GeminiAdapter

    settings = get_settings()
    if not settings.gemini_api_key:
        raise LLMNotConfiguredError(
            "GEMINI_API_KEY is not set. Set it in Railway before using Alfred."
        )
    adapter = GeminiAdapter(api_key=settings.gemini_api_key, model=settings.gemini_model)
    system, _ = extract_system_instruction(messages)
    return await adapter.generate(messages, tools, system)
