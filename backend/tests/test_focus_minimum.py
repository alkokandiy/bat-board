"""Focus sessions under MIN_FOCUS_MINUTES are discarded: not logged, not
counted, no points, no mission minutes."""

from datetime import datetime, timedelta, timezone

import models
from database import SessionLocal
from services import focus_service

_n = [900000]


def _user():
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"fm{_n[0]}", hashed_password="x", points=0)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _session(uid, minutes_ago, mission_id=None):
    db = SessionLocal()
    try:
        s = models.BatFocus(
            owner_id=uid, mission_id=mission_id,
            start_time=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        )
        db.add(s)
        db.commit()
        db.refresh(s)
        return s.id
    finally:
        db.close()


def test_short_session_is_discarded_and_not_stored():
    uid = _user()
    sid = _session(uid, minutes_ago=2)  # ~2 min elapsed
    db = SessionLocal()
    try:
        res = focus_service.end_focus_session(db, db.get(models.BatAccount, uid), sid)
        assert res is not None and res.discarded is True
        assert res.duration_minutes < focus_service.MIN_FOCUS_MINUTES
    finally:
        db.close()
    db = SessionLocal()
    try:
        assert db.get(models.BatFocus, sid) is None          # row deleted
        assert db.get(models.BatAccount, uid).points == 0    # no points
    finally:
        db.close()


def test_short_session_does_not_credit_mission():
    uid = _user()
    db = SessionLocal()
    try:
        m = models.BatMission(owner_id=uid, title="Deep work", focus_minutes=0)
        db.add(m)
        db.commit()
        mid = m.id
    finally:
        db.close()
    sid = _session(uid, minutes_ago=3, mission_id=mid)
    db = SessionLocal()
    try:
        focus_service.end_focus_session(db, db.get(models.BatAccount, uid), sid)
    finally:
        db.close()
    db = SessionLocal()
    try:
        assert db.get(models.BatMission, mid).focus_minutes == 0
    finally:
        db.close()


def test_long_enough_session_is_logged_and_credited():
    uid = _user()
    db = SessionLocal()
    try:
        m = models.BatMission(owner_id=uid, title="Real work", focus_minutes=0)
        db.add(m)
        db.commit()
        mid = m.id
    finally:
        db.close()
    sid = _session(uid, minutes_ago=12, mission_id=mid)
    db = SessionLocal()
    try:
        res = focus_service.end_focus_session(db, db.get(models.BatAccount, uid), sid)
        assert res.discarded is False
        assert res.duration_minutes >= focus_service.MIN_FOCUS_MINUTES
    finally:
        db.close()
    db = SessionLocal()
    try:
        assert db.get(models.BatFocus, sid) is not None
        assert db.get(models.BatMission, mid).focus_minutes >= focus_service.MIN_FOCUS_MINUTES
        assert db.get(models.BatAccount, uid).points >= focus_service.MIN_FOCUS_MINUTES
    finally:
        db.close()


def test_api_short_session_reports_discarded(client, auth_headers):
    h = auth_headers("fm_api_user")
    sid = client.post("/api/focus/sessions", headers=h, json={}).json()["id"]
    # Just started → elapsed ~0, so any duration is capped tiny and discarded.
    r = client.put(f"/api/focus/sessions/{sid}", headers=h, json={"duration_minutes": 3})
    assert r.status_code == 200
    assert r.json()["discarded"] is True
    # not in the session list
    listed = client.get("/api/focus/sessions", headers=h).json()
    assert all(s["id"] != sid for s in listed)


# --- backfilled time must not masquerade as a measured habit --------------

def test_the_suggestion_ignores_backfilled_blocks():
    """+15m on a mission row is a quantity remembered, not a session run.

    `suggested_focus_minutes` is documented as "the user's own median" and
    AGENTS.md forbids a constant in its place. Letting one-tap backfills into
    the sample would quietly turn that median into a median of button
    presses — which is worse than a constant, because it looks personal.
    """
    import models
    from database import SessionLocal
    from services import focus_service

    db = SessionLocal()
    try:
        u = models.BatAccount(username="fsug1", hashed_password="x", timezone="UTC")
        db.add(u)
        db.commit()
        db.refresh(u)

        base = datetime(2026, 11, 1, 9, 0)
        # Ten real 50-minute sessions...
        for i in range(10):
            db.add(models.BatFocus(
                owner_id=u.id, start_time=base + timedelta(days=i),
                end_time=base + timedelta(days=i, minutes=50),
                duration_minutes=50, logged_manually=False))
        # ...and twenty taps of "+15m".
        for i in range(20):
            db.add(models.BatFocus(
                owner_id=u.id, start_time=base + timedelta(days=i, hours=3),
                end_time=base + timedelta(days=i, hours=3, minutes=15),
                duration_minutes=15, logged_manually=True))
        db.commit()

        out = focus_service.suggested_focus_minutes(db, u)
        assert out["basis"] == "history"
        assert out["minutes"] == 50, "backfilled blocks dragged the median"
        assert out["sessions"] == 10
    finally:
        db.close()


def test_someone_who_only_backfills_is_told_it_is_a_default():
    """Honest, rather than inventing a personal number from nothing."""
    import models
    from database import SessionLocal
    from services import focus_service

    db = SessionLocal()
    try:
        u = models.BatAccount(username="fsug2", hashed_password="x", timezone="UTC")
        db.add(u)
        db.commit()
        db.refresh(u)

        base = datetime(2026, 11, 1, 9, 0)
        for i in range(12):
            db.add(models.BatFocus(
                owner_id=u.id, start_time=base + timedelta(days=i),
                end_time=base + timedelta(days=i, minutes=30),
                duration_minutes=30, logged_manually=True))
        db.commit()

        out = focus_service.suggested_focus_minutes(db, u)
        assert out["basis"] == "default"
        assert out["sessions"] == 0
    finally:
        db.close()
