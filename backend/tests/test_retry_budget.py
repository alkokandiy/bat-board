"""Failing fast beats failing late.

A provider outage used to cost 165 seconds of silence before the apology
arrived — five 5xx attempts at a 30-second timeout plus exponential backoff.
Somebody waiting in a chat reads three minutes as a dead bot, and sends the
message again, which starts the whole thing a second time.
"""

import asyncio

import pytest

from services.llm_providers import base


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _Err(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.status_code = status


def test_the_total_budget_is_about_a_minute_not_three():
    assert base.MAX_TOTAL_SECONDS <= 90
    worst_case_without_budget = (
        base.MAX_RETRIES_5XX * base.REQUEST_TIMEOUT
        + sum(base.RETRY_BASE_DELAY * (2 ** i) for i in range(base.MAX_RETRIES_5XX - 1))
    )
    assert base.MAX_TOTAL_SECONDS < worst_case_without_budget


def test_a_persistent_outage_gives_up_inside_the_budget(monkeypatch):
    """The real 503 case, with the clock and the network both stubbed out."""
    monkeypatch.setattr(base, "REQUEST_TIMEOUT", 0.01)
    monkeypatch.setattr(base, "RETRY_BASE_DELAY", 0.01)
    attempts = []

    async def always_503():
        attempts.append(1)
        raise _Err(503)

    with pytest.raises(base.LLMServiceError):
        _run(base.run_with_retries(always_503, "gemini"))
    # It tried properly rather than giving up at once...
    assert len(attempts) >= 2
    # ...and did not exceed its own retry ceiling.
    assert len(attempts) <= base.MAX_RETRIES_5XX


def test_a_rate_limit_is_reported_as_a_rate_limit(monkeypatch):
    """429 and 503 need different advice, so they stay different errors."""
    monkeypatch.setattr(base, "REQUEST_TIMEOUT", 0.01)
    monkeypatch.setattr(base, "RETRY_BASE_DELAY", 0.01)

    async def always_429():
        raise _Err(429)

    with pytest.raises(base.LLMLimitError):
        _run(base.run_with_retries(always_429, "gemini"))


def test_a_success_after_one_blip_still_succeeds(monkeypatch):
    """The budget must not turn a recoverable blip into a failure."""
    monkeypatch.setattr(base, "REQUEST_TIMEOUT", 0.05)
    monkeypatch.setattr(base, "RETRY_BASE_DELAY", 0.01)
    state = {"n": 0}

    async def flaky():
        state["n"] += 1
        if state["n"] == 1:
            raise _Err(503)
        return "recovered"

    assert _run(base.run_with_retries(flaky, "gemini")) == "recovered"


def test_a_real_client_error_is_not_retried_at_all(monkeypatch):
    """A 400 will fail identically every time; retrying only wastes the wait."""
    monkeypatch.setattr(base, "REQUEST_TIMEOUT", 0.05)
    attempts = []

    async def bad_request():
        attempts.append(1)
        raise _Err(400)

    with pytest.raises(_Err):
        _run(base.run_with_retries(bad_request, "gemini"))
    assert len(attempts) == 1


def test_the_failure_message_says_whose_fault_it_is():
    """"Alfred's thinking engine is overloaded" sounded like bat-board broke."""
    from services import alfred_agent

    reply = alfred_agent.SERVICE_DOWN_REPLY.lower()
    assert "provider" in reply
    assert "not been lost" in reply or "nothing you asked for has been lost" in reply
    assert "/setkey" in reply
