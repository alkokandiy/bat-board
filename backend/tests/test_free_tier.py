"""Free tier: users with no key of their own run on the operator-funded system
provider (daily-capped); BYOK stays unlimited; both inert until configured."""

import models
from database import SessionLocal
from services import alfred_agent, provider_config_service
from services.llm_provider import LLMResponse

_n = [300000]


def _mk_user(with_byok=False):
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"free{_n[0]}", hashed_password="x")
        db.add(u)
        db.commit()
        db.refresh(u)
        if with_byok:
            provider_config_service.save_config(db, u, "gemini", "m", "k")
        return u.id
    finally:
        db.close()


class _FakeAdapter:
    async def generate(self, messages, tools, system_instruction=None):
        return LLMResponse(text="At your service, sir.")


# --- resolution + tier flag ------------------------------------------------

def test_no_byok_no_system_raises(monkeypatch):
    uid = _mk_user(with_byok=False)
    monkeypatch.setattr(provider_config_service, "build_system_adapter", lambda: None)
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        try:
            alfred_agent.resolve_adapter_for_user(db, user)
            assert False, "expected NoProviderConfiguredError"
        except alfred_agent.NoProviderConfiguredError:
            pass
        assert alfred_agent.user_on_free_tier(db, user) is False
    finally:
        db.close()


def test_no_byok_with_system_uses_free_tier(monkeypatch):
    uid = _mk_user(with_byok=False)
    fake = _FakeAdapter()
    monkeypatch.setattr(provider_config_service, "build_system_adapter", lambda: fake)
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        assert alfred_agent.resolve_adapter_for_user(db, user) is fake
        assert alfred_agent.user_on_free_tier(db, user) is True
    finally:
        db.close()


def test_byok_takes_precedence_and_is_not_free_tier(monkeypatch):
    uid = _mk_user(with_byok=True)
    monkeypatch.setattr(provider_config_service, "build_system_adapter", lambda: _FakeAdapter())
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        adapter = alfred_agent.resolve_adapter_for_user(db, user)
        assert not isinstance(adapter, _FakeAdapter)   # built from the BYOK row
        assert alfred_agent.user_on_free_tier(db, user) is False
    finally:
        db.close()


def test_status_reports_free_tier(monkeypatch):
    uid = _mk_user(with_byok=False)
    monkeypatch.setattr(provider_config_service, "build_system_adapter", lambda: _FakeAdapter())
    db = SessionLocal()
    try:
        st = provider_config_service.get_config_status(db, db.get(models.BatAccount, uid))
        assert st == {"provider": None, "model_name": None, "configured": False, "free_tier": True}
    finally:
        db.close()


# --- cap -------------------------------------------------------------------

def test_check_usage_respects_custom_cap():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        assert alfred_agent.check_usage(db, user, cap=2) is True
        assert alfred_agent.check_usage(db, user, cap=2) is True
        assert alfred_agent.check_usage(db, user, cap=2) is False   # third blocked
    finally:
        db.close()


# --- end-to-end through the chat endpoint ----------------------------------

def test_free_tier_chat_works_then_caps(client, auth_headers, monkeypatch):
    h = auth_headers("free_e2e")
    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="free_e2e").first()
        provider_config_service.delete_config(db, user)   # drop the autouse dummy BYOK
    finally:
        db.close()
    monkeypatch.setattr(provider_config_service, "build_system_adapter", lambda: _FakeAdapter())
    monkeypatch.setattr(alfred_agent, "get_settings",
                        lambda: type("S", (), {"free_tier_daily_cap": 2})())

    sid = client.post("/api/alfred/sessions", json={"title": "t"}, headers=h).json()["id"]

    def say():
        return client.post("/api/alfred/chat", json={"message": "hi", "session_id": sid}, headers=h).json()["reply"]

    assert say() == "At your service, sir."
    assert say() == "At your service, sir."
    assert say() == alfred_agent.FREE_TIER_CAPPED_REPLY   # 3rd over the cap
