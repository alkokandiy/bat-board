"""Phase 25 — a habit's own record, which was all stored and never shown.

A habit row gave a streak and a bar over a log going back to the day it
started. `history` is that log, one month at a time.

The state machine is the substance. `rested` is not `missed`: a planned
rest leaves the denominator rather than entering it as a miss, and a
calendar drawing them the same would re-tell the person the exact thing the
rest day exists to stop saying. `not_due` is not a miss either — a weekly
habit is not failing on the other six days — and neither is a day that has
not happened yet.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

import models
from database import SessionLocal
from services import habit_service

_n = [994000]


def _mk_user(tz="UTC"):
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"hh{_n[0]}", hashed_password="x", timezone=tz)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _habit(db, owner_id, name="Press-ups", frequency="daily", **kw):
    h = models.BatHabit(owner_id=owner_id, name=name, frequency=frequency, **kw)
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


def _log_at(db, habit_id, when: datetime):
    db.add(models.HabitCompletionLog(habit_id=habit_id, completed_at=when))
    db.commit()


def _state_on(out, day: str) -> str:
    return next(d["state"] for d in out["days"] if d["date"] == day)


def test_it_covers_the_whole_month_in_order():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        h = _habit(db, uid)
        out = habit_service.history(db, user, h.id, month="2026-02")
        assert len(out["days"]) == 28                   # 2026 is not a leap year
        assert out["days"][0]["date"] == "2026-02-01"
        assert out["days"][-1]["date"] == "2026-02-28"
        assert out["month"] == "2026-02"
    finally:
        db.close()


def test_a_long_month_is_not_cut_short():
    """The 28th-plus-four trick for finding month end is easy to get wrong."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        h = _habit(db, uid)
        assert len(habit_service.history(db, user, h.id, month="2026-01")["days"]) == 31
        assert len(habit_service.history(db, user, h.id, month="2026-04")["days"]) == 30
        assert len(habit_service.history(db, user, h.id, month="2024-02")["days"]) == 29
    finally:
        db.close()


def test_a_check_in_marks_its_own_local_day():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        h = _habit(db, uid)
        _log_at(db, h.id, datetime(2026, 2, 10, 9, 0, tzinfo=timezone.utc))
        out = habit_service.history(db, user, h.id, month="2026-02")
        assert _state_on(out, "2026-02-10") == "done"
        assert _state_on(out, "2026-02-09") == "missed"
    finally:
        db.close()


def test_the_day_is_theirs_not_utcs():
    """A check-in at 23:00 in Tashkent is 18:00 UTC — the same day either
    way. At 02:00 local it is the PREVIOUS day in UTC, and the calendar
    must show the day they did it on."""
    uid = _mk_user(tz="Asia/Tashkent")               # UTC+5
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        h = _habit(db, uid)
        # 2026-02-10 21:00Z is 2026-02-11 02:00 in Tashkent.
        _log_at(db, h.id, datetime(2026, 2, 10, 21, 0, tzinfo=timezone.utc))
        out = habit_service.history(db, user, h.id, month="2026-02")
        assert _state_on(out, "2026-02-11") == "done"
        assert _state_on(out, "2026-02-10") != "done"
    finally:
        db.close()


def test_a_rest_day_is_not_a_miss():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        h = _habit(db, uid)
        db.add(models.BatHabitSkip(habit_id=h.id, owner_id=uid, local_date="2026-02-10"))
        db.commit()
        out = habit_service.history(db, user, h.id, month="2026-02")
        assert _state_on(out, "2026-02-10") == "rested"
        assert out["rested_this_month"] == 1
        assert out["missed_this_month"] == 27        # every other past day
    finally:
        db.close()


def test_a_rest_day_leaves_the_denominator_rather_than_counting_against_them():
    """The rule the whole rest-day feature exists for. Two identical months
    except one day rested: the rate must not go DOWN for resting."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        plain, rested = _habit(db, uid, name="A"), _habit(db, uid, name="B")
        for h in (plain, rested):
            for day in (3, 4, 5):
                _log_at(db, h.id, datetime(2026, 2, day, 9, 0, tzinfo=timezone.utc))
        # Ten rested days, not one: 3/28 and 3/27 both round to 11%, so a
        # single day proves nothing about a figure rounded to a percent.
        for day in range(6, 16):
            db.add(models.BatHabitSkip(habit_id=rested.id, owner_id=uid,
                                       local_date=f"2026-02-{day:02d}"))
        db.commit()
        a = habit_service.history(db, user, plain.id, month="2026-02")
        b = habit_service.history(db, user, rested.id, month="2026-02")
        assert b["due_so_far"] == a["due_so_far"] - 10
        assert b["check_in_rate"] > a["check_in_rate"]
    finally:
        db.close()


def test_a_day_the_habit_was_not_due_is_not_a_miss():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        # Mondays only. 2026-02-02 is a Monday; 2026-02-03 is not.
        h = _habit(db, uid, frequency="weekly", weekdays="0")
        out = habit_service.history(db, user, h.id, month="2026-02")
        assert _state_on(out, "2026-02-03") == "not_due"
        assert _state_on(out, "2026-02-02") == "missed"
    finally:
        db.close()


def test_the_rest_of_this_month_is_not_failure_yet():
    """Looking at November on the 20th must not paint the 21st-30th red."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        h = _habit(db, uid)
        today = date.today()
        out = habit_service.history(db, user, h.id)      # this month
        later = [d for d in out["days"] if date.fromisoformat(d["date"]) > today]
        assert later, "ran on the last day of a month; rerun tomorrow"
        assert {d["state"] for d in later} == {"upcoming"}
    finally:
        db.close()


def test_nothing_due_yet_reports_no_rate_rather_than_zero_percent():
    """0% is a verdict. A habit that has not been asked for anything yet
    has not failed, and a division would say it had."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        h = _habit(db, uid, frequency="weekly", weekdays="0")
        # A month entirely in the future: nothing was due, nothing missed.
        future = (date.today().replace(day=1) + timedelta(days=400)).strftime("%Y-%m")
        out = habit_service.history(db, user, h.id, month=future)
        assert out["due_so_far"] == 0
        assert out["check_in_rate"] is None
    finally:
        db.close()


def test_the_total_counts_every_check_in_ever_not_just_this_month():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        h = _habit(db, uid)
        _log_at(db, h.id, datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc))
        _log_at(db, h.id, datetime(2026, 2, 5, 9, 0, tzinfo=timezone.utc))
        _log_at(db, h.id, datetime(2026, 2, 6, 9, 0, tzinfo=timezone.utc))
        out = habit_service.history(db, user, h.id, month="2026-02")
        assert out["done_this_month"] == 2
        assert out["total_check_ins"] == 3
    finally:
        db.close()


def test_twice_in_one_day_is_one_done_day_and_two_check_ins():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        h = _habit(db, uid)
        _log_at(db, h.id, datetime(2026, 2, 5, 9, 0, tzinfo=timezone.utc))
        _log_at(db, h.id, datetime(2026, 2, 5, 18, 0, tzinfo=timezone.utc))
        out = habit_service.history(db, user, h.id, month="2026-02")
        assert out["done_this_month"] == 1
        assert _state_on(out, "2026-02-05") == "done"
        assert next(d["count"] for d in out["days"] if d["date"] == "2026-02-05") == 2
    finally:
        db.close()


# --- it is theirs, or it is nothing ----------------------------------------

def test_another_users_habit_is_not_readable():
    """`HabitCompletionLog` has no owner of its own — it is reachable only
    through the habit, so the habit is what must be checked."""
    mine, theirs = _mk_user(), _mk_user()
    db = SessionLocal()
    try:
        me = db.get(models.BatAccount, mine)
        their_habit = _habit(db, theirs, name="Their private ritual")
        _log_at(db, their_habit.id, datetime(2026, 2, 5, 9, 0, tzinfo=timezone.utc))
        assert habit_service.history(db, me, their_habit.id, month="2026-02") is None
    finally:
        db.close()


def test_a_habit_that_does_not_exist_is_not_found():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        assert habit_service.history(db, user, 99999, month="2026-02") is None
    finally:
        db.close()


def test_another_users_rest_days_do_not_colour_my_calendar():
    """The skip table has an owner_id AND a habit_id. Filtering on only one
    of them would let a shared id leak a rest day across accounts."""
    mine, theirs = _mk_user(), _mk_user()
    db = SessionLocal()
    try:
        me = db.get(models.BatAccount, mine)
        h = _habit(db, mine)
        db.add(models.BatHabitSkip(habit_id=h.id, owner_id=theirs,
                                   local_date="2026-02-10"))
        db.commit()
        out = habit_service.history(db, me, h.id, month="2026-02")
        assert _state_on(out, "2026-02-10") == "missed"
    finally:
        db.close()


@pytest.mark.parametrize("bad", ["2026", "nonsense", "2026-13-01", ""])
def test_a_month_that_is_not_a_month_is_refused(bad):
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        h = _habit(db, uid)
        if bad == "":
            # Empty means "this month", like omitting it — not an error.
            assert habit_service.history(db, user, h.id, month=bad) is not None
        else:
            with pytest.raises(ValueError):
                habit_service.history(db, user, h.id, month=bad)
    finally:
        db.close()


def test_keeping_it_on_a_day_it_was_not_due_cannot_push_the_rate_past_100():
    """A weekly habit kept on a spare Tuesday is real and worth showing —
    but it was never in the denominator, so counting it in the numerator
    would report more than a hundred percent of the occasions kept."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        h = _habit(db, uid, frequency="weekly", weekdays="0")     # Mondays
        # Every Monday in February 2026: the 2nd, 9th, 16th, 23rd.
        for day in (2, 9, 16, 23):
            _log_at(db, h.id, datetime(2026, 2, day, 9, 0, tzinfo=timezone.utc))
        # Plus three extra days it never asked for.
        for day in (3, 4, 5):
            _log_at(db, h.id, datetime(2026, 2, day, 9, 0, tzinfo=timezone.utc))
        out = habit_service.history(db, user, h.id, month="2026-02")
        assert out["done_this_month"] == 7        # every day it was kept
        assert out["check_in_rate"] == 100        # of the days that asked
    finally:
        db.close()
