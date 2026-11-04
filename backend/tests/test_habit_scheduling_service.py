"""Scheduling, through the service and the tools.

`habit_schedule` covers the arithmetic. This covers the part that touches
the database: that a schedule is stored and validated, that switching
frequency cleans up after itself, and — the point of the whole phase — that
adherence counts the chances a habit genuinely had rather than raw days.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

import models
from database import SessionLocal
from services import alfred_tools, habit_service

_n = [987000]


def _mk_user():
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"sc{_n[0]}", hashed_password="x", timezone="UTC")
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _log(db, habit, days_ago):
    db.add(models.HabitCompletionLog(
        habit_id=habit.id,
        completed_at=(datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(tzinfo=None)))
    db.commit()


class TestStoringASchedule:
    def test_a_weekly_habit_can_name_its_days(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = habit_service.create_habit(db, user, name="Gym",
                                           frequency="weekly", weekdays="Mon,Thu")
            assert h.weekdays == "0,3"
        finally:
            db.close()

    def test_a_monthly_habit_can_name_its_date(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = habit_service.create_habit(db, user, name="Rent",
                                           frequency="monthly", day_of_month=1)
            assert h.day_of_month == 1
        finally:
            db.close()

    def test_an_interval_habit_needs_its_number(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            with pytest.raises(ValueError, match="needs interval_days"):
                habit_service.create_habit(db, user, name="Water plants",
                                           frequency="interval")
        finally:
            db.close()

    def test_a_habit_made_the_old_way_is_unchanged(self):
        """Every row that exists today has all three columns NULL."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = habit_service.create_habit(db, user, name="Read", frequency="weekly")
            assert h.weekdays is None
            assert h.day_of_month is None
        finally:
            db.close()


class TestChangingASchedule:
    def test_switching_to_daily_clears_the_weekdays(self):
        """Or they come back if it is ever switched to weekly again."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = habit_service.create_habit(db, user, name="Gym",
                                           frequency="weekly", weekdays="Mon,Thu")
            habit_service.update_habit(db, user, h.id, frequency="daily")
            db.refresh(h)
            assert h.frequency == "daily"
            assert h.weekdays is None
        finally:
            db.close()

    def test_changing_only_the_days_keeps_the_frequency(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = habit_service.create_habit(db, user, name="Gym",
                                           frequency="weekly", weekdays="Mon")
            habit_service.update_habit(db, user, h.id, weekdays="Tue,Fri")
            db.refresh(h)
            assert h.frequency == "weekly"
            assert h.weekdays == "1,4"
        finally:
            db.close()

    def test_an_unrelated_edit_leaves_the_schedule_alone(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = habit_service.create_habit(db, user, name="Gym",
                                           frequency="weekly", weekdays="Mon,Thu")
            habit_service.update_habit(db, user, h.id, cue="after coffee")
            db.refresh(h)
            assert h.weekdays == "0,3"
        finally:
            db.close()


class TestAdherenceCountsRealChances:
    def test_a_twice_a_week_habit_kept_perfectly_does_not_read_as_two_of_fourteen(self):
        """The headline bug: the denominator was raw days."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = habit_service.create_habit(db, user, name="Gym",
                                           frequency="weekly", weekdays="Mon,Thu")
            [listed] = habit_service.list_habits(db, user)
            # Four Mondays-or-Thursdays in a fortnight, not fourteen days.
            assert listed.adherence_window == 4
        finally:
            db.close()

    def test_a_daily_habit_still_has_fourteen_chances(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            habit_service.create_habit(db, user, name="Press-ups", frequency="daily")
            [listed] = habit_service.list_habits(db, user)
            assert listed.adherence_window == 14
        finally:
            db.close()

    def test_an_unscheduled_weekly_habit_keeps_its_old_window(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            habit_service.create_habit(db, user, name="Read", frequency="weekly")
            [listed] = habit_service.list_habits(db, user)
            assert listed.adherence_window == 2       # 14 days // 7, as before
        finally:
            db.close()


class TestWhatTheScreenAndAlfredAreTold:
    def test_the_list_says_whether_it_is_due_today(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            today = date.today()
            # Scheduled only for a day that is not today.
            other = (today.weekday() + 3) % 7
            habit_service.create_habit(db, user, name="Gym", frequency="weekly",
                                       weekdays=str(other))
            [listed] = habit_service.list_habits(db, user)
            assert listed.due_today is False
        finally:
            db.close()

    def test_a_daily_habit_is_due_today(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            habit_service.create_habit(db, user, name="Press-ups")
            [listed] = habit_service.list_habits(db, user)
            assert listed.due_today is True
        finally:
            db.close()

    def test_alfred_is_told_the_schedule_in_words(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            habit_service.create_habit(db, user, name="Gym", frequency="weekly",
                                       weekdays="Mon,Thu")
            out = alfred_tools.execute_tool(db, user, "list_habits", {})
            assert out["habits"][0]["schedule"] == "every Mon, Thu"
        finally:
            db.close()

    def test_alfred_can_set_the_days_himself(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            out = alfred_tools.execute_tool(db, user, "create_habit", {
                "name": "Gym", "frequency": "weekly", "weekdays": "Tue,Sat"})
            assert out["habit"]["schedule"] == "every Tue, Sat"
        finally:
            db.close()
