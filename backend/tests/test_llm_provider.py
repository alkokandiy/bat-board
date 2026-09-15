"""Regression test for the thought_signature bug.

Production failure (Railway logs, 2026-09-15):
  400 INVALID_ARGUMENT — "Function call is missing a thought_signature
  in functionCall parts ... function call `default_api:get_profile`".
Every tool-using turn failed on its second leg because we replayed the
model's function calls without their thought signatures.

These tests run against a fake google.genai.Client (no network): they
prove the signature is captured on parse and replayed verbatim.
"""

from types import SimpleNamespace

import pytest

from google.genai import types
from services import llm_provider


@pytest.fixture
def fake_client(monkeypatch):
    calls = []

    class FakeModels:
        def __init__(self, script):
            self.script = script

        async def generate_content(self, model, contents, config):
            calls.append({"model": model, "contents": contents, "config": config})
            return self.script[min(len(calls) - 1, len(self.script) - 1)]

    class FakeAio:
        def __init__(self, script):
            self.models = FakeModels(script)

    class FakeClient:
        _script = []

        def __init__(self, api_key=None):
            self.aio = FakeAio(FakeClient._script)

    monkeypatch.setattr("google.genai.Client", FakeClient)
    monkeypatch.setattr(
        llm_provider, "get_settings",
        lambda: SimpleNamespace(gemini_api_key="test-key", gemini_model="test-model"),
    )
    return calls


def _call_response(name, args, signature):
    class FakeResponse:
        parts = [
            types.Part(
                function_call=types.FunctionCall(name=name, args=args),
                thought_signature=signature,
            )
        ]

    return FakeResponse()


def test_thought_signature_captured_and_replayed(fake_client):
    FakeClient = _fake_client_class()
    FakeClient._script = [
        _call_response("get_profile", {}, b"sig-bytes-123"),
        _text_response("done"),
    ]

    import asyncio

    async def run():
        first = await llm_provider.generate(
            [{"role": "user", "content": "who am i"}], []
        )
        assert len(first.tool_calls) == 1
        assert first.tool_calls[0].thought_signature == b"sig-bytes-123"

        messages = [
            {"role": "user", "content": "who am i"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"name": "get_profile", "arguments": {},
                 "thought_signature": first.tool_calls[0].thought_signature}]},
            {"role": "tool", "name": "get_profile",
             "result": {"username": "x", "points": 0, "bat_level": "The Orphan"}},
        ]
        second = await llm_provider.generate(messages, [])
        assert second.text == "done"

    asyncio.get_event_loop().run_until_complete(run())

    # The replayed second-leg request must echo the signature verbatim.
    replayed = fake_client[1]["contents"]
    echoed = [
        p for content in replayed for p in content.parts
        if p.function_call is not None
    ]
    assert len(echoed) == 1
    assert echoed[0].function_call.name == "get_profile"
    assert echoed[0].thought_signature == b"sig-bytes-123"


def _text_response(text):
    class FakeResponse:
        parts = [types.Part.from_text(text=text)]

    return FakeResponse()


def _fake_client_class():
    import google.genai

    return google.genai.Client
