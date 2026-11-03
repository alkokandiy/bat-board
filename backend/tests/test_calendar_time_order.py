"""An event cannot end before it begins.

Nothing enforced this. The form, the API and Alfred all accepted it, and the
result sorted and drew as a negative-length block — the sort of thing that
makes the board stop being worth trusting.
"""

from datetime import datetime, timedelta, timezone

import pytest

import models
from database import SessionLocal
from services import calendar_service

_n = [994000]


def _mk_user():
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"cal{_n[0]}", hashed_password="x", timezone="UTC")
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


NOON = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


def test_creating_one_that_ends_before_it_starts_is_refused():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        with pytest.raises(ValueError, match="cannot end before"):
            calendar_service.create_event(
                db, user, title="Backwards", start_time=NOON,
                end_time=NOON - timedelta(hours=1))
        assert calendar_service.list_upcoming_events(db, user) == []
    finally:
        db.close()


def test_an_event_with_no_end_is_fine():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        e = calendar_service.create_event(db, user, title="A moment", start_time=NOON)
        assert e.end_time is None
    finally:
        db.close()


def test_ending_exactly_when_it_starts_is_fine():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        e = calendar_service.create_event(
            db, user, title="Instant", start_time=NOON, end_time=NOON)
        assert e.end_time is not None
    finally:
        db.close()


def test_moving_the_start_past_an_untouched_end_is_refused():
    """The update only ever saw the fields passed to it.

    Pushing the start to after an end that was already stored is the same
    mistake, so the check is against the times the event will HAVE.
    """
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        e = calendar_service.create_event(
            db, user, title="Meeting", start_time=NOON,
            end_time=NOON + timedelta(hours=1))

        with pytest.raises(ValueError, match="cannot end before"):
            calendar_service.update_event(
                db, user, e.id, start_time=NOON + timedelta(hours=5))

        db.rollback()
        assert db.get(models.CalendarEvent, e.id).start_time.hour == 12
    finally:
        db.close()


def test_pulling_the_end_before_an_untouched_start_is_refused():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        e = calendar_service.create_event(
            db, user, title="Meeting", start_time=NOON,
            end_time=NOON + timedelta(hours=1))

        with pytest.raises(ValueError, match="cannot end before"):
            calendar_service.update_event(
                db, user, e.id, end_time=NOON - timedelta(hours=1))
    finally:
        db.close()


def test_a_legitimate_move_still_works():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        e = calendar_service.create_event(
            db, user, title="Meeting", start_time=NOON,
            end_time=NOON + timedelta(hours=1))
        moved = calendar_service.update_event(
            db, user, e.id,
            start_time=NOON + timedelta(days=1),
            end_time=NOON + timedelta(days=1, hours=1))
        assert moved.start_time.day == 4
    finally:
        db.close()


# --- the HTTP surface ------------------------------------------------------
# The PUT route assigns fields itself rather than going through the service
# (it has to: an explicit null there means "clear it", which the service reads
# as "leave it alone"), so it needs covering separately or the rule holds in
# one half of the app and not the other.

def test_the_api_refuses_to_create_a_backwards_event(client, auth_headers):
    h = auth_headers("calapi1")
    r = client.post("/api/calendar/events", headers=h, json={
        "title": "Backwards",
        "start_time": "2026-11-10T12:00:00Z",
        "end_time": "2026-11-10T09:00:00Z",
    })
    assert r.status_code == 400
    assert "end before" in r.json()["detail"]


def test_the_api_refuses_to_edit_one_into_being_backwards(client, auth_headers):
    h = auth_headers("calapi2")
    created = client.post("/api/calendar/events", headers=h, json={
        "title": "Meeting",
        "start_time": "2026-11-10T12:00:00Z",
        "end_time": "2026-11-10T13:00:00Z",
    })
    assert created.status_code == 201
    event_id = created.json()["id"]

    r = client.put(f"/api/calendar/events/{event_id}", headers=h,
                   json={"start_time": "2026-11-10T18:00:00Z"})
    assert r.status_code == 400

    # And the rejected edit did not land anyway.
    after = client.get("/api/calendar/events", headers=h).json()
    assert [e for e in after if e["id"] == event_id][0]["start_time"].startswith("2026-11-10T12:00")


def test_clearing_the_end_time_through_the_api_still_works(client, auth_headers):
    """An explicit null means "no end", and must not trip the check."""
    h = auth_headers("calapi3")
    created = client.post("/api/calendar/events", headers=h, json={
        "title": "Meeting",
        "start_time": "2026-11-10T12:00:00Z",
        "end_time": "2026-11-10T13:00:00Z",
    })
    event_id = created.json()["id"]

    r = client.put(f"/api/calendar/events/{event_id}", headers=h, json={"end_time": None})
    assert r.status_code == 200
    assert r.json()["end_time"] is None
