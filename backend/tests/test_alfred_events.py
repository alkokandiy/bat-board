"""Alfred's half of the calendar.

Two failures, both invisible from the web UI:

- He is told the time as the user's local wall clock ("2:47 AM, Asia/Tashkent,
  UTC+05:00") and the tool only says "ISO datetime", so he writes back a naive
  local time. It was stored as though it were UTC, which silently moved every
  event he created by the user's offset — five hours, for a Tashkent account.
- `list_upcoming_events` returned EVERY event the account has ever had, past
  included, under a name and description that both say "upcoming". With a real
  calendar that is a context flood AND an invitation to call last March's
  dentist appointment the next thing coming up.
"""

from datetime import datetime, timedelta, timezone

import pytest

import models
from database import SessionLocal
from services import alfred_tools, calendar_service

_n = [995000]


def _mk_user(tz="Asia/Tashkent"):
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"ae{_n[0]}", hashed_password="x", timezone=tz)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _run(db, user, name, args):
    return alfred_tools.execute_tool(db, user, name, args)


class TestTheTimeHeMeans:
    def test_a_naive_time_is_the_users_own_clock(self):
        """"Three in the afternoon" means three where they are."""
        uid = _mk_user("Asia/Tashkent")  # UTC+5, no DST
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            _run(db, user, "create_event",
                 {"title": "Dentist", "start_time": "2026-11-10T15:00:00"})

            [stored] = calendar_service.list_all_events(db, user)
            as_utc = stored.start_time.replace(tzinfo=timezone.utc) \
                if stored.start_time.tzinfo is None else stored.start_time
            # 15:00 in Tashkent is 10:00 UTC. Stored as 15:00 UTC, the user
            # would open their board and find it at 8pm.
            assert as_utc.astimezone(timezone.utc).hour == 10
        finally:
            db.close()

    def test_an_explicit_offset_is_respected(self):
        uid = _mk_user("Asia/Tashkent")
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            _run(db, user, "create_event",
                 {"title": "Call", "start_time": "2026-11-10T15:00:00+00:00"})
            [stored] = calendar_service.list_all_events(db, user)
            as_utc = stored.start_time.replace(tzinfo=timezone.utc) \
                if stored.start_time.tzinfo is None else stored.start_time
            assert as_utc.astimezone(timezone.utc).hour == 15
        finally:
            db.close()

    def test_a_z_suffix_is_respected(self):
        uid = _mk_user("Asia/Tashkent")
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            _run(db, user, "create_event",
                 {"title": "Call", "start_time": "2026-11-10T15:00:00Z"})
            [stored] = calendar_service.list_all_events(db, user)
            as_utc = stored.start_time.replace(tzinfo=timezone.utc) \
                if stored.start_time.tzinfo is None else stored.start_time
            assert as_utc.astimezone(timezone.utc).hour == 15
        finally:
            db.close()

    def test_the_end_time_moves_with_it(self):
        uid = _mk_user("Asia/Tashkent")
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            _run(db, user, "create_event", {
                "title": "Workshop",
                "start_time": "2026-11-10T09:00:00",
                "end_time": "2026-11-10T17:00:00",
            })
            [stored] = calendar_service.list_all_events(db, user)
            end = stored.end_time.replace(tzinfo=timezone.utc) \
                if stored.end_time.tzinfo is None else stored.end_time
            assert end.astimezone(timezone.utc).hour == 12
        finally:
            db.close()

    def test_editing_uses_the_same_clock(self):
        uid = _mk_user("Asia/Tashkent")
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            created = _run(db, user, "create_event",
                           {"title": "Dentist", "start_time": "2026-11-10T15:00:00"})
            _run(db, user, "update_event",
                 {"event_id": created["event"]["id"], "start_time": "2026-11-10T16:00:00"})
            [stored] = calendar_service.list_all_events(db, user)
            as_utc = stored.start_time.replace(tzinfo=timezone.utc) \
                if stored.start_time.tzinfo is None else stored.start_time
            assert as_utc.astimezone(timezone.utc).hour == 11
        finally:
            db.close()

    def test_a_utc_account_is_unaffected(self):
        uid = _mk_user("UTC")
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            _run(db, user, "create_event",
                 {"title": "Dentist", "start_time": "2026-11-10T15:00:00"})
            [stored] = calendar_service.list_all_events(db, user)
            as_utc = stored.start_time.replace(tzinfo=timezone.utc) \
                if stored.start_time.tzinfo is None else stored.start_time
            assert as_utc.astimezone(timezone.utc).hour == 15
        finally:
            db.close()


class TestWhatHeIsShown:
    def _three_events(self, db, user):
        now = datetime.now(timezone.utc)
        for title, when in [
            ("Long gone", now - timedelta(days=200)),
            ("Last week", now - timedelta(days=7)),
            ("Tomorrow", now + timedelta(days=1)),
            ("Next month", now + timedelta(days=30)),
        ]:
            calendar_service.create_event(db, user, title=title, start_time=when)

    def test_upcoming_means_upcoming(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            self._three_events(db, user)
            out = _run(db, user, "list_upcoming_events", {})
            titles = [e["title"] for e in out["events"]]
            assert "Tomorrow" in titles
            assert "Long gone" not in titles
            assert "Last week" not in titles
        finally:
            db.close()

    def test_an_event_running_right_now_still_counts(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            now = datetime.now(timezone.utc)
            calendar_service.create_event(
                db, user, title="In progress",
                start_time=now - timedelta(hours=1), end_time=now + timedelta(hours=1))
            out = _run(db, user, "list_upcoming_events", {})
            assert [e["title"] for e in out["events"]] == ["In progress"]
        finally:
            db.close()

    def test_a_window_narrows_it(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            self._three_events(db, user)
            out = _run(db, user, "list_upcoming_events", {"days": 7})
            titles = [e["title"] for e in out["events"]]
            assert titles == ["Tomorrow"]
        finally:
            db.close()

    def test_the_past_is_available_when_asked_for(self):
        """"What did I have last week" is a fair question."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            self._three_events(db, user)
            out = _run(db, user, "list_upcoming_events", {"include_past": True})
            titles = [e["title"] for e in out["events"]]
            assert "Last week" in titles and "Long gone" in titles
        finally:
            db.close()

    def test_he_is_told_the_local_time_not_only_the_instant(self):
        """Otherwise he has to do offset arithmetic to answer "when?"."""
        uid = _mk_user("Asia/Tashkent")
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            _run(db, user, "create_event",
                 {"title": "Dentist", "start_time": "2026-11-10T15:00:00"})
            out = _run(db, user, "list_upcoming_events", {"include_past": True})
            assert out["events"][0]["starts"] == "2026-11-10 15:00"
        finally:
            db.close()


class TestTheOtherInstants:
    """Countdowns and backfilled focus had the same naive-time problem.

    `log_past_focus`'s own schema already promised "in the user's own
    timezone"; the code read it as UTC, so the promise was not kept.
    """

    def test_a_countdown_target_is_their_clock(self):
        uid = _mk_user("Asia/Tashkent")
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            _run(db, user, "create_countdown",
                 {"title": "Launch", "target_date": "2027-01-01T00:00:00"})
            [c] = db.query(models.BatCountdown).filter_by(owner_id=uid).all()
            target = c.target_date.replace(tzinfo=timezone.utc) \
                if c.target_date.tzinfo is None else c.target_date
            # Midnight in Tashkent is 19:00 the day before, UTC.
            assert target.astimezone(timezone.utc).strftime("%Y-%m-%d %H") == "2026-12-31 19"
        finally:
            db.close()

    def test_moving_a_countdown_uses_the_same_clock(self):
        uid = _mk_user("Asia/Tashkent")
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            created = _run(db, user, "create_countdown",
                           {"title": "Launch", "target_date": "2027-01-01T00:00:00"})
            _run(db, user, "update_countdown",
                 {"countdown_id": created["countdown"]["id"],
                  "target_date": "2027-02-01T00:00:00"})
            [c] = db.query(models.BatCountdown).filter_by(owner_id=uid).all()
            target = c.target_date.replace(tzinfo=timezone.utc) \
                if c.target_date.tzinfo is None else c.target_date
            assert target.astimezone(timezone.utc).strftime("%Y-%m-%d %H") == "2027-01-31 19"
        finally:
            db.close()

    def test_backfilled_focus_lands_at_the_hour_they_said(self):
        uid = _mk_user("Asia/Tashkent")
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            _run(db, user, "log_past_focus",
                 {"minutes": 60, "when": "2026-10-17T14:00:00"})
            [f] = db.query(models.BatFocus).filter_by(owner_id=uid).all()
            started = f.start_time.replace(tzinfo=timezone.utc) \
                if f.start_time.tzinfo is None else f.start_time
            # 14:00 in Tashkent is 09:00 UTC.
            assert started.astimezone(timezone.utc).hour == 9
        finally:
            db.close()
