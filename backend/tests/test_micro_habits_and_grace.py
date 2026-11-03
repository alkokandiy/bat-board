"""Shrink the habit instead of losing it.

Two mechanisms from the owner's research, both aimed at the same failure:
a partial miss read as total failure, and the whole thing abandoned.

- A **grace period**: one missed period inside a run no longer ends it,
  provided the habit is otherwise being kept. A count that can only ever go
  to zero is one people walk away from after the first blameless gap.
- A **minimum viable** version: the two-minute form, in the user's own
  words. Doing it still starts the cue and closes the reward, and that loop
  is the thing being built — whether the run was five miles or putting the
  shoes on.

Neither touches what a check-in earns. The reward still follows recent
adherence, and `best_streak` is still never reset.
"""

from datetime import datetime, timedelta, timezone

import pytest

import models
from database import SessionLocal
from services import habit_service, nudges

_n = [991000]


def _mk_user():
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"mg{_n[0]}", hashed_password="x",
                              timezone="UTC", alfred_address="Master Wayne")
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _habit(db, uid, **kw):
    kw.setdefault("name", "Press-ups")
    h = models.BatHabit(owner_id=uid, frequency="daily", **kw)
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


def _history(db, habit, days_ago_list):
    """Completion log entries, so recent_adherence has something to read."""
    for d in days_ago_list:
        db.add(models.HabitCompletionLog(
            habit_id=habit.id,
            completed_at=(datetime.now(timezone.utc) - timedelta(days=d)).replace(tzinfo=None)))
    db.commit()


class TestGrace:
    def test_an_unbroken_run_still_just_counts_up(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, streak=4,
                       last_completed=(datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None))
            _history(db, h, [1, 2, 3, 4])
            habit_service.check_in_habit(db, user, h.id)
            db.refresh(h)
            assert h.streak == 5
            assert h.grace_used_in_run == 0
        finally:
            db.close()

    def test_one_missed_day_no_longer_destroys_a_run(self):
        """The blameless Tuesday."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, streak=20,
                       last_completed=(datetime.now(timezone.utc) - timedelta(days=2)).replace(tzinfo=None))
            _history(db, h, [2, 3, 4, 5, 6, 7, 8, 9])
            habit_service.check_in_habit(db, user, h.id)
            db.refresh(h)
            assert h.streak == 21
            assert h.grace_used_in_run == 1
        finally:
            db.close()

    def test_the_allowance_is_one_and_then_the_run_really_does_end(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, streak=20, grace_used_in_run=1,
                       last_completed=(datetime.now(timezone.utc) - timedelta(days=2)).replace(tzinfo=None))
            _history(db, h, [2, 3, 4, 5, 6, 7, 8, 9])
            habit_service.check_in_habit(db, user, h.id)
            db.refresh(h)
            assert h.streak == 1
            assert h.grace_used_in_run == 0
        finally:
            db.close()

    def test_a_clean_period_restores_the_allowance(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, streak=10, grace_used_in_run=1,
                       last_completed=(datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None))
            _history(db, h, [1, 2, 3, 4, 5])
            habit_service.check_in_habit(db, user, h.id)
            db.refresh(h)
            assert h.streak == 11
            assert h.grace_used_in_run == 0
        finally:
            db.close()

    def test_a_long_gap_is_not_forgiven(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, streak=20,
                       last_completed=(datetime.now(timezone.utc) - timedelta(days=9)).replace(tzinfo=None))
            _history(db, h, [9, 10, 11, 12, 13])
            habit_service.check_in_habit(db, user, h.id)
            db.refresh(h)
            assert h.streak == 1
        finally:
            db.close()

    def test_a_habit_barely_kept_gets_no_protection(self):
        """Otherwise the run becomes a participation trophy."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, streak=1,
                       last_completed=(datetime.now(timezone.utc) - timedelta(days=2)).replace(tzinfo=None))
            _history(db, h, [2])           # one in fourteen: well under the floor
            habit_service.check_in_habit(db, user, h.id)
            db.refresh(h)
            assert h.streak == 1
            assert h.grace_used_in_run == 0
        finally:
            db.close()

    def test_grace_never_touches_the_best_run(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, streak=3, best_streak=40,
                       last_completed=(datetime.now(timezone.utc) - timedelta(days=9)).replace(tzinfo=None))
            _history(db, h, [9, 10, 11])
            habit_service.check_in_habit(db, user, h.id)
            db.refresh(h)
            assert h.streak == 1
            assert h.best_streak == 40
        finally:
            db.close()

    def test_the_reward_still_follows_adherence_and_not_the_run(self):
        """Grace must not become a way to mint points."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid, streak=20,
                       last_completed=(datetime.now(timezone.utc) - timedelta(days=2)).replace(tzinfo=None))
            _history(db, h, [2, 3])        # a long run, but thin recent adherence
            before = user.points
            habit_service.check_in_habit(db, user, h.id)
            db.refresh(user)
            # 5 + min(adherence.done, 10). Three distinct periods once today
            # is counted, so well under what a 21-day run would imply.
            assert before < user.points <= before + 9
        finally:
            db.close()


class TestTheSmallerVersion:
    def test_it_is_stored_and_returned(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = habit_service.create_habit(
                db, user, name="Run", cue="after coffee",
                minimum_viable="put the shoes on")
            assert h.minimum_viable == "put the shoes on"
        finally:
            db.close()

    def test_blank_is_stored_as_nothing_rather_than_an_empty_string(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = habit_service.create_habit(db, user, name="Run", minimum_viable="   ")
            assert h.minimum_viable is None
        finally:
            db.close()

    def test_it_can_be_added_later(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            h = _habit(db, uid)
            habit_service.update_habit(db, user, h.id, minimum_viable="five of them")
            db.refresh(h)
            assert h.minimum_viable == "five of them"
        finally:
            db.close()


class TestHeOffersIt:
    def _ctx(self, db, uid):
        return nudges.build_context(db, db.get(models.BatAccount, uid),
                                    datetime.now(timezone.utc))

    def test_a_habit_rarely_kept_is_offered_a_smaller_version(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            h = _habit(db, uid, name="Five-mile run")
            _history(db, h, [1, 9])        # 2 of the last 14
            n = nudges.sig_shrink_the_habit(self._ctx(db, uid))
            assert n is not None
            assert n.kind == "offer_shrink"
            assert "Five-mile run" in n.facts
        finally:
            db.close()

    def test_one_already_going_well_is_left_alone(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            h = _habit(db, uid)
            _history(db, h, list(range(1, 13)))
            assert nudges.sig_shrink_the_habit(self._ctx(db, uid)) is None
        finally:
            db.close()

    def test_one_that_already_has_a_floor_is_not_asked_again(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            h = _habit(db, uid, minimum_viable="one press-up")
            _history(db, h, [1, 9])
            assert nudges.sig_shrink_the_habit(self._ctx(db, uid)) is None
        finally:
            db.close()

    def test_a_brand_new_habit_has_not_failed_at_anything(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            _habit(db, uid)                # no history at all
            assert nudges.sig_shrink_the_habit(self._ctx(db, uid)) is None
        finally:
            db.close()

    def test_he_is_told_to_ask_rather_than_invent_the_small_version(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            h = _habit(db, uid)
            _history(db, h, [1, 9])
            w = nudges.sig_shrink_the_habit(self._ctx(db, uid)).warrant.lower()
            assert "ask them what the smallest version is" in w
            assert "do not invent one" in w
            assert "not a person who lacks resolve" in w
        finally:
            db.close()
