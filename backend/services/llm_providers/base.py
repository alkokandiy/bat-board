"""Common interface for all LLM provider adapters.

Nothing outside services/llm_providers/ may import a provider SDK directly.
Callers (alfred_agent) only ever touch LLMProviderAdapter.generate().
"""

import asyncio
import structlog
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol, Tuple, TypeVar

logger = structlog.get_logger()

# Retry policy shared by all adapters (transient provider errors only).
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds; doubles each attempt
REQUEST_TIMEOUT = 30.0  # seconds per API attempt
TRANSIENT_STATUSES = frozenset({429, 500, 502, 503, 504})


@dataclass
class ToolCall:
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    # Opaque bytes from the model (Gemini "thought signature"). MUST be
    # replayed verbatim when this call is echoed back in later turns —
    # the API 400s without it. Never shown to users, never logged.
    # Non-Gemini adapters leave this None.
    thought_signature: Optional[bytes] = None


@dataclass
class LLMResponse:
    text: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_tool_calling: bool = False
    supports_vision_input: bool = False
    supports_audio_input: bool = False
    supports_image_generation: bool = False
    supports_search_grounding: bool = False


class LLMNotConfiguredError(RuntimeError):
    """Raised when generate() is called without an API key configured."""


class LLMLimitError(RuntimeError):
    """Raised when all retries are exhausted due to rate limiting (429)."""


class LLMServiceError(RuntimeError):
    """Raised when all retries are exhausted due to server errors (5xx)."""


class LLMProviderAdapter(Protocol):
    async def generate(
        self,
        messages: List[dict],
        tools: List[dict],
        system_instruction: Optional[str],
    ) -> LLMResponse:
        """One model call. messages use the provider-agnostic dict shape."""
        ...

    def capabilities(self, model_name: Optional[str] = None) -> ProviderCapabilities:
        """Capabilities for the given model (defaults to this adapter's model)."""
        ...


T = TypeVar("T")


def extract_system_instruction(messages: List[dict]) -> Tuple[Optional[str], List[dict]]:
    """Split the first system message out; providers needing top-level system use it."""
    system = None
    rest = []
    for msg in messages:
        if msg.get("role") == "system" and system is None:
            system = msg.get("content", "")
            continue
        rest.append(msg)
    return system, rest


def extract_status(exc: Exception) -> Optional[int]:
    """Best-effort HTTP status from provider/HTTPX error shapes."""
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


async def run_with_retries(fn: Callable[[], Awaitable[T]], provider: str) -> T:
    """Call fn with timeout + backoff on transient errors; map exhaustion to typed errors."""
    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            return await asyncio.wait_for(fn(), timeout=REQUEST_TIMEOUT)
        except asyncio.TimeoutError:
            last_exc = TimeoutError(f"{provider} API timed out after {REQUEST_TIMEOUT}s")
            logger.warning("llm_timeout", provider=provider, attempt=attempt + 1, max_retries=MAX_RETRIES)
        except Exception as exc:  # noqa: BLE001 — status-sniffed below, then re-raised
            last_exc = exc
            status = extract_status(exc)
            logger.warning(
                "llm_api_error", provider=provider,
                attempt=attempt + 1, max_retries=MAX_RETRIES,
                status_code=status, error=str(exc)[:200],
            )
            if status is not None and status not in TRANSIENT_STATUSES:
                raise  # Non-transient (400, 401, ...) — don't retry.
            if status is None and not _looks_transient(exc):
                raise
        await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))

    status = extract_status(last_exc) if last_exc else None
    if status == 429:
        raise LLMLimitError(f"{provider} is rate-limiting — too many requests. Try again shortly.")
    raise LLMServiceError(f"{provider} API unavailable after {MAX_RETRIES} retries: {last_exc}")


def _looks_transient(exc: Exception) -> bool:
    """Status-less errors worth retrying (timeouts, connection drops)."""
    name = type(exc).__name__
    return name in {"APITimeoutError", "APIConnectionError", "TimeoutError", "ConnectError", "ReadTimeout"}
