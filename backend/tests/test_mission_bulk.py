"""Bulk mission creation, duplicate-skipping, and the turn-summary fallback.

Covers the fixes for: adding many missions at once, Alfred duplicating
missions, and the repetitive "Done — anything else?" reply.
"""

import models
from database import SessionLocal
from services import alfred_tools, alfred_agent

_n = [500000]


def _mk_user():
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"mb{_n[0]}", hashed_password="x")
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _run(uid, name, args):
    db = SessionLocal()
    try:
        return alfred_tools.execute_tool(db, db.get(models.BatAccount, uid), name, args)
    finally:
        db.close()


def test_create_missions_batch_creates_all():
    uid = _mk_user()
    res = _run(uid, "create_missions", {"missions": [
        {"title": "Alpha"}, {"title": "Bravo", "priority": "high"}, {"title": "Charlie"},
    ]})
    assert res["created_count"] == 3
    assert res["skipped_duplicates"] == []

    db = SessionLocal()
    try:
        titles = {m.title for m in db.query(models.BatMission).filter_by(owner_id=uid)}
        assert titles == {"Alpha", "Bravo", "Charlie"}
    finally:
        db.close()


def test_create_missions_skips_in_batch_and_existing_duplicates():
    uid = _mk_user()
    # in-batch duplicate (different casing / spacing) is collapsed to one
    res = _run(uid, "create_missions", {"missions": [
        {"title": "Write report"}, {"title": "write  report"}, {"title": "Call bank"},
    ]})
    assert res["created_count"] == 2
    assert len(res["skipped_duplicates"]) == 1

    # a second batch that repeats an existing title skips it
    res2 = _run(uid, "create_missions", {"missions": [
        {"title": "Write Report"}, {"title": "New thing"},
    ]})
    assert res2["created_count"] == 1
    assert res2["skipped_duplicates"] == ["Write Report"]

    db = SessionLocal()
    try:
        assert db.query(models.BatMission).filter_by(owner_id=uid).count() == 3
    finally:
        db.close()


def test_single_create_mission_skips_duplicate():
    uid = _mk_user()
    first = _run(uid, "create_mission", {"title": "Patrol Gotham"})
    assert "mission" in first and not first.get("skipped")
    dup = _run(uid, "create_mission", {"title": "patrol gotham"})
    # Not a refusal: it hands back the existing mission so Alfred can enrich it.
    assert dup["created"] is False
    assert dup["existing_mission"]["title"] == "Patrol Gotham"
    db = SessionLocal()
    try:
        assert db.query(models.BatMission).filter_by(owner_id=uid).count() == 1
    finally:
        db.close()


def test_completed_mission_title_can_be_recreated():
    uid = _mk_user()
    m = _run(uid, "create_mission", {"title": "Ship v1"})
    _run(uid, "complete_mission", {"mission_id": m["mission"]["id"]})
    # once completed it's off the open board, so the title is free again
    again = _run(uid, "create_mission", {"title": "Ship v1"})
    assert "mission" in again and not again.get("skipped")


def test_list_missions_returns_everything():
    uid = _mk_user()
    _run(uid, "create_missions", {"missions": [{"title": f"M{i}"} for i in range(7)]})
    res = _run(uid, "list_missions", {})
    assert len(res["missions"]) == 7


def test_summary_is_varied_and_informative():
    # informative counts
    s = alfred_agent._summarize_turn([("create_missions", {"created_count": 6, "skipped_duplicates": ["a", "b"]})])
    assert "added 6" in s and "skipped 2" in s
    # opener comes from the varied set
    assert any(s.startswith(o) for o in alfred_agent._DONE_OPENERS)
    # empty turn keeps the gentle default
    assert alfred_agent._summarize_turn([]) == "Done — anything else?"
    # mixed
    s2 = alfred_agent._summarize_turn([
        ("complete_mission", {}), ("check_in_habit", {}), ("update_note", {}),
    ])
    assert "completed 1" in s2 and "checked in 1" in s2 and "updated 1" in s2


def test_list_missions_returns_deterministic_counts():
    uid = _mk_user()
    db = SessionLocal()
    try:
        for i in range(11):
            db.add(models.BatMission(owner_id=uid, title=f"P{i}", status="pending"))
        for i in range(3):
            db.add(models.BatMission(owner_id=uid, title=f"C{i}", status="completed"))
        db.add(models.BatMission(owner_id=uid, title="D", status="dismissed", is_dismissed=True))
        db.commit()
    finally:
        db.close()
    res = _run(uid, "list_missions", {})
    assert res["counts"] == {"pending": 11, "completed": 3, "dismissed": 1, "total": 15}
    assert res["showing"] == "pending"
    assert len(res["missions"]) == 11            # default shows pending only
    assert len(_run(uid, "list_missions", {"status": "all"})["missions"]) == 15
    assert len(_run(uid, "list_missions", {"status": "completed"})["missions"]) == 3
