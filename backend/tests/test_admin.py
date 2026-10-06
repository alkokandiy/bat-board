"""Admin endpoints: gated by ADMIN_USERNAMES, list/disable/enable/delete.

Additive feature — these tests also confirm non-admins are locked out and that
admins are protected from self/admin deletion.
"""

import models
from database import SessionLocal
from routers import admin as admin_router


def _mk_settings(*admins):
    # admin_usernames is a plain comma-separated string (env-safe), like prod.
    return type("S", (), {"admin_usernames": ",".join(admins)})()


def _uid(username):
    db = SessionLocal()
    try:
        u = db.query(models.BatAccount).filter_by(username=username).first()
        return u.id if u else None
    finally:
        db.close()


def test_non_admin_me_is_false_and_users_forbidden(client, auth_headers, monkeypatch):
    h = auth_headers("plainuser")
    monkeypatch.setattr(admin_router, "get_settings", lambda: _mk_settings())  # no admins
    assert client.get("/api/admin/me", headers=h).json() == {"is_admin": False}
    assert client.get("/api/admin/users", headers=h).status_code == 403


def test_admin_me_true_and_lists_users(client, auth_headers, monkeypatch):
    h = auth_headers("bossuser")
    monkeypatch.setattr(admin_router, "get_settings", lambda: _mk_settings("bossuser"))
    assert client.get("/api/admin/me", headers=h).json() == {"is_admin": True}
    r = client.get("/api/admin/users", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["total_users"] >= 1
    assert any(u["username"] == "bossuser" and u["is_admin"] for u in body["users"])


def test_disable_and_enable_user(client, auth_headers, monkeypatch):
    admin_h = auth_headers("boss2")
    auth_headers("victim2")  # create target
    monkeypatch.setattr(admin_router, "get_settings", lambda: _mk_settings("boss2"))
    vid = _uid("victim2")

    r = client.post(f"/api/admin/users/{vid}/disable", headers=admin_h)
    assert r.status_code == 200 and r.json()["is_active"] is False

    r = client.post(f"/api/admin/users/{vid}/enable", headers=admin_h)
    assert r.status_code == 200 and r.json()["is_active"] is True


def test_cannot_disable_or_delete_self(client, auth_headers, monkeypatch):
    admin_h = auth_headers("boss3")
    monkeypatch.setattr(admin_router, "get_settings", lambda: _mk_settings("boss3"))
    bid = _uid("boss3")
    assert client.post(f"/api/admin/users/{bid}/disable", headers=admin_h).status_code == 400
    assert client.delete(f"/api/admin/users/{bid}", headers=admin_h).status_code == 400


def test_cannot_delete_another_admin(client, auth_headers, monkeypatch):
    admin_h = auth_headers("boss4")
    auth_headers("boss5")
    monkeypatch.setattr(admin_router, "get_settings", lambda: _mk_settings("boss4", "boss5"))
    other = _uid("boss5")
    assert client.delete(f"/api/admin/users/{other}", headers=admin_h).status_code == 400


def test_delete_user_cascades(client, auth_headers, monkeypatch):
    admin_h = auth_headers("boss6")
    auth_headers("victim6")
    monkeypatch.setattr(admin_router, "get_settings", lambda: _mk_settings("boss6"))
    vid = _uid("victim6")

    # give the victim some data
    db = SessionLocal()
    try:
        db.add(models.BatMission(owner_id=vid, title="to be gone"))
        db.add(models.BatBriefing(owner_id=vid, kind="morning", send_time="07:00"))
        db.commit()
    finally:
        db.close()

    r = client.delete(f"/api/admin/users/{vid}", headers=admin_h)
    assert r.status_code == 200 and r.json()["deleted"] == "victim6"

    db = SessionLocal()
    try:
        assert db.get(models.BatAccount, vid) is None
        assert db.query(models.BatMission).filter_by(owner_id=vid).count() == 0
        assert db.query(models.BatBriefing).filter_by(owner_id=vid).count() == 0
    finally:
        db.close()


def test_users_endpoint_requires_auth(client, monkeypatch):
    monkeypatch.setattr(admin_router, "get_settings", lambda: _mk_settings("whoever"))
    assert client.get("/api/admin/users").status_code == 401
