"""Regression tests for the 2026-10-01 whole-project audit.

Each test pins one confirmed defect: it failed (or crashed) before the fix.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from google.genai import types

import models
from database import SessionLocal
from services import alfred_agent, telegram_service
from services.llm_provider import LLMResponse, ToolCall


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _points(client, h):
    return client.get("/api/account", headers=h).json()["points"]


def _backdate_focus(session_id, minutes):
    db = SessionLocal()
    try:
        s = db.query(models.BatFocus).filter_by(id=session_id).first()
        s.start_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        db.commit()
    finally:
        db.close()


# --- Security ---------------------------------------------------------------

def test_spa_route_does_not_serve_files_outside_dist(client):
    for path in ("/..%2f..%2fbackend%2fconfig.py", "/..%2f..%2f..%2fetc%2fpasswd"):
        r = client.get(path)
        assert "SECRET_KEY" not in r.text and "root:" not in r.text


def test_points_cannot_be_set_by_the_client(client, auth_headers):
    h = auth_headers("audit_points")
    before = _points(client, h)
    r = client.put("/api/account", headers=h, json={"points_delta": 99999})
    assert r.status_code == 200
    assert _points(client, h) == before


def test_token_follows_account_id_not_username(client, auth_headers):
    """A token must not authenticate whoever registers the old username."""
    client.post("/api/auth/register", json={"username": "audit_renamer", "password": "pass12345"})
    tokens = client.post(
        "/api/auth/login", data={"username": "audit_renamer", "password": "pass12345"}
    ).json()
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = client.get("/api/auth/me", headers=h).json()

    assert client.put("/api/account", headers=h, json={"username": "audit_renamed"}).status_code == 200
    client.post("/api/auth/register", json={"username": "audit_renamer", "password": "pass12345"})

    # Same token: still the original (renamed) account, not the newcomer.
    after = client.get("/api/auth/me", headers=h).json()
    assert after["id"] == me["id"]
    assert after["username"] == "audit_renamed"
    refreshed = client.post("/api/auth/refresh", json=tokens["refresh_token"])
    assert refreshed.status_code == 200


def test_password_rules_apply_to_change_password(client, auth_headers):
    h = auth_headers("audit_pw")
    r = client.put(
        "/api/account/password", headers=h,
        json={"current_password": "pass1234", "new_password": "x"},
    )
    assert r.status_code == 422


def test_rate_limit_key_uses_proxy_appended_ip():
    from dependencies import client_ip

    req = SimpleNamespace(
        headers={"x-forwarded-for": "1.1.1.1, 203.0.113.9"},
        client=SimpleNamespace(host="10.0.0.2"),
    )
    assert client_ip(req) == "203.0.113.9"
    req = SimpleNamespace(headers={}, client=SimpleNamespace(host="10.0.0.2"))
    assert client_ip(req) == "10.0.0.2"


# --- Points / focus / missions / habits --------------------------------------

def test_end_focus_without_duration_uses_wall_clock(client, auth_headers):
    h = auth_headers("audit_focus_clock")
    s = client.post("/api/focus/sessions", headers=h, json={}).json()
    _backdate_focus(s["id"], 12)
    r = client.put(f"/api/focus/sessions/{s['id']}", headers=h, json={})
    assert r.status_code == 200, r.text
    assert r.json()["duration_minutes"] == 12


def test_focus_end_is_idempotent_and_capped(client, auth_headers):
    h = auth_headers("audit_focus_cap")
    s = client.post("/api/focus/sessions", headers=h, json={}).json()
    _backdate_focus(s["id"], 30)
    before = _points(client, h)

    r = client.put(f"/api/focus/sessions/{s['id']}", headers=h, json={"duration_minutes": 100000})
    assert r.json()["duration_minutes"] <= 31
    credited = _points(client, h) - before
    assert 30 <= credited <= 31

    client.put(f"/api/focus/sessions/{s['id']}", headers=h, json={"duration_minutes": 25})
    assert _points(client, h) - before == credited


def test_reopening_a_mission_takes_back_its_reward(client, auth_headers):
    h = auth_headers("audit_reopen")
    m = client.post("/api/missions", headers=h, json={"title": "farm", "priority": "critical"}).json()
    before = _points(client, h)
    for _ in range(3):
        client.put(f"/api/missions/{m['id']}", headers=h, json={"status": "completed"})
        client.put(f"/api/missions/{m['id']}", headers=h, json={"status": "pending"})
    assert _points(client, h) == before
    client.put(f"/api/missions/{m['id']}", headers=h, json={"status": "completed"})
    assert _points(client, h) == before + 50


def test_null_on_required_mission_field_is_ignored(client, auth_headers):
    h = auth_headers("audit_null")
    m = client.post("/api/missions", headers=h, json={"title": "keep me"}).json()
    r = client.put(f"/api/missions/{m['id']}", headers=h, json={"title": None, "priority": None})
    assert r.status_code == 200
    assert r.json()["title"] == "keep me"


def test_weekly_habit_streak_continues_week_to_week(client, auth_headers):
    h = auth_headers("audit_weekly")
    habit = client.post("/api/habits", headers=h, json={"name": "review", "frequency": "weekly"}).json()
    db = SessionLocal()
    try:
        row = db.query(models.BatHabit).filter_by(id=habit["id"]).first()
        row.last_completed = datetime.now(timezone.utc) - timedelta(days=7)
        row.streak = 3
        db.commit()
    finally:
        db.close()

    first = client.post(f"/api/habits/{habit['id']}/check-in", headers=h).json()
    assert first["streak"] == 4
    before = _points(client, h)
    again = client.post(f"/api/habits/{habit['id']}/check-in", headers=h).json()
    assert again["streak"] == 4
    assert _points(client, h) == before  # same week: no second reward


# --- Timestamps ---------------------------------------------------------------

def test_timestamps_round_trip_as_utc_with_offset(client, auth_headers):
    h = auth_headers("audit_tz")
    r = client.post("/api/calendar/events", headers=h, json={
        "title": "standup", "start_time": "2026-10-05T14:00:00+05:00",
    })
    assert r.status_code == 201, r.text
    start = datetime.fromisoformat(r.json()["start_time"])
    assert start.utcoffset() == timedelta(0)
    assert start == datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)
    listed = client.get("/api/calendar/events", headers=h).json()
    assert any(datetime.fromisoformat(e["start_time"]) == start for e in listed)


# --- Alfred tool loop -----------------------------------------------------------

def _mock_llm(monkeypatch, script):
    calls = []

    class FakeAdapter:
        async def generate(self, messages, tools, system_instruction=None):
            calls.append([dict(m) for m in messages])
            return script[min(len(calls) - 1, len(script) - 1)]

    monkeypatch.setattr(alfred_agent, "resolve_adapter_for_user", lambda db, user: FakeAdapter())
    return calls


def _chat(client, h, text):
    sid = client.post("/api/alfred/sessions", json={"title": "t"}, headers=h).json()["id"]
    return client.post("/api/alfred/chat", json={"message": text, "session_id": sid}, headers=h)


def test_parallel_tool_calls_replay_as_one_assistant_turn(client, auth_headers, monkeypatch):
    h = auth_headers("audit_parallel")
    calls = _mock_llm(monkeypatch, [
        LLMResponse(tool_calls=[
            ToolCall("create_mission", {"title": "A"}, thought_signature=b"sig"),
            ToolCall("create_mission", {"title": "B"}),
        ]),
        LLMResponse(text="Both logged."),
    ])
    r = _chat(client, h, "two missions")
    assert r.json()["reply"] == "Both logged."

    replay = calls[1]
    assistant_turns = [m for m in replay if m["role"] == "assistant" and m.get("tool_calls")]
    assert len(assistant_turns) == 1
    assert [c["name"] for c in assistant_turns[0]["tool_calls"]] == ["create_mission"] * 2
    assert assistant_turns[0]["tool_calls"][0]["thought_signature"] == b"sig"
    assert [m["role"] for m in replay[-3:]] == ["assistant", "tool", "tool"]


def test_unknown_tool_spam_is_bounded(client, auth_headers, monkeypatch):
    h = auth_headers("audit_spin")
    calls = _mock_llm(monkeypatch, [LLMResponse(tool_calls=[ToolCall("no_such_tool", {})])])
    r = _chat(client, h, "go")
    assert r.status_code == 200
    assert len(calls) == alfred_agent.MAX_MODEL_CALLS_PER_TURN


def test_bad_tool_arguments_are_reported_not_fatal(client, auth_headers, monkeypatch):
    h = auth_headers("audit_badargs")
    calls = _mock_llm(monkeypatch, [
        LLMResponse(tool_calls=[ToolCall("create_mission", {})]),  # missing title
        LLMResponse(text="Which title, sir?"),
    ])
    r = _chat(client, h, "add one")
    assert r.json()["reply"] == "Which title, sir?"
    assert "error" in calls[1][-1]["result"]


def test_gemini_replays_parallel_calls_in_one_model_turn():
    from services.llm_providers.gemini import _to_gemini_content

    contents = _to_gemini_content({"role": "assistant", "content": None, "tool_calls": [
        {"name": "create_mission", "arguments": {"title": "A"}, "thought_signature": b"sig"},
        {"name": "create_mission", "arguments": {"title": "B"}, "thought_signature": None},
    ]})
    assert len(contents) == 1 and contents[0].role == "model"
    parts = contents[0].parts
    assert [p.function_call.name for p in parts] == ["create_mission", "create_mission"]
    assert parts[0].thought_signature == b"sig"
    assert isinstance(parts[0], types.Part)


def test_anthropic_groups_parallel_tool_results(monkeypatch):
    from services.llm_providers.anthropic_adapter import _to_anthropic_messages

    out = _to_anthropic_messages([
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"name": "a", "arguments": {}}, {"name": "b", "arguments": {}},
        ]},
        {"role": "tool", "name": "a", "result": {}},
        {"role": "tool", "name": "b", "result": {}},
    ])
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    ids = [b["id"] for b in out[1]["content"]]
    assert [b["tool_use_id"] for b in out[2]["content"]] == ids


# --- Telegram ---------------------------------------------------------------------

def test_long_telegram_replies_are_split(monkeypatch):
    sent = []
    monkeypatch.setattr(
        telegram_service, "_send_one",
        lambda token, chat, text, timeout, markup: sent.append((text, markup)) or True,
    )
    text = ("word " * 2000).strip()
    assert telegram_service.send_telegram_message("t", "1", text, reply_markup={"k": 1})
    assert len(sent) == 3
    assert all(len(t) <= 4096 for t, _ in sent)
    assert " ".join(t for t, _ in sent) == text
    assert [m for _, m in sent] == [None, None, {"k": 1}]


def test_relinking_an_already_linked_chat(client, auth_headers):
    first = auth_headers("audit_link_a")
    second = auth_headers("audit_link_b")
    db = SessionLocal()
    try:
        for h in (first, second):
            code = client.post("/api/account/telegram-link/generate-code", headers=h).json()["code"]
            user = telegram_service.exchange_link_code(db, code, "relink-chat")
            assert user is not None
    finally:
        db.close()
    assert client.get("/api/account/telegram-link/status", headers=second).json()["linked"]
    assert not client.get("/api/account/telegram-link/status", headers=first).json()["linked"]


# --- Multi-user hardening (migration 011) -----------------------------------------

def _set_tz(client, h, tz):
    r = client.put("/api/account", headers=h, json={"timezone": tz})
    assert r.status_code == 200, r.text
    return r


def test_timezone_is_validated_and_returned(client, auth_headers):
    h = auth_headers("audit_tz_setting")
    assert client.put("/api/account", headers=h, json={"timezone": "Mars/Olympus"}).status_code == 422
    _set_tz(client, h, "America/New_York")
    assert client.get("/api/auth/me", headers=h).json()["timezone"] == "America/New_York"


def test_register_stores_browser_timezone(client):
    r = client.post("/api/auth/register", json={
        "username": "audit_tz_signup", "password": "pass12345", "timezone": "Asia/Tashkent",
    })
    assert r.status_code == 201, r.text
    assert r.json()["timezone"] == "Asia/Tashkent"


def test_daily_habit_day_follows_user_timezone(client, auth_headers):
    """A check-in at 01:00 local (20:00 UTC the day before) is a new local day."""
    from services import habit_service
    from zoneinfo import ZoneInfo

    h = auth_headers("audit_tz_habit")
    _set_tz(client, h, "Asia/Tashkent")
    habit = client.post("/api/habits", headers=h, json={"name": "read"}).json()

    tz = ZoneInfo("Asia/Tashkent")
    local_now = datetime.now(tz)
    yesterday_evening = (local_now - timedelta(days=1)).replace(hour=23, minute=0)
    db = SessionLocal()
    try:
        row = db.query(models.BatHabit).filter_by(id=habit["id"]).first()
        row.last_completed = yesterday_evening.astimezone(timezone.utc)
        row.streak = 2
        db.commit()
        user = db.query(models.BatAccount).filter_by(username="audit_tz_habit").first()
        result = habit_service.check_in_habit(db, user, habit["id"])
        assert result.streak == 3
    finally:
        db.close()


def test_password_change_signs_out_other_sessions(client):
    client.post("/api/auth/register", json={"username": "audit_pw_revoke", "password": "pass12345"})
    login = lambda: client.post(
        "/api/auth/login", data={"username": "audit_pw_revoke", "password": "pass12345"}
    ).json()
    laptop, phone = login(), login()
    laptop_h = {"Authorization": f"Bearer {laptop['access_token']}"}

    r = client.put("/api/account/password", headers=laptop_h, json={
        "current_password": "pass12345", "new_password": "new-pass-6789",
    })
    assert r.status_code == 200, r.text
    fresh = {"Authorization": f"Bearer {r.json()['access_token']}"}

    assert client.get("/api/auth/me", headers=fresh).status_code == 200
    assert client.get("/api/auth/me", headers=laptop_h).status_code == 401
    phone_h = {"Authorization": f"Bearer {phone['access_token']}"}
    assert client.get("/api/auth/me", headers=phone_h).status_code == 401
    assert client.post("/api/auth/refresh", json=phone["refresh_token"]).status_code == 401


def test_link_code_guessing_is_throttled_per_chat(client, monkeypatch):
    from routers.telegram import LINK_THROTTLED_REPLY, process_telegram_update

    sent = []
    monkeypatch.setattr(telegram_service, "send_telegram_message", lambda *a, **kw: sent.append(a[2]) or True)

    def send(text):
        _run(process_telegram_update(
            {"message": {"message_id": 1, "chat": {"id": 777001}, "text": text}}, None,
        ))

    for i in range(telegram_service.LINK_MAX_FAILURES):
        send(f"{i:06d}")
    assert LINK_THROTTLED_REPLY not in sent
    send("999999")
    assert sent[-1] == LINK_THROTTLED_REPLY


def test_linked_user_sending_digits_reaches_alfred(client, auth_headers, monkeypatch):
    from routers.telegram import UNLINKED_REPLY, process_telegram_update

    h = auth_headers("audit_digits")
    db = SessionLocal()
    try:
        code = client.post("/api/account/telegram-link/generate-code", headers=h).json()["code"]
        assert telegram_service.exchange_link_code(db, code, "777002")
    finally:
        db.close()
    sent = []
    monkeypatch.setattr(telegram_service, "send_telegram_message", lambda *a, **kw: sent.append(a[2]) or True)
    _mock_llm(monkeypatch, [LLMResponse(text="Noted: 123456.")])

    class _Tasks:
        def add_task(self, *a, **kw):
            pass

    _run(process_telegram_update(
        {"message": {"message_id": 2, "chat": {"id": 777002}, "text": "123456"}}, _Tasks(),
    ))
    assert sent == ["Noted: 123456."]
    assert UNLINKED_REPLY not in sent


def test_usage_quota_is_one_row_and_capped(auth_headers, monkeypatch):
    auth_headers("audit_quota")
    monkeypatch.setattr(alfred_agent, "DAILY_MESSAGE_CAP", 3)
    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="audit_quota").first()
        results = [alfred_agent.check_usage(db, user) for _ in range(5)]
        assert results == [True, True, True, False, False]
        rows = db.query(models.BatAlfredUsage).filter_by(owner_id=user.id).all()
        assert len(rows) == 1 and rows[0].count == 3
    finally:
        db.close()


def test_usage_table_rejects_duplicate_day_rows(auth_headers):
    import pytest
    from sqlalchemy.exc import IntegrityError

    auth_headers("audit_quota_dupe")
    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="audit_quota_dupe").first()
        db.add(models.BatAlfredUsage(owner_id=user.id, day="2026-01-01", count=1))
        db.commit()
        db.add(models.BatAlfredUsage(owner_id=user.id, day="2026-01-01", count=1))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.close()


def test_placeholder_secrets_are_rejected_outside_development(monkeypatch):
    import pytest
    from config import Settings

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "set-this-to-a-random-64-char-string-in-railway")
    with pytest.raises(Exception, match="SECRET_KEY"):
        Settings()


# --- Alfred form of address (migration 012) -----------------------------------------

def _system_prompt_for(client, h, monkeypatch):
    calls = _mock_llm(monkeypatch, [LLMResponse(text="At your service.")])
    _chat(client, h, "hello")
    return calls[0][0]["content"]


def test_alfred_addresses_each_user_by_their_own_name(client, auth_headers, monkeypatch):
    a = auth_headers("audit_addr_bruce")
    b = auth_headers("audit_addr_selina")
    assert client.put("/api/account", headers=a, json={"alfred_address": "Master Wayne"}).status_code == 200

    prompt_a = _system_prompt_for(client, a, monkeypatch)
    prompt_b = _system_prompt_for(client, b, monkeypatch)
    assert '"Master Wayne"' in prompt_a
    assert '"audit_addr_selina"' in prompt_b  # default: username
    for prompt in (prompt_a, prompt_b):
        assert "Al-Kokandiy" not in prompt
        assert " his " not in prompt and "himself" not in prompt


def test_alfred_address_validation_and_reset(client, auth_headers):
    h = auth_headers("audit_addr_rules")
    assert client.put("/api/account", headers=h, json={"alfred_address": "x" * 61}).status_code == 422
    # Line breaks can't reach the prompt: whitespace is collapsed to single spaces.
    r = client.put("/api/account", headers=h, json={"alfred_address": "Master\nWayne\tsir"})
    assert r.json()["alfred_address"] == "Master Wayne sir"
    assert client.put("/api/account", headers=h, json={"alfred_address": "a\x00b"}).status_code == 422
    r = client.put("/api/account", headers=h, json={"alfred_address": "  Miss   Kyle "})
    assert r.json()["alfred_address"] == "Miss Kyle"
    r = client.put("/api/account", headers=h, json={"alfred_address": ""})
    assert r.json()["alfred_address"] is None


# --- Conversation management / reset -----------------------------------------------

def _new_session(client, h, title="t"):
    return client.post("/api/alfred/sessions", json={"title": title}, headers=h).json()["id"]


def test_rename_and_delete_conversation(client, auth_headers, monkeypatch):
    h = auth_headers("audit_chats")
    _mock_llm(monkeypatch, [LLMResponse(text="Hello.")])
    sid = _new_session(client, h)
    client.post("/api/alfred/chat", json={"message": "hi", "session_id": sid}, headers=h)

    r = client.patch(f"/api/alfred/sessions/{sid}", json={"title": "Gotham plans"}, headers=h)
    assert r.status_code == 200 and r.json()["title"] == "Gotham plans"
    assert client.patch(f"/api/alfred/sessions/{sid}", json={"title": "   "}, headers=h).status_code == 422

    assert client.delete(f"/api/alfred/sessions/{sid}", headers=h).status_code == 204
    assert sid not in [s["id"] for s in client.get("/api/alfred/sessions", headers=h).json()]
    assert client.get(f"/api/alfred/sessions/{sid}/messages", headers=h).status_code == 404
    db = SessionLocal()
    try:
        assert db.query(models.BatAlfredMessage).filter_by(session_id=sid).count() == 0
    finally:
        db.close()


def test_conversations_are_owner_scoped(client, auth_headers):
    owner = auth_headers("audit_chats_owner")
    other = auth_headers("audit_chats_other")
    sid = _new_session(client, owner)
    assert client.delete(f"/api/alfred/sessions/{sid}", headers=other).status_code == 404
    assert client.patch(f"/api/alfred/sessions/{sid}", json={"title": "x"}, headers=other).status_code == 404
    assert client.post("/api/alfred/reset", json={"erase_memory": True}, headers=other).status_code == 200
    assert sid in [s["id"] for s in client.get("/api/alfred/sessions", headers=owner).json()]


def test_deleting_active_session_starts_fresh_on_telegram(client, auth_headers):
    h = auth_headers("audit_chats_active")
    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="audit_chats_active").first()
        session = alfred_agent.create_session(db, user, "active")
        alfred_agent.set_active_session(db, user, session.id)
        sid = session.id
    finally:
        db.close()
    client.delete(f"/api/alfred/sessions/{sid}", headers=h)
    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="audit_chats_active").first()
        assert user.active_alfred_session_id is None
    finally:
        db.close()


def test_reset_alfred_keeps_key_and_user_notes(client, auth_headers, monkeypatch):
    h = auth_headers("audit_reset")
    _mock_llm(monkeypatch, [
        LLMResponse(tool_calls=[ToolCall("alfred_remember", {"title": "Coffee", "content": "Black."})]),
        LLMResponse(text="Noted."),
    ])
    sid = _new_session(client, h)
    client.post("/api/alfred/chat", json={"message": "I take coffee black", "session_id": sid}, headers=h)
    own_note = client.post("/api/notes", json={"title": "My own note"}, headers=h).json()

    r = client.post("/api/alfred/reset", json={}, headers=h)
    assert r.status_code == 200
    assert r.json()["sessions"] >= 1 and r.json()["messages"] >= 2 and r.json()["memory_notes"] == 0
    assert client.get("/api/alfred/sessions", headers=h).json() == []
    titles = [n["title"] for n in client.get("/api/notes", headers=h).json()]
    assert "Coffee" in titles and "My own note" in titles  # memory kept unless asked

    r = client.post("/api/alfred/reset", json={"erase_memory": True}, headers=h)
    assert r.json()["memory_notes"] == 1
    titles = [n["title"] for n in client.get("/api/notes", headers=h).json()]
    assert "Coffee" not in titles and own_note["title"] in titles
    assert client.get("/api/alfred/provider", headers=h).json()["configured"] is True
