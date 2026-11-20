"""Phase 23 — the day drawn as blocks against an hour scale.

The point of the strip is the gaps: unlogged time shows as a visible hole,
which invites backfill without anything nagging. That only works if the
blocks are placed in the user's own day, so the placement is computed here
rather than in the browser — these columns are naive UTC and the day is
theirs, so a block at 23:30 belongs to a different date depending on who
is looking.
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import models
from database import SessionLocal
from services import focus_service

_n = [995000]


def _mk_user(tz="UTC"):
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"fd{_n[0]}", hashed_password="x", timezone=tz)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _session(db, owner_id, start: datetime, end, **kw):
    """start/end as aware UTC; stored naive, as the column is."""
    s = models.BatFocus(
        owner_id=owner_id,
        start_time=start.astimezone(timezone.utc).replace(tzinfo=None),
        end_time=(end.astimezone(timezone.utc).replace(tzinfo=None)
                  if end is not None else None),
        duration_minutes=(round((end - start).total_seconds() / 60)
                          if end is not None else None),
        **kw)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_a_block_is_placed_at_the_minute_it_started():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _session(db, uid, datetime(2026, 2, 10, 9, 0, tzinfo=timezone.utc),
                 datetime(2026, 2, 10, 9, 45, tzinfo=timezone.utc))
        out = focus_service.day_timeline(db, user, date(2026, 2, 10))
        block = out["sessions"][0]
        assert block["start_minute"] == 540          # 09:00
        assert block["end_minute"] == 585            # 09:45
        assert block["minutes"] == 45
    finally:
        db.close()


def test_the_scale_is_their_midnight_not_utcs():
    """The same instant sits at a different place on a Tashkent day."""
    uid = _mk_user(tz="Asia/Tashkent")               # UTC+5
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        # 09:00Z is 14:00 in Tashkent.
        _session(db, uid, datetime(2026, 2, 10, 9, 0, tzinfo=timezone.utc),
                 datetime(2026, 2, 10, 10, 0, tzinfo=timezone.utc))
        out = focus_service.day_timeline(db, user, date(2026, 2, 10))
        assert out["sessions"][0]["start_minute"] == 840      # 14:00, not 09:00
    finally:
        db.close()


def test_a_block_crossing_midnight_appears_on_both_days_as_the_part_that_happened():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _session(db, uid, datetime(2026, 2, 10, 23, 0, tzinfo=timezone.utc),
                 datetime(2026, 2, 11, 1, 0, tzinfo=timezone.utc))

        first = focus_service.day_timeline(db, user, date(2026, 2, 10))["sessions"][0]
        assert (first["start_minute"], first["end_minute"]) == (1380, 1440)

        second = focus_service.day_timeline(db, user, date(2026, 2, 11))["sessions"][0]
        assert (second["start_minute"], second["end_minute"]) == (0, 60)

        # The clipped bar is one hour on each day; the session is still two.
        assert first["minutes"] == second["minutes"] == 120
    finally:
        db.close()


def test_yesterdays_blocks_are_not_on_todays_strip():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _session(db, uid, datetime(2026, 2, 9, 9, 0, tzinfo=timezone.utc),
                 datetime(2026, 2, 9, 10, 0, tzinfo=timezone.utc))
        assert focus_service.day_timeline(db, user, date(2026, 2, 10))["sessions"] == []
    finally:
        db.close()


def test_the_total_is_the_time_that_fell_on_this_day():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _session(db, uid, datetime(2026, 2, 10, 9, 0, tzinfo=timezone.utc),
                 datetime(2026, 2, 10, 10, 0, tzinfo=timezone.utc))
        _session(db, uid, datetime(2026, 2, 10, 23, 0, tzinfo=timezone.utc),
                 datetime(2026, 2, 11, 1, 0, tzinfo=timezone.utc))
        out = focus_service.day_timeline(db, user, date(2026, 2, 10))
        assert out["total_minutes"] == 120           # 60 + the hour before midnight
    finally:
        db.close()


def test_a_running_session_is_drawn_up_to_now():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        started = datetime.now(timezone.utc) - timedelta(minutes=30)
        _session(db, uid, started, None)
        out = focus_service.day_timeline(db, user)        # today
        block = next(b for b in out["sessions"] if b["running"])
        assert block["end_minute"] >= block["start_minute"] + 29
        assert block["end_minute"] <= out["now_minute"] + 1
    finally:
        db.close()


def test_there_is_no_now_line_on_a_day_that_is_not_today():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        past = focus_service.day_timeline(db, user, date(2026, 2, 10))
        assert past["now_minute"] is None
        today = focus_service.day_timeline(db, user)
        assert isinstance(today["now_minute"], int)
    finally:
        db.close()


def test_an_unfinished_session_from_a_past_day_does_not_smear_across_today():
    """A tab left open overnight has no end. Drawn naively it would run
    from its start to now and cover every day in between."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _session(db, uid, datetime(2026, 2, 1, 9, 0, tzinfo=timezone.utc), None)
        out = focus_service.day_timeline(db, user)        # today, years later
        assert out["sessions"] == []
    finally:
        db.close()


def test_a_block_is_named_by_what_it_was_spent_on():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        m = models.BatMission(owner_id=uid, title="Read Kahf surah")
        h = models.BatHabit(owner_id=uid, name="Press-ups")
        db.add_all([m, h])
        db.commit()
        _session(db, uid, datetime(2026, 2, 10, 9, 0, tzinfo=timezone.utc),
                 datetime(2026, 2, 10, 9, 30, tzinfo=timezone.utc), mission_id=m.id)
        _session(db, uid, datetime(2026, 2, 10, 11, 0, tzinfo=timezone.utc),
                 datetime(2026, 2, 10, 11, 30, tzinfo=timezone.utc), habit_id=h.id)
        _session(db, uid, datetime(2026, 2, 10, 13, 0, tzinfo=timezone.utc),
                 datetime(2026, 2, 10, 13, 30, tzinfo=timezone.utc))
        got = {(b["type"], b["name"]) for b in
               focus_service.day_timeline(db, user, date(2026, 2, 10))["sessions"]}
        assert got == {("mission", "Read Kahf surah"), ("habit", "Press-ups"),
                       ("none", None)}
    finally:
        db.close()


def test_work_time_is_named_rather_than_left_anonymous():
    """Work is a separate track and earns no points — but it is still time
    that went somewhere, and an unlabelled block is the hole this strip
    exists to make visible."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        t = models.BatWorkTask(owner_id=uid, title="Quarterly report")
        db.add(t)
        db.commit()
        _session(db, uid, datetime(2026, 2, 10, 9, 0, tzinfo=timezone.utc),
                 datetime(2026, 2, 10, 10, 0, tzinfo=timezone.utc), work_task_id=t.id)
        block = focus_service.day_timeline(db, user, date(2026, 2, 10))["sessions"][0]
        assert block["type"] == "work"
        assert block["name"] == "Quarterly report"
    finally:
        db.close()


def test_blocks_come_back_in_the_order_they_happened():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        for hour in (15, 9, 12):
            _session(db, uid, datetime(2026, 2, 10, hour, 0, tzinfo=timezone.utc),
                     datetime(2026, 2, 10, hour, 30, tzinfo=timezone.utc))
        starts = [b["start_minute"] for b in
                  focus_service.day_timeline(db, user, date(2026, 2, 10))["sessions"]]
        assert starts == sorted(starts)
    finally:
        db.close()


def test_another_users_day_is_not_mine():
    mine, theirs = _mk_user(), _mk_user()
    db = SessionLocal()
    try:
        me = db.get(models.BatAccount, mine)
        _session(db, theirs, datetime(2026, 2, 10, 9, 0, tzinfo=timezone.utc),
                 datetime(2026, 2, 10, 10, 0, tzinfo=timezone.utc))
        assert focus_service.day_timeline(db, me, date(2026, 2, 10))["sessions"] == []
    finally:
        db.close()


def test_a_block_pointing_at_someone_elses_mission_is_not_named():
    """The name is read back through an owner-scoped query, so a dangling
    or foreign link loses the name rather than leaking one."""
    mine, theirs = _mk_user(), _mk_user()
    db = SessionLocal()
    try:
        me = db.get(models.BatAccount, mine)
        their_mission = models.BatMission(owner_id=theirs, title="Their private work")
        db.add(their_mission)
        db.commit()
        _session(db, mine, datetime(2026, 2, 10, 9, 0, tzinfo=timezone.utc),
                 datetime(2026, 2, 10, 10, 0, tzinfo=timezone.utc),
                 mission_id=their_mission.id)
        block = focus_service.day_timeline(db, me, date(2026, 2, 10))["sessions"][0]
        assert block["name"] is None
        assert "Their private work" not in str(block)
    finally:
        db.close()


def test_a_zero_length_block_is_not_drawn():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        at = datetime(2026, 2, 10, 9, 0, tzinfo=timezone.utc)
        _session(db, uid, at, at)
        assert focus_service.day_timeline(db, user, date(2026, 2, 10))["sessions"] == []
    finally:
        db.close()


def test_an_empty_day_is_an_empty_day_not_an_error():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        out = focus_service.day_timeline(db, user, date(2026, 2, 10))
        assert out["sessions"] == []
        assert out["total_minutes"] == 0
        assert out["date"] == "2026-02-10"
    finally:
        db.close()
