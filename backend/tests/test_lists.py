"""Lists: the grouping a mission belongs to.

The two things worth guarding are the Inbox staying a non-row, and nothing
crossing between owners.
"""

import os
import sqlite3
import subprocess
import sys

import pytest

from services import list_service


@pytest.fixture
def db_for():
    """A session and the user row, for the tool layer, which takes both.

    Local to this module rather than in conftest: the other tool tests open
    a session by hand, and one more shared fixture earns less than it costs.
    """
    import contextlib

    from database import SessionLocal
    import models

    @contextlib.contextmanager
    def _open(username):
        db = SessionLocal()
        try:
            yield db, db.query(models.BatAccount).filter_by(username=username).first()
        finally:
            db.close()

    return _open


# --- the migration ------------------------------------------------------


def test_migration_032_adds_lists_and_leaves_existing_missions_unfiled(tmp_path):
    """A database at 031 with missions in it: they must survive, unfiled."""
    db_file = tmp_path / "lists.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_file}"}
    backend = os.path.dirname(os.path.dirname(__file__))

    def alembic(*args):
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=backend, env=env, capture_output=True, text=True,
        )

    r = alembic("upgrade", "031")
    assert r.returncode == 0, r.stderr[-800:]
    con = sqlite3.connect(db_file)
    con.execute(
        "INSERT INTO bat_account (username, hashed_password, points, bat_level, is_active, "
        "created_at, updated_at, token_version) VALUES ('old','x',0,'The Recruit',1,"
        "datetime('now'),datetime('now'),0)"
    )
    con.execute(
        "INSERT INTO bat_missions (title, priority, status, is_pinned, is_dismissed, "
        "focus_minutes, completed_focus_sessions, created_at, owner_id) "
        "VALUES ('from before lists','high','pending',0,0,0,0,datetime('now'),1)"
    )
    con.commit()
    assert "list_id" not in {row[1] for row in con.execute("PRAGMA table_info(bat_missions)")}
    con.close()

    r = alembic("upgrade", "head")
    assert r.returncode == 0, r.stderr[-800:]
    con = sqlite3.connect(db_file)
    cols = {row[1]: row for row in con.execute("PRAGMA table_info(bat_missions)")}
    assert "list_id" in cols and cols["list_id"][3] == 0      # notnull = 0 → nullable
    # The mission is still there and still readable, in the Inbox.
    assert con.execute("SELECT title, list_id FROM bat_missions").fetchall() \
        == [("from before lists", None)]
    assert con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='bat_lists'"
    ).fetchone() is not None
    con.close()

    r = alembic("downgrade", "031")
    assert r.returncode == 0, r.stderr[-800:]
    con = sqlite3.connect(db_file)
    assert "list_id" not in {row[1] for row in con.execute("PRAGMA table_info(bat_missions)")}
    # Reversible means the mission comes back, not that the table does.
    assert con.execute("SELECT title FROM bat_missions").fetchall() == [("from before lists",)]
    con.close()
    assert alembic("upgrade", "head").returncode == 0


# --- the API ------------------------------------------------------------


def _mk(client, h, name, **kw):
    r = client.post("/api/lists", json={"name": name, **kw}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_a_new_account_has_no_lists(client, auth_headers):
    h = auth_headers("lists_empty")
    assert client.get("/api/lists", headers=h).json() == []


def test_create_and_read_back(client, auth_headers):
    h = auth_headers("lists_crud")
    made = _mk(client, h, "Khorasan", color="#eab308", icon="shield")
    assert made["name"] == "Khorasan"
    assert made["archived"] is False
    assert made["open_missions"] == 0
    assert [l["name"] for l in client.get("/api/lists", headers=h).json()] == ["Khorasan"]


def test_a_name_is_required(client, auth_headers):
    h = auth_headers("lists_noname")
    assert client.post("/api/lists", json={"name": "   "}, headers=h).status_code in (400, 422)


def test_the_same_name_twice_is_refused(client, auth_headers):
    h = auth_headers("lists_dupe")
    _mk(client, h, "Health")
    r = client.post("/api/lists", json={"name": "health"}, headers=h)
    assert r.status_code == 400
    assert "already have a list" in r.json()["detail"]


def test_but_two_users_may_both_have_a_list_called_health(client, auth_headers):
    a, b = auth_headers("lists_mine"), auth_headers("lists_yours")
    _mk(client, a, "Health")
    _mk(client, b, "Health")


def test_an_archived_name_is_free_again(client, auth_headers):
    h = auth_headers("lists_archived_name")
    made = _mk(client, h, "Old project")
    client.put(f"/api/lists/{made['id']}", json={"archived": True}, headers=h)
    _mk(client, h, "Old project")        # the archived one is not a collision


def test_archived_lists_leave_the_rail_but_can_be_asked_for(client, auth_headers):
    h = auth_headers("lists_archived_rail")
    made = _mk(client, h, "Done with this")
    client.put(f"/api/lists/{made['id']}", json={"archived": True}, headers=h)
    assert client.get("/api/lists", headers=h).json() == []
    shown = client.get("/api/lists?include_archived=true", headers=h).json()
    assert [l["name"] for l in shown] == ["Done with this"]


def test_rename(client, auth_headers):
    h = auth_headers("lists_rename")
    made = _mk(client, h, "Cyber")
    r = client.put(f"/api/lists/{made['id']}", json={"name": "Cybersecurity"}, headers=h)
    assert r.status_code == 200 and r.json()["name"] == "Cybersecurity"


def test_a_colour_can_be_cleared_not_only_changed(client, auth_headers):
    h = auth_headers("lists_clear_colour")
    made = _mk(client, h, "Admin", color="#ff0000")
    r = client.put(f"/api/lists/{made['id']}", json={"color": None}, headers=h)
    assert r.json()["color"] is None


def test_an_omitted_field_is_left_alone(client, auth_headers):
    h = auth_headers("lists_omitted")
    made = _mk(client, h, "Admin", color="#ff0000", icon="folder")
    r = client.put(f"/api/lists/{made['id']}", json={"name": "Admin work"}, headers=h)
    assert r.json()["color"] == "#ff0000" and r.json()["icon"] == "folder"


def test_reorder(client, auth_headers):
    h = auth_headers("lists_order")
    a, b, c = (_mk(client, h, n) for n in ("A", "B", "C"))
    r = client.post("/api/lists/reorder",
                    json={"ordered_ids": [c["id"], a["id"], b["id"]]}, headers=h)
    assert [l["name"] for l in r.json()] == ["C", "A", "B"]
    assert [l["name"] for l in client.get("/api/lists", headers=h).json()] == ["C", "A", "B"]


# --- missions in lists --------------------------------------------------


def test_a_mission_can_be_created_in_a_list(client, auth_headers):
    h = auth_headers("lists_mission_create")
    made = _mk(client, h, "Khorasan")
    r = client.post("/api/missions",
                    json={"title": "Draft the brief", "list_id": made["id"]}, headers=h)
    assert r.status_code == 201 and r.json()["list_id"] == made["id"]


def test_a_mission_with_no_list_is_in_the_inbox(client, auth_headers):
    h = auth_headers("lists_inbox")
    r = client.post("/api/missions", json={"title": "Unfiled"}, headers=h)
    assert r.json()["list_id"] is None


def test_a_mission_can_be_moved_and_moved_back_to_the_inbox(client, auth_headers):
    h = auth_headers("lists_move")
    made = _mk(client, h, "Health")
    mid = client.post("/api/missions", json={"title": "Walk"}, headers=h).json()["id"]
    assert client.put(f"/api/missions/{mid}",
                      json={"list_id": made["id"]}, headers=h).json()["list_id"] == made["id"]
    # Back out again: an explicit null is the Inbox, not "leave it alone".
    assert client.put(f"/api/missions/{mid}",
                      json={"list_id": None}, headers=h).json()["list_id"] is None


def test_missions_can_be_filtered_to_one_list(client, auth_headers):
    h = auth_headers("lists_filter")
    one, two = _mk(client, h, "One"), _mk(client, h, "Two")
    client.post("/api/missions", json={"title": "in one", "list_id": one["id"]}, headers=h)
    client.post("/api/missions", json={"title": "in two", "list_id": two["id"]}, headers=h)
    client.post("/api/missions", json={"title": "unfiled"}, headers=h)

    got = client.get(f"/api/missions?list_id={one['id']}", headers=h).json()
    assert [m["title"] for m in got] == ["in one"]
    inbox = client.get("/api/missions?list_id=inbox", headers=h).json()
    assert [m["title"] for m in inbox] == ["unfiled"]
    assert len(client.get("/api/missions", headers=h).json()) == 3


def test_counts_are_open_missions_only(client, auth_headers):
    h = auth_headers("lists_counts")
    made = _mk(client, h, "Counted")
    for title in ("a", "b"):
        client.post("/api/missions", json={"title": title, "list_id": made["id"]}, headers=h)
    done = client.post("/api/missions",
                       json={"title": "c", "list_id": made["id"]}, headers=h).json()
    assert client.get("/api/lists", headers=h).json()[0]["open_missions"] == 3

    client.put(f"/api/missions/{done['id']}", json={"status": "completed"}, headers=h)
    # A badge that counted finished work would never go down.
    assert client.get("/api/lists", headers=h).json()[0]["open_missions"] == 2


def test_the_inbox_is_counted_too(client, auth_headers):
    h = auth_headers("lists_inbox_count")
    client.post("/api/missions", json={"title": "unfiled"}, headers=h)
    assert client.get("/api/lists/counts", headers=h).json()["inbox"] == 1


def test_deleting_a_list_refiles_its_missions_and_never_deletes_them(client, auth_headers):
    h = auth_headers("lists_delete")
    made = _mk(client, h, "Doomed")
    mid = client.post("/api/missions",
                      json={"title": "Still mine", "list_id": made["id"]}, headers=h).json()["id"]

    assert client.delete(f"/api/lists/{made['id']}", headers=h).status_code == 204
    assert client.get("/api/lists", headers=h).json() == []
    # The work outlives the list it was filed in.
    survivor = client.get("/api/missions", headers=h).json()
    assert [(m["id"], m["list_id"]) for m in survivor] == [(mid, None)]


# --- the ownership boundary ---------------------------------------------


def test_a_mission_cannot_be_created_in_another_users_list(client, auth_headers):
    mine, theirs = auth_headers("lists_attacker"), auth_headers("lists_victim")
    victim_list = _mk(client, theirs, "Private")
    r = client.post("/api/missions",
                    json={"title": "Trespass", "list_id": victim_list["id"]}, headers=mine)
    assert r.status_code == 400


def test_a_mission_cannot_be_moved_into_another_users_list(client, auth_headers):
    mine, theirs = auth_headers("lists_attacker2"), auth_headers("lists_victim2")
    victim_list = _mk(client, theirs, "Private")
    mid = client.post("/api/missions", json={"title": "Mine"}, headers=mine).json()["id"]
    # This is the one that would have slipped through: the PUT handler
    # writes payload fields straight onto the row.
    r = client.put(f"/api/missions/{mid}", json={"list_id": victim_list["id"]}, headers=mine)
    assert r.status_code == 400
    assert client.get("/api/missions", headers=mine).json()[0]["list_id"] is None


def test_another_users_list_cannot_be_renamed_or_deleted(client, auth_headers):
    mine, theirs = auth_headers("lists_attacker3"), auth_headers("lists_victim3")
    victim_list = _mk(client, theirs, "Private")
    assert client.put(f"/api/lists/{victim_list['id']}",
                      json={"name": "Owned"}, headers=mine).status_code == 404
    assert client.delete(f"/api/lists/{victim_list['id']}", headers=mine).status_code == 404
    # Untouched, and still theirs.
    assert client.get("/api/lists", headers=theirs).json()[0]["name"] == "Private"


def test_filtering_by_another_users_list_returns_nothing_not_their_missions(client, auth_headers):
    mine, theirs = auth_headers("lists_attacker4"), auth_headers("lists_victim4")
    victim_list = _mk(client, theirs, "Private")
    client.post("/api/missions",
                json={"title": "Secret", "list_id": victim_list["id"]}, headers=theirs)
    r = client.get(f"/api/missions?list_id={victim_list['id']}", headers=mine)
    assert r.status_code in (200, 400)
    if r.status_code == 200:
        assert r.json() == []


def test_a_list_id_that_does_not_exist_is_refused(client, auth_headers):
    h = auth_headers("lists_missing")
    assert client.post("/api/missions",
                       json={"title": "x", "list_id": 999999}, headers=h).status_code == 400


def test_reordering_with_a_foreign_id_ignores_it_rather_than_failing(client, auth_headers):
    mine, theirs = auth_headers("lists_reorder_mine"), auth_headers("lists_reorder_theirs")
    a = _mk(client, mine, "A")
    foreign = _mk(client, theirs, "Foreign")
    r = client.post("/api/lists/reorder",
                    json={"ordered_ids": [foreign["id"], a["id"]]}, headers=mine)
    assert r.status_code == 200
    assert [l["name"] for l in r.json()] == ["A"]


# --- Alfred -------------------------------------------------------------


def test_alfred_files_a_mission_into_a_list_by_name(client, auth_headers, db_for):
    """He is told list names, not ids, so names are what the tools take."""
    h = auth_headers("alfred_list_name")
    _mk(client, h, "Khorasan")
    with db_for("alfred_list_name") as (db, user):
        from services import alfred_tools
        out = alfred_tools.execute_tool(db, user, "create_mission",
                                        {"title": "Draft the brief", "list": "khorasan"})
        assert out["mission"]["list"] == "Khorasan"


def test_alfred_reads_a_missions_list_as_a_name_not_an_id(client, auth_headers, db_for):
    h = auth_headers("alfred_list_read")
    with db_for("alfred_list_read") as (db, user):
        from services import alfred_tools
        out = alfred_tools.execute_tool(db, user, "create_mission", {"title": "Unfiled"})
        # "Inbox", because "its list is None" is not a sentence to read aloud.
        assert out["mission"]["list"] == "Inbox"


def test_alfred_is_refused_an_unknown_list_and_told_which_exist(client, auth_headers, db_for):
    h = auth_headers("alfred_list_unknown")
    _mk(client, h, "Health")
    with db_for("alfred_list_unknown") as (db, user):
        from services import alfred_tools
        with pytest.raises(ValueError) as caught:
            alfred_tools.execute_tool(db, user, "create_mission",
                                       {"title": "x", "list": "Helth"})
    # The message has to carry the answer: the agent loop turns a ValueError
    # into {"error": <message>} and that is all he will see.
    msg = str(caught.value)
    assert "Helth" in msg and "Health" in msg and "create_list" in msg


def test_alfred_does_not_invent_a_list_to_file_a_mission(client, auth_headers, db_for):
    h = auth_headers("alfred_no_invent")
    with db_for("alfred_no_invent") as (db, user):
        from services import alfred_tools
        with pytest.raises(ValueError):
            alfred_tools.execute_tool(db, user, "create_mission",
                                       {"title": "x", "list": "Brand New"})
    assert client.get("/api/lists", headers=h).json() == []


def test_alfred_can_create_a_list_when_asked(client, auth_headers, db_for):
    h = auth_headers("alfred_create_list")
    with db_for("alfred_create_list") as (db, user):
        from services import alfred_tools
        out = alfred_tools.execute_tool(db, user, "create_list", {"name": "Cybersecurity"})
        assert out["list"]["name"] == "Cybersecurity"
    assert [l["name"] for l in client.get("/api/lists", headers=h).json()] == ["Cybersecurity"]


def test_alfred_sees_the_lists_with_their_counts(client, auth_headers, db_for):
    h = auth_headers("alfred_get_lists")
    made = _mk(client, h, "Counted")
    client.post("/api/missions", json={"title": "a", "list_id": made["id"]}, headers=h)
    client.post("/api/missions", json={"title": "unfiled"}, headers=h)
    with db_for("alfred_get_lists") as (db, user):
        from services import alfred_tools
        out = alfred_tools.execute_tool(db, user, "get_lists", {})
    assert out["lists"] == [{"name": "Counted", "open_missions": 1}]
    assert out["inbox_open_missions"] == 1


def test_alfred_can_move_a_mission_back_to_the_inbox(client, auth_headers, db_for):
    h = auth_headers("alfred_to_inbox")
    made = _mk(client, h, "Somewhere")
    mid = client.post("/api/missions",
                      json={"title": "Move me", "list_id": made["id"]}, headers=h).json()["id"]
    with db_for("alfred_to_inbox") as (db, user):
        from services import alfred_tools
        out = alfred_tools.execute_tool(db, user, "update_mission",
                                        {"mission_id": mid, "list": "Inbox"})
    assert out["mission"]["list"] == "Inbox"


def test_an_update_that_says_nothing_about_the_list_leaves_it_alone(client, auth_headers, db_for):
    h = auth_headers("alfred_list_untouched")
    made = _mk(client, h, "Keep me")
    mid = client.post("/api/missions",
                      json={"title": "Edit my title", "list_id": made["id"]}, headers=h).json()["id"]
    with db_for("alfred_list_untouched") as (db, user):
        from services import alfred_tools
        out = alfred_tools.execute_tool(db, user, "update_mission",
                                        {"mission_id": mid, "priority": "high"})
    # The silent-regression case: an absent `list` must not mean "Inbox".
    assert out["mission"]["list"] == "Keep me"
