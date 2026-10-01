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
