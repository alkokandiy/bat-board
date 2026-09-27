"""Background memory-reviewer tests (reviewer LLM mocked at adapter seam)."""

import asyncio
import time

import models
from database import SessionLocal
from services import alfred_agent, alfred_memory_reviewer
from services.alfred_memory_reviewer import schedule_memory_review as _real_schedule
from services.llm_provider import LLMResponse, ToolCall
_next_update_id = [9700]
SECRET_HEADER = {"X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret-12345"}


def _update(chat_id, text):
    _next_update_id[0] += 1
    return {
        "update_id": _next_update_id[0],
        "message": {"message_id": 1, "chat": {"id": chat_id}, "text": text},
    }


def _headers():
    return SECRET_HEADER


def _db():
    return SessionLocal()


def _mock_send(monkeypatch, order=None):
    from services import telegram_service

    def _send(*a, **kw):
        if order is not None:
            order.append("send")
        return True

    monkeypatch.setattr(telegram_service, "send_telegram_message", _send)
    return _send


def _link_chat(client, headers, chat_id):
    code = client.post("/api/account/telegram-link/generate-code", headers=headers).json()["code"]
    client.post("/api/telegram/webhook", json=_update(chat_id, code), headers=_headers())


def _fake_resolve(monkeypatch, script):
    """Scripted reviewer adapter. Returns (calls, tools_seen)."""
    calls = []
    seen_tools = []

    class FakeAdapter:
        async def generate(self, messages, tools, system_instruction=None):
            calls.append((messages, tools, system_instruction))
            seen_tools.extend(t["name"] for t in tools)
            item = script[min(len(calls) - 1, len(script) - 1)]
            if isinstance(item, Exception):
                raise item
            return item

    monkeypatch.setattr(alfred_agent, "resolve_adapter_for_user", lambda db, user: FakeAdapter())
    return calls, seen_tools


def _review(username, user_msg, reply):
    db = _db()
    try:
        user = db.query(models.BatAccount).filter_by(username=username).first()
        return asyncio.get_event_loop().run_until_complete(
            alfred_memory_reviewer.review_and_remember(db, user, user_msg, reply)
        )
    finally:
        db.close()


def _memory_notes(username):
    db = _db()
    try:
        user = db.query(models.BatAccount).filter_by(username=username).first()
        return db.query(models.BatNote).filter(
            models.BatNote.owner_id == user.id,
            models.BatNote.tags.ilike("%alfred-memory%"),
        ).all()
    finally:
        db.close()


def test_small_talk_writes_nothing(client, auth_headers, monkeypatch):
    auth_headers("rev_small")
    calls, _ = _fake_resolve(monkeypatch, [LLMResponse(text="nothing durable here")])

    assert _review("rev_small", "hey", "Hello, sir.") is None
    assert len(calls) == 1  # reviewer ran...
    assert _memory_notes("rev_small") == []  # ...and filed nothing


def test_durable_fact_gets_filed(client, auth_headers, monkeypatch):
    auth_headers("rev_fact")
    _fake_resolve(monkeypatch, [
        LLMResponse(tool_calls=[ToolCall("alfred_remember", {
            "title": "New Job", "content": "Started at X."})]),
    ])

    assert _review("rev_fact", "I just started a new job at X", "Congrats, sir.") is None

    notes = _memory_notes("rev_fact")
    assert len(notes) == 1
    assert notes[0].title == "New Job" and "X" in (notes[0].body or "")


def test_known_fact_updates_never_duplicates(client, auth_headers, monkeypatch):
    from services.alfred_tools import execute_tool

    auth_headers("rev_known")
    db = _db()
    try:
        user = db.query(models.BatAccount).filter_by(username="rev_known").first()
        execute_tool(db, user, "alfred_remember", {"title": "Running", "content": "5k twice a week."})
    finally:
        db.close()

    _fake_resolve(monkeypatch, [
        LLMResponse(tool_calls=[ToolCall("alfred_remember", {
            "title": "Running", "content": "5k twice a week, plus Sunday long run."})]),
    ])
    assert _review("rev_known", "I added a Sunday long run", "Noted, sir.") is None

    notes = _memory_notes("rev_known")
    assert [n.title for n in notes] == ["Running"]
    assert "Sunday long run" in notes[0].body


def test_reviewer_only_tool_is_remember(client, auth_headers, monkeypatch):
    auth_headers("rev_scope")
    _, seen_tools = _fake_resolve(monkeypatch, [
        LLMResponse(tool_calls=[ToolCall("create_mission", {"title": "HACK"})]),
    ])

    assert _review("rev_scope", "do something", "No.") is None
    assert seen_tools == ["alfred_remember"]

    db = _db()
    try:
        user = db.query(models.BatAccount).filter_by(username="rev_scope").first()
        assert db.query(models.BatMission).filter_by(owner_id=user.id).count() == 0
    finally:
        db.close()


def test_reviewer_failure_never_surfaces(client, auth_headers, monkeypatch):
    auth_headers("rev_fail")
    _fake_resolve(monkeypatch, [RuntimeError("boom")])

    # Must return normally — the user's already-sent reply is unaffected.
    assert _review("rev_fail", "anything", "Some reply.") is None
    assert _memory_notes("rev_fail") == []


def test_reply_sent_before_review_scheduled(client, auth_headers, monkeypatch):
    """Real scheduler + mocked worker: reply send precedes review execution."""
    from services import alfred_memory_reviewer as reviewer_mod

    h = auth_headers("rev_order")
    order = []
    _mock_send(monkeypatch, order)
    _link_chat(client, h, "rev-order")

    class FakeAdapter:
        async def generate(self, messages, tools, system_instruction=None):
            return LLMResponse(text="Live reply, sir.")

    monkeypatch.setattr(alfred_agent, "resolve_adapter_for_user", lambda db, user: FakeAdapter())
    # Real scheduler, mocked worker.
    monkeypatch.setattr(reviewer_mod, "schedule_memory_review", _real_schedule)

    async def fake_review(db, user, user_message, assistant_reply):
        order.append("review")

    monkeypatch.setattr(reviewer_mod, "review_and_remember", fake_review)

    client.post("/api/telegram/webhook", json=_update("rev-order", "hello?"), headers=_headers())
    assert order[0] == "send"
    assert "review" in order
    assert order.index("send") < order.index("review")


def test_scheduling_adds_no_latency(client, auth_headers, monkeypatch):
    """Scheduling is a list-append done after the reply exists — instant."""
    from types import SimpleNamespace

    stub = SimpleNamespace(tasks=[], add_task=lambda *a, **kw: stub.tasks.append((a, kw)))
    t0 = time.monotonic()
    _real_schedule(stub, 1, "hi", "hello")
    elapsed = time.monotonic() - t0
    assert elapsed < 1.0, f"scheduling took {elapsed:.2f}s"
    assert len(stub.tasks) == 1  # queued, not run
