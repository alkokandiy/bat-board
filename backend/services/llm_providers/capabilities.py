"""Static capability registry: what each (provider, model) pair can do.

Values below were verified against provider docs on 2026-09-25 (see
Batch A report for citations). Anything unverified is False — a wrong
True makes Alfred promise what the model can't do; a wrong False just
hides a feature until confirmed. Unknown pairs get an all-False default.
"""

from typing import Dict, Tuple

from .base import ProviderCapabilities

SAFE_DEFAULT = ProviderCapabilities()

CAPABILITIES: Dict[Tuple[str, str], ProviderCapabilities] = {
    ("gemini", "gemini-3.1-flash-lite"): ProviderCapabilities(
        supports_tool_calling=True,
        supports_vision_input=True,
        supports_audio_input=True,
        supports_image_generation=False,
        supports_search_grounding=True,
    ),
    ("anthropic", "claude-sonnet-5"): ProviderCapabilities(
        supports_tool_calling=True,
        supports_vision_input=False,
        supports_audio_input=False,
        supports_image_generation=False,
        supports_search_grounding=True,
    ),
    ("openai", "gpt-5.6"): ProviderCapabilities(
        supports_tool_calling=True,
        supports_vision_input=False,
        supports_audio_input=False,
        supports_image_generation=False,
        supports_search_grounding=False,
    ),
    ("deepseek", "deepseek-chat"): ProviderCapabilities(
        supports_tool_calling=True,
        supports_vision_input=False,
        supports_audio_input=False,
        supports_image_generation=False,
        supports_search_grounding=False,
    ),
    ("kimi", "kimi-k3"): ProviderCapabilities(
        supports_tool_calling=True,
        supports_vision_input=False,
        supports_audio_input=False,
        supports_image_generation=False,
        supports_search_grounding=False,
    ),
}


def get_capabilities(provider: str, model: str) -> ProviderCapabilities:
    """Conservative all-False default for unrecognized pairs — never crash."""
    return CAPABILITIES.get((provider, model), SAFE_DEFAULT)
