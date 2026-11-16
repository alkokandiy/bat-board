"""Moving things by dragging them.

A drag is one gesture and means one thing: *this happens later now*. The
two rules worth guarding are that moving an event keeps its length, and
that moving a mission keeps the time of day it was due at.
"""

import contextlib

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


def _event(client, h, **body):
    r = client.post("/api/calendar/events", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _mission(client, h, **body):
    r = client.post("/api/missions", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


# --- events -------------------------------------------------------------


def test_moving_an_event_keeps_how_long_it_lasts(client, auth_headers):
    """The whole point. Setting the start alone would shorten it."""
    h = auth_headers("move_len")
    ev = _event(client, h, title="Standup",
                start_time="2026-11-20T09:00:00",
                end_time="2026-11-20T10:30:00")

    r = client.post(f"/api/calendar/events/{ev['id']}/move",
                    json={"start_time": "2026-11-20T14:00:00"}, headers=h)
    assert r.status_code == 200, r.text
    moved = r.json()
    assert moved["start_time"].startswith("2026-11-20T14:00")
    # 90 minutes, still.
    assert moved["end_time"].startswith("2026-11-20T15:30")


def test_moving_an_event_to_another_day_keeps_its_length_too(client, auth_headers):
    h = auth_headers("move_day")
    ev = _event(client, h, title="Long one",
                start_time="2026-11-20T09:00:00",
                end_time="2026-11-20T11:00:00")
    r = client.post(f"/api/calendar/events/{ev['id']}/move",
                    json={"start_time": "2026-11-23T09:00:00"}, headers=h)
    moved = r.json()
    assert moved["start_time"].startswith("2026-11-23T09:00")
    assert moved["end_time"].startswith("2026-11-23T11:00")


def test_moving_an_event_earlier_works_the_same(client, auth_headers):
    h = auth_headers("move_earlier")
    ev = _event(client, h, title="Early",
                start_time="2026-11-20T15:00:00",
                end_time="2026-11-20T16:00:00")
    moved = client.post(f"/api/calendar/events/{ev['id']}/move",
                        json={"start_time": "2026-11-20T08:00:00"}, headers=h).json()
    assert moved["start_time"].startswith("2026-11-20T08:00")
    assert moved["end_time"].startswith("2026-11-20T09:00")


def test_an_event_with_no_end_simply_starts_later(client, auth_headers):
    h = auth_headers("move_noend")
    ev = _event(client, h, title="Open ended", start_time="2026-11-20T09:00:00")
    assert ev["end_time"] is None
    moved = client.post(f"/api/calendar/events/{ev['id']}/move",
                        json={"start_time": "2026-11-20T13:00:00"}, headers=h).json()
    assert moved["start_time"].startswith("2026-11-20T13:00")
    assert moved["end_time"] is None


def test_a_move_that_would_push_the_start_past_the_end_is_not_a_time_order_error(client, auth_headers):
    """The failure this function exists to prevent.

    Through `update_event` with only a start, dragging a 09:00–10:00 event
    to 14:00 leaves the end at 10:00 and the move is refused for ending
    before it begins — an error about time order, for a gesture that was
    never about time order.
    """
    h = auth_headers("move_not_order_error")
    ev = _event(client, h, title="Meeting",
                start_time="2026-11-20T09:00:00",
                end_time="2026-11-20T10:00:00")

    # What a naive drag handler would send:
    naive = client.put(f"/api/calendar/events/{ev['id']}",
                       json={"start_time": "2026-11-20T14:00:00"}, headers=h)
    assert naive.status_code == 400

    # What moving actually does:
    r = client.post(f"/api/calendar/events/{ev['id']}/move",
                    json={"start_time": "2026-11-20T14:00:00"}, headers=h)
    assert r.status_code == 200
    assert r.json()["end_time"].startswith("2026-11-20T15:00")


def test_another_users_event_cannot_be_moved(client, auth_headers):
    mine, theirs = auth_headers("move_att"), auth_headers("move_vic")
    ev = _event(client, theirs, title="Private", start_time="2026-11-20T09:00:00")
    r = client.post(f"/api/calendar/events/{ev['id']}/move",
                    json={"start_time": "2026-11-20T23:00:00"}, headers=mine)
    assert r.status_code == 404
    still = client.get("/api/calendar/events", headers=theirs).json()
    assert still[0]["start_time"].startswith("2026-11-20T09:00")


# --- missions -----------------------------------------------------------


def test_moving_a_mission_keeps_the_time_of_day(client, auth_headers):
    h = auth_headers("move_mission_time")
    m = _mission(client, h, title="Call the bank", due_date="2026-11-20T16:30:00")
    r = client.post(f"/api/missions/{m['id']}/move", json={"day": "2026-11-25"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["due_date"].startswith("2026-11-25T16:30")


def test_the_day_you_drop_on_is_the_day_you_get(client, auth_headers):
    """The off-by-one that converting timezones here would cause.

    The board reads a mission's day as the first ten characters of what is
    stored, so moving replaces exactly those ten and converts nothing.
    """
    h = auth_headers("move_mission_offbyone")
    for at in ("00:00:00", "23:00:00", "12:00:00"):
        m = _mission(client, h, title=f"At {at}", due_date=f"2026-11-20T{at}")
        moved = client.post(f"/api/missions/{m['id']}/move",
                            json={"day": "2026-11-21"}, headers=h).json()
        assert moved["due_date"][:10] == "2026-11-21", at


def test_a_mission_with_no_date_gets_one(client, auth_headers):
    h = auth_headers("move_mission_undated")
    m = _mission(client, h, title="Someday")
    assert m["due_date"] is None
    moved = client.post(f"/api/missions/{m['id']}/move",
                        json={"day": "2026-12-01"}, headers=h).json()
    assert moved["due_date"].startswith("2026-12-01T00:00")


def test_rubbish_is_refused(client, auth_headers):
    h = auth_headers("move_mission_rubbish")
    m = _mission(client, h, title="x", due_date="2026-11-20T09:00:00")
    for day in ("tomorrow", "2026-13-45", "20-11-2026"):
        r = client.post(f"/api/missions/{m['id']}/move", json={"day": day}, headers=h)
        assert r.status_code in (400, 422), day
    # Untouched.
    assert client.get("/api/missions", headers=h).json()[0]["due_date"].startswith("2026-11-20")


def test_another_users_mission_cannot_be_moved(client, auth_headers):
    mine, theirs = auth_headers("move_m_att"), auth_headers("move_m_vic")
    m = _mission(client, theirs, title="Private", due_date="2026-11-20T09:00:00")
    r = client.post(f"/api/missions/{m['id']}/move", json={"day": "2026-11-21"}, headers=mine)
    assert r.status_code == 404
    assert client.get("/api/missions", headers=theirs).json()[0]["due_date"].startswith("2026-11-20")


def test_moving_does_not_touch_anything_else(client, auth_headers):
    """A drag changes when, and nothing else — not the list, not the
    section, not the priority, not whether it is done."""
    h = auth_headers("move_only_when")
    lst = client.post("/api/lists", json={"name": "Work"}, headers=h).json()
    sec = client.post("/api/sections",
                      json={"list_id": lst["id"], "name": "Now"}, headers=h).json()
    m = _mission(client, h, title="Careful", due_date="2026-11-20T09:00:00",
                 priority="critical", list_id=lst["id"], section_id=sec["id"],
                 is_pinned=True)

    moved = client.post(f"/api/missions/{m['id']}/move",
                        json={"day": "2026-11-21"}, headers=h).json()
    assert moved["priority"] == "critical"
    assert moved["list_id"] == lst["id"]
    assert moved["section_id"] == sec["id"]
    assert moved["is_pinned"] is True
    assert moved["status"] == "pending"


def test_the_order_rule_works_whichever_way_the_time_is_spelt(client, auth_headers):
    """A pre-existing 500, found while building the move endpoint.

    These columns are naive, but the API serialises them with a "Z" and a
    client may send an offset of its own. Comparing a client's aware
    datetime against a stored naive one raised TypeError inside
    `ensure_time_order` — a 500 about nothing, where the answer should
    have been an ordinary 400 about time order.

    An offset is not a different rule. Each of these ends before the
    event starts and each must be refused the same way.
    """
    h = auth_headers("tz_order")
    ev = _event(client, h, title="Ordered", start_time="2026-11-20T09:00:00")
    for end in ("2026-11-20T08:00:00", "2026-11-20T08:00:00Z", "2026-11-20T13:00:00+06:00"):
        r = client.put(f"/api/calendar/events/{ev['id']}",
                       json={"end_time": end}, headers=h)
        assert r.status_code == 400, f"{end} -> {r.status_code}"


def test_an_end_after_the_start_is_accepted_whichever_way_it_is_spelt(client, auth_headers):
    """The other side of it: normalising must not make everything a 400."""
    h = auth_headers("tz_order_ok")
    ev = _event(client, h, title="Fine", start_time="2026-11-20T09:00:00")
    for end in ("2026-11-20T11:00:00", "2026-11-20T11:00:00Z", "2026-11-20T17:00:00+06:00"):
        r = client.put(f"/api/calendar/events/{ev['id']}",
                       json={"end_time": end}, headers=h)
        assert r.status_code == 200, f"{end} -> {r.text}"
