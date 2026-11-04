"""The scheduler must notice it is being ignored.

Reported: "all reminders were just noise. Last one month I didn't put medicine
and didn't write based on reminders, all skipped, and Alfred keeps sending
reminder everyday tirelessly."

Reproduced in the code: `_fire_reminders` read `enabled` and the schedule and
nothing else. There was no outcome to read, so thirty consecutive ignores and
thirty consecutive successes produced identical behaviour.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

import models
from database import SessionLocal
from services import reminder_feedback, scheduler

_n = [997000]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _tick():
    return _run(scheduler.run_tick(db=SessionLocal(), adapter_for=lambda d, u: None))


@pytest.fixture
def sink(monkeypatch):
    sent = []
    monkeypatch.setattr(
        scheduler.telegram_service, "send_telegram_message",
        lambda token, chat_id, text, **kw: sent.append({"text": text, "markup": kw.get("reply_markup")}) or True)
    monkeypatch.setattr(scheduler, "get_settings",
                        lambda: type("S", (), {"telegram_bot_token": "t"})())
    return sent


def _mk_user():
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"rq{_n[0]}", hashed_password="x",
                              timezone="UTC", alfred_address="Master Wayne")
        db.add(u)
        db.commit()
        db.refresh(u)
        db.add(models.BatPersonalAccessToken(
            owner_id=u.id, token_hash=f"q{_n[0]}", telegram_chat_id=str(7700 + _n[0])))
        db.commit()
        return u.id
    finally:
        db.close()


def _due_now_reminder(db, owner_id):
    """A daily reminder whose slot is the current minute, created yesterday."""
    now = datetime.now(timezone.utc)
    r = models.BatReminder(
        owner_id=owner_id, message="Take the medicine", recurrence="daily",
        send_time=now.strftime("%H:%M"), enabled=True,
        created_at=(now - timedelta(days=1)).replace(tzinfo=None),
        updated_at=(now - timedelta(days=1)).replace(tzinfo=None))
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def test_it_goes_out_with_something_to_press(sink):
    uid = _mk_user()
    db = SessionLocal()
    try:
        _due_now_reminder(db, uid)
    finally:
        db.close()

    _tick()
    mine = [m for m in sink if "medicine" in m["text"]]
    assert mine, "the reminder did not fire at all"
    buttons = mine[0]["markup"]["inline_keyboard"][0]
    assert [b["text"] for b in buttons] == ["Done", "Not today", "Stop this"]
    assert all(b["callback_data"].startswith("rem:") for b in buttons)


def _reminders_in(sink):
    """The reminder firings in what was sent, and nothing else.

    Identified by the Done/Not today keyboard, which only a reminder
    carries. Matching on the reminder's words instead was wrong: when a
    reminder is retired Alfred says SO, by name, and that message quotes it
    — which is the whole point of retiring it out loud rather than silently.
    """
    return [m for m in sink
            if "rem:" in str(m.get("markup") or "")]


def test_a_run_of_silence_retires_it(sink):
    """Three unanswered occurrences and it stops, instead of a month of them."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        r = _due_now_reminder(db, uid)
        rid = r.id
        # Three already sent, none answered — the state after three evenings.
        for d in (3, 2, 1):
            when = datetime.now(timezone.utc) - timedelta(days=d)
            db.add(models.BatReminderLog(
                reminder_id=rid, owner_id=uid,
                local_date=when.date().isoformat(), sent_at=when.replace(tzinfo=None)))
        r.consecutive_ignored = reminder_feedback.IGNORED_LIMIT - 1
        db.commit()
    finally:
        db.close()

    summary = _tick()
    assert summary["reminders_suspended"] == 1
    assert not _reminders_in(sink)

    db = SessionLocal()
    try:
        assert reminder_feedback.is_suspended(db.get(models.BatReminder, rid))
    finally:
        db.close()


def test_a_suspended_reminder_stays_quiet_on_later_ticks(sink):
    uid = _mk_user()
    db = SessionLocal()
    try:
        r = _due_now_reminder(db, uid)
        r.suspended_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
    finally:
        db.close()

    _tick()
    assert not _reminders_in(sink)


def test_one_that_is_being_answered_is_left_alone(sink):
    """Adaptation only ever reduces noise. A working reminder keeps working."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        r = _due_now_reminder(db, uid)
        when = datetime.now(timezone.utc) - timedelta(days=1)
        db.add(models.BatReminderLog(
            reminder_id=r.id, owner_id=uid, local_date=when.date().isoformat(),
            sent_at=when.replace(tzinfo=None), outcome="done",
            responded_at=when.replace(tzinfo=None)))
        db.commit()
    finally:
        db.close()

    _tick()
    # Also the positive control for _reminders_in: if this were vacuous, the
    # "stays quiet" assertions above would pass whatever the scheduler did.
    assert _reminders_in(sink), "a reminder in use was silenced"


def test_an_unanswered_occurrence_is_counted_when_the_next_one_comes_due(sink):
    uid = _mk_user()
    db = SessionLocal()
    try:
        r = _due_now_reminder(db, uid)
        rid = r.id
        when = datetime.now(timezone.utc) - timedelta(days=1)
        db.add(models.BatReminderLog(
            reminder_id=rid, owner_id=uid, local_date=when.date().isoformat(),
            sent_at=when.replace(tzinfo=None)))
        db.commit()
    finally:
        db.close()

    _tick()
    db = SessionLocal()
    try:
        assert db.get(models.BatReminder, rid).consecutive_ignored == 1
    finally:
        db.close()
