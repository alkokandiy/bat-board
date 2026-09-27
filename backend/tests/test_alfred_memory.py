"""Batch C tests: Alfred's self-managed memory (tools mocked at adapter seam)."""

import models
from database import SessionLocal
from services import alfred_agent
from services.alfred_tools import execute_tool
from services.llm_provider import LLMResponse, ToolCall

_next_update_id = [9600]
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


def _user(username):
    db = _db()
    try:
        return db.query(models.BatAccount).filter_by(username=username).first()
    finally:
        db.close()


def _mock_send(monkeypatch):
    from services import telegram_service

    sent = []
    monkeypatch.setattr(
        telegram_service, "send_telegram_message", lambda *a, **kw: sent.append((a, kw)) or True
    )
    return sent


def _link_chat(client, headers, chat_id):
    code = client.post("/api/account/telegram-link/generate-code", headers=headers).json()["code"]
    client.post("/api/telegram/webhook", json=_update(chat_id, code), headers=_headers())


def _mock_llm(monkeypatch, script):
    calls = []

    class FakeAdapter:
        async def generate(self, messages, tools, system_instruction=None):
            calls.append((messages, tools, system_instruction))
            item = script[min(len(calls) - 1, len(script) - 1)]
            if isinstance(item, Exception):
                raise item
            return item

    monkeypatch.setattr(alfred_agent, "resolve_adapter_for_user", lambda db, user: FakeAdapter())
    return calls


def _exec(username, tool_name, args):
    db = _db()
    try:
        user = db.query(models.BatAccount).filter_by(username=username).first()
        return execute_tool(db, user, tool_name, args), user.id
    finally:
        db.close()


def test_remember_upserts_same_title(client, auth_headers):
    auth_headers("mem_upsert")

    first, _ = _exec("mem_upsert", "alfred_remember", {"title": "Coffee", "content": "Oat flat white."})
    assert first["updated"] is False

    second, owner_id = _exec("mem_upsert", "alfred_remember", {"title": "Coffee", "content": "Espresso now."})
    assert second["updated"] is True
    assert second["note"]["id"] == first["note"]["id"]

    db = _db()
    try:
        rows = db.query(models.BatNote).filter_by(owner_id=owner_id, title="Coffee").all()
        assert len(rows) == 1
        assert rows[0].body == "Espresso now."
        assert "alfred-memory" in (rows[0].tags or "")
    finally:
        db.close()


def test_recall_never_leaks_user_notes(client, auth_headers):
    h = auth_headers("mem_scope")
    # User's OWN note containing the query word — must never surface.
    client.post("/api/notes", json={"title": "Private", "body": "my secret peanut recipe"}, headers=h)

    _exec("mem_scope", "alfred_remember", {"title": "Snacks", "content": "peanuts at the study desk"})

    result, _ = _exec("mem_scope", "alfred_recall", {"query": "peanut"})
    titles = [m["title"] for m in result["memories"]]
    assert titles == ["Snacks"]
    assert all("body" in m for m in result["memories"])


def test_list_topics_titles_only_no_bodies(client, auth_headers):
    auth_headers("mem_topics")
    _exec("mem_topics", "alfred_remember", {"title": "Tea", "content": "Earl Grey, one sugar. Very particular."})

    result, _ = _exec("mem_topics", "alfred_list_memory_topics", {})
    assert len(result["topics"]) == 1
    topic = result["topics"][0]
    assert topic["title"] == "Tea"
    assert "body" not in topic
    assert "Earl Grey" in topic["description"]


def test_legacy_profile_note_discoverable_after_tag(client, auth_headers):
    """Post-migration end state: legacy title + alfred-memory tag → recall finds it."""
    from services import notes_service

    h = auth_headers("mem_legacy")
    note_id = client.post(
        "/api/notes", json={"title": "Alfred Context — Master Profile", "body": "seed profile"},
        headers=h,
    ).json()["id"]

    db = _db()
    try:
        user = db.query(models.BatAccount).filter_by(username="mem_legacy").first()
        notes_service.update_note(db, user, note_id, tags="alfred-memory")
    finally:
        db.close()

    result, _ = _exec("mem_legacy", "alfred_recall", {"query": "profile"})
    assert [m["title"] for m in result["memories"]] == ["Alfred Context — Master Profile"]
    assert result["memories"][0]["body"] == "seed profile"


def test_full_conversation_remember_then_recall(client, auth_headers, monkeypatch):
    h = auth_headers("mem_conv")
    sent = _mock_send(monkeypatch)
    _link_chat(client, h, "mem-conv")

    calls = _mock_llm(monkeypatch, [
        LLMResponse(tool_calls=[ToolCall("alfred_remember", {
            "title": "Brother", "content": "Master's brother is named Thomas."})]),
        LLMResponse(text="Noted, sir."),
        LLMResponse(tool_calls=[ToolCall("alfred_list_memory_topics", {})]),
        LLMResponse(tool_calls=[ToolCall("alfred_recall", {"query": "brother"})]),
        LLMResponse(text="Your brother is named Thomas, sir."),
    ])
    client.post("/api/telegram/webhook", json=_update("mem-conv", "My brother's name is Thomas"), headers=_headers())
    client.post("/api/telegram/webhook", json=_update("mem-conv", "What's my brother's name?"), headers=_headers())

    assert len(calls) == 5
    # The recall result actually reached the model before the final reply.
    recall_result = calls[3][0][-1]
    assert recall_result["role"] == "tool"
    assert "Thomas" in str(recall_result["result"])
    assert "Thomas" in sent[-1][0][2]
