"""Phase 15 — a mission carries its own warnings.

Reminders could already point at a mission, but they fired at a clock time
the user typed, so the link was decorative: the warning had a date of its
own and the mission's due date had another. Phase 14 made rescheduling a
drag of the wrist, which turned that into a reminder that goes stale in one
gesture.

A `relative` reminder stores how many DAYS of notice it gives and reads the
date off the mission on every tick, so there is nothing stored to be wrong.
The headline tests are the two that prove it moves: push the mission back
and today's warning goes quiet, pull it forward and the warning arrives.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

import models
from database import SessionLocal
from services import alfred_tools, briefing_service, scheduler

_n = [900000]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _mk_user(tz="UTC"):
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"mr{_n[0]}", hashed_password="x",
                              timezone=tz, alfred_address="Master Wayne")
        db.add(u)
        db.commit()
        db.refresh(u)
        db.add(models.BatPersonalAccessToken(
            owner_id=u.id, token_hash=f"mh{_n[0]}",
            telegram_chat_id=str(7700 + _n[0])))
        db.commit()
        return u.id
    finally:
        db.close()


def _mk_mission(db, uid, *, due, title="File the tax return"):
    m = models.BatMission(owner_id=uid, title=title, due_date=due)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@pytest.fixture
def sink(monkeypatch):
    sent = []
    monkeypatch.setattr(scheduler.telegram_service, "send_telegram_message",
                        lambda token, chat_id, text, **kw: sent.append(text) or True)
    monkeypatch.setattr(scheduler, "get_settings",
                        lambda: type("S", (), {"telegram_bot_token": "t"})())
    return sent


def _aged(db, reminder, local_now):
    """Backdate the row so only the schedule can decide, not BACKFIRE_GRACE."""
    reminder.created_at = local_now - timedelta(days=10)
    reminder.updated_at = local_now - timedelta(days=10)
    db.commit()


def _warn_now(db, uid, *, days_ahead, offset_days, local_now, tz="UTC"):
    """A relative reminder whose warning falls at this very minute.

    `days_ahead` is where the mission is due relative to today, `offset_days`
    the notice asked for; the two agreeing is what puts the warning now.
    """
    user = db.get(models.BatAccount, uid)
    due_local = (local_now + timedelta(days=days_ahead)).replace(
        hour=17, minute=0, second=0, microsecond=0)
    m = _mk_mission(db, uid, due=due_local.astimezone(timezone.utc).replace(tzinfo=None))
    r = briefing_service.create_reminder(
        db, user, message="Tax return is due", recurrence="relative",
        send_time=local_now.strftime("%H:%M"), offset_days=offset_days,
        mission_id=m.id)
    _aged(db, r, local_now)
    return m, r


# --- the resolver ----------------------------------------------------------

def test_a_days_notice_lands_the_day_before_at_the_time_asked_for():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        # Due Friday 2026-03-20 at 17:00 UTC.
        m = _mk_mission(db, uid, due=datetime(2026, 3, 20, 17, 0))
        r = briefing_service.create_reminder(
            db, user, message="Tax return is due", recurrence="relative",
            send_time="09:00", offset_days=1, mission_id=m.id)
        now = datetime(2026, 3, 19, 9, 0, tzinfo=ZoneInfo("UTC"))
        at = scheduler._relative_due_at(db, user, r, now)
        assert at == datetime(2026, 3, 19, 9, 0, tzinfo=ZoneInfo("UTC"))
    finally:
        db.close()


def test_zero_days_notice_is_the_morning_of():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        m = _mk_mission(db, uid, due=datetime(2026, 3, 20, 17, 0))
        r = briefing_service.create_reminder(
            db, user, message="Tax return is due", recurrence="relative",
            send_time="07:30", offset_days=0, mission_id=m.id)
        now = datetime(2026, 3, 20, 7, 30, tzinfo=ZoneInfo("UTC"))
        assert scheduler._relative_due_at(db, user, r, now) == \
            datetime(2026, 3, 20, 7, 30, tzinfo=ZoneInfo("UTC"))
    finally:
        db.close()


def test_the_day_before_means_their_day_not_utcs():
    """A mission due just after midnight UTC is due the previous day in New York.

    The due date is stored naive UTC. Reading it as a date without converting
    would make "the day before it is due" count back from the wrong day for
    anyone west of UTC — a whole day out, which is the entire feature wrong.
    """
    uid = _mk_user(tz="America/New_York")
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        # 2026-03-20T02:00Z is 2026-03-19 at 22:00 in New York.
        m = _mk_mission(db, uid, due=datetime(2026, 3, 20, 2, 0))
        r = briefing_service.create_reminder(
            db, user, message="Tax return is due", recurrence="relative",
            send_time="09:00", offset_days=1, mission_id=m.id)
        ny = ZoneInfo("America/New_York")
        at = scheduler._relative_due_at(db, user, r, datetime(2026, 3, 18, 9, 0, tzinfo=ny))
        # Due on the 19th to them, so a day's notice is the 18th — not the 19th.
        assert at == datetime(2026, 3, 18, 9, 0, tzinfo=ny)
    finally:
        db.close()


@pytest.mark.parametrize("wreck,expected_reason", [
    ("no_due_date", "nothing to count back from"),
    ("completed", "already done"),
    ("dismissed", "dismissed"),
    ("unlinked", "no mission"),
])
def test_there_is_nothing_to_warn_about(wreck, expected_reason):
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        m = _mk_mission(db, uid, due=datetime(2026, 3, 20, 17, 0))
        r = briefing_service.create_reminder(
            db, user, message="Tax return is due", recurrence="relative",
            send_time="09:00", offset_days=1, mission_id=m.id)
        if wreck == "no_due_date":
            m.due_date = None
        elif wreck == "completed":
            m.status = "completed"
        elif wreck == "dismissed":
            m.is_dismissed = True
        elif wreck == "unlinked":
            r.mission_id = None
        db.commit()
        now = datetime(2026, 3, 19, 9, 0, tzinfo=ZoneInfo("UTC"))
        assert scheduler._relative_due_at(db, user, r, now) is None, expected_reason
    finally:
        db.close()


def test_it_will_not_read_another_users_mission():
    """The reminder is scoped by owner on the way out, not only on the way in.

    `_valid_link` refuses a foreign mission at creation time, so this is the
    second lock: were a row ever to carry a foreign mission_id, the scheduler
    must still not read that mission's due date back to the wrong person.
    """
    mine, theirs = _mk_user(), _mk_user()
    db = SessionLocal()
    try:
        me = db.get(models.BatAccount, mine)
        their_mission = _mk_mission(db, theirs, due=datetime(2026, 3, 20, 17, 0))
        my_mission = _mk_mission(db, mine, due=datetime(2026, 3, 20, 17, 0))
        r = briefing_service.create_reminder(
            db, me, message="Tax return is due", recurrence="relative",
            send_time="09:00", offset_days=1, mission_id=my_mission.id)
        r.mission_id = their_mission.id     # as a bad write would leave it
        db.commit()
        now = datetime(2026, 3, 19, 9, 0, tzinfo=ZoneInfo("UTC"))
        assert scheduler._relative_due_at(db, me, r, now) is None
    finally:
        db.close()


# --- the headline: it moves with the mission -------------------------------

def test_a_warning_due_now_is_sent(sink):
    uid = _mk_user()
    local_now = datetime.now(ZoneInfo("UTC"))
    db = SessionLocal()
    try:
        _warn_now(db, uid, days_ahead=1, offset_days=1, local_now=local_now)
    finally:
        db.close()
    summary = _run(scheduler.run_tick(db=SessionLocal(), adapter_for=lambda d, u: None))
    assert summary["reminders_sent"] == 1
    assert any("Tax return is due" in t for t in sink)


def test_pushing_the_mission_back_takes_its_warning_with_it(sink):
    """The bug Phase 14 made easy: drag the mission, and the old warning
    would still have gone off about work that is no longer due."""
    uid = _mk_user()
    local_now = datetime.now(ZoneInfo("UTC"))
    db = SessionLocal()
    try:
        m, _ = _warn_now(db, uid, days_ahead=1, offset_days=1, local_now=local_now)
        # Rescheduled a week later — nothing about the reminder is touched.
        m.due_date = m.due_date + timedelta(days=7)
        db.commit()
    finally:
        db.close()
    summary = _run(scheduler.run_tick(db=SessionLocal(), adapter_for=lambda d, u: None))
    assert summary["reminders_sent"] == 0
    assert not any("Tax return is due" in t for t in sink)


def test_pulling_the_mission_forward_brings_its_warning_with_it(sink):
    """The other direction, and the one a stored date could never do."""
    uid = _mk_user()
    local_now = datetime.now(ZoneInfo("UTC"))
    db = SessionLocal()
    try:
        # Due in eight days with a day's notice: the warning is a week off.
        m, _ = _warn_now(db, uid, days_ahead=8, offset_days=1, local_now=local_now)
        mission_id = m.id
    finally:
        db.close()
    assert _run(scheduler.run_tick(db=SessionLocal(),
                                   adapter_for=lambda d, u: None))["reminders_sent"] == 0

    db = SessionLocal()
    try:
        m = db.get(models.BatMission, mission_id)
        m.due_date = m.due_date - timedelta(days=7)   # now due tomorrow
        db.commit()
    finally:
        db.close()
    summary = _run(scheduler.run_tick(db=SessionLocal(), adapter_for=lambda d, u: None))
    assert summary["reminders_sent"] == 1
    assert any("Tax return is due" in t for t in sink)


def test_a_fixed_time_reminder_on_a_mission_still_does_not_move(sink):
    """Deliberately unchanged. "08:00 daily" means 08:00, whatever the
    mission does — only `relative` follows the due date."""
    uid = _mk_user()
    local_now = datetime.now(ZoneInfo("UTC"))
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        m = _mk_mission(db, uid, due=(local_now + timedelta(days=1))
                        .astimezone(timezone.utc).replace(tzinfo=None))
        r = briefing_service.create_reminder(
            db, user, message="Tax return is due", recurrence="daily",
            send_time=local_now.strftime("%H:%M"), mission_id=m.id)
        _aged(db, r, local_now)
        m.due_date = m.due_date + timedelta(days=30)
        db.commit()
    finally:
        db.close()
    summary = _run(scheduler.run_tick(db=SessionLocal(), adapter_for=lambda d, u: None))
    assert summary["reminders_sent"] == 1


def test_it_rings_once_for_one_deadline(sink):
    uid = _mk_user()
    local_now = datetime.now(ZoneInfo("UTC"))
    db = SessionLocal()
    try:
        _warn_now(db, uid, days_ahead=1, offset_days=1, local_now=local_now)
    finally:
        db.close()
    first = _run(scheduler.run_tick(db=SessionLocal(), adapter_for=lambda d, u: None))
    second = _run(scheduler.run_tick(db=SessionLocal(), adapter_for=lambda d, u: None))
    assert first["reminders_sent"] == 1
    assert second["reminders_sent"] == 0
    assert sum("Tax return is due" in t for t in sink) == 1


def test_two_warnings_on_one_mission_are_two_reminders(sink):
    """"A day ahead, and again on the day" — the plan's own example.

    Both point at the same mission with different notice, and today only the
    one whose day it is goes out.
    """
    uid = _mk_user()
    local_now = datetime.now(ZoneInfo("UTC"))
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        m, _ = _warn_now(db, uid, days_ahead=1, offset_days=1, local_now=local_now)
        on_the_day = briefing_service.create_reminder(
            db, user, message="Tax return is due TODAY", recurrence="relative",
            send_time=local_now.strftime("%H:%M"), offset_days=0, mission_id=m.id)
        _aged(db, on_the_day, local_now)
    finally:
        db.close()
    summary = _run(scheduler.run_tick(db=SessionLocal(), adapter_for=lambda d, u: None))
    assert summary["reminders_sent"] == 1
    assert any("Tax return is due" in t for t in sink)
    assert not any("TODAY" in t for t in sink)


# --- validation ------------------------------------------------------------

def test_a_relative_reminder_needs_a_mission_to_count_back_from():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        with pytest.raises(ValueError, match="mission"):
            briefing_service.create_reminder(
                db, user, message="Something", recurrence="relative",
                send_time="09:00", offset_days=1)
    finally:
        db.close()


def test_a_relative_reminder_needs_to_say_how_much_notice():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        m = _mk_mission(db, uid, due=datetime(2026, 3, 20, 17, 0))
        with pytest.raises(ValueError, match="offset_days"):
            briefing_service.create_reminder(
                db, user, message="Something", recurrence="relative",
                send_time="09:00", mission_id=m.id)
    finally:
        db.close()


@pytest.mark.parametrize("bad", [-1, 366, "soon"])
def test_nonsense_notice_is_refused(bad):
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        m = _mk_mission(db, uid, due=datetime(2026, 3, 20, 17, 0))
        with pytest.raises(ValueError):
            briefing_service.create_reminder(
                db, user, message="Something", recurrence="relative",
                send_time="09:00", offset_days=bad, mission_id=m.id)
    finally:
        db.close()


def test_switching_an_unlinked_reminder_to_relative_is_refused():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        r = briefing_service.create_reminder(
            db, user, message="Take medicine", recurrence="daily", send_time="08:00")
        with pytest.raises(ValueError, match="mission"):
            briefing_service.update_reminder(db, user, r.id, recurrence="relative",
                                             offset_days=1)
        # Refused means unchanged, not half-changed.
        db.refresh(r)
        assert r.recurrence == "daily"
        assert r.offset_days is None
    finally:
        db.close()


def test_a_mission_arriving_in_the_same_call_satisfies_the_rule():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        m = _mk_mission(db, uid, due=datetime(2026, 3, 20, 17, 0))
        r = briefing_service.create_reminder(
            db, user, message="Take medicine", recurrence="daily", send_time="08:00")
        out = briefing_service.update_reminder(
            db, user, r.id, recurrence="relative", offset_days=2, mission_id=m.id)
        assert out.recurrence == "relative"
        assert out.offset_days == 2
        assert out.mission_id == m.id
    finally:
        db.close()


# --- how it reads ----------------------------------------------------------

@pytest.mark.parametrize("offset,expected", [
    (0, "09:00 on the day it is due"),
    (1, "09:00 the day before it is due"),
    (3, "09:00, 3 days before it is due"),
])
def test_the_schedule_reads_as_a_phrase_not_a_bare_time(offset, expected):
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        m = _mk_mission(db, uid, due=datetime(2026, 3, 20, 17, 0))
        r = briefing_service.create_reminder(
            db, user, message="Tax return is due", recurrence="relative",
            send_time="09:00", offset_days=offset, mission_id=m.id)
        assert briefing_service.when_label(r) == expected
    finally:
        db.close()


def test_a_fixed_reminder_still_reads_as_its_time():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        r = briefing_service.create_reminder(
            db, user, message="Take medicine", recurrence="daily", send_time="08:00")
        assert briefing_service.when_label(r) == "08:00"
    finally:
        db.close()


def test_alfred_can_see_the_notice_he_set():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        m = _mk_mission(db, uid, due=datetime(2026, 3, 20, 17, 0))
        briefing_service.create_reminder(
            db, user, message="Tax return is due", recurrence="relative",
            send_time="09:00", offset_days=1, mission_id=m.id)
        shown = alfred_tools.execute_tool(db, user, "list_reminders", {})["reminders"][0]
        assert shown["recurrence"] == "relative"
        assert shown["offset_days"] == 1
        assert shown["when"] == "09:00 the day before it is due"
        # Still linked, so the notification keeps its "Start focus" button.
        assert "mission" in (shown["about"] or "")
    finally:
        db.close()


def test_alfred_can_create_one_through_his_tool():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        m = _mk_mission(db, uid, due=datetime(2026, 3, 20, 17, 0))
        out = alfred_tools.execute_tool(db, user, "create_reminder", {
            "message": "Tax return is due", "recurrence": "relative",
            "send_time": "09:00", "offset_days": 1, "mission_id": m.id})
        assert "error" not in out
        saved = db.query(models.BatReminder).filter(
            models.BatReminder.owner_id == uid).one()
        assert saved.offset_days == 1
        assert saved.recurrence == "relative"
    finally:
        db.close()


# --- which day the occurrence is filed under -------------------------------

def _tz_where_local_hour_is(hour: int) -> ZoneInfo:
    """A fixed-offset zone in which it is currently `hour` o'clock.

    The straddle below needs local time to be just after midnight, which is
    true somewhere whatever the clock says here. Etc/GMT signs are inverted:
    Etc/GMT-5 is UTC+5.
    """
    want = (hour - datetime.now(timezone.utc).hour) % 24
    offset = want if want <= 12 else want - 24          # into [-11, 12]
    return ZoneInfo(f"Etc/GMT{-offset:+d}")


def test_a_late_warning_is_filed_under_its_own_day_not_the_day_it_arrived(sink):
    """The occurrence is keyed on the day the warning was FOR.

    LATE_WINDOW lets a warning still go out up to three hours after its
    slot, so a 23:00 warning delivered after a cron outage can arrive at
    01:00 the next day. Filing that under the day it happened to arrive
    would put the row on a date the warning was never about — and the next
    deadline that lands on that date would then be silently suppressed as a
    duplicate, losing a warning outright.
    """
    tz = _tz_where_local_hour_is(1)
    uid = _mk_user(tz=str(tz))
    local_now = datetime.now(tz)
    yesterday = (local_now - timedelta(days=1)).date()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        # Due today to them; a day's notice puts the warning at 23:00
        # yesterday, which is two hours ago.
        due_local = local_now.replace(hour=12, minute=0, second=0, microsecond=0)
        m = _mk_mission(db, uid, due=due_local.astimezone(timezone.utc).replace(tzinfo=None))
        r = briefing_service.create_reminder(
            db, user, message="Tax return is due", recurrence="relative",
            send_time="23:00", offset_days=1, mission_id=m.id)
        _aged(db, r, local_now)
        rid = r.id
    finally:
        db.close()

    assert _run(scheduler.run_tick(db=SessionLocal(),
                                   adapter_for=lambda d, u: None))["reminders_sent"] == 1
    db = SessionLocal()
    try:
        row = db.query(models.BatReminderLog).filter(
            models.BatReminderLog.reminder_id == rid).one()
        assert row.local_date == yesterday.isoformat(), (
            "filed under the day it arrived instead of the day it was for")
    finally:
        db.close()
