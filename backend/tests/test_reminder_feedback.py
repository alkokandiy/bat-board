"""A reminder that nobody answers must stop asking.

The owner's medicine reminder fired every evening for a month. He took none
of them. It kept going, unchanged, because the system had no way to know:
`BatReminderLog` recorded `sent_at` and nothing else, the message carried no
buttons, and `_fire_reminders` fired on schedule for ever.

A cue that fires and is never closed by a reward does not stay neutral — the
association is trained away, and repeating the cue unchanged accelerates it.
These cover the return path and what the scheduler does with it.
"""

from datetime import datetime, timedelta, timezone

import pytest

import models
from database import SessionLocal
from services import reminder_feedback

_n = [996000]


def _mk_user():
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"rf{_n[0]}", hashed_password="x", timezone="UTC")
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _reminder(db, owner_id, message="Take the medicine"):
    r = models.BatReminder(owner_id=owner_id, message=message,
                           recurrence="daily", send_time="21:00", enabled=True)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _sent(db, reminder, owner_id, days_ago=0, outcome=None):
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    row = models.BatReminderLog(
        reminder_id=reminder.id, owner_id=owner_id,
        local_date=when.date().isoformat(), sent_at=when.replace(tzinfo=None),
        outcome=outcome)
    db.add(row)
    db.commit()
    return row


class TestAnswering:
    def test_done_is_recorded_against_the_latest_occurrence(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            r = _reminder(db, uid)
            _sent(db, r, uid, days_ago=1)
            _sent(db, r, uid, days_ago=0)

            row = reminder_feedback.record_outcome(db, user, r.id, "done")
            assert row.outcome == "done"
            assert row.responded_at is not None
            # The older one is untouched.
            assert reminder_feedback.summary(db, user, r.id)["ignored"] == 1
        finally:
            db.close()

    def test_an_unknown_outcome_is_refused(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            r = _reminder(db, uid)
            _sent(db, r, uid)
            with pytest.raises(ValueError, match="Unknown outcome"):
                reminder_feedback.record_outcome(db, user, r.id, "maybe")
        finally:
            db.close()

    def test_another_persons_reminder_cannot_be_answered(self):
        mine, theirs = _mk_user(), _mk_user()
        db = SessionLocal()
        try:
            other = db.get(models.BatAccount, theirs)
            r = _reminder(db, mine)
            _sent(db, r, mine)
            assert reminder_feedback.record_outcome(db, other, r.id, "done") is None
        finally:
            db.close()

    def test_answering_one_never_sent_is_a_no_op(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            r = _reminder(db, uid)
            assert reminder_feedback.record_outcome(db, user, r.id, "done") is None
        finally:
            db.close()

    def test_changing_the_answer_is_allowed(self):
        """Tapping "not today" and then doing it anyway is the truth later."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            r = _reminder(db, uid)
            _sent(db, r, uid)
            reminder_feedback.record_outcome(db, user, r.id, "skipped")
            row = reminder_feedback.record_outcome(db, user, r.id, "done")
            assert row.outcome == "done"
        finally:
            db.close()


class TestTheRunOfSilence:
    def test_silence_accumulates(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            r = _reminder(db, uid)
            reminder_feedback.note_unanswered(db, r)
            reminder_feedback.note_unanswered(db, r)
            assert r.consecutive_ignored == 2
            assert not reminder_feedback.is_suspended(r)
        finally:
            db.close()

    def test_a_run_suspends_it(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            r = _reminder(db, uid)
            for _ in range(reminder_feedback.IGNORED_LIMIT):
                reminder_feedback.note_unanswered(db, r)
            assert reminder_feedback.is_suspended(r)
        finally:
            db.close()

    def test_any_answer_clears_the_run(self):
        """"Not today" counts. It means the message arrived and was read."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            r = _reminder(db, uid)
            reminder_feedback.note_unanswered(db, r)
            reminder_feedback.note_unanswered(db, r)
            _sent(db, r, uid)

            reminder_feedback.record_outcome(db, user, r.id, "skipped")
            db.refresh(r)
            assert r.consecutive_ignored == 0
            assert not reminder_feedback.is_suspended(r)
        finally:
            db.close()

    def test_answering_un_suspends_it(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            r = _reminder(db, uid)
            for _ in range(reminder_feedback.IGNORED_LIMIT):
                reminder_feedback.note_unanswered(db, r)
            _sent(db, r, uid)
            reminder_feedback.record_outcome(db, user, r.id, "done")
            db.refresh(r)
            assert r.suspended_at is None
        finally:
            db.close()


class TestWhatAlfredCanSee:
    def test_silence_reads_as_ignored_not_as_success(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            r = _reminder(db, uid)
            for d in range(3):
                _sent(db, r, uid, days_ago=d)
            out = reminder_feedback.history(db, user, r.id)
            assert [h["outcome"] for h in out] == ["ignored", "ignored", "ignored"]
        finally:
            db.close()

    def test_the_summary_counts_the_month_he_described(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            r = _reminder(db, uid)
            for d in range(30):
                _sent(db, r, uid, days_ago=d)
            s = reminder_feedback.summary(db, user, r.id)
            assert s["sent"] == 30
            assert s["ignored"] == 30
            assert s["done"] == 0
        finally:
            db.close()

    def test_history_is_scoped_to_the_owner(self):
        mine, theirs = _mk_user(), _mk_user()
        db = SessionLocal()
        try:
            other = db.get(models.BatAccount, theirs)
            r = _reminder(db, mine)
            _sent(db, r, mine)
            assert reminder_feedback.history(db, other, r.id) == []
        finally:
            db.close()
