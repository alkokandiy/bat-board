"""Timed focus sessions: start with planned_minutes, stop by lookup, and the
cron auto-ending + Telegram ping."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

import models
from database import SessionLocal
from services import alfred_tools, focus_service, scheduler

_n = [600000]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _chat_of(uid):
    db = SessionLocal()
    try:
        row = (db.query(models.BatPersonalAccessToken)
               .filter_by(owner_id=uid, revoked=False).first())
        return row.telegram_chat_id if row else None
    finally:
        db.close()


def _mine(sink, uid):
    """Only the messages sent to THIS test's user. run_tick serves every linked
    account, so a shared sink also catches other tests' users."""
    cid = _chat_of(uid)
    return [text for (chat_id, text) in sink if chat_id == cid]


def _mk_user(linked=True):
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"ft{_n[0]}", hashed_password="x", alfred_address="Master Wayne",
                              # these tests aren't about proactive check-ins
                              nudges_enabled=False)
        db.add(u)
        db.commit()
        db.refresh(u)
        if linked:
            db.add(models.BatPersonalAccessToken(
                owner_id=u.id, token_hash=f"h{_n[0]}", telegram_chat_id=str(7000 + _n[0])))
            db.commit()
        return u.id
    finally:
        db.close()


def _tool(uid, name, args=None):
    db = SessionLocal()
    try:
        return alfred_tools.execute_tool(db, db.get(models.BatAccount, uid), name, args or {})
    finally:
        db.close()


@pytest.fixture
def sink(monkeypatch):
    sent = []
    monkeypatch.setattr(scheduler.telegram_service, "send_telegram_message",
                        lambda token, chat_id, text, **kw: (sent.append((chat_id, text)) or True))
    monkeypatch.setattr(scheduler, "get_settings", lambda: type("S", (), {"telegram_bot_token": "t"})())
    return sent


# --- tool behaviour --------------------------------------------------------

def test_start_timed_session_stores_planned_and_blocks_second():
    uid = _mk_user(linked=False)
    res = _tool(uid, "start_focus_session", {"planned_minutes": 25})
    assert res["session"]["planned_minutes"] == 25
    assert "message you here" in res["session"]["note"]
    # second start is rejected while one runs
    res2 = _tool(uid, "start_focus_session", {"planned_minutes": 10})
    assert "error" in res2 and "already running" in res2["error"]


def test_start_validates_planned_range():
    uid = _mk_user(linked=False)
    assert "error" in _tool(uid, "start_focus_session", {"planned_minutes": 3})
    assert "error" in _tool(uid, "start_focus_session", {"planned_minutes": 500})


def test_get_active_and_stop():
    uid = _mk_user(linked=False)
    _tool(uid, "start_focus_session", {"planned_minutes": 25})
    active = _tool(uid, "get_active_focus_session")["active"]
    assert active is not None and active["planned_minutes"] == 25
    assert "remaining_minutes" in active
    # stop with no active after stopping
    out = _tool(uid, "stop_focus_session")
    # just started → under 5 min → discarded
    assert out["session"]["discarded"] is True
    assert _tool(uid, "get_active_focus_session")["active"] is None


def test_stop_with_no_session():
    uid = _mk_user(linked=False)
    assert "No focus session" in _tool(uid, "stop_focus_session")["note"]


# --- cron auto-end ---------------------------------------------------------

def _timed_session(uid, started_minutes_ago, planned, mission_id=None):
    db = SessionLocal()
    try:
        s = models.BatFocus(
            owner_id=uid, mission_id=mission_id, planned_minutes=planned,
            start_time=datetime.now(timezone.utc) - timedelta(minutes=started_minutes_ago),
        )
        db.add(s)
        db.commit()
        db.refresh(s)
        return s.id
    finally:
        db.close()


def test_cron_autoends_due_timed_session_and_pings(sink):
    uid = _mk_user(linked=True)
    db = SessionLocal()
    try:
        m = models.BatMission(owner_id=uid, title="Write report", focus_minutes=0)
        db.add(m)
        db.commit()
        mid = m.id
    finally:
        db.close()
    sid = _timed_session(uid, started_minutes_ago=26, planned=25, mission_id=mid)

    summary = _run(scheduler.run_tick(db=SessionLocal(), adapter_for=lambda d, u: None))
    assert summary["focus_autoended"] == 1
    assert summary["focus_pings_sent"] == 1
    mine = _mine(sink, uid)
    assert len(mine) == 1 and "Focus complete" in mine[0] and "Write report" in mine[0]

    db = SessionLocal()
    try:
        s = db.get(models.BatFocus, sid)
        assert s.end_time is not None and s.duration_minutes == 25   # logged planned
        assert db.get(models.BatMission, mid).focus_minutes == 25    # credited
    finally:
        db.close()


def test_cron_leaves_unfinished_and_untimed_sessions(sink):
    uid = _mk_user(linked=True)
    not_due = _timed_session(uid, started_minutes_ago=5, planned=25)   # 20 min left
    db = SessionLocal()
    try:
        # untimed (web) open session — planned_minutes NULL, must be ignored
        s = models.BatFocus(owner_id=uid, start_time=datetime.now(timezone.utc) - timedelta(hours=3))
        db.add(s)
        db.commit()
        untimed = s.id
    finally:
        db.close()

    summary = _run(scheduler.run_tick(db=SessionLocal(), adapter_for=lambda d, u: None))
    assert summary["focus_autoended"] == 0
    assert _mine(sink, uid) == []
    db = SessionLocal()
    try:
        assert db.get(models.BatFocus, not_due).end_time is None
        assert db.get(models.BatFocus, untimed).end_time is None
    finally:
        db.close()
