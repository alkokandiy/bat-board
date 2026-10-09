"""Three fixes:

1. A slot that had already passed when the item was created/edited must NOT be
   back-fired by the catch-up window (an 08:00 reminder set at 09:50 fired at once).
2. Reminders can be bounded in time ("for one month") and stop afterwards.
3. A duplicate create reports the existing item for enrichment, not a refusal.
"""

import asyncio
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

import models
from database import SessionLocal
from services import alfred_tools, briefing_service, scheduler

_n = [800000]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _mk_user(linked=True):
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"rw{_n[0]}", hashed_password="x",
                              timezone="UTC", alfred_address="Master Wayne")
        db.add(u)
        db.commit()
        db.refresh(u)
        if linked:
            db.add(models.BatPersonalAccessToken(
                owner_id=u.id, token_hash=f"h{_n[0]}", telegram_chat_id=str(5500 + _n[0])))
            db.commit()
        return u.id
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


# --- 1. no back-firing of slots that predate the item ----------------------

def test_slot_before_creation_does_not_fire():
    now = datetime(2026, 10, 9, 9, 50, tzinfo=ZoneInfo("UTC"))
    created = now                      # just created, at 09:50
    # 08:00 today is 1h50m "late" — inside LATE_WINDOW, but before it existed
    assert scheduler._within_window(now, time(8, 0), created) is False
    # with no creation stamp the old catch-up behaviour still applies
    assert scheduler._within_window(now, time(8, 0), None) is True


def test_slot_after_creation_still_fires():
    now = datetime(2026, 10, 9, 8, 5, tzinfo=ZoneInfo("UTC"))
    created = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)   # created days ago
    assert scheduler._within_window(now, time(8, 0), created) is True


def test_new_reminder_for_earlier_today_stays_quiet(sink):
    """The medicine case: set at ~now for a time already past today."""
    uid = _mk_user()
    local_now = datetime.now(ZoneInfo("UTC"))
    earlier = (local_now - timedelta(hours=2)).strftime("%H:%M")
    db = SessionLocal()
    try:
        briefing_service.create_reminder(db, db.get(models.BatAccount, uid),
                                         message="Take medicine", recurrence="daily",
                                         send_time=earlier)
    finally:
        db.close()

    summary = _run(scheduler.run_tick(db=SessionLocal(), adapter_for=lambda d, u: None))
    assert summary["reminders_sent"] == 0
    assert not any("Take medicine" in t for t in sink)


# --- 2. bounded reminders --------------------------------------------------

def test_reminder_accepts_and_reports_end_date():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        end = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
        r = briefing_service.create_reminder(db, user, message="Take medicine",
                                             recurrence="daily", send_time="08:00",
                                             ends_on=end)
        assert r.ends_on == end
        shown = alfred_tools.execute_tool(db, user, "list_reminders", {})["reminders"][0]
        assert shown["ends_on"] == end
    finally:
        db.close()


def test_expired_reminder_stops_and_disables(sink):
    uid = _mk_user()
    local_now = datetime.now(ZoneInfo("UTC"))
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        r = briefing_service.create_reminder(
            db, user, message="Finished course", recurrence="daily",
            send_time=(local_now - timedelta(minutes=1)).strftime("%H:%M"),
            ends_on=(local_now.date() - timedelta(days=1)).isoformat())
        rid = r.id
        # pretend it was created long ago so only the end date can stop it
        r.created_at = local_now - timedelta(days=10)
        r.updated_at = local_now - timedelta(days=10)
        db.commit()
    finally:
        db.close()

    summary = _run(scheduler.run_tick(db=SessionLocal(), adapter_for=lambda d, u: None))
    assert summary["reminders_sent"] == 0
    assert not any("Finished course" in t for t in sink)
    db = SessionLocal()
    try:
        assert db.get(models.BatReminder, rid).enabled is False   # stopped for good
    finally:
        db.close()


def test_unexpired_bounded_reminder_still_fires(sink):
    uid = _mk_user()
    local_now = datetime.now(ZoneInfo("UTC"))
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        r = briefing_service.create_reminder(
            db, user, message="Legs treatment", recurrence="daily",
            send_time=(local_now - timedelta(minutes=1)).strftime("%H:%M"),
            ends_on=(local_now.date() + timedelta(days=20)).isoformat())
        r.created_at = local_now - timedelta(days=3)
        r.updated_at = local_now - timedelta(days=3)
        db.commit()
    finally:
        db.close()

    summary = _run(scheduler.run_tick(db=SessionLocal(), adapter_for=lambda d, u: None))
    assert summary["reminders_sent"] == 1
    assert any("Legs treatment" in t for t in sink)


def test_end_date_can_be_cleared():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        end = (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat()
        r = briefing_service.create_reminder(db, user, message="m", recurrence="daily",
                                             send_time="08:00", ends_on=end)
        updated = briefing_service.update_reminder(db, user, r.id, ends_on="none")
        assert updated.ends_on is None
    finally:
        db.close()


# --- 3. duplicate -> enrich, not refuse ------------------------------------

def test_duplicate_create_returns_existing_for_enrichment():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        first = alfred_tools.execute_tool(db, user, "create_mission",
                                          {"title": "Start the Winter Soldier 2027 program"})
        assert "mission" in first

        again = alfred_tools.execute_tool(db, user, "create_mission",
                                          {"title": "start the winter soldier 2027 program"})
        assert again["created"] is False
        assert again["existing_mission"]["id"] == first["mission"]["id"]
        # it hands Alfred the existing item AND tells him to enrich it
        assert "update_mission" in again["next_step"]
        # and it is not framed as a refusal
        assert "skipped" not in again
    finally:
        db.close()
