"""The board must mean what it says.

Three failures from one afternoon on the work track:

- "add work task, priclist button creation" drew "I have added... you now have
  four new items", naming three things that had never been created. The next
  list showed them missing.
- "mark it done" completed the right task AND quietly removed a neighbouring
  one, so a nine-item list became seven.
- Ten hours of real work across two days could not be recorded at all, because
  focus only existed as a timer running at the time.

Once someone cannot trust the list, the board stops being worth keeping.
"""

from datetime import datetime, timedelta, timezone

import pytest

import models
from database import SessionLocal
from services import alfred_agent, alfred_tools, focus_service, work_service

_n = [990000]


def _mk_user():
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"bi{_n[0]}", hashed_password="x",
                              timezone="UTC", alfred_address="Master Wayne",
                              work_enabled=True)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


# --- acting on the right record -------------------------------------------

def test_completing_the_wrong_task_is_refused():
    """A nine-item list became seven: "mark it done" landed on a neighbour too."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        right = work_service.create_task(db, user, title="intercompany produkt sonlar")
        wrong = work_service.create_task(db, user, title="takliflarni pastga o'tkazib qo'yish POS")

        out = alfred_agent.wrong_target(db, user, "complete_work_task", {
            "task_id": wrong.id,
            "expected_title": "intercompany produkt sonlar"})
        assert out is not None and "WRONG TARGET" in out["error"]

        # The right one passes untouched.
        assert alfred_agent.wrong_target(db, user, "complete_work_task", {
            "task_id": right.id,
            "expected_title": "intercompany produkt sonlar"}) is None
    finally:
        db.close()


def test_every_targeted_mutation_can_state_its_target():
    """Miss one and that tool keeps the old act-on-a-guessed-id behaviour."""
    for tool in alfred_tools.ALL_TOOLS:
        if tool["name"] not in alfred_tools.TARGETED_TOOL_NAMES:
            continue
        schema = tool.get("parameters") or tool.get("input_schema") or {}
        assert "expected_title" in schema.get("properties", {}), tool["name"]


def test_the_resolver_knows_every_targeted_tool():
    """An unresolvable target would silently skip the check entirely."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        m = models.BatMission(owner_id=uid, title="A mission", status="pending")
        h = models.BatHabit(owner_id=uid, name="A habit", frequency="daily")
        note = models.BatNote(owner_id=uid, title="A note")
        db.add_all([m, h, note])
        db.flush()
        t = work_service.create_task(db, user, title="A work task")
        db.commit()

        cases = {
            "complete_mission": ({"mission_id": m.id}, "A mission"),
            "update_mission": ({"mission_id": m.id}, "A mission"),
            "check_in_habit": ({"habit_id": h.id}, "A habit"),
            "update_habit": ({"habit_id": h.id}, "A habit"),
            "update_note": ({"note_id": note.id}, "A note"),
            "complete_work_task": ({"task_id": t.id}, "A work task"),
            "update_work_task": ({"task_id": t.id}, "A work task"),
        }
        assert set(cases) == alfred_tools.TARGETED_TOOL_NAMES
        for name, (args, title) in cases.items():
            assert alfred_tools.describe_tool_target(db, user, name, args) == title, name
    finally:
        db.close()


def test_the_charter_forbids_reporting_a_change_that_did_not_happen():
    """"I have added... four new items" when one call was made."""
    prompt = alfred_agent.IDENTITY_CORE.lower()
    assert "never report a change you did not just make" in prompt
    assert "counts come from the tool" in prompt


# --- recording work that already happened ----------------------------------

def _hours_ago(h):
    return datetime.now(timezone.utc) - timedelta(hours=h)


def test_focus_can_be_logged_after_the_fact():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        task = work_service.create_task(db, user, title="fix discrepency")
        s = focus_service.log_past_session(db, user, minutes=120,
                                           when=_hours_ago(26),
                                           work_task_id=task.id)
        assert s.duration_minutes == 120
        assert s.logged_manually is True
        assert s.end_time > s.start_time
    finally:
        db.close()


def test_backfilled_work_hours_reach_the_work_report():
    """Every work report read zero hours however much was actually done."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        task = work_service.create_task(db, user, title="create stock guard")
        focus_service.log_past_session(db, user, minutes=120,
                                       when=datetime.now(timezone.utc) - timedelta(hours=3),
                                       work_task_id=task.id)
        report = work_service.build_report(db, user, "today")
        assert report["minutes"] >= 120
    finally:
        db.close()


def test_backfilled_time_credits_the_mission_it_belongs_to():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        m = models.BatMission(owner_id=uid, title="Write the thing", status="pending")
        db.add(m)
        db.commit()
        focus_service.log_past_session(db, user, minutes=90, when=_hours_ago(5),
                                       mission_id=m.id)
        db.refresh(m)
        assert m.focus_minutes == 90
    finally:
        db.close()


def test_backfilled_time_awards_no_points():
    """Points are a record of what happened, not a claim that can be typed in."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        before = user.points
        focus_service.log_past_session(db, user, minutes=120, when=_hours_ago(4))
        db.refresh(user)
        assert user.points == before
    finally:
        db.close()


@pytest.mark.parametrize("kwargs, fragment", [
    ({"minutes": 2}, "at least"),
    ({"minutes": 20 * 60}, "hours in one entry"),
])
def test_implausible_entries_are_refused(kwargs, fragment):
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        with pytest.raises(ValueError) as exc:
            focus_service.log_past_session(db, user, when=_hours_ago(2), **kwargs)
        assert fragment in str(exc.value)
    finally:
        db.close()


def test_the_future_cannot_be_logged_as_focus():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        with pytest.raises(ValueError) as exc:
            focus_service.log_past_session(
                db, user, minutes=60,
                when=datetime.now(timezone.utc) + timedelta(days=1))
        assert "future" in str(exc.value)
    finally:
        db.close()


def test_a_session_belongs_to_one_thing_only():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        m = models.BatMission(owner_id=uid, title="M", status="pending")
        h = models.BatHabit(owner_id=uid, name="H", frequency="daily")
        db.add_all([m, h])
        db.commit()
        with pytest.raises(ValueError) as exc:
            focus_service.log_past_session(db, user, minutes=30, when=_hours_ago(2),
                                           mission_id=m.id, habit_id=h.id)
        assert "one thing" in str(exc.value)
    finally:
        db.close()


def test_backfilling_onto_someone_elses_record_is_refused():
    mine, theirs = _mk_user(), _mk_user()
    db = SessionLocal()
    try:
        m = models.BatMission(owner_id=theirs, title="Not yours", status="pending")
        db.add(m)
        db.commit()
        with pytest.raises(ValueError) as exc:
            focus_service.log_past_session(db, db.get(models.BatAccount, mine),
                                           minutes=30, when=_hours_ago(2),
                                           mission_id=m.id)
        assert "not found" in str(exc.value).lower()
    finally:
        db.close()
