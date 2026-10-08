"""Alfred's proactive check-ins: signals fire on real state, guardrails stop
him being a nuisance, and each occasion fires exactly once."""

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

import models
from database import SessionLocal
from services import alfred_tools, nudges, scheduler

_n = [400000]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _mk_user(linked=True, **kw):
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"nu{_n[0]}", hashed_password="x",
                              timezone="UTC", alfred_address="Master Wayne", **kw)
        db.add(u)
        db.commit()
        db.refresh(u)
        if linked:
            db.add(models.BatPersonalAccessToken(
                owner_id=u.id, token_hash=f"h{_n[0]}", telegram_chat_id=str(6000 + _n[0])))
            db.commit()
        return u.id
    finally:
        db.close()


def _noon(day_offset=0):
    return datetime.now(ZoneInfo("UTC")).replace(hour=16, minute=0, second=0, microsecond=0) \
        + timedelta(days=day_offset)


@pytest.fixture
def sink(monkeypatch):
    sent = []
    monkeypatch.setattr(scheduler.telegram_service, "send_telegram_message",
                        lambda token, chat_id, text, **kw: sent.append(text) or True)
    monkeypatch.setattr(scheduler, "get_settings",
                        lambda: type("S", (), {"telegram_bot_token": "t"})())
    return sent


# --- signals ---------------------------------------------------------------

def test_countdown_horizon_fires_at_a_mark():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatCountdown(owner_id=uid, title="Final exam",
                                   target_date=datetime.now(timezone.utc) + timedelta(days=7, hours=2)))
        db.commit()
        n = nudges.evaluate(db, user, _noon())
        assert n is not None and n.kind == "countdown"
        assert "Final exam" in n.draft and "7 days" in n.draft
    finally:
        db.close()


def test_drift_asks_rather_than_scolds():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatMission(owner_id=uid, title="Write report", status="pending"))
        db.commit()
        n = nudges.evaluate(db, user, _noon())
        assert n is not None and n.kind == "drift"
        assert "drifting" in n.draft.lower()
        assert "?" in n.draft           # it asks
    finally:
        db.close()


def test_good_day_is_acknowledged_not_only_nagging():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        now = datetime.now(timezone.utc)
        db.add(models.BatFocus(owner_id=uid, start_time=now - timedelta(hours=2),
                               end_time=now - timedelta(hours=1), duration_minutes=120))
        db.commit()
        n = nudges.evaluate(db, user, _noon())
        assert n is not None and n.kind == "praise"
        assert "2h" in n.draft
    finally:
        db.close()


def test_overdue_pileup_offers_help():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        old = datetime.now(timezone.utc) - timedelta(days=5)
        for i in range(3):
            db.add(models.BatMission(owner_id=uid, title=f"Late {i}",
                                     status="pending", due_date=old))
        db.commit()
        n = nudges.evaluate(db, user, _noon())
        assert n is not None and n.kind == "overdue"
    finally:
        db.close()


# --- guardrails ------------------------------------------------------------

def test_quiet_hours_block_everything():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatMission(owner_id=uid, title="X", status="pending"))
        db.commit()
        night = datetime.now(ZoneInfo("UTC")).replace(hour=2, minute=0, second=0, microsecond=0)
        assert nudges.in_quiet_hours(user, night) is True
        assert nudges.evaluate(db, user, night) is None
    finally:
        db.close()


def test_disabled_user_is_never_nudged():
    uid = _mk_user(nudges_enabled=False)
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatMission(owner_id=uid, title="X", status="pending"))
        db.commit()
        assert nudges.evaluate(db, user, _noon()) is None
    finally:
        db.close()


def test_recent_conversation_suppresses_nudges():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatMission(owner_id=uid, title="X", status="pending"))
        sess = models.BatAlfredSession(owner_id=uid, title="t")
        db.add(sess)
        db.commit()
        # 10 minutes before the evaluation moment → mid-conversation
        db.add(models.BatAlfredMessage(owner_id=uid, session_id=sess.id, role="user",
                                       content="hi", created_at=_noon() - timedelta(minutes=10)))
        db.commit()
        assert nudges.evaluate(db, user, _noon()) is None   # mid-conversation
    finally:
        db.close()


def test_daily_cap_and_global_cooldown():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        now = _noon()
        today = now.date().isoformat()
        # cap reached
        for i in range(nudges.DEFAULT_PER_DAY):
            db.add(models.BatNudgeLog(owner_id=uid, nudge_key=f"k{i}", kind="x",
                                      local_date=today,
                                      sent_at=datetime.now(timezone.utc) - timedelta(hours=5)))
        db.commit()
        assert nudges.may_nudge(db, user, now) is False
    finally:
        db.close()


def test_same_occasion_never_fires_twice():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatMission(owner_id=uid, title="X", status="pending"))
        db.commit()
        n = nudges.evaluate(db, user, _noon())
        assert n is not None
        assert nudges.record(db, user, n, _noon()) is True
        assert nudges.record(db, user, n, _noon()) is False   # unique key holds
        assert nudges.already_sent(db, user, n.key) is True
    finally:
        db.close()


# --- settings tool ---------------------------------------------------------

def test_settings_tool_reads_and_writes():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        got = alfred_tools.execute_tool(db, user, "get_nudge_settings", {})["nudges"]
        assert got["enabled"] is True and got["per_day"] == nudges.DEFAULT_PER_DAY

        out = alfred_tools.execute_tool(db, user, "set_nudge_settings",
                                        {"per_day": 1, "quiet_start": "21:00"})["nudges"]
        assert out["per_day"] == 1 and out["quiet_start"] == "21:00"

        bad = alfred_tools.execute_tool(db, user, "set_nudge_settings", {"quiet_start": "9pm"})
        assert "error" in bad
        bad2 = alfred_tools.execute_tool(db, user, "set_nudge_settings", {"per_day": 99})
        assert "error" in bad2
    finally:
        db.close()


# --- end to end through the tick -------------------------------------------

def test_tick_sends_one_nudge(sink):
    uid = _mk_user()
    db = SessionLocal()
    try:
        # run_tick uses the real clock, so park quiet hours away from "now"
        h = datetime.now(ZoneInfo("UTC")).hour
        user = db.get(models.BatAccount, uid)
        user.nudge_quiet_start = f"{(h + 2) % 24:02d}:00"
        user.nudge_quiet_end = f"{(h + 3) % 24:02d}:00"
        db.add(models.BatCountdown(owner_id=uid, title="Flight",
                                   target_date=datetime.now(timezone.utc) + timedelta(days=3, hours=2)))
        db.commit()
    finally:
        db.close()

    summary = _run(scheduler.run_tick(db=SessionLocal(), adapter_for=lambda d, u: None))
    assert summary["nudges_sent"] >= 1
    assert any("Flight" in t for t in sink)

    # a second tick right after must stay quiet (cooldown + once-only key)
    sink.clear()
    summary2 = _run(scheduler.run_tick(db=SessionLocal(), adapter_for=lambda d, u: None))
    assert summary2["nudges_sent"] == 0
    assert sink == []
