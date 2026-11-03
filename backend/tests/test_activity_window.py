"""Context we can actually observe.

"I was just working, in the job and in personal missions. I don't know how I
could have, or no idea how to fix it."

Recording time required remembering to start a timer before the work, or
remembering afterwards to say so. Both are acts of memory, and memory is the
thing that failed — so the board read zero for a month of real work.

The research's answer is a context engine fed by biometrics and geofencing,
which this product does not have and will not get. But the database is full
of timestamped evidence that a person was there: their own messages, focus
sessions, work notes, habit check-ins. That is enough to notice a day with
plenty of evidence of a person and none of their work, and to ask about it
with the specifics in hand.

What it must never do is turn absence into a claim about the person. A quiet
stretch means the app saw nothing, not that they were resting.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

import models
from database import SessionLocal
from services import activity

_n = [999000]


def _mk_user(tz="UTC"):
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"aw{_n[0]}", hashed_password="x", timezone=tz)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


TODAY = date(2026, 11, 3)


def _at(hour, minute=0):
    """A naive-UTC stamp on TODAY, as stored."""
    return datetime(TODAY.year, TODAY.month, TODAY.day, hour, minute)


_sessions = {}


def _session(db, uid):
    """Messages hang off a session; one per user is enough here."""
    if uid not in _sessions:
        sess = models.BatAlfredSession(owner_id=uid, title="probe")
        db.add(sess)
        db.commit()
        db.refresh(sess)
        _sessions[uid] = sess.id
    return _sessions[uid]


def _msg(db, uid, hour, minute=0, role="user"):
    db.add(models.BatAlfredMessage(owner_id=uid, role=role, content="x",
                                   session_id=_session(db, uid),
                                   created_at=_at(hour, minute)))
    db.commit()


def _focus(db, uid, hour, minutes):
    db.add(models.BatFocus(owner_id=uid, start_time=_at(hour),
                           end_time=_at(hour) + timedelta(minutes=minutes),
                           duration_minutes=minutes))
    db.commit()


class TestWhatTheRecordShows:
    def test_a_day_with_no_trace_is_simply_unobserved(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            w = activity.observed_day(db, db.get(models.BatAccount, uid), TODAY)
            assert w.observed is False
            assert w.span_minutes == 0
            assert w.unaccounted_minutes == 0
        finally:
            db.close()

    def test_first_and_last_trace_bound_the_day(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            _msg(db, uid, 9, 12)
            _msg(db, uid, 13, 30)
            _msg(db, uid, 18, 40)
            w = activity.observed_day(db, db.get(models.BatAccount, uid), TODAY)
            assert w.first_seen.strftime("%H:%M") == "09:12"
            assert w.last_seen.strftime("%H:%M") == "18:40"
            assert w.signals == 3
        finally:
            db.close()

    def test_alfreds_own_replies_prove_nothing(self):
        """A briefing fires into an empty room as happily as a full one."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            _msg(db, uid, 6, 0, role="assistant")
            _msg(db, uid, 23, 0, role="assistant")
            w = activity.observed_day(db, db.get(models.BatAccount, uid), TODAY)
            assert w.observed is False
        finally:
            db.close()

    def test_recorded_focus_reduces_what_is_unaccounted_for(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            _msg(db, uid, 9)
            _msg(db, uid, 17)
            _focus(db, uid, 10, 240)
            w = activity.observed_day(db, db.get(models.BatAccount, uid), TODAY)
            assert w.span_minutes == 8 * 60
            assert w.tracked_minutes == 240
            assert w.unaccounted_minutes == 240
        finally:
            db.close()

    def test_more_tracked_than_span_never_goes_negative(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            _msg(db, uid, 9)
            _focus(db, uid, 9, 600)
            w = activity.observed_day(db, db.get(models.BatAccount, uid), TODAY)
            assert w.unaccounted_minutes == 0
        finally:
            db.close()

    def test_a_habit_check_in_counts_as_evidence_of_a_person(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            h = models.BatHabit(owner_id=uid, name="Press-ups", frequency="daily")
            db.add(h)
            db.commit()
            db.add(models.HabitCompletionLog(habit_id=h.id, completed_at=_at(7, 15)))
            db.commit()
            w = activity.observed_day(db, db.get(models.BatAccount, uid), TODAY)
            assert w.signals == 1
            assert w.first_seen.strftime("%H:%M") == "07:15"
        finally:
            db.close()

    def test_a_work_note_counts_too(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            db.add(models.BatWorkNote(owner_id=uid, content="shipped it",
                                      created_at=_at(16, 5)))
            db.commit()
            w = activity.observed_day(db, db.get(models.BatAccount, uid), TODAY)
            assert w.signals == 1
        finally:
            db.close()

    def test_another_persons_day_is_not_mine(self):
        mine, theirs = _mk_user(), _mk_user()
        db = SessionLocal()
        try:
            _msg(db, theirs, 10)
            w = activity.observed_day(db, db.get(models.BatAccount, mine), TODAY)
            assert w.observed is False
        finally:
            db.close()

    def test_the_day_is_the_users_own_day(self):
        """23:30 in Tashkent is 18:30 UTC — the same day for them, not for UTC."""
        uid = _mk_user("Asia/Tashkent")
        db = SessionLocal()
        try:
            _msg(db, uid, 18, 30)   # stored UTC
            w = activity.observed_day(db, db.get(models.BatAccount, uid), TODAY)
            assert w.last_seen.strftime("%H:%M") == "23:30"
        finally:
            db.close()


class TestNoticingAnUntrackedDay:
    def test_a_full_day_about_with_nothing_recorded_is_worth_asking_about(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            for h in (9, 12, 15, 18):
                _msg(db, uid, h)
            w = activity.observed_day(db, db.get(models.BatAccount, uid), TODAY)
            assert activity.looks_like_an_untracked_day(w)
        finally:
            db.close()

    def test_one_stray_message_is_not_a_working_day(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            _msg(db, uid, 9)
            _msg(db, uid, 21)
            w = activity.observed_day(db, db.get(models.BatAccount, uid), TODAY)
            # A wide span, but almost no evidence of what happened between.
            assert w.signals < activity.MIN_SIGNALS_FOR_A_DAY
            assert not activity.looks_like_an_untracked_day(w)
        finally:
            db.close()

    def test_a_day_already_accounted_for_is_left_alone(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            for h in (9, 12, 15, 17):
                _msg(db, uid, h)
            _focus(db, uid, 9, 8 * 60)
            w = activity.observed_day(db, db.get(models.BatAccount, uid), TODAY)
            assert not activity.looks_like_an_untracked_day(w)
        finally:
            db.close()

    def test_a_short_errand_is_not_an_untracked_day(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            for m in (0, 20, 40):
                _msg(db, uid, 10, m)
            w = activity.observed_day(db, db.get(models.BatAccount, uid), TODAY)
            assert w.unaccounted_minutes < activity.MIN_GAP_WORTH_MENTIONING
            assert not activity.looks_like_an_untracked_day(w)
        finally:
            db.close()

    def test_a_quiet_day_is_never_read_as_a_restful_one(self):
        """No evidence means we do not know. It must not become a claim."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            w = activity.observed_day(db, db.get(models.BatAccount, uid), TODAY)
            assert not activity.looks_like_an_untracked_day(w)
            assert w.summary()["observed"] is False
        finally:
            db.close()


# --- what Alfred does with it ---------------------------------------------

class TestHeAsksOnce:
    """The nudge built on the window above."""

    def _ctx(self, db, uid, at_hour=20):
        from datetime import datetime as _dt
        from services import nudges
        user = db.get(models.BatAccount, uid)
        now = _dt.now(timezone.utc).replace(hour=at_hour, minute=0)
        return nudges.build_context(db, user, now)

    def _busy_today(self, db, uid):
        """Traces across today, with no focus recorded."""
        from datetime import datetime as _dt
        base = _dt.now(timezone.utc)
        sid = _session(db, uid)
        for h in (9, 12, 15, 18):
            db.add(models.BatAlfredMessage(
                owner_id=uid, role="user", content="x", session_id=sid,
                created_at=base.replace(hour=h, minute=0, tzinfo=None)))
        db.commit()

    def test_a_busy_untracked_day_is_raised_in_the_evening(self):
        from services import nudges
        uid = _mk_user()
        db = SessionLocal()
        try:
            self._busy_today(db, uid)
            n = nudges.sig_untracked_day(self._ctx(db, uid, at_hour=20))
            assert n is not None
            assert n.kind == "offer_reconstruct"
            assert "unaccounted" in n.facts
        finally:
            db.close()

    def test_nothing_is_said_mid_morning(self):
        """There is nothing to reconstruct while the day is still happening."""
        from services import nudges
        uid = _mk_user()
        db = SessionLocal()
        try:
            self._busy_today(db, uid)
            assert nudges.sig_untracked_day(self._ctx(db, uid, at_hour=11)) is None
        finally:
            db.close()

    def test_a_quiet_day_is_left_completely_alone(self):
        from services import nudges
        uid = _mk_user()
        db = SessionLocal()
        try:
            assert nudges.sig_untracked_day(self._ctx(db, uid, at_hour=20)) is None
        finally:
            db.close()

    def test_the_warrant_forbids_treating_the_window_as_a_claim(self):
        from services import nudges
        uid = _mk_user()
        db = SessionLocal()
        try:
            self._busy_today(db, uid)
            n = nudges.sig_untracked_day(self._ctx(db, uid, at_hour=20))
            w = n.warrant.lower()
            assert "never present the observed window as a claim" in w
            assert "do not imply they were idle" in w
            assert "ask once" in w
        finally:
            db.close()

    def test_it_is_keyed_to_the_day_so_it_cannot_repeat(self):
        from services import nudges
        uid = _mk_user()
        db = SessionLocal()
        try:
            self._busy_today(db, uid)
            n = nudges.sig_untracked_day(self._ctx(db, uid, at_hour=20))
            assert n.key.startswith("untracked:")
        finally:
            db.close()
