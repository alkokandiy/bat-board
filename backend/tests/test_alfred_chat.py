"""Tests for the in-app Alfred chat endpoint (LLM mocked)."""

from services import llm_provider
from services.llm_provider import LLMResponse, ToolCall
from services import telegram_service


def _mock_llm(monkeypatch, script):
    calls = []

    async def fake(messages, tools):
        calls.append((messages, tools))
        item = script[min(len(calls) - 1, len(script) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(llm_provider, "generate", fake)
    return calls


def test_alfred_chat_round_trip(client, auth_headers, monkeypatch):
    h = auth_headers("alfred_chat_user")
    calls = _mock_llm(monkeypatch, [
        LLMResponse(tool_calls=[ToolCall("create_mission", {"title": "Chat mission"})]),
        LLMResponse(text="Logged, sir."),
    ])

    r = client.post("/api/alfred/chat", json={"message": "add a mission"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == {"reply": "Logged, sir."}
    assert len(calls) == 2

    import models
    from database import SessionLocal

    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="alfred_chat_user").first()
        assert any(m.title == "Chat mission" for m in
                   db.query(models.BatMission).filter_by(owner_id=user.id).all())
        # Shared memory: turn stored, visible to Telegram-side history too.
        assert db.query(models.BatAlfredMessage).filter_by(owner_id=user.id).count() == 2
    finally:
        db.close()


def test_alfred_chat_unconfigured_without_key(client, auth_headers):
    h = auth_headers("alfred_chat_nokey")
    r = client.post("/api/alfred/chat", json={"message": "hello"}, headers=h)
    assert r.status_code == 200
    assert "isn't configured yet" in r.json()["reply"]


def test_alfred_chat_validation(client, auth_headers):
    h = auth_headers("alfred_chat_valid")
    assert client.post("/api/alfred/chat", json={"message": ""}, headers=h).status_code == 422
    assert client.post("/api/alfred/chat", json={}, headers=h).status_code == 422
    assert client.post("/api/alfred/chat", json={"message": "x" * 2001}, headers=h).status_code == 422
    # No auth → 401/403, never reaches the LLM.
    assert client.post("/api/alfred/chat", json={"message": "hi"}).status_code in (401, 403)


def test_alfred_chat_destructive_gate_over_chat(client, auth_headers, monkeypatch):
    h = auth_headers("alfred_chat_gate")
    note_id = client.post("/api/notes", json={"title": "Chat shred"}, headers=h).json()["id"]
    calls = _mock_llm(monkeypatch, [
        LLMResponse(tool_calls=[ToolCall("delete_note", {"note_id": note_id})]),
    ])

    r = client.post("/api/alfred/chat", json={"message": "delete it"}, headers=h)
    assert r.json()["reply"] == (
        "Delete the note 'Chat shred'? This can't be undone. Reply YES to confirm."
    )

    r = client.post("/api/alfred/chat", json={"message": "YES"}, headers=h)
    assert r.json()["reply"] == "Deleted 'Chat shred'."
    assert len(calls) == 1  # confirmation executed with zero additional LLM calls

    import models
    from database import SessionLocal

    db = SessionLocal()
    try:
        assert db.query(models.BatNote).filter_by(id=note_id).first() is None
    finally:
        db.close()
