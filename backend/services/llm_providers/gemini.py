"""Gemini adapter — existing behavior, moved here unchanged."""

from typing import List, Optional

from .base import (
    LLMProviderAdapter,
    LLMResponse,
    ProviderCapabilities,
    ToolCall,
    run_with_retries,
)
from .capabilities import get_capabilities

PROVIDER_KEY = "gemini"


class GeminiAdapter:
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
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)

        system = system_instruction
        contents = []
        for msg in messages:
            if msg.get("role") == "system":
                if system is None:
                    system = msg.get("content", "")
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

        async def _call():
            return await client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    tools=[types.Tool(function_declarations=function_declarations)] if function_declarations else None,
                    temperature=0.7,
                ),
            )

        response = await run_with_retries(_call, provider="Gemini")
        return _parse_response(response)


def _parse_response(response) -> LLMResponse:
    text_parts = []
    tool_calls = []
    # Iterate parts directly (not response.function_calls): the parsed helper
    # drops per-part fields, and we need each call's thought_signature to
    # replay it verbatim in later turns.
    for part in (response.parts or []):
        if part.text:
            text_parts.append(part.text)
        if part.function_call is not None:
            fc = part.function_call
            tool_calls.append(ToolCall(
                name=fc.name,
                arguments=dict(fc.args or {}),
                thought_signature=part.thought_signature,
            ))
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
            # from_function_call() can't carry a thought_signature, so build
            # the Part directly — replaying it verbatim is API-mandated.
            parts.append(
                types.Part(
                    function_call=types.FunctionCall(
                        name=tc["name"], args=tc.get("arguments", {})
                    ),
                    thought_signature=tc.get("thought_signature"),
                )
            )
        return [types.Content(role="model", parts=parts)]
    gemini_role = "model" if role == "assistant" else "user"
    return [
        types.Content(
            role=gemini_role,
            parts=[types.Part.from_text(text=msg.get("content", ""))],
        )
    ]
