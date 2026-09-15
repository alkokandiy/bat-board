"""LLM provider abstraction for Alfred.

Minimal interface, NOT tied to any single SDK's shape — a second provider
(DeepSeek, OpenAI-compatible, ...) implements generate() without touching
any calling code:

    class ToolCall: name: str, arguments: dict
    class LLMResponse: text: str | None, tool_calls: list[ToolCall]
    async def generate(messages: list[dict], tools: list[dict]) -> LLMResponse

Message dicts: {"role": "system"|"user"|"assistant"|"tool", ...}
  - system:    {"role": "system", "content": str}
  - user/assistant: {"role": ..., "content": str}
  - tool result: {"role": "tool", "name": str, "result": dict}

Tool dicts (provider-agnostic JSON-schema style):
  {"name": str, "description": str,
   "parameters": {"type": "object", "properties": {...}, "required": [...]}}
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config import get_settings


@dataclass
class ToolCall:
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    text: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)


class LLMNotConfiguredError(RuntimeError):
    """Raised when generate() is called without an API key configured."""


async def generate(messages: List[dict], tools: List[dict]) -> LLMResponse:
    """Default provider: Gemini. Fail-closed when GEMINI_API_KEY is unset."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise LLMNotConfiguredError(
            "GEMINI_API_KEY is not set. Set it in Railway before using Alfred."
        )
    return await _generate_gemini(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        messages=messages,
        tools=tools,
    )


async def _generate_gemini(api_key: str, model: str, messages: List[dict], tools: List[dict]) -> LLMResponse:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    system_instruction = None
    contents = []
    for msg in messages:
        role = msg.get("role")
        if role == "system" and system_instruction is None:
            system_instruction = msg.get("content", "")
            continue
        contents.extend(_to_gemini_content(msg))

    function_declarations = [
        types.FunctionDeclaration(
            name=t["name"],
            description=t.get("description", ""),
            parameters=t.get("parameters", {"type": "object", "properties": {}}),
        )
        for t in tools
    ]

    response = await client.aio.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[types.Tool(function_declarations=function_declarations)] if function_declarations else None,
        ),
    )

    text_parts = []
    for part in (response.parts or []):
        if part.text:
            text_parts.append(part.text)
    tool_calls = [
        ToolCall(name=fc.name, arguments=dict(fc.args or {}))
        for fc in (response.function_calls or [])
    ]
    text = "\n".join(text_parts).strip() or None
    return LLMResponse(text=text, tool_calls=tool_calls)


def _to_gemini_content(msg: dict):
    """Convert one provider-agnostic message dict to Gemini Content parts."""
    from google.genai import types

    role = msg.get("role")
    if role == "tool":
        return [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_function_response(
                        name=msg.get("name", "tool"),
                        response={"result": msg.get("result", {})},
                    )
                ],
            )
        ]
    if role == "assistant" and msg.get("tool_calls"):
        parts = []
        if msg.get("content"):
            parts.append(types.Part.from_text(text=msg["content"]))
        for tc in msg["tool_calls"]:
            parts.append(
                types.Part.from_function_call(name=tc["name"], args=tc.get("arguments", {}))
            )
        return [types.Content(role="model", parts=parts)]
    gemini_role = "model" if role == "assistant" else "user"
    return [
        types.Content(
            role=gemini_role,
            parts=[types.Part.from_text(text=msg.get("content", ""))],
        )
    ]
