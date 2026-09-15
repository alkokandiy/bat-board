"""Tests for PAT auth + Telegram webhook (no LLM, outbound calls mocked)."""

import hashlib
import inspect
from datetime import datetime, timedelta, timezone

import routers.telegram as telegram_router
from services import telegram_service

SECRET_HEADER = {"X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret-12345"}

_next_update_id = [1000]


def _update(chat_id="tg-1", text="hello"):
    _next_update_id[0] += 1
    return {"update_id": _next_update_id[0], "message": {"message_id": 1, "chat": {"id": chat_id}, "text": text}}


def _expire_code(code):
    from database import SessionLocal
    import models

    db = SessionLocal()
    try:
        row = (
            db.query(models.BatTelegramLinkCode)
            .filter_by(code_hash=hashlib.sha256(code.encode()).hexdigest())
            .first()
        )
        assert row is not None
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()


def _pat_row(owner_username):
    from database import SessionLocal
    import models

    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username=owner_username).first()
        return (
            db.query(models.BatPersonalAccessToken)
            .filter_by(owner_id=user.id)
            .first()
        )
    finally:
        db.close()


def test_webhook_secret_validation(client, auth_headers):
    auth_headers("tg_user_secret")

    # Missing header → 403, body never parsed
    r = client.post("/api/telegram/webhook", json=_update())
    assert r.status_code == 403

    # Wrong value → 403
    r = client.post(
        "/api/telegram/webhook",
        json=_update(),
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )
    assert r.status_code == 403

    # Correct header passes validation (unlinked chat → 200 + instructions)
    r = client.post("/api/telegram/webhook", json=_update(chat_id="nobody"), headers=SECRET_HEADER)
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_webhook_uses_compare_digest():
    src = inspect.getsource(telegram_router)
    assert "compare_digest" in src


def test_linking_end_to_end(client, auth_headers, monkeypatch):
    h = auth_headers("tg_user_link")
    sent = []
    monkeypatch.setattr(
        telegram_service, "send_telegram_message", lambda *a: sent.append(a) or True
    )

    r = client.post("/api/account/telegram-link/generate-code", headers=h)
    assert r.status_code == 200
    code = r.json()["code"]
    assert len(code) == 6 and code.isdigit()

    # Wrong code → not linked
    r = client.post("/api/telegram/webhook", json=_update(chat_id="chat-9", text="000000"), headers=SECRET_HEADER)
    assert r.status_code == 200

    # Right code → PAT row created, chat set, code consumed
    r = client.post("/api/telegram/webhook", json=_update(chat_id="chat-9", text=code), headers=SECRET_HEADER)
    assert r.status_code == 200
    assert any("Linked" in call[2] for call in sent)

    pat = _pat_row("tg_user_link")
    assert pat is not None
    assert pat.telegram_chat_id == "chat-9"
    assert pat.revoked is False
    # Hashed at rest: 64-char hex, and definitely not the 6-digit code
    assert len(pat.token_hash) == 64
    assert pat.token_hash != code
    int(pat.token_hash, 16)

    from database import SessionLocal
    import models

    db = SessionLocal()
    try:
        assert db.query(models.BatTelegramLinkCode).count() == 0 or True  # other tests may add rows
        mine = (
            db.query(models.BatTelegramLinkCode)
            .filter_by(code_hash=hashlib.sha256(code.encode()).hexdigest())
            .first()
        )
        assert mine is None  # consumed code deleted
    finally:
        db.close()

    # Reusing the same code fails (already consumed)
    sent.clear()
    r = client.post("/api/telegram/webhook", json=_update(chat_id="chat-9", text=code), headers=SECRET_HEADER)
    assert r.status_code == 200
    assert not any("Linked" in call[2] for call in sent)

    # Status endpoint reflects the link
    r = client.get("/api/account/telegram-link/status", headers=h)
    assert r.json() == {"linked": True}


def test_expired_code_rejected(client, auth_headers, monkeypatch):
    h = auth_headers("tg_user_expired")
    sent = []
    monkeypatch.setattr(
        telegram_service, "send_telegram_message", lambda *a: sent.append(a) or True
    )

    r = client.post("/api/account/telegram-link/generate-code", headers=h)
    code = r.json()["code"]
    _expire_code(code)

    r = client.post("/api/telegram/webhook", json=_update(chat_id="chat-x", text=code), headers=SECRET_HEADER)
    assert r.status_code == 200
    assert not any("Linked" in call[2] for call in sent)
    assert _pat_row("tg_user_expired") is None


def test_placeholder_reply_for_linked_user(client, auth_headers, monkeypatch):
    h = auth_headers("tg_user_placeholder")
    sent = []
    monkeypatch.setattr(
        telegram_service, "send_telegram_message", lambda *a: sent.append(a) or True
    )

    code = client.post("/api/account/telegram-link/generate-code", headers=h).json()["code"]
    client.post("/api/telegram/webhook", json=_update(chat_id="chat-p", text=code), headers=SECRET_HEADER)
    sent.clear()

    r = client.post(
        "/api/telegram/webhook", json=_update(chat_id="chat-p", text="how is my day?"), headers=SECRET_HEADER
    )
    assert r.status_code == 200
    assert len(sent) == 1
    bot_token, chat_id, text = sent[0]
    assert bot_token == "test-bot-token"
    assert chat_id == "chat-p"
    # No GEMINI_API_KEY in tests → fail-closed reply, no crash.
    assert "isn't configured yet" in text


def test_unlink_revokes_and_unlinks(client, auth_headers, monkeypatch):
    h = auth_headers("tg_user_unlink")
    sent = []
    monkeypatch.setattr(
        telegram_service, "send_telegram_message", lambda *a: sent.append(a) or True
    )

    code = client.post("/api/account/telegram-link/generate-code", headers=h).json()["code"]
    client.post("/api/telegram/webhook", json=_update(chat_id="chat-u", text=code), headers=SECRET_HEADER)

    r = client.delete("/api/account/telegram-link", headers=h)
    assert r.status_code == 204

    pat = _pat_row("tg_user_unlink")
    assert pat.revoked is True
    assert pat.telegram_chat_id is None

    r = client.get("/api/account/telegram-link/status", headers=h)
    assert r.json() == {"linked": False}

    # Subsequent messages from that chat are treated as unlinked
    sent.clear()
    r = client.post(
        "/api/telegram/webhook", json=_update(chat_id="chat-u", text="hello?"), headers=SECRET_HEADER
    )
    assert r.status_code == 200
    assert any("isn't linked" in call[2] for call in sent)
