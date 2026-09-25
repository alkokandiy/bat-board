"""Tests for the in-app Alfred chat endpoint (LLM mocked)."""

from services import alfred_agent, llm_provider
from services.llm_provider import LLMResponse, ToolCall
from services import telegram_service


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


def _create_session(client, headers, title="Test session"):
    """Helper: create an Alfred session and return its id."""
    r = client.post("/api/alfred/sessions", json={"title": title}, headers=headers)
    return r.json()["id"]


def test_alfred_chat_round_trip(client, auth_headers, monkeypatch):
    h = auth_headers("alfred_chat_user")
    session_id = _create_session(client, h, "Chat test")
    calls = _mock_llm(monkeypatch, [
        LLMResponse(tool_calls=[ToolCall("create_mission", {"title": "Chat mission"})]),
        LLMResponse(text="Logged, sir."),
    ])

    r = client.post("/api/alfred/chat", json={"message": "add a mission", "session_id": session_id}, headers=h)
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
        # Shared memory: turn stored in the session.
        assert db.query(models.BatAlfredMessage).filter_by(session_id=session_id).count() == 2
    finally:
        db.close()


def test_alfred_chat_no_provider_setup_reply(client, auth_headers):
    h = auth_headers("alfred_chat_noconfig")
    # Remove the autouse dummy config → truly unconfigured user.
    from database import SessionLocal
    import models
    from services import provider_config_service

    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="alfred_chat_noconfig").first()
        provider_config_service.delete_config(db, user)
    finally:
        db.close()

    session_id = _create_session(client, h, "Noconfig test")
    r = client.post("/api/alfred/chat", json={"message": "hello", "session_id": session_id}, headers=h)
    assert r.status_code == 200
    assert "isn't connected to a model" in r.json()["reply"]


def test_alfred_chat_validation(client, auth_headers):
    h = auth_headers("alfred_chat_valid")
    session_id = _create_session(client, h, "Validation test")
    assert client.post("/api/alfred/chat", json={"message": "", "session_id": session_id}, headers=h).status_code == 422
    assert client.post("/api/alfred/chat", json={}, headers=h).status_code == 422
    assert client.post("/api/alfred/chat", json={"message": "x" * 2001, "session_id": session_id}, headers=h).status_code == 422
    # No auth → 401/403, never reaches the LLM.
    assert client.post("/api/alfred/chat", json={"message": "hi", "session_id": session_id}).status_code in (401, 403)
    # Missing session_id → 422
    assert client.post("/api/alfred/chat", json={"message": "hi"}, headers=h).status_code == 422


def test_alfred_chat_destructive_gate_over_chat(client, auth_headers, monkeypatch):
    h = auth_headers("alfred_chat_gate")
    session_id = _create_session(client, h, "Gate test")
    note_id = client.post("/api/notes", json={"title": "Chat shred"}, headers=h).json()["id"]
    calls = _mock_llm(monkeypatch, [
        LLMResponse(tool_calls=[ToolCall("delete_note", {"note_id": note_id})]),
    ])

    r = client.post("/api/alfred/chat", json={"message": "delete it", "session_id": session_id}, headers=h)
    assert r.json()["reply"] == (
        "Delete the note 'Chat shred'? This can't be undone. Reply YES to confirm."
    )

    r = client.post("/api/alfred/chat", json={"message": "YES", "session_id": session_id}, headers=h)
    assert r.json()["reply"] == "Deleted 'Chat shred'."
    assert len(calls) == 1  # confirmation executed with zero additional LLM calls

    import models
    from database import SessionLocal

    db = SessionLocal()
    try:
        assert db.query(models.BatNote).filter_by(id=note_id).first() is None
    finally:
        db.close()
