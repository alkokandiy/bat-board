"""Adapter translation/parsing tests (all provider SDK calls mocked, no network)."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from services.llm_providers.anthropic_adapter import AnthropicAdapter
from services.llm_providers.base import ProviderCapabilities
from services.llm_providers.capabilities import get_capabilities
from services.llm_providers.gemini import GeminiAdapter
from services.llm_providers.openai_compatible import OpenAICompatibleAdapter


TOOLS = [{
    "name": "list_missions",
    "description": "List the user's missions.",
    "parameters": {
        "type": "object",
        "properties": {"due_date": {"type": "string"}},
    },
}]

MESSAGES = [
    {"role": "system", "content": "You are Alfred."},
    {"role": "user", "content": "what missions?"},
]


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# --- Gemini: schema translation keeps existing wire format ---

def test_gemini_tool_schema_translation(monkeypatch):
    from google.genai import types as genai_types

    seen = {}

    class FakeModels:
        async def generate_content(self, model, contents, config):
            seen["model"] = model
            seen["config"] = config
            seen["contents"] = contents
            return SimpleNamespace(parts=[genai_types.Part.from_text(text="ok")])

    class FakeClient:
        def __init__(self, api_key=None):
            self.aio = SimpleNamespace(models=FakeModels())

    monkeypatch.setattr("google.genai.Client", FakeClient)

    adapter = GeminiAdapter(api_key="k", model="gemini-3.1-flash-lite")
    resp = run(adapter.generate(MESSAGES, TOOLS, "You are Alfred."))
    assert resp.text == "ok"
    assert resp.tool_calls == []

    decls = seen["config"].tools[0].function_declarations
    assert len(decls) == 1
    assert decls[0].name == "list_missions"
    assert decls[0].parameters.properties["due_date"].type == genai_types.Type.STRING
    # system instruction passed explicitly, never duplicated into contents
    assert seen["config"].system_instruction == "You are Alfred."
    roles = [c.role for c in seen["contents"]]
    assert "system" not in roles


# --- Anthropic: input_schema, top-level system, tool_use parsing ---

def test_anthropic_tool_schema_and_system(monkeypatch):
    seen = {}

    tool_block = SimpleNamespace(type="tool_use", id="toolu_1", name="list_missions", input={"due_date": "2026-09-16"})
    response = SimpleNamespace(content=[tool_block])

    class FakeMessages:
        async def create(self, **kwargs):
            seen.update(kwargs)
            return response

    class FakeClient:
        def __init__(self, api_key=None):
            self.messages = FakeMessages()

    monkeypatch.setattr("anthropic.AsyncAnthropic", FakeClient)

    adapter = AnthropicAdapter(api_key="k", model="claude-sonnet-5")
    resp = run(adapter.generate(MESSAGES, TOOLS, "You are Alfred."))

    tools = seen["tools"]
    assert tools[0]["name"] == "list_missions"
    assert "input_schema" in tools[0] and "parameters" not in tools[0]
    assert tools[0]["input_schema"]["properties"]["due_date"] == {"type": "string"}
    assert seen["system"] == "You are Alfred."
    assert all(m["role"] != "system" for m in seen["messages"])

    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "list_missions"
    assert resp.tool_calls[0].arguments == {"due_date": "2026-09-16"}


def test_anthropic_tool_result_pairing(monkeypatch):
    seen = {}

    class FakeMessages:
        async def create(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="done")])

    class FakeClient:
        def __init__(self, api_key=None):
            self.messages = FakeMessages()

    monkeypatch.setattr("anthropic.AsyncAnthropic", FakeClient)

    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"name": "list_missions", "arguments": {}, "thought_signature": None},
        ]},
        {"role": "tool", "name": "list_missions", "result": {"missions": []}},
    ]
    adapter = AnthropicAdapter(api_key="k", model="claude-sonnet-5")
    resp = run(adapter.generate(history, [], None))
    assert resp.text == "done"

    msgs = seen["messages"]
    assistant = msgs[1]
    tool_use_id = assistant["content"][0]["id"]
    assert assistant["content"][0]["type"] == "tool_use"
    tool_msg = msgs[2]
    assert tool_msg["content"][0]["tool_use_id"] == tool_use_id


# --- OpenAI-compatible: function wrapper, JSON-string args, pairing ---

def _openai_client_factory(seen, message):
    class FakeCompletions:
        async def create(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self, api_key=None, base_url=None):
            seen["base_url"] = base_url
            self.chat = FakeChat()

    return FakeClient


def test_openai_tool_schema_and_json_args(monkeypatch):
    seen = {}
    tool_call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="list_missions", arguments='{"due_date": "2026-09-16"}'),
    )
    message = SimpleNamespace(content=None, tool_calls=[tool_call])
    monkeypatch.setattr("openai.AsyncOpenAI", _openai_client_factory(seen, message))

    adapter = OpenAICompatibleAdapter.for_provider("deepseek", api_key="k", model="deepseek-chat")
    resp = run(adapter.generate(MESSAGES, TOOLS, "You are Alfred."))

    assert seen["base_url"] == "https://api.deepseek.com"
    wrapped = seen["tools"][0]
    assert wrapped["type"] == "function"
    assert wrapped["function"]["name"] == "list_missions"
    assert seen["messages"][0] == {"role": "system", "content": "You are Alfred."}

    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].arguments == {"due_date": "2026-09-16"}


def test_openai_unparseable_args_skipped_not_crash(monkeypatch):
    seen = {}
    bad = SimpleNamespace(id="call_1", function=SimpleNamespace(name="x", arguments="not-json{{{"))
    good = SimpleNamespace(id="call_2", function=SimpleNamespace(name="y", arguments='{"a": 1}'))
    message = SimpleNamespace(content="hi", tool_calls=[bad, good])
    monkeypatch.setattr("openai.AsyncOpenAI", _openai_client_factory(seen, message))

    adapter = OpenAICompatibleAdapter.for_provider("kimi", api_key="k", model="kimi-k3")
    resp = run(adapter.generate([MESSAGES[1]], [], None))
    assert resp.text == "hi"
    assert [c.name for c in resp.tool_calls] == ["y"]


def test_openai_tool_call_id_pairing(monkeypatch):
    seen = {}
    message = SimpleNamespace(content="done", tool_calls=None)
    monkeypatch.setattr("openai.AsyncOpenAI", _openai_client_factory(seen, message))

    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"name": "list_missions", "arguments": {}},
        ]},
        {"role": "tool", "name": "list_missions", "result": {"missions": []}},
    ]
    adapter = OpenAICompatibleAdapter.for_provider("openai", api_key="k", model="gpt-5.6")
    run(adapter.generate(history, [], None))

    msgs = seen["messages"]
    call_id = msgs[1]["tool_calls"][0]["id"]
    assert msgs[2]["role"] == "tool"
    assert msgs[2]["tool_call_id"] == call_id


# --- Registry ---

def test_registry_known_pairs():
    assert get_capabilities("gemini", "gemini-3.1-flash-lite").supports_tool_calling is True
    assert get_capabilities("anthropic", "claude-sonnet-5").supports_tool_calling is True
    assert get_capabilities("openai", "gpt-5.6").supports_tool_calling is True
    assert get_capabilities("deepseek", "deepseek-chat").supports_tool_calling is True
    assert get_capabilities("kimi", "kimi-k3").supports_tool_calling is True


def test_registry_unknown_pair_returns_safe_default():
    caps = get_capabilities("nope", "nope-999")
    assert caps == ProviderCapabilities()
    assert caps.supports_tool_calling is False
