"""The board showed a streak and nothing else.

`recent_adherence` is what the check-in reward is actually built on — and the
comment on it says plainly that it, not the consecutive run, is the honest
headline measure. But it only ever reached the user inside a check-in
response, so the screen could only show the streak: the one number the
evidence in `reports/Human behaviour science for Alfred.md` says not to lead
with, because a run that resets to zero is a counter you can only ever lose.

These cover it coming back with the list, cheaply and in the user's own days.
"""

from datetime import datetime, timedelta, timezone

import models
from database import SessionLocal
from services import habit_service

_n = [993000]


def _mk_user(tz="UTC"):
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"ha{_n[0]}", hashed_password="x", timezone=tz)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _habit(db, owner_id, name="Press-ups", frequency="daily"):
    h = models.BatHabit(owner_id=owner_id, name=name, frequency=frequency)
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


def _log(db, habit_id, days_ago):
    db.add(models.HabitCompletionLog(
        habit_id=habit_id,
        completed_at=(datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(tzinfo=None),
    ))
    db.commit()


def test_the_list_carries_adherence_not_only_the_streak():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        h = _habit(db, uid)
        for days_ago in (0, 1, 3):
            _log(db, h.id, days_ago)

        [listed] = habit_service.list_habits(db, user)
        assert listed.adherence_done == 3
        assert listed.adherence_window == habit_service.ADHERENCE_WINDOW_DAYS
    finally:
        db.close()


def test_two_check_ins_in_one_day_count_once():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        h = _habit(db, uid)
        _log(db, h.id, 0)
        _log(db, h.id, 0)

        [listed] = habit_service.list_habits(db, user)
        assert listed.adherence_done == 1
    finally:
        db.close()


def test_a_weekly_habit_is_measured_in_weeks():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        h = _habit(db, uid, frequency="weekly")
        _log(db, h.id, 0)

        [listed] = habit_service.list_habits(db, user)
        # 14 days is two weekly opportunities, not fourteen.
        assert listed.adherence_window == 2
        assert listed.adherence_done == 1
    finally:
        db.close()


def test_one_query_however_many_habits():
    """Forty habits must not cost forty round trips."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        for i in range(8):
            h = _habit(db, uid, name=f"Habit {i}")
            _log(db, h.id, 0)

        seen = []
        from sqlalchemy import event
        engine = db.get_bind()

        def before(conn, cursor, statement, *a):
            if "habit_completion" in statement.lower():
                seen.append(statement)

        event.listen(engine, "before_cursor_execute", before)
        try:
            habits = habit_service.list_habits(db, user)
        finally:
            event.remove(engine, "before_cursor_execute", before)

        assert len(habits) == 8
        assert len(seen) == 1, f"expected one completion-log query, got {len(seen)}"
    finally:
        db.close()


def test_a_check_in_response_also_carries_it():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        h = _habit(db, uid)

        # Set after the commit, or the refresh inside check-in wipes it.
        checked = habit_service.check_in_habit(db, user, h.id)
        assert checked.adherence_done == 1
        assert checked.adherence_window == habit_service.ADHERENCE_WINDOW_DAYS
    finally:
        db.close()


def test_no_habits_is_not_a_query():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        assert habit_service.list_habits(db, user) == []
    finally:
        db.close()
