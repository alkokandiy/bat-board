"""The corporate / work track.

The load-bearing tests here are the SEPARATION ones: work must never award Bat
Points, never appear among personal missions, and never reach briefings or
Alfred's proactive check-ins.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import models
from database import SessionLocal
from services import alfred_tools, briefings, focus_service, nudges, work_service

_n = [950000]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _mk_user():
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"wk{_n[0]}", hashed_password="x",
                              work_enabled=True,
                              timezone="UTC", alfred_address="Master Wayne", points=0)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _tool(uid, name, args=None):
    db = SessionLocal()
    try:
        return alfred_tools.execute_tool(db, db.get(models.BatAccount, uid), name, args or {})
    finally:
        db.close()


# --- separation (the point of the whole feature) ---------------------------

def test_work_tasks_never_appear_among_personal_missions():
    uid = _mk_user()
    _tool(uid, "create_work_task", {"title": "Ship client invoice"})
    _tool(uid, "create_mission", {"title": "Read 20 pages"})

    missions = _tool(uid, "list_missions", {"status": "all"})
    titles = [m["title"] for m in missions["missions"]]
    assert "Read 20 pages" in titles
    assert "Ship client invoice" not in titles
    assert missions["counts"]["total"] == 1          # work is not counted


def test_completing_work_awards_no_bat_points():
    uid = _mk_user()
    t = _tool(uid, "create_work_task", {"title": "Deploy release"})["work_task"]
    out = _tool(uid, "complete_work_task", {"task_id": t["id"]})
    assert out["points_awarded"] == 0
    db = SessionLocal()
    try:
        assert db.get(models.BatAccount, uid).points == 0
    finally:
        db.close()


def test_focus_on_work_logs_time_but_awards_no_points():
    uid = _mk_user()
    t = _tool(uid, "create_work_task", {"title": "Refactor billing"})["work_task"]
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        s = models.BatFocus(owner_id=uid, work_task_id=t["id"],
                            start_time=datetime.now(timezone.utc) - timedelta(minutes=40))
        db.add(s)
        db.commit()
        db.refresh(s)
        ended = focus_service.end_focus_session(db, user, s.id)
        assert ended.duration_minutes >= 5
    finally:
        db.close()
    db = SessionLocal()
    try:
        assert db.get(models.BatAccount, uid).points == 0          # job isn't scored
        assert db.get(models.BatWorkTask, t["id"]).focus_minutes >= 5   # time still counted
    finally:
        db.close()


def test_work_is_absent_from_briefings_and_nudges():
    uid = _mk_user()
    for i in range(4):
        _tool(uid, "create_work_task", {"title": f"Work item {i}"})
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        data = briefings.gather_briefing_data(db, user, "morning")
        assert data["due"] == [] and data["overdue"] == []
        text = briefings.render_template(user, "morning", data)
        assert "Work item" not in text
        # the proactive engine sees no personal work to nag about either
        ctx = nudges.build_context(db, user, datetime.now(timezone.utc).replace(hour=16))
        assert ctx.open_missions == []
    finally:
        db.close()


# --- task flow -------------------------------------------------------------

def test_status_flow_and_completion_timestamp():
    uid = _mk_user()
    t = _tool(uid, "create_work_task", {"title": "Spec review", "project": "Atlas"})["work_task"]
    assert t["status"] == "todo" and t["project"] == "Atlas"

    doing = _tool(uid, "update_work_task", {"task_id": t["id"], "status": "doing"})["work_task"]
    assert doing["status"] == "doing" and doing["completed_at"] is None

    blocked = _tool(uid, "update_work_task", {"task_id": t["id"], "status": "blocked"})["work_task"]
    assert blocked["status"] == "blocked"

    done = _tool(uid, "complete_work_task", {"task_id": t["id"]})["work_task"]
    assert done["status"] == "done" and done["completed_at"] is not None


def test_bulk_create_skips_duplicates():
    uid = _mk_user()
    res = _tool(uid, "create_work_tasks", {"tasks": [
        {"title": "Standup notes"}, {"title": "standup  notes"}, {"title": "Vendor call"},
    ]})
    assert res["created_count"] == 2 and len(res["skipped_duplicates"]) == 1


def test_list_defaults_to_open_with_counts():
    uid = _mk_user()
    a = _tool(uid, "create_work_task", {"title": "A"})["work_task"]
    _tool(uid, "create_work_task", {"title": "B", "status": "blocked"})
    _tool(uid, "complete_work_task", {"task_id": a["id"]})

    listed = _tool(uid, "list_work_tasks", {})
    assert [t["title"] for t in listed["work_tasks"]] == ["B"]     # done hidden
    assert listed["counts"]["blocked"] == 1
    assert len(_tool(uid, "list_work_tasks", {"include_done": True})["work_tasks"]) == 2


# --- journal + reports -----------------------------------------------------

def test_journal_is_separate_from_personal_notes():
    uid = _mk_user()
    _tool(uid, "log_work_note", {"content": "Learned the deploy pipeline", "kind": "learning"})
    assert len(_tool(uid, "list_work_notes", {"kind": "learning"})["work_notes"]) == 1
    # personal notes are untouched
    assert _tool(uid, "list_notes", {})["notes"] == []


def test_report_covers_work_only_and_asks_for_reflection():
    uid = _mk_user()
    t = _tool(uid, "create_work_task", {"title": "Close Q3 books"})["work_task"]
    _tool(uid, "complete_work_task", {"task_id": t["id"]})
    _tool(uid, "create_work_task", {"title": "Waiting on legal", "status": "blocked"})
    _tool(uid, "log_work_note", {"content": "Legal sign-off takes 3 days", "kind": "learning"})
    _tool(uid, "create_mission", {"title": "Personal thing"})

    out = _tool(uid, "work_report", {"period": "today"})
    report = out["report"]
    assert "Close Q3 books" in report
    assert "Waiting on legal" in report and "Blocked" in report
    assert "Legal sign-off takes 3 days" in report
    assert "Personal thing" not in report          # personal stays out
    assert report.rstrip().endswith("?")           # ends by asking
    assert "log_work_note" in out["next_step"]


def test_report_counts_work_days_without_being_told():
    uid = _mk_user()
    _tool(uid, "create_work_task", {"title": "Today's thing"})
    db = SessionLocal()
    try:
        data = work_service.build_report(db, db.get(models.BatAccount, uid), "week")
        assert len(data["work_days"]) == 1         # inferred from activity
    finally:
        db.close()


def test_empty_report_is_honest():
    uid = _mk_user()
    report = _tool(uid, "work_report", {"period": "month"})["report"]
    assert "Nothing on the work ledger" in report


def test_bad_period_rejected():
    uid = _mk_user()
    assert "error" in _tool(uid, "work_report", {"period": "quarter"})
