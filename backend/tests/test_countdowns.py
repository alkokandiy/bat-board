"""Tests for the Countdowns API (router + service + owner scoping + rate limit)."""

from datetime import datetime, timedelta, timezone


def _iso(dt):
    return dt.isoformat()


def test_countdowns_crud_round_trip(client, headers):
    future = _iso(datetime.now(timezone.utc) + timedelta(days=10))
    r = client.post(
        "/api/countdowns",
        json={"title": "Launch", "target_date": future},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    cd = r.json()
    assert cd["title"] == "Launch"
    assert 9 <= cd["days_remaining"] <= 10
    cd_id = cd["id"]

    r = client.get("/api/countdowns", headers=headers)
    assert r.status_code == 200
    assert any(c["id"] == cd_id for c in r.json())

    assert client.delete("/api/countdowns/999999", headers=headers).status_code == 404

    r = client.delete(f"/api/countdowns/{cd_id}", headers=headers)
    assert r.status_code == 204

    r = client.get("/api/countdowns", headers=headers)
    assert all(c["id"] != cd_id for c in r.json())


def test_countdowns_past_due_no_crash(client, auth_headers):
    h = auth_headers("countdown_user_past")
    past = _iso(datetime.now(timezone.utc) - timedelta(days=3, hours=2))
    r = client.post(
        "/api/countdowns", json={"title": "Overdue", "target_date": past}, headers=h
    )
    assert r.status_code == 201, r.text
    assert r.json()["days_remaining"] <= 0

    # datetime-local format without timezone (what the frontend sends)
    r = client.post(
        "/api/countdowns",
        json={"title": "LocalFmt", "target_date": "2030-01-01T12:00"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    assert r.json()["days_remaining"] > 0


def test_countdowns_sort_soonest_first(client, auth_headers):
    h = auth_headers("countdown_user_sort")
    now = datetime.now(timezone.utc)
    for days in (30, 1, 7):
        client.post(
            "/api/countdowns",
            json={"title": f"D{days}", "target_date": _iso(now + timedelta(days=days))},
            headers=h,
        )
    r = client.get("/api/countdowns", headers=h)
    titles = [c["title"] for c in r.json() if c["title"].startswith("D")]
    assert titles == ["D1", "D7", "D30"]


def test_countdowns_owner_scoping(client, headers, auth_headers):
    other = auth_headers("countdown_user_b")
    future = _iso(datetime.now(timezone.utc) + timedelta(days=5))
    r = client.post(
        "/api/countdowns", json={"title": "mine", "target_date": future}, headers=headers
    )
    cd_id = r.json()["id"]

    r = client.get("/api/countdowns", headers=other)
    assert all(c["id"] != cd_id for c in r.json())
    assert client.delete(f"/api/countdowns/{cd_id}", headers=other).status_code == 404

    r = client.get("/api/countdowns", headers=headers)
    assert any(c["id"] == cd_id for c in r.json())


def test_countdowns_rate_limit(client, auth_headers):
    h = auth_headers("countdown_user_ratelimit")
    future = _iso(datetime.now(timezone.utc) + timedelta(days=5))
    statuses = set()
    for _ in range(35):
        r = client.post(
            "/api/countdowns", json={"title": "spam", "target_date": future}, headers=h
        )
        statuses.add(r.status_code)
    assert 429 in statuses
