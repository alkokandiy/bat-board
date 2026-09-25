"""OpenAI-compatible adapter (Chat Completions).

One class, instantiated per provider via base_url:
- OpenAI:   https://api.openai.com/v1
- DeepSeek: https://api.deepseek.com
- Kimi:     https://api.moonshot.ai/v1

Wire differences vs the common shape:
- tools wrapped as {"type": "function", "function": {...}}.
- tool call arguments arrive as a JSON STRING — parse failure is logged
  and treated as no valid tool call (never crashes the turn).
- tool messages require tool_call_id matching a prior call id. Our common
  ToolCall has no id, so synthetic ids are paired in order (same approach
  as the Anthropic adapter).
"""

import json
import structlog
from typing import Dict, List, Optional

from .base import LLMResponse, ProviderCapabilities, ToolCall, run_with_retries
from .capabilities import get_capabilities

logger = structlog.get_logger()

PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
    "kimi": "https://api.moonshot.ai/v1",
}


class OpenAICompatibleAdapter:
    def __init__(self, api_key: str, model: str, base_url: str, provider_key: str):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.provider_key = provider_key

    @classmethod
    def for_provider(cls, provider_key: str, api_key: str, model: str) -> "OpenAICompatibleAdapter":
        return cls(api_key=api_key, model=model, base_url=PROVIDER_BASE_URLS[provider_key], provider_key=provider_key)

    def capabilities(self, model_name: Optional[str] = None) -> ProviderCapabilities:
        return get_capabilities(self.provider_key, model_name or self.model)

    async def generate(
        self,
        messages: List[dict],
        tools: List[dict],
        system_instruction: Optional[str],
    ) -> LLMResponse:
        import openai

        client = openai.AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

        openai_tools = [
            {"type": "function", "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {"type": "object", "properties": {}}),
            }}
            for t in tools
        ]
        openai_messages = _to_openai_messages(messages, system_instruction)

        kwargs: Dict = {"model": self.model, "messages": openai_messages, "temperature": 0.7}
        if openai_tools:
            kwargs["tools"] = openai_tools

        async def _call():
            return await client.chat.completions.create(**kwargs)

        response = await run_with_retries(_call, provider=self.provider_key.title())
        return _parse_response(response)


def _to_openai_messages(messages: List[dict], system_instruction: Optional[str]) -> List[dict]:
    """Translate common messages; synthetic tool_call ids paired in order."""
    out: List[dict] = []
    if system_instruction:
        out.append({"role": "system", "content": system_instruction})
    pending_ids: List[str] = []
    call_counter = 0

    def _next_id(name: str) -> str:
        nonlocal call_counter
        call_counter += 1
        return f"call_{call_counter}_{name}"

    for msg in messages:
        role = msg.get("role")
        if role == "system":
            if not system_instruction:
                out.append({"role": "system", "content": msg.get("content", "")})
            continue
        if role == "tool":
            tool_call_id = pending_ids.pop(0) if pending_ids else _next_id(msg.get("name", "tool"))
            out.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": json.dumps(msg.get("result", {}), default=str),
            })
            continue
        if role == "assistant" and msg.get("tool_calls"):
            calls = []
            for tc in msg["tool_calls"]:
                tool_call_id = _next_id(tc["name"])
                pending_ids.append(tool_call_id)
                calls.append({
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc.get("arguments", {})),
                    },
                })
            out.append({
                "role": "assistant",
                "content": msg.get("content"),
                "tool_calls": calls,
            })
            continue
        out.append({
            "role": "assistant" if role == "assistant" else "user",
            "content": msg.get("content", ""),
        })
    return out


def _parse_response(response) -> LLMResponse:
    text_parts = []
    tool_calls = []
    choices = getattr(response, "choices", None) or []
    if not choices:
        return LLMResponse(text=None, tool_calls=[])
    message = getattr(choices[0], "message", None)
    if message is None:
        return LLMResponse(text=None, tool_calls=[])
    content = getattr(message, "content", None)
    if content:
        text_parts.append(content)
    for tc in (getattr(message, "tool_calls", None) or []):
        fn = getattr(tc, "function", None)
        if fn is None:
            continue
        raw_args = getattr(fn, "arguments", None) or "{}"
        try:
            arguments = json.loads(raw_args)
            if not isinstance(arguments, dict):
                raise ValueError(f"arguments JSON is not an object: {raw_args[:100]}")
        except (ValueError, TypeError) as exc:
            logger.warning("llm_tool_args_unparseable", name=getattr(fn, "name", ""), error=str(exc)[:150])
            continue
        tool_calls.append(ToolCall(name=getattr(fn, "name", ""), arguments=arguments))
    text = "\n".join(text_parts).strip() or None
    return LLMResponse(text=text, tool_calls=tool_calls)
