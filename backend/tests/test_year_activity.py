"""What each day of a year had in it.

Two numbers, because they answer different questions. `minutes` is effort
— time actually spent — and `done` is output: missions completed plus
habits kept. A day of three hours' focus and nothing finished is a real
day, and so is the reverse; one number would hide both.
"""

from datetime import datetime, timedelta, timezone

import models
from database import SessionLocal
from services import stats_service

_n = [955000]


def _mk_user(tz="UTC"):
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"ya{_n[0]}", hashed_password="x", timezone=tz)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _focus(db, uid, when, minutes):
    db.add(models.BatFocus(
        owner_id=uid, start_time=when.replace(tzinfo=None),
        end_time=(when + timedelta(minutes=minutes)).replace(tzinfo=None),
        duration_minutes=minutes))
    db.commit()


def _done_mission(db, uid, when):
    db.add(models.BatMission(owner_id=uid, title="done", status="completed",
                             completed_at=when.replace(tzinfo=None)))
    db.commit()


def _kept_habit(db, uid, when):
    h = models.BatHabit(owner_id=uid, name="Run", frequency="daily")
    db.add(h)
    db.commit()
    db.refresh(h)
    db.add(models.HabitCompletionLog(habit_id=h.id, completed_at=when.replace(tzinfo=None)))
    db.commit()


class TestTheYearHeatmap:
    def test_an_empty_year_has_no_days(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            assert stats_service.year_activity(db, user, 2026) == {"year": 2026, "days": []}
        finally:
            db.close()

    def test_effort_and_output_are_counted_apart(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            day = datetime(2026, 3, 9, 10, tzinfo=timezone.utc)
            _focus(db, uid, day, 90)
            _done_mission(db, uid, day)
            _kept_habit(db, uid, day)
            [cell] = stats_service.year_activity(db, user, 2026)["days"]
            assert cell["date"] == "2026-03-09"
            assert cell["minutes"] == 90
            assert cell["done"] == 2        # one mission, one habit
        finally:
            db.close()

    def test_a_day_of_effort_with_nothing_finished_still_counts(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            _focus(db, uid, datetime(2026, 5, 1, 9, tzinfo=timezone.utc), 180)
            [cell] = stats_service.year_activity(db, user, 2026)["days"]
            assert cell["minutes"] == 180 and cell["done"] == 0
        finally:
            db.close()

    def test_only_days_with_something_come_back(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            _focus(db, uid, datetime(2026, 1, 5, 9, tzinfo=timezone.utc), 25)
            _focus(db, uid, datetime(2026, 7, 20, 9, tzinfo=timezone.utc), 50)
            out = stats_service.year_activity(db, user, 2026)["days"]
            assert [c["date"] for c in out] == ["2026-01-05", "2026-07-20"]
        finally:
            db.close()

    def test_two_sessions_on_one_day_add_up(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            day = datetime(2026, 2, 2, 9, tzinfo=timezone.utc)
            _focus(db, uid, day, 20)
            _focus(db, uid, day + timedelta(hours=3), 40)
            [cell] = stats_service.year_activity(db, user, 2026)["days"]
            assert cell["minutes"] == 60
        finally:
            db.close()

    def test_another_year_is_not_included(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            _focus(db, uid, datetime(2025, 6, 1, 9, tzinfo=timezone.utc), 30)
            _focus(db, uid, datetime(2026, 6, 1, 9, tzinfo=timezone.utc), 30)
            out = stats_service.year_activity(db, user, 2026)["days"]
            assert [c["date"] for c in out] == ["2026-06-01"]
        finally:
            db.close()

    def test_it_is_counted_in_the_users_own_days(self):
        # 22:30 UTC on the 1st is already the 2nd in Tashkent (UTC+5).
        uid = _mk_user(tz="Asia/Tashkent")
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            _focus(db, uid, datetime(2026, 4, 1, 22, 30, tzinfo=timezone.utc), 30)
            [cell] = stats_service.year_activity(db, user, 2026)["days"]
            assert cell["date"] == "2026-04-02"
        finally:
            db.close()

    def test_someone_elses_year_is_not_yours(self):
        mine, theirs = _mk_user(), _mk_user()
        db = SessionLocal()
        try:
            other = db.get(models.BatAccount, theirs)
            _focus(db, mine, datetime(2026, 8, 8, 9, tzinfo=timezone.utc), 45)
            assert stats_service.year_activity(db, other, 2026)["days"] == []
        finally:
            db.close()

    def test_an_unfinished_session_is_not_effort_yet(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            db.add(models.BatFocus(
                owner_id=uid,
                start_time=datetime(2026, 9, 9, 9, tzinfo=timezone.utc).replace(tzinfo=None)))
            db.commit()
            assert stats_service.year_activity(db, user, 2026)["days"] == []
        finally:
            db.close()
