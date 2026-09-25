"""Anthropic adapter (Messages API).

Wire differences vs the common shape:
- tools use `input_schema` (not `parameters`); input arrives as a dict.
- system prompt is a top-level `system` parameter, not a message.
- assistant tool_use blocks carry provider ids; tool_result blocks must
  reference them. Our common ToolCall has no id, so this adapter assigns
  synthetic ids in order: each assistant-with-tool_calls message consumes
  the next N tool messages. Both sides are translated here, so pairing holds.
"""

import json
import structlog
from typing import Dict, List, Optional

from .base import LLMResponse, ProviderCapabilities, ToolCall, run_with_retries
from .capabilities import get_capabilities

logger = structlog.get_logger()

PROVIDER_KEY = "anthropic"
MAX_TOKENS = 2048


class AnthropicAdapter:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def capabilities(self, model_name: Optional[str] = None) -> ProviderCapabilities:
        return get_capabilities(PROVIDER_KEY, model_name or self.model)

    async def generate(
        self,
        messages: List[dict],
        tools: List[dict],
        system_instruction: Optional[str],
    ) -> LLMResponse:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self.api_key)

        system = system_instruction
        rest = []
        for msg in messages:
            if msg.get("role") == "system" and system is None:
                system = msg.get("content", "")
                continue
            rest.append(msg)

        anthropic_tools = [
            {
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
            }
            for t in tools
        ]
        anthropic_messages = _to_anthropic_messages(rest)

        kwargs: Dict = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "messages": anthropic_messages,
        }
        if system:
            kwargs["system"] = system
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        async def _call():
            return await client.messages.create(**kwargs)

        response = await run_with_retries(_call, provider="Anthropic")
        return _parse_response(response)


def _to_anthropic_messages(messages: List[dict]) -> List[dict]:
    """Translate common messages; synthetic tool_use ids paired in order."""
    out: List[dict] = []
    pending_ids: List[str] = []
    call_counter = 0

    def _next_id(name: str) -> str:
        nonlocal call_counter
        call_counter += 1
        return f"call_{call_counter}_{name}"

    for msg in messages:
        role = msg.get("role")
        if role == "tool":
            tool_use_id = pending_ids.pop(0) if pending_ids else _next_id(msg.get("name", "tool"))
            out.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": json.dumps(msg.get("result", {}), default=str),
                }],
            })
            continue
        if role == "assistant" and msg.get("tool_calls"):
            blocks = []
            if msg.get("content"):
                blocks.append({"type": "text", "text": msg["content"]})
            for tc in msg["tool_calls"]:
                tool_use_id = _next_id(tc["name"])
                pending_ids.append(tool_use_id)
                blocks.append({
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": tc["name"],
                    "input": tc.get("arguments", {}),
                })
            out.append({"role": "assistant", "content": blocks})
            continue
        out.append({
            "role": "assistant" if role == "assistant" else "user",
            "content": msg.get("content", ""),
        })
    return out


def _parse_response(response) -> LLMResponse:
    text_parts = []
    tool_calls = []
    for block in (getattr(response, "content", None) or []):
        btype = getattr(block, "type", None)
        if btype == "text" and getattr(block, "text", None):
            text_parts.append(block.text)
        elif btype == "tool_use":
            tool_calls.append(ToolCall(
                name=getattr(block, "name", ""),
                arguments=dict(getattr(block, "input", None) or {}),
            ))
    text = "\n".join(text_parts).strip() or None
    return LLMResponse(text=text, tool_calls=tool_calls)
