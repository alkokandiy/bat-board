"""Two things the website could not see.

**A running session only existed in the browser.** The id, whether it was
running, how much was left — all React state. A reload lost the lot while
the row here stayed open, so the clock vanished from the screen and the
time was either credited to a session nobody could see or swept up as
abandoned hours later. The server is the only place the session actually
exists, so it has to be recoverable from here.

**Habit time only ever went up.** `focus_minutes` is a lifetime total,
which answers "how much have I ever put into this" — not the question in
front of someone deciding whether today is done. It also never went down,
so the number grew for ever and meant less each day.
"""

from datetime import datetime, timedelta, timezone

import pytest

import models
from database import SessionLocal
from services import focus_service, habit_service

_n = [967000]


@pytest.fixture(autouse=True)
def _no_sessions_left_running():
    """Clear up after each test.

    These tests deliberately leave focus sessions OPEN, which is the state
    being tested. The cron tick scans every user's open sessions and
    auto-ends the ones whose time is up, so leaving them behind made a
    scheduler test in another module count sessions this module created —
    passing alone and failing in the full run.
    """
    yield
    db = SessionLocal()
    try:
        ids = [r[0] for r in db.query(models.BatAccount.id)
               .filter(models.BatAccount.username.like("fr%")).all()]
        if ids:
            db.query(models.BatFocus).filter(
                models.BatFocus.owner_id.in_(ids)).delete(synchronize_session=False)
            db.commit()
    finally:
        db.close()


def _mk_user(tz="UTC"):
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"fr{_n[0]}", hashed_password="x", timezone=tz)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _habit(db, uid, **kw):
    kw.setdefault("name", "Pentest 101")
    kw.setdefault("frequency", "daily")
    h = models.BatHabit(owner_id=uid, **kw)
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


def _session(db, uid, *, habit_id=None, start, minutes, ended=True):
    s = models.BatFocus(
        owner_id=uid, habit_id=habit_id,
        start_time=start.replace(tzinfo=None),
        end_time=(start + timedelta(minutes=minutes)).replace(tzinfo=None) if ended else None,
        duration_minutes=minutes if ended else None,
        planned_minutes=minutes,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


class TestPickingTheClockBackUp:
    def test_nothing_running_says_so(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            assert focus_service.active_session_state(db, user) == {"active": False}
        finally:
            db.close()

    def test_a_running_session_comes_back_with_its_clock(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            started = datetime.now(timezone.utc) - timedelta(minutes=6)
            s = _session(db, uid, start=started, minutes=25, ended=False)

            state = focus_service.active_session_state(db, user)
            assert state["active"] is True
            assert state["id"] == s.id
            assert state["planned_minutes"] == 25
            # Six minutes gone, nineteen to go — within a second of it.
            assert abs(state["elapsed_seconds"] - 360) <= 2
            assert abs(state["remaining_seconds"] - (25 * 60 - 360)) <= 2
        finally:
            db.close()

    def test_elapsed_is_wall_clock_not_what_the_tab_watched(self):
        """A tab that was closed for ten minutes did not pause the session."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            _session(db, uid, start=datetime.now(timezone.utc) - timedelta(minutes=40),
                     minutes=25, ended=False)
            state = focus_service.active_session_state(db, user)
            assert state["elapsed_seconds"] >= 40 * 60 - 2
            assert state["remaining_seconds"] == 0, "a finished clock has nothing left"
        finally:
            db.close()

    def test_an_untimed_session_has_no_remaining(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            s = models.BatFocus(owner_id=uid, start_time=datetime.now(timezone.utc).replace(tzinfo=None))
            db.add(s)
            db.commit()
            state = focus_service.active_session_state(db, user)
            assert state["active"] is True
            assert state["remaining_seconds"] is None
        finally:
            db.close()

    def test_it_carries_what_the_session_was_on(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid)
            _session(db, uid, habit_id=h.id,
                     start=datetime.now(timezone.utc), minutes=25, ended=False)
            assert focus_service.active_session_state(db, user)["habit_id"] == h.id
        finally:
            db.close()

    def test_someone_elses_session_is_not_yours(self):
        mine, theirs = _mk_user(), _mk_user()
        db = SessionLocal()
        try:
            other = db.get(models.BatAccount, theirs)
            _session(db, mine, start=datetime.now(timezone.utc), minutes=25, ended=False)
            assert focus_service.active_session_state(db, other) == {"active": False}
        finally:
            db.close()

    def test_a_finished_session_is_not_running(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            _session(db, uid, start=datetime.now(timezone.utc) - timedelta(minutes=30),
                     minutes=25, ended=True)
            assert focus_service.active_session_state(db, user)["active"] is False
        finally:
            db.close()


class TestTimeOnAHabitThisPeriod:
    def test_it_counts_what_was_focused_today(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid)
            _session(db, uid, habit_id=h.id,
                     start=datetime.now(timezone.utc) - timedelta(hours=1), minutes=26)
            [out] = habit_service.attach_adherence(db, user, [h])
            assert out.focus_minutes_period == 26
        finally:
            db.close()

    def test_yesterday_does_not_count_toward_today(self):
        """The whole point: the number starts again when the period does."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid)
            _session(db, uid, habit_id=h.id,
                     start=datetime.now(timezone.utc) - timedelta(days=1), minutes=45)
            [out] = habit_service.attach_adherence(db, user, [h])
            assert out.focus_minutes_period == 0
        finally:
            db.close()

    def test_a_weekly_habit_counts_the_whole_week(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, name="Weekly", frequency="weekly")
            now = datetime.now(timezone.utc)
            # Yesterday is the same weekly occasion unless today is Monday.
            _session(db, uid, habit_id=h.id, start=now, minutes=20)
            [out] = habit_service.attach_adherence(db, user, [h])
            assert out.focus_minutes_period >= 20
        finally:
            db.close()

    def test_two_sessions_today_add_up(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid)
            now = datetime.now(timezone.utc)
            _session(db, uid, habit_id=h.id, start=now - timedelta(hours=2), minutes=10)
            _session(db, uid, habit_id=h.id, start=now - timedelta(hours=1), minutes=16)
            [out] = habit_service.attach_adherence(db, user, [h])
            assert out.focus_minutes_period == 26
        finally:
            db.close()

    def test_a_session_still_running_is_not_counted_yet(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid)
            _session(db, uid, habit_id=h.id, start=datetime.now(timezone.utc),
                     minutes=25, ended=False)
            [out] = habit_service.attach_adherence(db, user, [h])
            assert out.focus_minutes_period == 0
        finally:
            db.close()

    def test_another_habit_s_time_is_not_borrowed(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            mine = _habit(db, uid, name="Mine")
            other = _habit(db, uid, name="Other")
            _session(db, uid, habit_id=other.id,
                     start=datetime.now(timezone.utc), minutes=30)
            rows = habit_service.attach_adherence(db, user, [mine, other])
            by_name = {h.name: h.focus_minutes_period for h in rows}
            assert by_name == {"Mine": 0, "Other": 30}
        finally:
            db.close()

    def test_the_lifetime_total_is_still_there(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, focus_minutes=500)
            [out] = habit_service.attach_adherence(db, user, [h])
            assert out.focus_minutes == 500
            assert out.focus_minutes_period == 0
        finally:
            db.close()
