"""Static capability registry: what each (provider, model) pair can do.

Values verified against provider docs 2026-09-25/26 (Batch A report +
verification pass: Anthropic/OpenAI vision+audio re-checked directly).
A wrong True makes Alfred promise what the model can't do; a wrong False
just hides a feature until confirmed. Unknown pairs get all-False.
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
    # Vision True: platform.claude.com vision guide — Messages API takes
    # image blocks (base64/URL/file, JPEG/PNG/GIF/WebP) across Claude models.
    # Image gen stays False (docs FAQ: "Can Claude generate images? No").
    # Audio stays False: input block types are text/image/document/tool —
    # no audio block exists (open SDK feature request, Feb 2026).
    ("anthropic", "claude-sonnet-5"): ProviderCapabilities(
        supports_tool_calling=True,
        supports_vision_input=True,
        supports_audio_input=False,
        supports_image_generation=False,
        supports_search_grounding=True,
    ),
    # Vision True: images-vision guide — Chat Completions takes image_url
    # parts; sizing table lists the gpt-5.6 family as vision models.
    # Image gen stays False (Images API / Responses tool only, not chat).
    # Audio stays False: chat audio input needs dedicated audio models
    # (gpt-4o-audio-preview, gpt-audio-1.5) — no evidence for gpt-5.6.
    ("openai", "gpt-5.6"): ProviderCapabilities(
        supports_tool_calling=True,
        supports_vision_input=True,
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
