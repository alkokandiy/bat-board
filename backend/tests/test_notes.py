"""Tests for the Notes API (router + service + owner scoping + rate limit)."""


def test_notes_crud_round_trip(client, headers):
    r = client.post(
        "/api/notes",
        json={"title": "First", "body": "hello world", "category": "ideas"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    note = r.json()
    assert note["title"] == "First"
    assert note["is_pinned"] is False
    note_id = note["id"]

    r = client.get("/api/notes", headers=headers)
    assert r.status_code == 200
    assert any(n["id"] == note_id for n in r.json())

    r = client.put("/api/notes/999999", json={"title": "x"}, headers=headers)
    assert r.status_code == 404

    r = client.put(f"/api/notes/{note_id}", json={"title": "Renamed", "is_pinned": True}, headers=headers)
    assert r.status_code == 200
    assert r.json()["title"] == "Renamed"
    assert r.json()["is_pinned"] is True

    r = client.delete(f"/api/notes/{note_id}", headers=headers)
    assert r.status_code == 204

    r = client.get("/api/notes", headers=headers)
    assert all(n["id"] != note_id for n in r.json())


def test_notes_owner_scoping(client, headers, auth_headers):
    other = auth_headers("notes_user_b")
    r = client.post("/api/notes", json={"title": "private"}, headers=headers)
    note_id = r.json()["id"]

    # Other user cannot see it in their list
    r = client.get("/api/notes", headers=other)
    assert all(n["id"] != note_id for n in r.json())

    # Other user cannot update or delete it (guessed ID)
    assert client.put(f"/api/notes/{note_id}", json={"title": "hijack"}, headers=other).status_code == 404
    assert client.delete(f"/api/notes/{note_id}", headers=other).status_code == 404

    # Owner's note untouched
    r = client.get("/api/notes", headers=headers)
    mine = [n for n in r.json() if n["id"] == note_id]
    assert len(mine) == 1 and mine[0]["title"] == "private"


def test_notes_search_and_sort(client, auth_headers):
    h = auth_headers("notes_user_search")
    client.post("/api/notes", json={"title": "Zebra alpha", "body": "..."}, headers=h)
    client.post("/api/notes", json={"title": "Apple beta", "body": "..."}, headers=h)
    client.post("/api/notes", json={"title": "Other", "body": "mentions zebra here"}, headers=h)

    r = client.get("/api/notes?search=zebra", headers=h)
    assert r.status_code == 200
    assert len(r.json()) == 2

    r = client.get("/api/notes?search=ZEBRA", headers=h)
    assert len(r.json()) == 2

    r = client.get("/api/notes?sort=title", headers=h)
    titles = [n["title"] for n in r.json()]
    assert titles == sorted(titles, key=str.lower)

    r = client.get("/api/notes?sort=bogus", headers=h)
    assert r.status_code == 422


def test_notes_pin_sort_first(client, auth_headers):
    h = auth_headers("notes_user_pin")
    client.post("/api/notes", json={"title": "aaa plain"}, headers=h)
    r = client.post("/api/notes", json={"title": "zzz pinned", "is_pinned": True}, headers=h)
    assert r.json()["is_pinned"] is True

    r = client.get("/api/notes?sort=title", headers=h)
    assert r.json()[0]["title"] == "zzz pinned"


def test_notes_rate_limit(client, auth_headers):
    h = auth_headers("notes_user_ratelimit")
    statuses = set()
    for _ in range(35):
        r = client.post("/api/notes", json={"title": "spam"}, headers=h)
        statuses.add(r.status_code)
    assert 429 in statuses
