"""A dead reminder becomes a question, once.

Phase 0 stopped the repeating. On its own that would be worse than before:
the reminder simply goes quiet and nobody says why, which looks like the app
forgetting rather than the app noticing.

So Alfred raises it — exactly once per reminder, as the user's own data and
not as a failing — and he can see the record before he opens his mouth.
"""

from datetime import datetime, timedelta, timezone

import pytest

import models
from database import SessionLocal
from services import alfred_tools, nudges, reminder_feedback

_n = [998000]


def _mk_user():
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"rc{_n[0]}", hashed_password="x",
                              timezone="UTC", alfred_address="Master Wayne")
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _reminder(db, owner_id, suspended=False, ignored=0):
    r = models.BatReminder(owner_id=owner_id, message="Take the medicine",
                           recurrence="daily", send_time="21:00", enabled=True,
                           consecutive_ignored=ignored)
    if suspended:
        r.suspended_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _ctx(db, uid):
    user = db.get(models.BatAccount, uid)
    return nudges.build_context(db, user, datetime.now(timezone.utc))


class TestHeNoticesAndSaysSo:
    def test_a_suspended_reminder_produces_a_nudge(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            _reminder(db, uid, suspended=True, ignored=11)
            n = nudges.sig_reminder_not_working(_ctx(db, uid))
            assert n is not None
            assert n.kind == "reminder_dead"
            assert "11" in n.facts
            assert "medicine" in n.facts
        finally:
            db.close()

    def test_a_healthy_reminder_produces_nothing(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            _reminder(db, uid, suspended=False)
            assert nudges.sig_reminder_not_working(_ctx(db, uid)) is None
        finally:
            db.close()

    def test_the_warrant_tells_him_to_blame_the_cue_and_not_the_person(self):
        """Motivational Interviewing, not a telling-off."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            _reminder(db, uid, suspended=True, ignored=5)
            n = nudges.sig_reminder_not_working(_ctx(db, uid))
            w = n.warrant.lower()
            assert "their data, not their failing" in w
            assert "drop it" in w          # retiring it is a good answer
            assert "do not argue" in w
        finally:
            db.close()

    def test_it_can_only_ever_fire_once_per_reminder(self):
        """The key is the occasion, and bat_nudge_log makes it unique."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            r = _reminder(db, uid, suspended=True, ignored=3)
            n = nudges.sig_reminder_not_working(_ctx(db, uid))
            assert n.key == f"reminder_dead:{r.id}"
        finally:
            db.close()

    def test_another_persons_dead_reminder_is_not_his_business(self):
        mine, theirs = _mk_user(), _mk_user()
        db = SessionLocal()
        try:
            _reminder(db, mine, suspended=True, ignored=4)
            assert nudges.sig_reminder_not_working(_ctx(db, theirs)) is None
        finally:
            db.close()


class TestNotTwoAtOnce:
    # Both of these pin one reference moment and place the reminder relative
    # to IT. Timestamping from the real clock while evaluating at a fixed
    # hour makes the gap negative for half the day, which looks like a pass.
    REF = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)

    def _reminder_sent(self, db, uid, minutes_ago):
        r = _reminder(db, uid)
        sent = self.REF - timedelta(minutes=minutes_ago)
        db.add(models.BatReminderLog(
            reminder_id=r.id, owner_id=uid,
            local_date=sent.date().isoformat(), sent_at=sent.replace(tzinfo=None)))
        db.commit()
        return r

    def test_a_nudge_waits_after_a_reminder_has_just_gone_out(self):
        """The reminder was asked for. The nudge beside it was not."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            self._reminder_sent(db, uid, minutes_ago=2)
            assert nudges.may_nudge(db, user, self.REF) is False
        finally:
            db.close()

    def test_an_old_reminder_does_not_hold_him_back_for_ever(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            self._reminder_sent(db, uid, minutes_ago=6 * 60)
            assert nudges.may_nudge(db, user, self.REF) is True
        finally:
            db.close()

    def test_the_boundary_is_where_it_says_it_is(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            just_inside = int(nudges.REMINDER_QUIET.total_seconds() // 60) - 1
            self._reminder_sent(db, uid, minutes_ago=just_inside)
            assert nudges.may_nudge(db, user, self.REF) is False
        finally:
            db.close()


class TestWhatHeCanLookUp:
    def test_he_can_read_the_record(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            r = _reminder(db, uid)
            for d in range(4):
                when = datetime.now(timezone.utc) - timedelta(days=d)
                db.add(models.BatReminderLog(
                    reminder_id=r.id, owner_id=uid,
                    local_date=when.date().isoformat(),
                    sent_at=when.replace(tzinfo=None),
                    outcome="done" if d == 3 else None))
            db.commit()

            out = alfred_tools.execute_tool(db, user, "reminder_history",
                                            {"reminder_id": r.id})
            assert out["summary"]["sent"] == 4
            assert out["summary"]["ignored"] == 3
            assert out["summary"]["done"] == 1
        finally:
            db.close()

    def test_the_list_shows_him_which_ones_are_dead(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            _reminder(db, uid, suspended=True, ignored=6)
            out = alfred_tools.execute_tool(db, user, "list_reminders", {})
            assert out["reminders"][0]["suspended"] is True
            assert out["reminders"][0]["consecutive_ignored"] == 6
        finally:
            db.close()

    def test_resuming_clears_the_suspension_and_the_count(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            r = _reminder(db, uid, suspended=True, ignored=9)
            out = alfred_tools.execute_tool(db, user, "resume_reminder",
                                            {"reminder_id": r.id})
            assert out["resumed"] is True
            db.refresh(r)
            assert r.suspended_at is None and r.consecutive_ignored == 0
        finally:
            db.close()

    def test_he_cannot_resume_someone_elses(self):
        mine, theirs = _mk_user(), _mk_user()
        db = SessionLocal()
        try:
            other = db.get(models.BatAccount, theirs)
            r = _reminder(db, mine, suspended=True)
            out = alfred_tools.execute_tool(db, other, "resume_reminder",
                                            {"reminder_id": r.id})
            assert "error" in out
            db.refresh(r)
            assert r.suspended_at is not None
        finally:
            db.close()

    def test_history_for_a_reminder_with_nothing_recorded_says_so(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            r = _reminder(db, uid)
            out = alfred_tools.execute_tool(db, user, "reminder_history",
                                            {"reminder_id": r.id})
            assert "error" in out
        finally:
            db.close()
