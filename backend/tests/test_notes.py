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


# --- Alfred's private memory is kept out of the user's notes ---------------

def test_notes_scope_separates_alfred_memory(client, auth_headers):
    """Alfred's memory notes live in the notes table under a tag. They are HIS
    record, so they must not clutter the user's own notes by default."""
    h = auth_headers("notes_scope_user")
    client.post("/api/notes", headers=h, json={"title": "My own note", "body": "mine"})
    client.post("/api/notes", headers=h,
                json={"title": "Identity", "body": "remembered", "tags": "alfred-memory"})

    mine = client.get("/api/notes", headers=h).json()                     # default
    assert [n["title"] for n in mine] == ["My own note"]

    alfred = client.get("/api/notes?scope=alfred", headers=h).json()
    assert [n["title"] for n in alfred] == ["Identity"]

    both = client.get("/api/notes?scope=all", headers=h).json()
    assert {n["title"] for n in both} == {"My own note", "Identity"}


def test_notes_scope_rejects_unknown_value(client, auth_headers):
    h = auth_headers("notes_scope_bad")
    assert client.get("/api/notes?scope=everything", headers=h).status_code == 422


def test_alfred_still_reads_and_writes_its_own_memory(auth_headers):
    """The separation must not blind Alfred to his own memory."""
    from database import SessionLocal
    import models
    from services import alfred_tools

    auth_headers("notes_scope_alfred")
    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="notes_scope_alfred").first()
        alfred_tools.execute_tool(db, user, "alfred_remember",
                                  {"title": "Prefers tea", "content": "Earl Grey"})
        topics = alfred_tools.execute_tool(db, user, "alfred_list_memory_topics", {})
        assert any(t["title"] == "Prefers tea" for t in topics["topics"])
        recalled = alfred_tools.execute_tool(db, user, "alfred_recall", {"query": "tea"})
        assert recalled["memories"] and "Earl Grey" in recalled["memories"][0]["body"]
        # ...while the user-facing notes tool does not show it
        listed = alfred_tools.execute_tool(db, user, "list_notes", {})
        assert all(n["title"] != "Prefers tea" for n in listed["notes"])
    finally:
        db.close()
