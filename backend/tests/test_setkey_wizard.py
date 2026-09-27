"""Guided /setkey wizard tests (provider SDKs mocked, no network)."""

import json

import models
from database import SessionLocal
from services import alfred_agent, provider_config_service, telegram_service

SECRET_HEADER = {"X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret-12345"}

_next_update_id = [9500]


def _update(chat_id="tg-wiz", text="hello", message_id=7):
    _next_update_id[0] += 1
    return {
        "update_id": _next_update_id[0],
        "message": {"message_id": message_id, "chat": {"id": chat_id}, "text": text},
    }


def _callback(from_id, data, cb_id="cb-1"):
    _next_update_id[0] += 1
    return {
        "update_id": _next_update_id[0],
        "callback_query": {
            "id": cb_id,
            "from": {"id": from_id, "first_name": "T"},
            "message": {"message_id": 9, "chat": {"id": str(from_id)}, "text": "pick"},
            "data": data,
        },
    }


def _db():
    return SessionLocal()


def _user(username):
    db = _db()
    try:
        return db.query(models.BatAccount).filter_by(username=username).first()
    finally:
        db.close()


def _mock_send(monkeypatch):
    sent = []
    monkeypatch.setattr(
        telegram_service, "send_telegram_message", lambda *a, **kw: sent.append((a, kw)) or True
    )
    return sent


def _mock_scrub(monkeypatch):
    deleted = []
    monkeypatch.setattr(
        telegram_service, "delete_telegram_message",
        lambda *a, **kw: deleted.append((a, kw)) or True,
    )
    answered = []
    monkeypatch.setattr(
        telegram_service, "answer_callback_query",
        lambda *a, **kw: answered.append((a, kw)) or True,
    )
    return deleted, answered


def _mock_test_ok(monkeypatch):
    async def fake_test(provider, model_name, raw_api_key):
        return True, "Key works."

    monkeypatch.setattr(provider_config_service, "test_config", fake_test)


def _link_chat(client, headers, chat_id):
    code = client.post("/api/account/telegram-link/generate-code", headers=headers).json()["code"]
    client.post("/api/telegram/webhook", json=_update(chat_id, code), headers=SECRET_HEADER)


def _wizard_row(username):
    db = _db()
    try:
        user = db.query(models.BatAccount).filter_by(username=username).first()
        return (
            db.query(models.BatPendingAlfredAction)
            .filter_by(owner_id=user.id, action_type="setup_wizard")
            .first()
        )
    finally:
        db.close()


def _last_markup(sent):
    # sent items: ((token, chat, text), {"reply_markup": {...}})
    for (a, kw) in reversed(sent):
        if kw.get("reply_markup"):
            return a[2], kw["reply_markup"]
    return None, None


def test_detect_provider_from_key():
    assert provider_config_service.detect_provider_from_key("AIzaSyABC123") == "gemini"
    assert provider_config_service.detect_provider_from_key("sk-ant-xyz") == "anthropic"
    assert provider_config_service.detect_provider_from_key("sk-xyz123") is None
    assert provider_config_service.detect_provider_from_key("") is None
    assert provider_config_service.detect_provider_from_key("  AIzaSyABC123  ") == "gemini"


def test_autodetect_gemini_skips_provider_question(client, auth_headers, monkeypatch):
    h = auth_headers("wiz_auto")
    sent = _mock_send(monkeypatch)
    deleted, _ = _mock_scrub(monkeypatch)
    _link_chat(client, h, "wiz-auto")

    client.post("/api/telegram/webhook", json=_update("wiz-auto", "/setkey"), headers=SECRET_HEADER)
    assert any("Paste your API key" in a[2] for a, kw in sent)

    sent.clear()
    client.post(
        "/api/telegram/webhook", json=_update("wiz-auto", "AIzaSyABCDEF123456", message_id=11),
        headers=SECRET_HEADER,
    )
    # Raw key message scrubbed.
    assert len(deleted) == 1 and deleted[0][0][2] == 11
    # Provider question skipped → model keyboard shown.
    text, markup = _last_markup(sent)
    assert "gemini" in text
    datas = [b["callback_data"] for row in markup["inline_keyboard"] for b in row]
    assert any(d.startswith("wmodel:") for d in datas)
    assert not any(d.startswith("wprov:") for d in datas)

    row = _wizard_row("wiz_auto")
    args = json.loads(row.action_args)
    assert args["stage"] == "awaiting_model" and args["provider"] == "gemini"
    assert "AIzaSyABCDEF123456" not in row.action_args
    assert provider_config_service.decrypt_key(args["key_encrypted"]) == "AIzaSyABCDEF123456"


def test_ambiguous_key_asks_provider(client, auth_headers, monkeypatch):
    h = auth_headers("wiz_amb")
    sent = _mock_send(monkeypatch)
    _mock_scrub(monkeypatch)
    _link_chat(client, h, "wiz-amb")

    client.post("/api/telegram/webhook", json=_update("wiz-amb", "/setkey"), headers=SECRET_HEADER)
    sent.clear()
    client.post(
        "/api/telegram/webhook", json=_update("wiz-amb", "sk-zzz111aaa", message_id=12),
        headers=SECRET_HEADER,
    )
    text, markup = _last_markup(sent)
    assert "provider" in text.lower()
    datas = [b["callback_data"] for row in markup["inline_keyboard"] for b in row]
    assert {f"wprov:{p}" for p in ("gemini", "anthropic", "openai", "deepseek", "kimi")} <= set(datas)

    row = _wizard_row("wiz_amb")
    args = json.loads(row.action_args)
    assert args["stage"] == "awaiting_provider"
    assert "sk-zzz111aaa" not in row.action_args


def test_full_flow_across_calls_saves(client, auth_headers, monkeypatch):
    h = auth_headers("wiz_full")
    sent = _mock_send(monkeypatch)
    _mock_scrub(monkeypatch)
    _mock_test_ok(monkeypatch)
    _link_chat(client, h, "424242")

    client.post("/api/telegram/webhook", json=_update("424242", "/setkey"), headers=SECRET_HEADER)
    client.post("/api/telegram/webhook", json=_update("424242", "sk-ds-testkey", message_id=13), headers=SECRET_HEADER)
    client.post("/api/telegram/webhook", json=_callback(424242, "wprov:deepseek", cb_id="cb-a"), headers=SECRET_HEADER)
    client.post(
        "/api/telegram/webhook", json=_callback(424242, "wmodel:deepseek-chat", cb_id="cb-b"),
        headers=SECRET_HEADER,
    )

    db = _db()
    try:
        user = db.query(models.BatAccount).filter_by(username="wiz_full").first()
        row = provider_config_service.get_config_row(db, user)
        assert row.provider == "deepseek" and row.model_name == "deepseek-chat"
        assert provider_config_service.get_decrypted_key(db, user) == "sk-ds-testkey"
        assert (
            db.query(models.BatPendingAlfredAction).filter_by(owner_id=user.id).first() is None
        )
    finally:
        db.close()
    assert any("saved" in a[2] for a, kw in sent), [a[2] for a, kw in sent]


def test_expired_wizard_ignored_then_fresh_start(client, auth_headers, monkeypatch):
    from datetime import datetime, timedelta, timezone

    h = auth_headers("wiz_exp")

    class FakeAdapter:
        async def generate(self, messages, tools, system_instruction=None):
            return FakeResp()

    class FakeResp:
        text = "Normal reply, sir."
        tool_calls = []

    monkeypatch.setattr(alfred_agent, "resolve_adapter_for_user", lambda db, user: FakeAdapter())
    sent = _mock_send(monkeypatch)
    _link_chat(client, h, "wiz-exp")

    # Plant an expired wizard row directly.
    db = _db()
    try:
        user = db.query(models.BatAccount).filter_by(username="wiz_exp").first()
        db.add(models.BatPendingAlfredAction(
            owner_id=user.id, action_type="setup_wizard",
            action_args=json.dumps({"wizard": "setkey", "stage": "awaiting_key"}),
            confirmation_message="",
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        ))
        db.commit()
    finally:
        db.close()

    # Expired → plain text goes to the normal turn, not the wizard.
    client.post("/api/telegram/webhook", json=_update("wiz-exp", "hello there"), headers=SECRET_HEADER)
    assert any("Normal reply" in a[2] for a, kw in sent)

    # Fresh /setkey works after the abandoned one.
    sent.clear()
    client.post("/api/telegram/webhook", json=_update("wiz-exp", "/setkey"), headers=SECRET_HEADER)
    assert any("Paste your API key" in a[2] for a, kw in sent)


def test_setkey_clears_destructive_and_vice_versa(client, auth_headers, monkeypatch):
    from datetime import datetime, timedelta, timezone

    h = auth_headers("wiz_pend")
    sent = _mock_send(monkeypatch)
    _link_chat(client, h, "wiz-pend")

    db = _db()
    try:
        user = db.query(models.BatAccount).filter_by(username="wiz_pend").first()
        db.add(models.BatPendingAlfredAction(
            owner_id=user.id, action_type="delete_note",
            action_args=json.dumps({"note_id": 1}), confirmation_message="x",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
        ))
        db.commit()
    finally:
        db.close()

    client.post("/api/telegram/webhook", json=_update("wiz-pend", "/setkey"), headers=SECRET_HEADER)

    db = _db()
    try:
        user = db.query(models.BatAccount).filter_by(username="wiz_pend").first()
        rows = db.query(models.BatPendingAlfredAction).filter_by(owner_id=user.id).all()
        assert [r.action_type for r in rows] == ["setup_wizard"]
    finally:
        db.close()

    # And a /-command clears the wizard back.
    sent.clear()
    client.post("/api/telegram/webhook", json=_update("wiz-pend", "/new"), headers=SECRET_HEADER)
    assert any("new conversation" in a[2] for a, kw in sent)
    db = _db()
    try:
        user = db.query(models.BatAccount).filter_by(username="wiz_pend").first()
        assert db.query(models.BatPendingAlfredAction).filter_by(owner_id=user.id).first() is None
    finally:
        db.close()


def test_regression_tools_bearing_validation(monkeypatch):
    """A key failing ONLY on tools-bearing calls must fail test_config.

    Old code validated with tools=[] — such a key would wrongly pass and be
    saved, failing one message later. New code must reject it at save time.
    """
    from services.llm_providers.base import LLMResponse

    class ToolsFailAdapter:
        def __init__(self, api_key, model):
            pass

        async def generate(self, messages, tools, system_instruction=None):
            if tools:
                exc = RuntimeError("400 INVALID_ARGUMENT: function calling not enabled")
                exc.status_code = 400
                raise exc
            return LLMResponse(text="ok")

    monkeypatch.setattr(
        provider_config_service, "build_adapter",
        lambda provider, model_name, raw_api_key: ToolsFailAdapter(raw_api_key, model_name),
    )

    import asyncio

    ok, msg = asyncio.get_event_loop().run_until_complete(
        provider_config_service.test_config("gemini", "gemini-3.1-flash-lite", "k")
    )
    assert ok is False
    assert "400" in msg
