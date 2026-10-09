"""The work profile: guided setup, schedule awareness, and automatic reports."""

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

import models
from database import SessionLocal
from services import alfred_tools, nudges, scheduler, work_service

_n = [970000]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _mk_user(linked=True):
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"wp{_n[0]}", hashed_password="x",
                              timezone="UTC", alfred_address="Master Wayne")
        db.add(u)
        db.commit()
        db.refresh(u)
        if linked:
            db.add(models.BatPersonalAccessToken(
                owner_id=u.id, token_hash=f"h{_n[0]}", telegram_chat_id=str(4400 + _n[0])))
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
                        lambda token, chat_id, text, **kw: sent.append(text) or True)
    monkeypatch.setattr(scheduler, "get_settings",
                        lambda: type("S", (), {"telegram_bot_token": "t"})())
    return sent


# --- guided setup ----------------------------------------------------------

def test_setup_asks_days_then_hours_then_finishes():
    uid = _mk_user()
    first = _tool(uid, "get_work_profile")
    assert first["configured"] is False
    assert "Which days" in first["next_question"]

    after_days = _tool(uid, "set_work_profile", {"work_days": "Mon,Tue,Wed,Thu,Fri"})
    assert after_days["profile"]["work_days"] == "0,1,2,3,4"
    assert "hours" in after_days["next_question"]            # moved to the next step
    assert after_days["configured"] is False                 # hours still missing

    after_hours = _tool(uid, "set_work_profile", {"work_start": "09:00", "work_end": "18:00"})
    assert after_hours["configured"] is True                 # essentials complete
    # optional enrichment is offered, never required
    assert after_hours["next_question"] is not None
    assert after_hours["missing_essential"] == []


def test_setup_completes_and_stops_asking():
    uid = _mk_user()
    _tool(uid, "set_work_profile", {
        "work_days": "Mon,Tue,Wed,Thu,Fri", "work_start": "09:00", "work_end": "18:00",
        "employer": "Wayne Enterprises", "role": "Analyst", "expected_weekly_hours": 40,
        "report_time": "19:00", "started_on": "2026-01-15",
    })
    st = _tool(uid, "get_work_profile")
    assert st["configured"] is True
    assert st["next_question"] is None                       # nothing left to ask
    assert st["profile"]["work_days_label"] == "Mon, Tue, Wed, Thu, Fri"


def test_profile_validation():
    uid = _mk_user()
    assert "error" in _tool(uid, "set_work_profile", {"work_start": "9am"})
    assert "error" in _tool(uid, "set_work_profile", {"expected_weekly_hours": 500})
    assert "error" in _tool(uid, "set_work_profile", {"work_days": "Funday"})


# --- schedule awareness ----------------------------------------------------

def test_is_working_now_respects_days_and_hours():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        p = work_service.upsert_profile(db, user, work_days="Mon,Tue,Wed,Thu,Fri",
                                        work_start="09:00", work_end="18:00")
        tue_noon = datetime(2026, 10, 6, 12, 0, tzinfo=ZoneInfo("UTC"))     # Tuesday
        tue_night = datetime(2026, 10, 6, 22, 0, tzinfo=ZoneInfo("UTC"))
        sat_noon = datetime(2026, 10, 10, 12, 0, tzinfo=ZoneInfo("UTC"))    # Saturday
        assert work_service.is_working_now(p, tue_noon) is True
        assert work_service.is_working_now(p, tue_night) is False
        assert work_service.is_working_now(p, sat_noon) is False
    finally:
        db.close()


def test_no_drift_nudge_while_at_work():
    """The false accusation this profile exists to prevent."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatMission(owner_id=uid, title="Personal thing", status="pending"))
        db.commit()
        tue_4pm = datetime(2026, 10, 6, 16, 0, tzinfo=ZoneInfo("UTC"))      # Tuesday

        # with no profile he asks whether they're drifting
        n = nudges.evaluate(db, user, tue_4pm)
        assert n is not None and n.kind == "drift"

        # once he knows they're at work, he does not
        work_service.upsert_profile(db, user, work_days="Mon,Tue,Wed,Thu,Fri",
                                    work_start="09:00", work_end="18:00")
        n2 = nudges.evaluate(db, user, tue_4pm)
        assert n2 is None or n2.kind != "drift"
    finally:
        db.close()


def test_expected_minutes_from_weekly_hours():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        p = work_service.upsert_profile(db, user, work_days="Mon,Tue,Wed,Thu,Fri",
                                        work_start="09:00", work_end="17:00",
                                        expected_weekly_hours=40)
        mon = datetime(2026, 10, 5).date()        # Monday
        fri = datetime(2026, 10, 9).date()        # Friday
        assert work_service.scheduled_days_in(p, mon, fri) == 5
        assert work_service.expected_minutes(p, mon, fri) == 40 * 60
        assert work_service.expected_minutes(p, mon, mon) == 8 * 60
    finally:
        db.close()


def test_report_measures_against_the_schedule():
    uid = _mk_user()
    _tool(uid, "set_work_profile", {"work_days": "Mon,Tue,Wed,Thu,Fri",
                                    "work_start": "09:00", "work_end": "17:00",
                                    "expected_weekly_hours": 40})
    _tool(uid, "create_work_task", {"title": "Something"})
    report = _tool(uid, "work_report", {"period": "week"})["report"]
    assert "Against your schedule" in report


# --- automatic reports -----------------------------------------------------

def _profile_due_now(uid, **extra):
    """Give the user a profile whose report_time is right now."""
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        now = datetime.now(ZoneInfo("UTC"))
        p = work_service.upsert_profile(
            db, user, work_days="Mon,Tue,Wed,Thu,Fri", work_start="09:00", work_end="18:00",
            report_time=(now - timedelta(minutes=1)).strftime("%H:%M"), **extra)
        p.created_at = now - timedelta(days=3)
        p.updated_at = now - timedelta(days=3)
        db.commit()
    finally:
        db.close()


def test_daily_report_only_on_a_day_that_was_worked(sink):
    uid = _mk_user()
    _profile_due_now(uid, daily_report=True)

    # nothing moved today → no report
    summary = _run(scheduler.run_tick(db=SessionLocal(), adapter_for=lambda d, u: None))
    assert summary["work_reports_sent"] == 0

    # something moved → it was a working day → report goes out
    _tool(uid, "create_work_task", {"title": "Vendor call"})
    summary2 = _run(scheduler.run_tick(db=SessionLocal(), adapter_for=lambda d, u: None))
    assert summary2["work_reports_sent"] == 1
    assert any("Work — today" in t for t in sink)

    # and not twice
    sink.clear()
    summary3 = _run(scheduler.run_tick(db=SessionLocal(), adapter_for=lambda d, u: None))
    assert summary3["work_reports_sent"] == 0


def test_no_automatic_report_without_a_report_time(sink):
    uid = _mk_user()
    db = SessionLocal()
    try:
        work_service.upsert_profile(db, db.get(models.BatAccount, uid),
                                    work_days="Mon,Tue,Wed,Thu,Fri",
                                    work_start="09:00", work_end="18:00")
    finally:
        db.close()
    _tool(uid, "create_work_task", {"title": "Thing"})
    summary = _run(scheduler.run_tick(db=SessionLocal(), adapter_for=lambda d, u: None))
    assert summary["work_reports_sent"] == 0      # reports stay on-request
