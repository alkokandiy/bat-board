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

import asyncio
import structlog
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config import get_settings

logger = structlog.get_logger()

# Retry config for transient Gemini errors (429 rate limit, 503 overloaded).
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds; doubles each attempt
_REQUEST_TIMEOUT = 30.0  # seconds per API call


@dataclass
class ToolCall:
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    # Opaque bytes from the model (Gemini "thought signature"). MUST be
    # replayed verbatim when this call is echoed back in later turns —
    # the API 400s without it. Never shown to users, never logged.
    thought_signature: Optional[bytes] = None


@dataclass
class LLMResponse:
    text: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)


class LLMNotConfiguredError(RuntimeError):
    """Raised when generate() is called without an API key configured."""


class LLMLimitError(RuntimeError):
    """Raised when all retries are exhausted due to rate limiting (429)."""


class LLMServiceError(RuntimeError):
    """Raised when all retries are exhausted due to server errors (503)."""


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

    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        tools=[types.Tool(function_declarations=function_declarations)] if function_declarations else None,
                        temperature=0.7,
                    ),
                ),
                timeout=_REQUEST_TIMEOUT,
            )
            # Success — parse and return.
            return _parse_response(response)

        except asyncio.TimeoutError:
            last_exc = TimeoutError(f"Gemini API timed out after {_REQUEST_TIMEOUT}s")
            logger.warning("llm_timeout", attempt=attempt + 1, max_retries=_MAX_RETRIES)
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            await asyncio.sleep(delay)
            continue

        except Exception as exc:
            last_exc = exc
            status_code = _extract_status(exc)
            is_transient = status_code in (429, 500, 502, 503, 504)

            logger.warning(
                "llm_api_error",
                attempt=attempt + 1,
                max_retries=_MAX_RETRIES,
                status_code=status_code,
                error=str(exc)[:200],
            )

            if not is_transient:
                raise  # Non-transient error (400, 401, etc.) — don't retry.

            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            await asyncio.sleep(delay)
            continue

    # All retries exhausted.
    status_code = _extract_status(last_exc) if last_exc else None
    if status_code == 429:
        raise LLMLimitError("Gemini is rate-limiting — too many requests. Try again shortly.")
    raise LLMServiceError(f"Gemini API unavailable after {_MAX_RETRIES} retries: {last_exc}")


def _parse_response(response) -> LLMResponse:
    """Parse Gemini response into provider-agnostic LLMResponse."""
    text_parts = []
    tool_calls = []
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


def _extract_status(exc: Exception) -> Optional[int]:
    """Try to pull an HTTP status code from a Gemini/HTTPX error."""
    # google-genai wraps httpx; the status often sits on .response.status_code
    for attr in ("status_code", "code"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
    resp = getattr(exc, "response", None)
    if resp is not None:
        val = getattr(resp, "status_code", None)
        if isinstance(val, int):
            return val
    return None


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
