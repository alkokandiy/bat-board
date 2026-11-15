"""Sections inside a list.

The invariant under test throughout: a mission's section belongs to the
mission's own list. Everything awkward about this table follows from it.
"""

import contextlib
import os
import sqlite3
import subprocess
import sys

import pytest


@pytest.fixture
def db_for():
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


def _list(client, h, name):
    r = client.post("/api/lists", json={"name": name}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _section(client, h, list_id, name):
    r = client.post("/api/sections", json={"list_id": list_id, "name": name}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _mission(client, h, **body):
    r = client.post("/api/missions", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


# --- the migration ------------------------------------------------------


def test_migration_033_leaves_existing_missions_ungrouped(tmp_path):
    db_file = tmp_path / "sections.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_file}"}
    backend = os.path.dirname(os.path.dirname(__file__))

    def alembic(*args):
        return subprocess.run([sys.executable, "-m", "alembic", *args],
                              cwd=backend, env=env, capture_output=True, text=True)

    assert alembic("upgrade", "032").returncode == 0
    con = sqlite3.connect(db_file)
    con.execute(
        "INSERT INTO bat_account (username, hashed_password, points, bat_level, is_active, "
        "created_at, updated_at, token_version) VALUES ('old','x',0,'The Recruit',1,"
        "datetime('now'),datetime('now'),0)")
    con.execute(
        "INSERT INTO bat_missions (title, priority, status, is_pinned, is_dismissed, "
        "focus_minutes, completed_focus_sessions, created_at, owner_id) "
        "VALUES ('before sections','high','pending',0,0,0,0,datetime('now'),1)")
    con.commit()
    con.close()

    r = alembic("upgrade", "head")
    assert r.returncode == 0, r.stderr[-800:]
    con = sqlite3.connect(db_file)
    cols = {row[1]: row for row in con.execute("PRAGMA table_info(bat_missions)")}
    assert "section_id" in cols and cols["section_id"][3] == 0     # nullable
    assert con.execute("SELECT title, section_id FROM bat_missions").fetchall() \
        == [("before sections", None)]
    con.close()

    assert alembic("downgrade", "032").returncode == 0
    con = sqlite3.connect(db_file)
    assert "section_id" not in {row[1] for row in con.execute("PRAGMA table_info(bat_missions)")}
    assert con.execute("SELECT title FROM bat_missions").fetchall() == [("before sections",)]
    con.close()
    assert alembic("upgrade", "head").returncode == 0


# --- the basics ---------------------------------------------------------


def test_create_and_read_back(client, auth_headers):
    h = auth_headers("sec_crud")
    lst = _list(client, h, "Khorasan")
    made = _section(client, h, lst["id"], "Research")
    assert made["name"] == "Research" and made["list_id"] == lst["id"]
    assert [s["name"] for s in client.get("/api/sections", headers=h).json()] == ["Research"]


def test_sections_can_be_asked_for_one_list_at_a_time(client, auth_headers):
    h = auth_headers("sec_per_list")
    a, b = _list(client, h, "A"), _list(client, h, "B")
    _section(client, h, a["id"], "In A")
    _section(client, h, b["id"], "In B")
    got = client.get(f"/api/sections?list_id={a['id']}", headers=h).json()
    assert [s["name"] for s in got] == ["In A"]
    assert len(client.get("/api/sections", headers=h).json()) == 2


def test_the_same_name_in_two_different_lists_is_not_a_duplicate(client, auth_headers):
    """Two projects may each have a Research section; neither is a copy."""
    h = auth_headers("sec_same_name")
    a, b = _list(client, h, "A"), _list(client, h, "B")
    _section(client, h, a["id"], "Research")
    _section(client, h, b["id"], "Research")


def test_but_twice_in_the_same_list_is(client, auth_headers):
    h = auth_headers("sec_dupe")
    lst = _list(client, h, "One")
    _section(client, h, lst["id"], "Research")
    r = client.post("/api/sections",
                    json={"list_id": lst["id"], "name": "research"}, headers=h)
    assert r.status_code == 400 and "already has a section" in r.json()["detail"]


def test_a_section_needs_a_name(client, auth_headers):
    h = auth_headers("sec_noname")
    lst = _list(client, h, "One")
    r = client.post("/api/sections", json={"list_id": lst["id"], "name": "  "}, headers=h)
    assert r.status_code in (400, 422)


def test_rename(client, auth_headers):
    h = auth_headers("sec_rename")
    lst = _list(client, h, "One")
    made = _section(client, h, lst["id"], "Reserch")
    r = client.put(f"/api/sections/{made['id']}", json={"name": "Research"}, headers=h)
    assert r.status_code == 200 and r.json()["name"] == "Research"


def test_reorder_within_a_list(client, auth_headers):
    h = auth_headers("sec_order")
    lst = _list(client, h, "One")
    a = _section(client, h, lst["id"], "A")
    b = _section(client, h, lst["id"], "B")
    c = _section(client, h, lst["id"], "C")
    r = client.post("/api/sections/reorder",
                    json={"list_id": lst["id"], "ordered_ids": [c["id"], a["id"], b["id"]]},
                    headers=h)
    assert [s["name"] for s in r.json()] == ["C", "A", "B"]


def test_reordering_one_list_does_not_touch_another_lists_sections(client, auth_headers):
    """Not just "the ids are ignored" — their positions must not move either.

    Checking only the reordered list's own result cannot see this: the
    response is filtered to that list, so another list being silently
    renumbered underneath looks identical to nothing happening.
    """
    h = auth_headers("sec_order_cross")
    a, b = _list(client, h, "A"), _list(client, h, "B")
    in_a = _section(client, h, a["id"], "Mine")
    b_first = _section(client, h, b["id"], "B one")
    b_second = _section(client, h, b["id"], "B two")

    before = [(s["id"], s["position"]) for s
              in client.get(f"/api/sections?list_id={b['id']}", headers=h).json()]

    r = client.post("/api/sections/reorder",
                    json={"list_id": a["id"], "ordered_ids": [b_second["id"], in_a["id"]]},
                    headers=h)
    assert [s["name"] for s in r.json()] == ["Mine"]

    after = [(s["id"], s["position"]) for s
             in client.get(f"/api/sections?list_id={b['id']}", headers=h).json()]
    assert after == before
    assert [row[0] for row in after] == [b_first["id"], b_second["id"]]


# --- the invariant ------------------------------------------------------


def test_a_mission_can_be_created_in_a_section(client, auth_headers):
    h = auth_headers("sec_mission")
    lst = _list(client, h, "Khorasan")
    sec = _section(client, h, lst["id"], "Research")
    m = _mission(client, h, title="Read the paper", list_id=lst["id"], section_id=sec["id"])
    assert m["section_id"] == sec["id"]


def test_a_section_from_another_list_is_refused(client, auth_headers):
    h = auth_headers("sec_wrong_list")
    a, b = _list(client, h, "A"), _list(client, h, "B")
    sec_of_b = _section(client, h, b["id"], "B's section")
    r = client.post("/api/missions",
                    json={"title": "x", "list_id": a["id"], "section_id": sec_of_b["id"]},
                    headers=h)
    assert r.status_code == 400
    assert "different list" in r.json()["detail"]


def test_a_mission_in_the_inbox_cannot_be_in_a_section(client, auth_headers):
    h = auth_headers("sec_inbox")
    lst = _list(client, h, "Somewhere")
    sec = _section(client, h, lst["id"], "Research")
    # No list_id at all: the Inbox is not a list, so it has nowhere to hang one.
    r = client.post("/api/missions", json={"title": "x", "section_id": sec["id"]}, headers=h)
    assert r.status_code == 400
    assert "Inbox" in r.json()["detail"]


def test_moving_a_mission_to_another_list_drops_its_section(client, auth_headers):
    """The section belongs to the old list and cannot come along."""
    h = auth_headers("sec_move_list")
    a, b = _list(client, h, "A"), _list(client, h, "B")
    sec = _section(client, h, a["id"], "Research")
    m = _mission(client, h, title="Travelling", list_id=a["id"], section_id=sec["id"])

    moved = client.put(f"/api/missions/{m['id']}", json={"list_id": b["id"]}, headers=h).json()
    assert moved["list_id"] == b["id"]
    # Ungrouped in its new list, not pointing at a section outside it.
    assert moved["section_id"] is None


def test_a_list_and_a_section_can_be_set_in_one_request(client, auth_headers):
    """The section is checked against the list it is ENDING UP in."""
    h = auth_headers("sec_move_both")
    a, b = _list(client, h, "A"), _list(client, h, "B")
    sec_of_b = _section(client, h, b["id"], "Landing")
    m = _mission(client, h, title="Travelling", list_id=a["id"])
    r = client.put(f"/api/missions/{m['id']}",
                   json={"list_id": b["id"], "section_id": sec_of_b["id"]}, headers=h)
    assert r.status_code == 200
    assert (r.json()["list_id"], r.json()["section_id"]) == (b["id"], sec_of_b["id"])


def test_and_the_order_of_that_pair_does_not_save_an_invalid_one(client, auth_headers):
    h = auth_headers("sec_move_both_bad")
    a, b = _list(client, h, "A"), _list(client, h, "B")
    sec_of_a = _section(client, h, a["id"], "Staying")
    m = _mission(client, h, title="Travelling", list_id=a["id"])
    # Moving to B while claiming A's section: the section is wrong for the
    # destination, whichever field the handler happens to read first.
    r = client.put(f"/api/missions/{m['id']}",
                   json={"list_id": b["id"], "section_id": sec_of_a["id"]}, headers=h)
    assert r.status_code == 400
    unchanged = client.get("/api/missions", headers=h).json()[0]
    assert (unchanged["list_id"], unchanged["section_id"]) == (a["id"], None)


def test_moving_a_mission_to_the_inbox_drops_its_section(client, auth_headers):
    h = auth_headers("sec_to_inbox")
    lst = _list(client, h, "A")
    sec = _section(client, h, lst["id"], "Research")
    m = _mission(client, h, title="x", list_id=lst["id"], section_id=sec["id"])
    r = client.put(f"/api/missions/{m['id']}", json={"list_id": None}, headers=h)
    assert (r.json()["list_id"], r.json()["section_id"]) == (None, None)


def test_a_mission_can_leave_its_section_and_stay_in_the_list(client, auth_headers):
    h = auth_headers("sec_ungroup")
    lst = _list(client, h, "A")
    sec = _section(client, h, lst["id"], "Research")
    m = _mission(client, h, title="x", list_id=lst["id"], section_id=sec["id"])
    r = client.put(f"/api/missions/{m['id']}", json={"section_id": None}, headers=h)
    assert (r.json()["list_id"], r.json()["section_id"]) == (lst["id"], None)


def test_an_update_that_says_nothing_about_either_leaves_both_alone(client, auth_headers):
    h = auth_headers("sec_untouched")
    lst = _list(client, h, "A")
    sec = _section(client, h, lst["id"], "Research")
    m = _mission(client, h, title="x", list_id=lst["id"], section_id=sec["id"])
    r = client.put(f"/api/missions/{m['id']}", json={"priority": "high"}, headers=h)
    assert (r.json()["list_id"], r.json()["section_id"]) == (lst["id"], sec["id"])


def test_missions_can_be_filtered_to_a_section_and_to_the_ungrouped(client, auth_headers):
    h = auth_headers("sec_filter")
    lst = _list(client, h, "A")
    sec = _section(client, h, lst["id"], "Research")
    _mission(client, h, title="grouped", list_id=lst["id"], section_id=sec["id"])
    _mission(client, h, title="loose", list_id=lst["id"])

    got = client.get(f"/api/missions?section_id={sec['id']}", headers=h).json()
    assert [m["title"] for m in got] == ["grouped"]
    none = client.get("/api/missions?section_id=none", headers=h).json()
    assert [m["title"] for m in none] == ["loose"]


def test_counts_are_open_missions_only(client, auth_headers):
    h = auth_headers("sec_counts")
    lst = _list(client, h, "A")
    sec = _section(client, h, lst["id"], "Research")
    _mission(client, h, title="a", list_id=lst["id"], section_id=sec["id"])
    done = _mission(client, h, title="b", list_id=lst["id"], section_id=sec["id"])
    assert client.get("/api/sections", headers=h).json()[0]["open_missions"] == 2
    client.put(f"/api/missions/{done['id']}", json={"status": "completed"}, headers=h)
    assert client.get("/api/sections", headers=h).json()[0]["open_missions"] == 1


# --- what happens when things are deleted -------------------------------


def test_deleting_a_section_ungroups_its_missions_and_keeps_them_in_the_list(client, auth_headers):
    h = auth_headers("sec_delete")
    lst = _list(client, h, "A")
    sec = _section(client, h, lst["id"], "Doomed")
    m = _mission(client, h, title="Survivor", list_id=lst["id"], section_id=sec["id"])

    assert client.delete(f"/api/sections/{sec['id']}", headers=h).status_code == 204
    after = client.get("/api/missions", headers=h).json()
    # Still there, still in the list: only the subdivision went.
    assert [(x["id"], x["list_id"], x["section_id"]) for x in after] \
        == [(m["id"], lst["id"], None)]


def test_deleting_a_list_takes_its_sections_but_not_its_missions(client, auth_headers):
    h = auth_headers("sec_delete_list")
    lst = _list(client, h, "A")
    sec = _section(client, h, lst["id"], "Inside")
    m = _mission(client, h, title="Survivor", list_id=lst["id"], section_id=sec["id"])

    assert client.delete(f"/api/lists/{lst['id']}", headers=h).status_code == 204
    # A section cannot outlive the list it subdivides...
    assert client.get("/api/sections", headers=h).json() == []
    # ...but the work outlives both.
    after = client.get("/api/missions", headers=h).json()
    assert [(x["id"], x["list_id"], x["section_id"]) for x in after] == [(m["id"], None, None)]


# --- the ownership boundary ---------------------------------------------


def test_a_section_cannot_be_hung_off_another_users_list(client, auth_headers):
    mine, theirs = auth_headers("sec_att1"), auth_headers("sec_vic1")
    victim = _list(client, theirs, "Private")
    r = client.post("/api/sections",
                    json={"list_id": victim["id"], "name": "Trespass"}, headers=mine)
    assert r.status_code == 400


def test_a_mission_cannot_be_put_in_another_users_section(client, auth_headers):
    mine, theirs = auth_headers("sec_att2"), auth_headers("sec_vic2")
    victim_list = _list(client, theirs, "Private")
    victim_sec = _section(client, theirs, victim_list["id"], "Private section")
    my_list = _list(client, mine, "Mine")
    m = _mission(client, mine, title="Mine", list_id=my_list["id"])
    r = client.put(f"/api/missions/{m['id']}",
                   json={"section_id": victim_sec["id"]}, headers=mine)
    assert r.status_code == 400
    assert client.get("/api/missions", headers=mine).json()[0]["section_id"] is None


def test_another_users_section_cannot_be_renamed_or_deleted(client, auth_headers):
    mine, theirs = auth_headers("sec_att3"), auth_headers("sec_vic3")
    victim_list = _list(client, theirs, "Private")
    victim_sec = _section(client, theirs, victim_list["id"], "Private section")
    assert client.put(f"/api/sections/{victim_sec['id']}",
                      json={"name": "Owned"}, headers=mine).status_code == 404
    assert client.delete(f"/api/sections/{victim_sec['id']}",
                         headers=mine).status_code == 404
    assert client.get("/api/sections", headers=theirs).json()[0]["name"] == "Private section"


def test_another_users_sections_are_not_listed(client, auth_headers):
    mine, theirs = auth_headers("sec_att4"), auth_headers("sec_vic4")
    victim_list = _list(client, theirs, "Private")
    _section(client, theirs, victim_list["id"], "Private section")
    assert client.get("/api/sections", headers=mine).json() == []


# --- Alfred -------------------------------------------------------------


def test_alfred_files_a_mission_into_a_section_by_name(client, auth_headers, db_for):
    h = auth_headers("sec_alfred_file")
    lst = _list(client, h, "Khorasan")
    _section(client, h, lst["id"], "Research")
    with db_for("sec_alfred_file") as (db, user):
        from services import alfred_tools
        out = alfred_tools.execute_tool(db, user, "create_mission", {
            "title": "Read the paper", "list": "Khorasan", "section": "research"})
    assert (out["mission"]["list"], out["mission"]["section"]) == ("Khorasan", "Research")


def test_alfred_is_told_which_sections_a_list_has_when_he_gets_it_wrong(client, auth_headers, db_for):
    h = auth_headers("sec_alfred_wrong")
    lst = _list(client, h, "Khorasan")
    _section(client, h, lst["id"], "Research")
    with db_for("sec_alfred_wrong") as (db, user):
        from services import alfred_tools
        with pytest.raises(ValueError) as caught:
            alfred_tools.execute_tool(db, user, "create_mission", {
                "title": "x", "list": "Khorasan", "section": "Reserch"})
    msg = str(caught.value)
    assert "Reserch" in msg and "Research" in msg


def test_alfred_cannot_put_a_section_on_a_mission_with_no_list(client, auth_headers, db_for):
    h = auth_headers("sec_alfred_nolist")
    lst = _list(client, h, "Khorasan")
    _section(client, h, lst["id"], "Research")
    with db_for("sec_alfred_nolist") as (db, user):
        from services import alfred_tools
        with pytest.raises(ValueError) as caught:
            alfred_tools.execute_tool(db, user, "create_mission",
                                      {"title": "x", "section": "Research"})
    assert "list" in str(caught.value).lower()


def test_alfred_sees_each_lists_sections_without_a_second_call(client, auth_headers, db_for):
    h = auth_headers("sec_alfred_sees")
    lst = _list(client, h, "Khorasan")
    _section(client, h, lst["id"], "Research")
    _section(client, h, lst["id"], "Writing")
    with db_for("sec_alfred_sees") as (db, user):
        from services import alfred_tools
        out = alfred_tools.execute_tool(db, user, "get_lists", {})
    assert out["lists"][0]["sections"] == ["Research", "Writing"]


def test_alfred_can_create_a_section_when_asked(client, auth_headers, db_for):
    h = auth_headers("sec_alfred_create")
    _list(client, h, "Khorasan")
    with db_for("sec_alfred_create") as (db, user):
        from services import alfred_tools
        out = alfred_tools.execute_tool(db, user, "create_section",
                                        {"list": "Khorasan", "name": "Research"})
    assert out["section"] == {"name": "Research", "list": "Khorasan"}


def test_alfred_does_not_invent_a_section(client, auth_headers, db_for):
    h = auth_headers("sec_alfred_no_invent")
    lst = _list(client, h, "Khorasan")
    with db_for("sec_alfred_no_invent") as (db, user):
        from services import alfred_tools
        with pytest.raises(ValueError):
            alfred_tools.execute_tool(db, user, "create_mission", {
                "title": "x", "list": "Khorasan", "section": "Brand New"})
    assert client.get("/api/sections", headers=h).json() == []


def test_alfred_can_move_a_mission_out_of_its_section(client, auth_headers, db_for):
    h = auth_headers("sec_alfred_out")
    lst = _list(client, h, "Khorasan")
    sec = _section(client, h, lst["id"], "Research")
    m = _mission(client, h, title="x", list_id=lst["id"], section_id=sec["id"])
    with db_for("sec_alfred_out") as (db, user):
        from services import alfred_tools
        out = alfred_tools.execute_tool(db, user, "update_mission",
                                        {"mission_id": m["id"], "section": "none"})
    # Out of the section, still in the list.
    assert out["mission"]["section"] is None and out["mission"]["list"] == "Khorasan"


def test_alfred_moving_lists_and_sections_at_once_checks_the_destination(client, auth_headers, db_for):
    h = auth_headers("sec_alfred_both")
    a, b = _list(client, h, "A"), _list(client, h, "B")
    _section(client, h, b["id"], "Landing")
    m = _mission(client, h, title="Travelling", list_id=a["id"])
    with db_for("sec_alfred_both") as (db, user):
        from services import alfred_tools
        out = alfred_tools.execute_tool(db, user, "update_mission", {
            "mission_id": m["id"], "list": "B", "section": "Landing"})
    assert (out["mission"]["list"], out["mission"]["section"]) == ("B", "Landing")
