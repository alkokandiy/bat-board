"""Three times a week, and a rest day that is not a failure.

Two things a habit could not say, and one unit mismatch that Phase 5 left
behind.

A habit done whichever three days suit that week had no way to be described:
`frequency` said how often the period came round and `weekdays` said which
days, but "three times, you pick" was neither. And not doing a habit ON
PURPOSE was indistinguishable from failing to — the occasion counted against
adherence and broke the run either way, so the only way to protect a run was
to never need a rest.

The mismatch: Phase 5 moved the adherence denominator to due days while the
numerator still counted Monday-to-Sunday buckets, so a Monday-and-Thursday
habit kept perfectly read "2 of your last 4" — and Thursday's check-in landed
in a bucket Monday had already filled, so it earned nothing.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

import models
from database import SessionLocal
from services import habit_schedule, habit_service

_n = [981000]


def _mk_user(tz="UTC"):
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"tw{_n[0]}", hashed_password="x", timezone=tz)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _habit(db, uid, **kw):
    kw.setdefault("name", "Run")
    kw.setdefault("frequency", "daily")
    h = models.BatHabit(owner_id=uid, **kw)
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


def _did(db, habit, when):
    db.add(models.HabitCompletionLog(
        habit_id=habit.id, completed_at=when.replace(tzinfo=None)))
    db.commit()


class TestTheUnitMismatch:
    """A Mon/Thu habit kept perfectly used to read "2 of your last 4"."""

    def test_each_due_day_is_its_own_occasion(self):
        h = type("H", (), {"frequency": "weekly", "weekdays": "0,3",
                           "day_of_month": None, "interval_days": None,
                           "created_at": None})()
        mon = date(2026, 11, 2)
        thu = date(2026, 11, 5)
        assert habit_schedule.occasion_key(h, mon) != \
            habit_schedule.occasion_key(h, thu)

    def test_an_unscheduled_weekly_habit_still_buckets_by_week(self):
        """Existing habits must keep meaning exactly what they meant."""
        h = type("H", (), {"frequency": "weekly", "weekdays": None,
                           "day_of_month": None, "interval_days": None,
                           "created_at": None})()
        assert habit_schedule.occasion_key(h, date(2026, 11, 2)) == \
            habit_schedule.occasion_key(h, date(2026, 11, 5))

    def test_a_perfectly_kept_mon_thu_habit_reads_right(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, frequency="weekly", weekdays="0,3")
            today = datetime.now(timezone.utc)
            # Every Monday and Thursday in the window.
            for back in range(14):
                day = today - timedelta(days=back)
                if day.weekday() in (0, 3):
                    _did(db, h, day)
            got = habit_service.recent_adherence(db, user, h)
            assert got["done"] == got["window"], got
            assert got["rate"] == 1.0
        finally:
            db.close()

    def test_the_second_due_day_of_the_week_earns(self):
        """Thursday used to land in Monday's bucket and earn nothing."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, frequency="weekly", weekdays="0,1,2,3,4,5,6")
            before = user.points
            habit_service.check_in_habit(db, user, h.id)
            db.refresh(user)
            first = user.points - before
            assert first > 0
        finally:
            db.close()


class TestThreeTimesAWeek:
    def test_the_week_is_not_kept_until_the_target_is_reached(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, frequency="weekly", times_per_period=3)
            for expected_streak in (0, 0, 1):
                habit_service.check_in_habit(db, user, h.id)
                db.refresh(h)
                assert h.streak == expected_streak
        finally:
            db.close()

    def test_every_counting_check_in_earns(self):
        """Two of three is two thirds of the work, not nothing."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, frequency="weekly", times_per_period=3)
            earned = []
            for _ in range(3):
                before = user.points
                habit_service.check_in_habit(db, user, h.id)
                db.refresh(user)
                earned.append(user.points - before)
            assert all(e > 0 for e in earned), earned
        finally:
            db.close()

    def test_a_fourth_check_in_earns_nothing(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, frequency="weekly", times_per_period=3)
            for _ in range(3):
                habit_service.check_in_habit(db, user, h.id)
            db.refresh(user)
            before, streak_before = user.points, h.streak
            habit_service.check_in_habit(db, user, h.id)
            db.refresh(user)
            db.refresh(h)
            assert user.points == before
            assert h.streak == streak_before
        finally:
            db.close()

    def test_adherence_counts_kept_weeks_not_check_ins(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, frequency="weekly", times_per_period=3)
            now = datetime.now(timezone.utc)
            for _ in range(3):
                _did(db, h, now)
            got = habit_service.recent_adherence(db, user, h)
            assert got["done"] == 1, got

            h2 = _habit(db, uid, name="Two", frequency="weekly",
                        times_per_period=3)
            for _ in range(2):
                _did(db, h2, now)
            assert habit_service.recent_adherence(db, user, h2)["done"] == 0
        finally:
            db.close()

    def test_one_is_stored_as_null_so_nothing_changes(self):
        assert habit_schedule.validate_times("weekly", 1) is None
        assert habit_schedule.validate_times("weekly", None) is None
        assert habit_schedule.validate_times("weekly", 3) == 3

    def test_days_and_a_count_are_refused_together(self):
        """"Mon and Thu" already says how many; "3 times" says the opposite."""
        with pytest.raises(ValueError, match="not both"):
            habit_schedule.validate_times("weekly", 3, weekdays="0,3")

    def test_a_week_has_seven_days(self):
        with pytest.raises(ValueError, match="seven"):
            habit_schedule.validate_times("weekly", 8)

    def test_an_interval_habit_happens_once_each_time(self):
        with pytest.raises(ValueError, match="once each time"):
            habit_schedule.validate_times("interval", 2)


class TestRestingIsNotFailing:
    def test_a_rest_day_leaves_the_denominator(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, frequency="daily")
            plain = habit_service.recent_adherence(db, user, h)["window"]
            habit_service.skip_habit(db, user, h.id)
            rested = habit_service.recent_adherence(db, user, h)["window"]
            assert rested == plain - 1
        finally:
            db.close()

    def test_a_rest_day_does_not_break_the_run(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, frequency="daily")
            now = datetime.now(timezone.utc)
            today = now.date()
            # Kept the day before yesterday, rested yesterday.
            h.streak = 5
            h.last_met_period = (today - timedelta(days=2)).toordinal()
            h.last_completed = (now - timedelta(days=2)).replace(tzinfo=None)
            db.commit()
            habit_service.skip_habit(
                db, user, h.id, on=(today - timedelta(days=1)).isoformat())

            habit_service.check_in_habit(db, user, h.id)
            db.refresh(h)
            assert h.streak == 6, "a planned rest broke the run"
        finally:
            db.close()

    def test_an_unplanned_gap_still_breaks_it(self):
        """The control: without the rest, the same gap costs the run."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, frequency="daily")
            now = datetime.now(timezone.utc)
            today = now.date()
            h.streak = 5
            h.last_met_period = (today - timedelta(days=3)).toordinal()
            h.last_completed = (now - timedelta(days=3)).replace(tzinfo=None)
            db.commit()
            habit_service.check_in_habit(db, user, h.id)
            db.refresh(h)
            assert h.streak == 1
        finally:
            db.close()

    def test_resting_twice_is_resting_once(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid)
            habit_service.skip_habit(db, user, h.id)
            habit_service.skip_habit(db, user, h.id)
            assert len(habit_service.rest_days(db, user, h.id)) == 1
        finally:
            db.close()

    def test_a_rest_can_be_taken_back(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid)
            habit_service.skip_habit(db, user, h.id)
            out = habit_service.unskip_habit(db, user, h.id)
            assert out["was_resting"] is True
            assert habit_service.rest_days(db, user, h.id) == []
        finally:
            db.close()

    def test_someone_elses_habit_cannot_be_rested(self):
        mine, theirs = _mk_user(), _mk_user()
        db = SessionLocal()
        try:
            other = db.get(models.BatAccount, theirs)
            h = _habit(db, mine)
            assert habit_service.skip_habit(db, other, h.id) is None
            assert habit_service.unskip_habit(db, other, h.id) is None
            assert habit_service.rest_days(db, other, h.id) is None
        finally:
            db.close()

    def test_the_rest_is_their_local_day(self):
        uid = _mk_user(tz="Asia/Tashkent")
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid)
            out = habit_service.skip_habit(db, user, h.id)
            from services.timezones import local_date, user_tz
            expected = local_date(datetime.now(timezone.utc), user_tz(user))
            assert out["date"] == expected.isoformat()
        finally:
            db.close()

    def test_a_malformed_date_is_refused(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid)
            with pytest.raises(ValueError, match="2026-11-04"):
                habit_service.skip_habit(db, user, h.id, on="next tuesday")
        finally:
            db.close()


class TestWhatTheBoardIsTold:
    def test_progress_and_rest_reach_the_api(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, frequency="weekly", times_per_period=3)
            habit_service.check_in_habit(db, user, h.id)
            habit_service.skip_habit(db, user, h.id)
            [out] = habit_service.attach_adherence(db, user, [h])
            assert out.times_target == 3
            assert out.done_this_period == 1
            assert out.resting_today is True
        finally:
            db.close()

    def test_an_ordinary_habit_reports_one_and_no_rest(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid)
            [out] = habit_service.attach_adherence(db, user, [h])
            assert out.times_target == 1
            assert out.done_this_period == 0
            assert out.resting_today is False
        finally:
            db.close()


class TestChangingTheScheduleIsSafe:
    def test_the_occasion_key_is_cleared_when_the_schedule_changes(self):
        """A stored key would compare days against week numbers."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, frequency="daily")
            habit_service.check_in_habit(db, user, h.id)
            db.refresh(h)
            assert h.last_met_period is not None
            habit_service.update_habit(db, user, h.id, frequency="weekly")
            db.refresh(h)
            assert h.last_met_period is None
        finally:
            db.close()

    def test_the_run_survives_a_schedule_change(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, frequency="daily")
            habit_service.check_in_habit(db, user, h.id)
            db.refresh(h)
            before = h.streak
            habit_service.update_habit(db, user, h.id, frequency="weekly")
            db.refresh(h)
            assert h.streak == before
        finally:
            db.close()


class TestRestingIsNotNagged:
    """Being nudged about a day you deliberately took off is the same noise
    the reminder work was about, wearing a different hat."""

    def _ctx(self, db, user):
        from services import nudges
        return nudges.build_context(db, user, datetime.now(timezone.utc))

    def test_a_resting_habit_is_not_outstanding(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, name="Run")
            assert any(x.id == h.id for x in self._ctx(db, user).habits_pending)
            habit_service.skip_habit(db, user, h.id)
            assert not any(x.id == h.id
                           for x in self._ctx(db, user).habits_pending)
        finally:
            db.close()

    def test_a_habit_not_due_today_is_not_outstanding(self):
        """A Mon/Thu habit was counted pending all seven days."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            today = datetime.now(timezone.utc).date()
            not_today = ",".join(
                str(d) for d in range(7) if d != today.weekday())
            h = _habit(db, uid, name="Gym", frequency="weekly",
                       weekdays=not_today)
            assert not any(x.id == h.id
                           for x in self._ctx(db, user).habits_pending)
        finally:
            db.close()


class TestAlfredCanDoItToo:
    """The web API and Alfred must call the same code, or they will disagree
    about the same habit."""

    def _run(self, db, user, name, args):
        from services import alfred_tools
        return alfred_tools.execute_tool(db, user, name, args)

    def test_he_can_offer_a_rest_day(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, name="Run")
            out = self._run(db, user, "rest_habit",
                            {"habit_id": h.id, "note": "ill"})
            assert out["resting"] is True
            assert habit_service.recent_adherence(db, user, h)["window"] == 13

            back = self._run(db, user, "unrest_habit", {"habit_id": h.id})
            assert back["was_resting"] is True
        finally:
            db.close()

    def test_he_can_create_three_times_a_week(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            out = self._run(db, user, "create_habit", {
                "name": "Gym", "frequency": "weekly", "times_per_period": 3})
            assert out["habit"]["times_per_period"] == 3
        finally:
            db.close()

    def test_he_cannot_set_days_and_a_count_at_once(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            with pytest.raises(ValueError, match="not both"):
                self._run(db, user, "create_habit", {
                    "name": "Gym", "frequency": "weekly",
                    "weekdays": "0,3", "times_per_period": 3})
        finally:
            db.close()

    def test_a_rest_on_someone_elses_habit_is_refused(self):
        mine, theirs = _mk_user(), _mk_user()
        db = SessionLocal()
        try:
            other = db.get(models.BatAccount, theirs)
            h = _habit(db, mine, name="Private")
            out = self._run(db, other, "rest_habit", {"habit_id": h.id})
            assert out == {"error": "Habit not found"}
        finally:
            db.close()
