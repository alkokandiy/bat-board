"""Telegram-first signup: a brand-new chatter gets an account auto-created and
a welcome, with no web step."""

import asyncio

from starlette.background import BackgroundTasks

import models
from database import SessionLocal
from routers import telegram as tg
from services import alfred_agent, telegram_service
from services.llm_provider import LLMResponse

_c = [0]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _chat():
    _c[0] += 1
    return f"signup-chat-{_c[0]}"


def _update(chat_id, text):
    return {"update_id": hash(chat_id + text) & 0xFFFFFF,
            "message": {"message_id": 1, "chat": {"id": chat_id}, "text": text}}


def _mock_send(monkeypatch):
    sent = []
    monkeypatch.setattr(telegram_service, "send_telegram_message",
                        lambda token, chat_id, text, **kw: sent.append(text) or True)
    return sent


# --- service ---------------------------------------------------------------

def test_create_account_and_lookup():
    cid = _chat()
    db = SessionLocal()
    try:
        acct = telegram_service.create_telegram_account(db, cid)
        assert acct.username.startswith("bat-")
        assert telegram_service.get_user_by_chat_id(db, cid).id == acct.id
        # a linked PAT exists
        assert db.query(models.BatPersonalAccessToken).filter_by(
            telegram_chat_id=cid, revoked=False).count() == 1
    finally:
        db.close()


# --- webhook ---------------------------------------------------------------

def test_start_autocreates_and_welcomes(monkeypatch):
    sent = _mock_send(monkeypatch)
    cid = _chat()
    _run(tg.process_telegram_update(_update(cid, "/start"), BackgroundTasks()))

    db = SessionLocal()
    try:
        assert telegram_service.get_user_by_chat_id(db, cid) is not None
    finally:
        db.close()
    assert any("I'm Alfred" in t for t in sent)


def test_first_real_message_creates_and_answers(monkeypatch):
    sent = _mock_send(monkeypatch)
    monkeypatch.setattr(alfred_agent, "resolve_adapter_for_user",
                        lambda db, user: _FakeAdapter())
    cid = _chat()
    _run(tg.process_telegram_update(_update(cid, "what can you do?"), BackgroundTasks()))

    # welcome + a real answer both went out
    assert any("I'm Alfred" in t for t in sent)
    assert any("At your service" in t for t in sent)


def test_second_message_does_not_duplicate_account(monkeypatch):
    _mock_send(monkeypatch)
    monkeypatch.setattr(alfred_agent, "resolve_adapter_for_user",
                        lambda db, user: _FakeAdapter())
    cid = _chat()
    _run(tg.process_telegram_update(_update(cid, "hello"), BackgroundTasks()))
    _run(tg.process_telegram_update(_update(cid, "again"), BackgroundTasks()))

    db = SessionLocal()
    try:
        linked = db.query(models.BatPersonalAccessToken).filter_by(
            telegram_chat_id=cid, revoked=False).count()
        assert linked == 1   # one account, not two
    finally:
        db.close()


class _FakeAdapter:
    async def generate(self, messages, tools, system_instruction=None):
        return LLMResponse(text="At your service, sir.")
