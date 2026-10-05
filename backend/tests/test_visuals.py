"""Phase 4 visuals: focus-week chart + daily-brief card, delivered to Telegram.

Charts are drawn from the user's real data (Pillow) and sent via sendPhoto.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import models
from database import SessionLocal
from routers.telegram import process_telegram_update
from services import alfred_agent, alfred_tools, telegram_service, visuals
from services.llm_provider import LLMResponse, ToolCall
from services.llm_providers.base import ProviderCapabilities

_next = [8800]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _text_update(chat_id, text):
    _next[0] += 1
    return {"update_id": _next[0], "message": {"message_id": 1, "chat": {"id": chat_id}, "text": text}}


class FakeAdapter:
    def __init__(self, script):
        self._script = script
        self.calls = 0

    def capabilities(self, model_name=None):
        return ProviderCapabilities(supports_tool_calling=True)

    async def generate(self, messages, tools, system_instruction=None):
        item = self._script[min(self.calls, len(self._script) - 1)]
        self.calls += 1
        return item


def _link(client, h, chat_id):
    code = client.post("/api/account/telegram-link/generate-code", headers=h).json()["code"]
    db = SessionLocal()
    try:
        telegram_service.exchange_link_code(db, code, str(chat_id))
    finally:
        db.close()


def _seed_focus(username, minutes_by_dayback):
    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username=username).first()
        now = datetime.now(timezone.utc)
        for back, mins in minutes_by_dayback.items():
            db.add(models.BatFocus(
                owner_id=user.id, start_time=now - timedelta(days=back, minutes=mins),
                end_time=now - timedelta(days=back), duration_minutes=mins, mode="normal"))
        db.commit()
        return user.id
    finally:
        db.close()


def _is_png(b):
    return isinstance(b, bytes) and b[:8] == b"\x89PNG\r\n\x1a\n"


# --- renderers ---

def test_focus_week_and_daily_brief_render_png(client, auth_headers):
    h = auth_headers("viz_render")
    _seed_focus("viz_render", {1: 30, 2: 45, 4: 20})
    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="viz_render").first()
        png, cap = visuals.render_focus_week(db, user)
        assert _is_png(png) and len(png) > 1000 and "Focus" in cap
        png2, cap2 = visuals.render_daily_brief(db, user)
        assert _is_png(png2) and "brief" in cap2.lower()
    finally:
        db.close()


# --- tool layer ---

def test_visual_tools_queue_media_when_sink_present(client, auth_headers):
    h = auth_headers("viz_tool")
    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="viz_tool").first()
        sink = []
        r = alfred_tools.execute_tool(db, user, "show_focus_chart", {}, media_sink=sink)
        assert r["status"] == "sent" and len(sink) == 1 and _is_png(sink[0]["png"])
        r2 = alfred_tools.execute_tool(db, user, "show_daily_brief", {}, media_sink=sink)
        assert r2["status"] == "sent" and len(sink) == 2
    finally:
        db.close()


def test_visual_tool_without_sink_reports_unavailable(client, auth_headers):
    h = auth_headers("viz_web")
    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="viz_web").first()
        r = alfred_tools.execute_tool(db, user, "show_focus_chart", {})  # no sink (web)
        assert r["status"] == "unavailable_here" and "Telegram" in r["note"]
    finally:
        db.close()


# --- end-to-end via Telegram ---

def test_asking_for_focus_chart_sends_a_photo(client, auth_headers, monkeypatch):
    h = auth_headers("viz_tg")
    _link(client, h, 880001)
    _seed_focus("viz_tg", {1: 60, 3: 25})
    adapter = FakeAdapter([
        LLMResponse(tool_calls=[ToolCall("show_focus_chart", {})]),
        LLMResponse(text="Here's your focus week, sir."),
    ])
    monkeypatch.setattr(alfred_agent, "resolve_adapter_for_user", lambda db, user: adapter)
    sent, photos = [], []
    monkeypatch.setattr(telegram_service, "send_telegram_message", lambda *a, **kw: sent.append(a[2]) or True)
    monkeypatch.setattr(telegram_service, "send_telegram_photo",
                        lambda token, chat, png, caption="", **kw: photos.append((png, caption)) or True)

    _run(process_telegram_update(_text_update(880001, "show me my focus this week"), None))

    assert "Here's your focus week, sir." in sent
    assert len(photos) == 1 and _is_png(photos[0][0]) and "Focus" in photos[0][1]
