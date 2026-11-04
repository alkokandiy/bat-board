"""A reminder can point at the thing it is about.

The research pass suggested putting "Start focus" on every reminder. The
owner pushed back and was right: most reminders are not work, and taking a
tablet is a minute long — under MIN_FOCUS_MINUTES, so it would never become
a session even if you tapped it.

The fix is not a button on every reminder, it is a reminder that knows what
it is for. Free text gets Done / Not today / Stop this; one pointing at a
mission, habit or work task also gets Start focus, because there is finally
somewhere real to attach the time.

And a habit reminder marked Done checks the habit in, so the board and the
reminder stop disagreeing about the same act.
"""

from datetime import datetime, timezone

import pytest

import models
from database import SessionLocal
from services import briefing_service, focus_service, reminder_feedback, scheduler

_n = [989000]


def _mk_user():
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"rl{_n[0]}", hashed_password="x",
                              timezone="UTC", work_enabled=True)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _mission(db, uid, title="Pricelist"):
    m = models.BatMission(owner_id=uid, title=title, status="pending")
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def _habit(db, uid, name="Press-ups"):
    h = models.BatHabit(owner_id=uid, name=name, frequency="daily")
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


class TestWhatAReminderCanOffer:
    def test_free_text_gets_no_focus_button(self):
        """"Take the medicine" is not a focus session."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            r = briefing_service.create_reminder(
                db, user, message="Take the medicine", recurrence="daily",
                send_time="21:00")
            assert reminder_feedback.can_start_focus(r) is False
            rows = scheduler._reminder_keyboard(r)["inline_keyboard"]
            assert len(rows) == 1
            assert [b["text"] for b in rows[0]] == ["Done", "Not today", "Stop this"]
        finally:
            db.close()

    def test_a_mission_reminder_can_start_the_work(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            m = _mission(db, uid)
            r = briefing_service.create_reminder(
                db, user, message="Work on the pricelist", recurrence="daily",
                send_time="09:00", mission_id=m.id)
            assert reminder_feedback.link_of(r) == ("mission", m.id)
            rows = scheduler._reminder_keyboard(r)["inline_keyboard"]
            assert len(rows) == 2
            assert rows[1][0]["text"] == "Start focus"
            assert rows[1][0]["callback_data"] == f"rem:focus:{r.id}"
        finally:
            db.close()

    def test_a_habit_reminder_can_too(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid)
            r = briefing_service.create_reminder(
                db, user, message="Press-ups", recurrence="daily",
                send_time="07:00", habit_id=h.id)
            assert reminder_feedback.link_of(r) == ("habit", h.id)
            assert reminder_feedback.can_start_focus(r) is True
        finally:
            db.close()


class TestTheLinkIsChecked:
    def test_someone_elses_mission_is_refused(self):
        mine, theirs = _mk_user(), _mk_user()
        db = SessionLocal()
        try:
            other = db.get(models.BatAccount, theirs)
            m = _mission(db, mine)
            with pytest.raises(ValueError, match="No such mission"):
                briefing_service.create_reminder(
                    db, other, message="Snoop", recurrence="daily",
                    send_time="09:00", mission_id=m.id)
        finally:
            db.close()

    def test_an_unknown_id_is_refused(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            with pytest.raises(ValueError, match="No such"):
                briefing_service.create_reminder(
                    db, user, message="Ghost", recurrence="daily",
                    send_time="09:00", mission_id=999999)
        finally:
            db.close()

    def test_two_links_at_once_are_refused(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            m, h = _mission(db, uid), _habit(db, uid)
            with pytest.raises(ValueError, match="one thing"):
                briefing_service.create_reminder(
                    db, user, message="Both", recurrence="daily",
                    send_time="09:00", mission_id=m.id, habit_id=h.id)
        finally:
            db.close()

    def test_a_rejected_link_leaves_the_reminder_unchanged(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            r = briefing_service.create_reminder(
                db, user, message="Original", recurrence="daily", send_time="21:00")
            with pytest.raises(ValueError):
                briefing_service.update_reminder(
                    db, user, r.id, message="Edited", mission_id=999999)
            db.refresh(r)
            assert r.message == "Original"
        finally:
            db.close()


class TestDoneFinishesTheThing:
    def test_done_on_a_habit_reminder_checks_the_habit_in(self):
        """Otherwise the reminder says done and the board says not kept."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid)
            r = briefing_service.create_reminder(
                db, user, message="Press-ups", recurrence="daily",
                send_time="07:00", habit_id=h.id)
            db.add(models.BatReminderLog(
                reminder_id=r.id, owner_id=uid,
                local_date=datetime.now(timezone.utc).date().isoformat()))
            db.commit()

            reminder_feedback.record_outcome(db, user, r.id, "done")
            assert reminder_feedback.check_in_linked_habit(db, user, r) == h.id
            db.refresh(h)
            assert h.last_completed is not None
            assert h.streak == 1
        finally:
            db.close()

    def test_done_on_a_plain_reminder_checks_nothing_in(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            r = briefing_service.create_reminder(
                db, user, message="Take the medicine", recurrence="daily",
                send_time="21:00")
            assert reminder_feedback.check_in_linked_habit(db, user, r) is None
        finally:
            db.close()

    def test_done_on_a_mission_reminder_does_not_complete_the_mission(self):
        """Doing some of the work is not finishing it. Only habits check in."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            m = _mission(db, uid)
            r = briefing_service.create_reminder(
                db, user, message="Pricelist", recurrence="daily",
                send_time="09:00", mission_id=m.id)
            assert reminder_feedback.check_in_linked_habit(db, user, r) is None
            db.refresh(m)
            assert m.status == "pending"
        finally:
            db.close()


class TestStartingTheSession:
    def test_the_session_is_attached_to_what_the_reminder_points_at(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            m = _mission(db, uid)
            r = briefing_service.create_reminder(
                db, user, message="Pricelist", recurrence="daily",
                send_time="09:00", mission_id=m.id)
            kind, target = reminder_feedback.link_of(r)
            session = focus_service.start_focus_session(db, user, **{f"{kind}_id": target})
            assert session.mission_id == m.id
            assert session.end_time is None
        finally:
            db.close()
