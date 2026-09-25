"""Batch B tests: BYOK provider configs (real Fernet cipher, no network)."""

import models
from database import SessionLocal
from services import alfred_agent, provider_config_service, telegram_service
from services.llm_providers.anthropic_adapter import AnthropicAdapter
from services.llm_providers.gemini import GeminiAdapter
from services.llm_providers.openai_compatible import OpenAICompatibleAdapter

SECRET_HEADER = {"X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret-12345"}

_next_update_id = [9000]


def _update(chat_id="tg-prov", text="hello", message_id=42):
    _next_update_id[0] += 1
    return {
        "update_id": _next_update_id[0],
        "message": {"message_id": message_id, "chat": {"id": chat_id}, "text": text},
    }


def _mock_send(monkeypatch):
    sent = []
    monkeypatch.setattr(
        telegram_service, "send_telegram_message", lambda *a, **kw: sent.append((a, kw)) or True
    )
    return sent


def _link_chat(client, headers, chat_id):
    code = client.post("/api/account/telegram-link/generate-code", headers=headers).json()["code"]
    client.post("/api/telegram/webhook", json=_update(chat_id, code), headers=SECRET_HEADER)


def test_encryption_roundtrip_and_not_plaintext(client, auth_headers):
    auth_headers("prov_enc_user")
    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="prov_enc_user").first()
        row = provider_config_service.save_config(db, user, "gemini", "gemini-3.1-flash-lite", "super-secret-key-123")
        assert row.api_key_encrypted != "super-secret-key-123"
        assert "super-secret" not in row.api_key_encrypted
        assert provider_config_service.get_decrypted_key(db, user) == "super-secret-key-123"
    finally:
        db.close()


def test_status_never_returns_key(client, auth_headers):
    h = auth_headers("prov_status_user")
    r = client.get("/api/alfred/provider", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True
    assert body["provider"] == "gemini"
    assert set(body.keys()) == {"provider", "model_name", "configured"}


def test_endpoint_rejects_save_when_test_fails(client, auth_headers, monkeypatch):
    async def fake_test(provider, model_name, raw_api_key):
        return False, "401 Unauthorized: bad key"

    monkeypatch.setattr(provider_config_service, "test_config", fake_test)
    h = auth_headers("prov_reject_user")

    r = client.post(
        "/api/alfred/provider",
        json={"provider": "openai", "model_name": "gpt-5.6", "api_key": "bad-key"},
        headers=h,
    )
    assert r.status_code == 400
    assert "bad key" in r.json()["detail"]

    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="prov_reject_user").first()
        row = provider_config_service.get_config_row(db, user)
        # Autouse dummy config untouched — the rejected openai save never landed.
        assert row.provider == "gemini"
    finally:
        db.close()


def test_endpoint_saves_when_test_passes(client, auth_headers, monkeypatch):
    async def fake_test(provider, model_name, raw_api_key):
        return True, "Key works."

    monkeypatch.setattr(provider_config_service, "test_config", fake_test)
    h = auth_headers("prov_save_user")

    r = client.post(
        "/api/alfred/provider",
        json={"provider": "anthropic", "model_name": "claude-sonnet-5", "api_key": "good-key"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"provider": "anthropic", "model_name": "claude-sonnet-5", "configured": True}

    r = client.delete("/api/alfred/provider", headers=h)
    assert r.json()["configured"] is False


def test_setkey_valid_saves_and_deletes_message(client, auth_headers, monkeypatch):
    async def fake_test(provider, model_name, raw_api_key):
        return True, "Key works."

    monkeypatch.setattr(provider_config_service, "test_config", fake_test)
    deleted = []
    monkeypatch.setattr(
        telegram_service, "delete_telegram_message",
        lambda *a, **kw: deleted.append((a, kw)) or True,
    )
    sent = _mock_send(monkeypatch)

    h = auth_headers("prov_setkey_user")
    _link_chat(client, h, "chat-setkey")

    r = client.post(
        "/api/telegram/webhook",
        json=_update("chat-setkey", "/setkey deepseek deepseek-chat my-ds-key", message_id=77),
        headers=SECRET_HEADER,
    )
    assert r.status_code == 200

    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="prov_setkey_user").first()
        row = provider_config_service.get_config_row(db, user)
        assert row.provider == "deepseek"
        assert row.model_name == "deepseek-chat"
        assert provider_config_service.get_decrypted_key(db, user) == "my-ds-key"
    finally:
        db.close()

    assert any("saved" in a[2] for a, kw in sent), sent
    assert len(deleted) == 1
    (args, kw) = deleted[0]
    assert args[1] == "chat-setkey" and args[2] == 77


def test_setkey_invalid_not_saved_but_message_still_scrubbed(client, auth_headers, monkeypatch):
    async def fake_test(provider, model_name, raw_api_key):
        return False, "401 Unauthorized: invalid x-api-key"

    monkeypatch.setattr(provider_config_service, "test_config", fake_test)
    deleted = []
    monkeypatch.setattr(
        telegram_service, "delete_telegram_message",
        lambda *a, **kw: deleted.append((a, kw)) or True,
    )
    sent = _mock_send(monkeypatch)

    h = auth_headers("prov_setkey_bad")
    _link_chat(client, h, "chat-setkey-bad")

    r = client.post(
        "/api/telegram/webhook",
        json=_update("chat-setkey-bad", "/setkey kimi kimi-k3 wrong-key", message_id=78),
        headers=SECRET_HEADER,
    )
    assert r.status_code == 200

    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="prov_setkey_bad").first()
        assert provider_config_service.get_config_row(db, user).provider == "gemini"
    finally:
        db.close()

    assert any("not saved" in a[2] for a, kw in sent), sent
    assert len(deleted) == 1  # scrubbed even on failure


def test_no_config_zero_llm_calls(client, auth_headers, monkeypatch):
    from services import llm_provider

    h = auth_headers("prov_noconfig_user")
    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="prov_noconfig_user").first()
        provider_config_service.delete_config(db, user)
    finally:
        db.close()

    # Bomb on every LLM entry point: neither the legacy path nor any
    # adapter may be touched without a config row.
    async def _bomb(*a, **kw):
        raise AssertionError("LLM must not be touched without a config")

    monkeypatch.setattr(llm_provider, "generate", _bomb)

    r = client.post("/api/alfred/sessions", json={"title": "s"}, headers=h)
    session_id = r.json()["id"]
    r = client.post("/api/alfred/chat", json={"message": "hello?", "session_id": session_id}, headers=h)
    assert r.status_code == 200
    assert "isn't connected to a model" in r.json()["reply"]


def test_per_user_routing(client, auth_headers):
    ha = auth_headers("prov_route_a")
    hb = auth_headers("prov_route_b")
    hc = auth_headers("prov_route_c")

    db = SessionLocal()
    try:
        ua = db.query(models.BatAccount).filter_by(username="prov_route_a").first()
        ub = db.query(models.BatAccount).filter_by(username="prov_route_b").first()
        uc = db.query(models.BatAccount).filter_by(username="prov_route_c").first()
        provider_config_service.save_config(db, ua, "gemini", "gemini-3.1-flash-lite", "k1")
        provider_config_service.save_config(db, ub, "anthropic", "claude-sonnet-5", "k2")
        provider_config_service.save_config(db, uc, "deepseek", "deepseek-chat", "k3")

        aa = alfred_agent.resolve_adapter_for_user(db, ua)
        ab = alfred_agent.resolve_adapter_for_user(db, ub)
        ac = alfred_agent.resolve_adapter_for_user(db, uc)
    finally:
        db.close()

    assert isinstance(aa, GeminiAdapter) and aa.model == "gemini-3.1-flash-lite"
    assert isinstance(ab, AnthropicAdapter) and ab.model == "claude-sonnet-5"
    assert isinstance(ac, OpenAICompatibleAdapter)
    assert ac.base_url == "https://api.deepseek.com" and ac.model == "deepseek-chat"
    assert ha and hb and hc
