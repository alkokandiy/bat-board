"""Regressions for two vulnerabilities found in the security review.

1. The Telegram link-code brute-force guard was gated on `user is None`, which
   Telegram-first signup silently killed: a chat gets an account on its first
   message, so an attacker who said "hi" once could guess 6-digit link codes
   for ever with no counter and no lockout. A hit re-links the victim's account
   to the attacker's chat.
2. Admin rights are keyed on the username, and usernames are freely chosen and
   changeable — so an admin name nobody currently holds was claimable.
"""

import asyncio

from starlette.background import BackgroundTasks

import models
from database import SessionLocal
from routers import admin as admin_router
from routers import telegram as tg
from services import telegram_service

_c = [0]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _chat():
    _c[0] += 1
    return f"sec-chat-{_c[0]}"


def _update(chat_id, text):
    _c[0] += 1
    return {"update_id": 880000 + _c[0],
            "message": {"message_id": 1, "chat": {"id": chat_id}, "text": text}}


def _mock_send(monkeypatch):
    sent = []
    monkeypatch.setattr(telegram_service, "send_telegram_message",
                        lambda token, chat_id, text, **kw: sent.append(text) or True)
    return sent


# --- 1. link-code brute force ---------------------------------------------

def test_link_code_guesses_are_throttled_even_for_a_linked_chat(monkeypatch):
    sent = _mock_send(monkeypatch)
    cid = _chat()

    # One ordinary message: Telegram-first signup links this chat to an account.
    _run(tg.process_telegram_update(_update(cid, "hi"), BackgroundTasks()))
    db = SessionLocal()
    try:
        assert telegram_service.get_user_by_chat_id(db, cid) is not None
    finally:
        db.close()

    # Now guess link codes. Before the fix these were never counted or blocked.
    sent.clear()
    for i in range(8):
        _run(tg.process_telegram_update(_update(cid, f"{100000 + i}"), BackgroundTasks()))

    db = SessionLocal()
    try:
        assert telegram_service.link_attempts_blocked(db, cid) is True
    finally:
        db.close()
    assert any("Too many incorrect codes" in t for t in sent)


def test_failures_are_recorded_for_a_linked_chat(monkeypatch):
    _mock_send(monkeypatch)
    cid = _chat()
    _run(tg.process_telegram_update(_update(cid, "hello"), BackgroundTasks()))

    _run(tg.process_telegram_update(_update(cid, "123456"), BackgroundTasks()))
    db = SessionLocal()
    try:
        row = (db.query(models.BatTelegramLinkAttempt)
               .filter_by(chat_id=cid).first())
        assert row is not None and row.failures >= 1   # the counter now moves
    finally:
        db.close()


def test_a_valid_code_still_links_and_clears_failures(client, auth_headers, monkeypatch):
    """The guard must not break the legitimate flow."""
    sent = _mock_send(monkeypatch)
    h = auth_headers("sec_link_user")
    cid = _chat()
    _run(tg.process_telegram_update(_update(cid, "hi"), BackgroundTasks()))

    code = client.post("/api/account/telegram-link/generate-code", headers=h).json()["code"]
    sent.clear()
    _run(tg.process_telegram_update(_update(cid, code), BackgroundTasks()))

    assert any("Linked" in t for t in sent)
    db = SessionLocal()
    try:
        assert telegram_service.get_user_by_chat_id(db, cid).username == "sec_link_user"
        assert telegram_service.link_attempts_blocked(db, cid) is False
    finally:
        db.close()


# --- 2. admin username claiming -------------------------------------------

def _admins(monkeypatch, *names):
    monkeypatch.setattr(admin_router, "get_settings",
                        lambda: type("S", (), {"admin_usernames": ",".join(names)})())


def test_cannot_register_into_an_unclaimed_admin_name(client, monkeypatch):
    _admins(monkeypatch, "ghost_admin")
    r = client.post("/api/auth/register",
                    json={"username": "ghost_admin", "password": "pass1234"})
    assert r.status_code == 409          # the name is not claimable


def test_cannot_register_a_case_variant_of_an_admin_name(client, monkeypatch):
    _admins(monkeypatch, "ghost_admin2")
    r = client.post("/api/auth/register",
                    json={"username": "Ghost_Admin2", "password": "pass1234"})
    assert r.status_code == 409


def test_cannot_rename_into_an_admin_name(client, auth_headers, monkeypatch):
    h = auth_headers("sec_plain_user")
    _admins(monkeypatch, "ghost_admin3")
    r = client.put("/api/account", headers=h, json={"username": "ghost_admin3"})
    assert r.status_code == 409
    # and they did not become an admin
    monkeypatch.setattr(admin_router, "get_settings",
                        lambda: type("S", (), {"admin_usernames": "ghost_admin3"})())
    assert client.get("/api/admin/users", headers=h).status_code == 403


def test_ordinary_rename_still_works(client, auth_headers, monkeypatch):
    h = auth_headers("sec_rename_user")
    _admins(monkeypatch, "ghost_admin4")
    r = client.put("/api/account", headers=h, json={"username": "sec_renamed_ok"})
    assert r.status_code == 200


def test_admin_matching_is_case_insensitive(client, auth_headers, monkeypatch):
    """An owner configured as "Admin" who registered as "admin" keeps powers."""
    h = auth_headers("sec_case_admin")
    _admins(monkeypatch, "SEC_CASE_ADMIN")
    assert client.get("/api/admin/users", headers=h).status_code == 200
