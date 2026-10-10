"""The work track over HTTP, and the switch that turns the whole side off.

Two promises are tested here above all:

1. **Disabling is clean.** With the track off the entire API answers 409 and the
   status endpoint reports `enabled: false`, so the UI has one thing to read and
   the sidebar simply isn't rendered. Nothing half-shown.
2. **Disabling is not deletion.** Turn it off, turn it back on, everything is
   exactly where it was.

Plus the rule that must survive every refactor: finishing work awards no Bat
Points.
"""

from datetime import datetime, timezone

import models
from database import SessionLocal
from routers.work import WORK_OFF_DETAIL
from services import alfred_tools, nudges, scheduler, work_service

OFF_ROUTES = [
    ("get", "/api/work/tasks", None),
    ("post", "/api/work/tasks", {"title": "x"}),
    ("put", "/api/work/tasks/1", {"status": "doing"}),
    ("post", "/api/work/tasks/1/complete", None),
    ("delete", "/api/work/tasks/1", None),
    ("get", "/api/work/notes", None),
    ("post", "/api/work/notes", {"content": "x"}),
    ("put", "/api/work/profile", {"role": "x"}),
    ("get", "/api/work/report?period=today", None),
]


def _enable(client, h, on=True):
    r = client.put("/api/work/status", headers=h, json={"enabled": on})
    assert r.status_code == 200, r.text
    return r.json()


def _user(username):
    db = SessionLocal()
    try:
        return db.query(models.BatAccount).filter_by(username=username).first()
    finally:
        db.close()


# --- the switch -------------------------------------------------------------

def test_work_is_off_for_a_fresh_user(client, auth_headers):
    """A new account sees no work side at all until it asks for one."""
    h = auth_headers("work_fresh")
    st = client.get("/api/work/status", headers=h).json()
    assert st["enabled"] is False
    assert st["chosen"] is False        # defaulted, not decided
    assert st["has_data"] is False


def test_every_work_route_is_409_while_off(client, auth_headers):
    h = auth_headers("work_off_user")
    for method, url, body in OFF_ROUTES:
        kwargs = {"headers": h}
        if body is not None:
            kwargs["json"] = body
        r = getattr(client, method)(url, **kwargs)
        assert r.status_code == 409, f"{method} {url} → {r.status_code}"
        assert r.json()["detail"] == WORK_OFF_DETAIL


def test_turning_it_on_opens_the_track(client, auth_headers):
    h = auth_headers("work_on_user")
    st = _enable(client, h)
    assert st["enabled"] is True and st["chosen"] is True
    assert client.get("/api/work/tasks", headers=h).status_code == 200
    # The setup is driven by the same steps Alfred uses.
    assert st["configured"] is False
    assert "work_days" in st["missing_essential"]
    assert st["next_question"]


def test_disabling_hides_but_never_deletes(client, auth_headers):
    h = auth_headers("work_keepdata")
    _enable(client, h)
    task = client.post("/api/work/tasks", headers=h,
                       json={"title": "Quarterly audit", "project": "Finance"}).json()
    client.post("/api/work/notes", headers=h,
                json={"content": "Learned the audit flow", "kind": "learning"})

    _enable(client, h, False)
    assert client.get("/api/work/tasks", headers=h).status_code == 409
    st = client.get("/api/work/status", headers=h).json()
    assert st["enabled"] is False
    assert st["has_data"] is True        # the data is still there, just not reachable

    _enable(client, h, True)
    tasks = client.get("/api/work/tasks", headers=h).json()
    assert [t["id"] for t in tasks] == [task["id"]]
    notes = client.get("/api/work/notes", headers=h).json()
    assert notes[0]["content"] == "Learned the audit flow"


def test_existing_work_users_keep_the_track_without_choosing(client, auth_headers):
    """The live-deploy guarantee: the track shipped before this switch existed,
    so anyone already using it must stay switched on with no backfill."""
    h = auth_headers("work_legacy")
    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="work_legacy").first()
        assert user.work_enabled is None                  # never chose
        work_service.create_task(db, user, title="Legacy ticket")
        assert work_service.is_enabled(db, user) is True   # resolved from their data
    finally:
        db.close()
    assert client.get("/api/work/tasks", headers=h).status_code == 200
    assert client.get("/api/work/status", headers=h).json()["chosen"] is False


# --- tasks ------------------------------------------------------------------

def test_task_crud_and_open_filtering(client, auth_headers):
    h = auth_headers("work_crud")
    _enable(client, h)
    a = client.post("/api/work/tasks", headers=h, json={"title": "Write RFC"}).json()
    b = client.post("/api/work/tasks", headers=h,
                    json={"title": "Review PR", "status": "doing", "project": "Platform"}).json()
    assert b["status"] == "doing" and b["project"] == "Platform"

    assert {t["id"] for t in client.get("/api/work/tasks", headers=h).json()} == {a["id"], b["id"]}

    moved = client.put(f"/api/work/tasks/{a['id']}", headers=h,
                       json={"status": "blocked"}).json()
    assert moved["status"] == "blocked"

    done = client.post(f"/api/work/tasks/{b['id']}/complete", headers=h).json()
    assert done["status"] == "done" and done["completed_at"]
    open_ids = {t["id"] for t in client.get("/api/work/tasks", headers=h).json()}
    assert open_ids == {a["id"]}                       # done drops out by default
    all_ids = {t["id"] for t in client.get("/api/work/tasks?include_done=true", headers=h).json()}
    assert all_ids == {a["id"], b["id"]}

    assert client.delete(f"/api/work/tasks/{a['id']}", headers=h).status_code == 204
    assert client.delete(f"/api/work/tasks/{a['id']}", headers=h).status_code == 404


def test_finishing_work_awards_no_bat_points(client, auth_headers):
    h = auth_headers("work_nopoints")
    _enable(client, h)
    before = client.get("/api/account", headers=h).json()
    t = client.post("/api/work/tasks", headers=h, json={"title": "Close ticket"}).json()
    client.post(f"/api/work/tasks/{t['id']}/complete", headers=h)
    after = client.get("/api/account", headers=h).json()
    assert after["points"] == before["points"]
    assert after["bat_level"] == before["bat_level"]


def test_work_tasks_are_not_personal_missions(client, auth_headers):
    h = auth_headers("work_notmission")
    _enable(client, h)
    client.post("/api/work/tasks", headers=h, json={"title": "Employer deliverable"})
    titles = [m["title"] for m in client.get("/api/missions", headers=h).json()]
    assert "Employer deliverable" not in titles


def test_tasks_are_owner_scoped(client, auth_headers):
    mine, theirs = auth_headers("work_owner_a"), auth_headers("work_owner_b")
    _enable(client, mine)
    _enable(client, theirs)
    t = client.post("/api/work/tasks", headers=mine, json={"title": "Mine only"}).json()
    assert client.get("/api/work/tasks", headers=theirs).json() == []
    assert client.put(f"/api/work/tasks/{t['id']}", headers=theirs,
                      json={"status": "done"}).status_code == 404
    assert client.delete(f"/api/work/tasks/{t['id']}", headers=theirs).status_code == 404


def test_bad_input_is_refused(client, auth_headers):
    h = auth_headers("work_badinput")
    _enable(client, h)
    assert client.post("/api/work/tasks", headers=h,
                       json={"title": "x", "status": "procrastinating"}).status_code == 422
    assert client.get("/api/work/tasks?task_status=nope", headers=h).status_code == 422
    assert client.get("/api/work/notes?kind=nope", headers=h).status_code == 422
    assert client.get("/api/work/report?period=decade", headers=h).status_code == 422
    assert client.post("/api/work/tasks", headers=h, json={"title": "   "}).status_code == 422


# --- profile and report -----------------------------------------------------

def test_profile_update_drives_the_setup_state(client, auth_headers):
    h = auth_headers("work_profile_api")
    _enable(client, h)
    st = client.put("/api/work/profile", headers=h,
                    json={"work_days": "Mon,Tue,Wed,Thu,Fri"}).json()
    assert st["profile"]["work_days"] == "0,1,2,3,4"
    assert st["profile"]["work_days_label"] == "Mon, Tue, Wed, Thu, Fri"
    assert st["configured"] is False                  # hours still missing

    st = client.put("/api/work/profile", headers=h,
                    json={"work_start": "09:00", "work_end": "18:00",
                          "employer": "Wayne Enterprises"}).json()
    assert st["configured"] is True and st["missing_essential"] == []
    assert st["profile"]["employer"] == "Wayne Enterprises"

    assert client.put("/api/work/profile", headers=h,
                      json={"work_start": "25:99"}).status_code == 422


def test_report_matches_alfreds_and_ends_with_a_question(client, auth_headers):
    h = auth_headers("work_report_api")
    _enable(client, h)
    t = client.post("/api/work/tasks", headers=h, json={"title": "Ship the thing"}).json()
    client.post(f"/api/work/tasks/{t['id']}/complete", headers=h)
    client.post("/api/work/notes", headers=h,
                json={"content": "Found the deploy gotcha", "kind": "learning"})

    r = client.get("/api/work/report?period=today", headers=h).json()
    assert [c["title"] for c in r["completed"]] == ["Ship the thing"]
    assert r["learnings"][0]["content"] == "Found the deploy gotcha"
    assert r["work_days"] == 1
    assert r["open_counts"] == {"todo": 0, "doing": 0, "blocked": 0}
    assert r["text"].rstrip().endswith("?")           # the reflection is the point


# --- Alfred's side of the same switch ---------------------------------------

def test_alfred_is_not_shown_work_tools_when_off(client, auth_headers):
    h = auth_headers("work_alfred_off")
    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="work_alfred_off").first()
        names = {t["name"] for t in alfred_tools.tools_for(db, user)}
        assert not (names & alfred_tools.WORK_TOOL_NAMES)
        assert "set_work_track" in names              # he can always switch it on
        assert "create_mission" in names              # the rest is untouched

        # And if he calls one anyway, it is refused rather than executed.
        res = alfred_tools.execute_tool(db, user, "create_work_task", {"title": "sneaky"})
        assert "error" in res
        assert db.query(models.BatWorkTask).filter_by(owner_id=user.id).count() == 0
        assert alfred_tools.work_blocked(db, user, "delete_work_task") is True
    finally:
        db.close()


def test_alfred_can_switch_the_track_on_and_then_work(client, auth_headers):
    h = auth_headers("work_alfred_on")
    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="work_alfred_on").first()
        res = alfred_tools.execute_tool(db, user, "set_work_track", {"enabled": True})
        assert res["work_enabled"] is True and res["changed"] is True
        names = {t["name"] for t in alfred_tools.tools_for(db, user)}
        assert alfred_tools.WORK_TOOL_NAMES <= names
        alfred_tools.execute_tool(db, user, "create_work_task", {"title": "Now allowed"})
    finally:
        db.close()
    assert [t["title"] for t in client.get("/api/work/tasks", headers=h).json()] == ["Now allowed"]


def test_the_web_switch_and_alfreds_switch_are_the_same_switch(client, auth_headers):
    h = auth_headers("work_same_switch")
    _enable(client, h)
    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="work_same_switch").first()
        alfred_tools.execute_tool(db, user, "set_work_track", {"enabled": False})
    finally:
        db.close()
    assert client.get("/api/work/status", headers=h).json()["enabled"] is False
    assert client.get("/api/work/tasks", headers=h).status_code == 409


def test_system_prompt_drops_the_work_track_when_off():
    from services.alfred_agent import _build_system_prompt

    user = models.BatAccount(username="pm", alfred_address="Master Wayne", timezone="UTC")
    on = _build_system_prompt(user, work_enabled=True)
    off = _build_system_prompt(user, work_enabled=False)
    assert "TWO TRACKS" in on and "work_report" in on
    assert "TWO TRACKS" not in off
    assert "switched OFF" in off and "set_work_track(enabled=true)" in off


# --- the background side ----------------------------------------------------

def test_no_automatic_work_report_while_off(client, auth_headers, monkeypatch):
    """A profile that still says "report at 19:00" must stay silent when the
    track is off — the settings are kept, not acted on."""
    h = auth_headers("work_sched_off")
    _enable(client, h)
    client.put("/api/work/profile", headers=h,
               json={"work_days": "Mon,Tue,Wed,Thu,Fri", "work_start": "09:00",
                     "work_end": "18:00", "report_time": "19:00", "daily_report": True})
    client.post("/api/work/tasks", headers=h, json={"title": "Did a thing"})

    sent = []
    monkeypatch.setattr(scheduler, "_send",
                        lambda db, user, chat_id, text: sent.append(text) or True)

    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="work_sched_off").first()
        local_now = datetime.now(timezone.utc).replace(hour=19, minute=0, second=0,
                                                       microsecond=0)
        # With the track ON the report goes out at 19:00 ...
        summary = {"work_reports_sent": 0}
        scheduler._fire_work_reports(db, user, "chat-sched-off", local_now, summary)
        assert summary["work_reports_sent"] == 1 and sent

        # ... and with it OFF the very same call stays quiet.
        work_service.set_enabled(db, user, False)
        sent.clear()
        summary = {"work_reports_sent": 0}
        scheduler._fire_work_reports(db, user, "chat-sched-off", local_now, summary)
        assert summary["work_reports_sent"] == 0
        assert sent == []
    finally:
        db.close()


def test_work_facts_leave_the_nudge_engine_when_work_is_off(client, auth_headers):
    """The "nothing timed today" reminder is wanted, so it is never silenced —
    with work off it simply stops consulting work and speaks personally again."""
    auth_headers("work_nudge_off")
    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="work_nudge_off").first()
        user.timezone = "UTC"
        work_service.set_enabled(db, user, True)
        work_service.upsert_profile(db, user, work_days="0,1,2,3,4,5,6",
                                    work_start="00:00", work_end="23:59")
        work_service.create_task(db, user, title="Something at the office")
        local_now = datetime.now(timezone.utc).replace(hour=16, minute=0)

        # Work on: he knows they are at their desk, and words it that way.
        ctx = nudges.build_context(db, user, local_now)
        assert ctx.at_work is True and ctx.work_activity_today is True
        assert "at work" in nudges.sig_drift(ctx).draft

        # Work off: no work facts at all, and the reminder still exists.
        work_service.set_enabled(db, user, False)
        ctx = nudges.build_context(db, user, local_now)
        assert ctx.at_work is False and ctx.work_activity_today is False
        from services import mission_service
        mission_service.create_mission(db, user, title="Personal mission")
        ctx = nudges.build_context(db, user, local_now)
        drift = nudges.sig_drift(ctx)
        assert drift is not None and "at work" not in drift.draft
    finally:
        db.close()
