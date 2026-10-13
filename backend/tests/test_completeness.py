"""Loose ends: items missing the one field that gives them traction.

Half-filled items are the reason things get forgotten — a mission with no
date never feels urgent, a habit with no moment attached depends on
remembering. This module finds exactly those two gaps and the cold notes, and
deliberately ignores every decorative field, because pestering someone to
fill in tags is the behaviour the rest of Alfred's design avoids.
"""

from datetime import datetime, timedelta, timezone

import models
from database import SessionLocal
from services import completeness

_n = [900000]


def _mk_user():
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"lc{_n[0]}", hashed_password="x",
                              timezone="UTC", alfred_address="Master Wayne")
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _naive(dt):
    return dt.replace(tzinfo=None)


def _old(days):
    return _naive(datetime.now(timezone.utc) - timedelta(days=days))


# --- missions --------------------------------------------------------------

def test_a_settled_mission_with_no_date_is_a_loose_end():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatMission(owner_id=uid, title="Mission Statement",
                                 status="pending", created_at=_old(10)))
        db.commit()
        out = completeness.review(db, user)
        titles = [i["title"] for i in out["missions_without_a_date"]["items"]]
        assert titles == ["Mission Statement"]
        assert out["missions_without_a_date"]["items"][0]["age_days"] >= 9
    finally:
        db.close()


def test_a_mission_created_minutes_ago_is_left_alone():
    """Not yet forgotten — it has not had a chance to be finished."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatMission(owner_id=uid, title="Just added",
                                 status="pending", created_at=_naive(datetime.now(timezone.utc))))
        db.commit()
        assert completeness.review(db, user)["missions_without_a_date"]["items"] == []
    finally:
        db.close()


def test_a_mission_that_already_has_a_date_is_not_a_loose_end():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatMission(owner_id=uid, title="Dated", status="pending",
                                 created_at=_old(10), due_date=_old(-3)))
        db.commit()
        assert completeness.review(db, user)["missions_without_a_date"]["items"] == []
    finally:
        db.close()


def test_completed_and_dismissed_missions_are_ignored():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatMission(owner_id=uid, title="Done", status="completed",
                                 created_at=_old(10)))
        db.add(models.BatMission(owner_id=uid, title="Dropped", status="pending",
                                 is_dismissed=True, created_at=_old(10)))
        db.commit()
        assert completeness.review(db, user)["missions_without_a_date"]["items"] == []
    finally:
        db.close()


# --- habits ----------------------------------------------------------------

def test_a_habit_with_no_cue_is_a_loose_end_and_one_with_a_cue_is_not():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatHabit(owner_id=uid, name="Memorization", frequency="daily"))
        db.add(models.BatHabit(owner_id=uid, name="Math", frequency="daily",
                               cue="after breakfast"))
        db.commit()
        names = [i["name"] for i in completeness.review(db, user)["habits_without_a_cue"]["items"]]
        assert names == ["Memorization"]
    finally:
        db.close()


def test_a_whitespace_cue_does_not_count_as_a_cue():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatHabit(owner_id=uid, name="Blank", frequency="daily", cue="   "))
        db.commit()
        assert len(completeness.review(db, user)["habits_without_a_cue"]["items"]) == 1
    finally:
        db.close()


# --- notes -----------------------------------------------------------------

def test_a_cold_note_surfaces_but_a_pinned_or_recent_one_does_not():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatNote(owner_id=uid, title="Films to watch",
                              created_at=_old(90), updated_at=_old(60)))
        db.add(models.BatNote(owner_id=uid, title="Pinned thing", is_pinned=True,
                              created_at=_old(90), updated_at=_old(60)))
        db.add(models.BatNote(owner_id=uid, title="Touched yesterday",
                              created_at=_old(90), updated_at=_old(1)))
        db.commit()
        titles = [i["title"] for i in completeness.review(db, user)["notes_gone_cold"]["items"]]
        assert titles == ["Films to watch"]
    finally:
        db.close()


def test_alfreds_own_memory_notes_are_never_offered_back():
    """His record of them is not their writing, and not theirs to tidy."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatNote(owner_id=uid, title="What I know", tags="alfred-memory",
                              created_at=_old(90), updated_at=_old(60)))
        db.commit()
        assert completeness.review(db, user)["notes_gone_cold"]["items"] == []
    finally:
        db.close()


# --- shape -----------------------------------------------------------------

def test_everything_is_scoped_to_its_owner():
    mine, theirs = _mk_user(), _mk_user()
    db = SessionLocal()
    try:
        db.add(models.BatMission(owner_id=theirs, title="Not mine",
                                 status="pending", created_at=_old(10)))
        db.add(models.BatHabit(owner_id=theirs, name="Not mine either",
                               frequency="daily"))
        db.commit()
        out = completeness.review(db, db.get(models.BatAccount, mine))
        assert out["total"] == 0
    finally:
        db.close()


def test_the_result_carries_the_reason_and_the_question_not_just_a_list():
    """Alfred reasons from these; a bare list would make him recite again."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        out = completeness.review(db, user)
        for kind in ("missions_without_a_date", "habits_without_a_cue", "notes_gone_cold"):
            assert out[kind]["why"] and out[kind]["question"] and out[kind]["fix"]
        assert "OFFERS, never demands" in out["note"]
        assert "leave it" in out["note"].lower()
    finally:
        db.close()


def test_a_long_list_is_capped_so_it_is_never_an_audit():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        for i in range(12):
            db.add(models.BatMission(owner_id=uid, title=f"Thing {i}",
                                     status="pending", created_at=_old(10)))
        db.commit()
        items = completeness.review(db, user)["missions_without_a_date"]["items"]
        assert len(items) == completeness.MAX_PER_KIND
    finally:
        db.close()
