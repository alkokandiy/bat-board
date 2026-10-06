"""Phase F: proactive briefings & reminders.

Covers the pure scheduling logic (windows, recurrence), the exactly-once tick,
content building (template + provider-polish fallback + section toggles),
news parsing/degradation, the config service validation, and the cron endpoint
guard. Delivery is stubbed — no real Telegram or provider calls.
"""

import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

import models
from database import SessionLocal
from services import briefings, briefing_service, scheduler

_uid = [700000]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _mk_user(tz="UTC", linked=True):
    _uid[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"brief{_uid[0]}", hashed_password="x",
                              timezone=tz, alfred_address="Master Wayne")
        db.add(u)
        db.commit()
        db.refresh(u)
        if linked:
            db.add(models.BatPersonalAccessToken(
                owner_id=u.id, token_hash=f"h{_uid[0]}", telegram_chat_id=str(9000 + _uid[0])))
            db.commit()
        return u.id
    finally:
        db.close()


def _now_hhmm(tz, offset_minutes=0):
    return (datetime.now(ZoneInfo(tz)) + timedelta(minutes=offset_minutes)).strftime("%H:%M")


@pytest.fixture
def sink(monkeypatch):
    """Capture outbound Telegram messages instead of sending them."""
    sent = []
    monkeypatch.setattr(scheduler.telegram_service, "send_telegram_message",
                        lambda token, chat_id, text, **kw: (sent.append((chat_id, text)) or True))
    monkeypatch.setattr(scheduler, "get_settings", lambda: type("S", (), {"telegram_bot_token": "t"})())
    return sent


def _no_adapter(db, user):
    return None


# --- pure window / recurrence logic ----------------------------------------

def test_within_window_fires_on_time_and_skips_late():
    base = datetime(2026, 1, 5, 7, 0, tzinfo=ZoneInfo("UTC"))  # Monday 07:00
    assert scheduler._within_window(base, time(7, 0)) is True
    assert scheduler._within_window(base + timedelta(minutes=59), time(7, 0)) is True
    assert scheduler._within_window(base + timedelta(hours=2, minutes=59), time(7, 0)) is True
    # more than 3h late → skip (no stale morning brief at noon)
    assert scheduler._within_window(base + timedelta(hours=3, minutes=1), time(7, 0)) is False
    # before the scheduled minute → not yet
    assert scheduler._within_window(base - timedelta(minutes=1), time(7, 0)) is False


def test_reminder_recurrence_matching():
    monday = datetime(2026, 1, 5, 8, 0, tzinfo=ZoneInfo("UTC"))  # weekday()==0

    daily = models.BatReminder(recurrence="daily", send_time="08:00", message="m")
    assert scheduler._reminder_due_today(daily, monday)

    wk = models.BatReminder(recurrence="weekly", send_time="08:00", weekdays="0,3", message="m")
    assert scheduler._reminder_due_today(wk, monday)
    assert not scheduler._reminder_due_today(wk, monday + timedelta(days=1))  # Tuesday

    mo = models.BatReminder(recurrence="monthly", send_time="08:00", day_of_month=5, message="m")
    assert scheduler._reminder_due_today(mo, monday)
    assert not scheduler._reminder_due_today(mo, monday + timedelta(days=1))

    once = models.BatReminder(recurrence="once", send_time="08:00", run_date="2026-01-05", message="m")
    assert scheduler._reminder_due_today(once, monday)
    assert not scheduler._reminder_due_today(once, monday + timedelta(days=1))


def test_monthly_clamps_to_month_end():
    # day_of_month=31 should fire on 28 Feb (non-leap 2026)
    feb28 = datetime(2026, 2, 28, 9, 0, tzinfo=ZoneInfo("UTC"))
    r = models.BatReminder(recurrence="monthly", send_time="09:00", day_of_month=31, message="m")
    assert scheduler._reminder_due_today(r, feb28)


# --- exactly-once tick (integration) ---------------------------------------

def test_briefing_fires_once_then_dedupes(sink):
    uid = _mk_user(tz="UTC")
    db = SessionLocal()
    try:
        briefing_service.upsert_briefing(db, db.get(models.BatAccount, uid),
                                         kind="morning", send_time=_now_hhmm("UTC"))
    finally:
        db.close()

    db = SessionLocal()
    try:
        s1 = _run(scheduler.run_tick(db, adapter_for=_no_adapter))
    finally:
        db.close()
    assert s1["briefings_sent"] == 1
    assert len(sink) == 1

    db = SessionLocal()
    try:
        s2 = _run(scheduler.run_tick(db, adapter_for=_no_adapter))
    finally:
        db.close()
    assert s2["briefings_sent"] == 0  # already logged today
    assert len(sink) == 1


def test_disabled_briefing_does_not_fire(sink):
    uid = _mk_user(tz="UTC")
    db = SessionLocal()
    try:
        briefing_service.upsert_briefing(db, db.get(models.BatAccount, uid),
                                         kind="morning", enabled=False, send_time=_now_hhmm("UTC"))
    finally:
        db.close()
    db = SessionLocal()
    try:
        s = _run(scheduler.run_tick(db, adapter_for=_no_adapter))
    finally:
        db.close()
    assert s["briefings_sent"] == 0
    assert sink == []


def test_user_without_telegram_is_skipped(sink):
    uid = _mk_user(tz="UTC", linked=False)
    db = SessionLocal()
    try:
        briefing_service.upsert_briefing(db, db.get(models.BatAccount, uid),
                                         kind="morning", send_time=_now_hhmm("UTC"))
    finally:
        db.close()
    db = SessionLocal()
    try:
        s = _run(scheduler.run_tick(db, adapter_for=_no_adapter))
    finally:
        db.close()
    assert sink == []


def test_future_briefing_not_yet_due(sink):
    uid = _mk_user(tz="UTC")
    db = SessionLocal()
    try:
        briefing_service.upsert_briefing(db, db.get(models.BatAccount, uid),
                                         kind="night", send_time=_now_hhmm("UTC", offset_minutes=90))
    finally:
        db.close()
    db = SessionLocal()
    try:
        _run(scheduler.run_tick(db, adapter_for=_no_adapter))
    finally:
        db.close()
    assert sink == []


def test_once_reminder_disables_after_firing(sink):
    uid = _mk_user(tz="UTC")
    today = datetime.now(ZoneInfo("UTC")).date().isoformat()
    db = SessionLocal()
    try:
        r = briefing_service.create_reminder(db, db.get(models.BatAccount, uid),
                                             message="take pill", recurrence="once",
                                             send_time=_now_hhmm("UTC"), run_date=today)
        rid = r.id
    finally:
        db.close()
    db = SessionLocal()
    try:
        s = _run(scheduler.run_tick(db, adapter_for=_no_adapter))
    finally:
        db.close()
    assert s["reminders_sent"] == 1
    db = SessionLocal()
    try:
        assert db.get(models.BatReminder, rid).enabled is False
    finally:
        db.close()


def test_daily_reminder_fires_with_alfred_voice(sink):
    uid = _mk_user(tz="UTC")
    db = SessionLocal()
    try:
        briefing_service.create_reminder(db, db.get(models.BatAccount, uid),
                                         message="drink water", recurrence="daily",
                                         send_time=_now_hhmm("UTC"))
    finally:
        db.close()
    db = SessionLocal()
    try:
        _run(scheduler.run_tick(db, adapter_for=_no_adapter))
    finally:
        db.close()
    assert len(sink) == 1
    assert "drink water" in sink[0][1]
    assert "Master Wayne" in sink[0][1]


# --- content: template, toggles, polish fallback ---------------------------

def test_template_contains_sections():
    uid = _mk_user(tz="UTC")
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatHabit(owner_id=uid, name="Meditate", frequency="daily", streak=3))
        db.commit()
        data = briefings.gather_briefing_data(db, user, "morning")
        text = briefings.render_template(user, "morning", data)
    finally:
        db.close()
    assert "Good morning" in text
    assert "Meditate" in text
    assert "Habits" in text


def test_build_falls_back_to_template_on_provider_failure():
    uid = _mk_user(tz="UTC")

    class BoomAdapter:
        async def generate(self, messages, tools, system_instruction=None):
            raise RuntimeError("provider down")

    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        b = briefing_service.upsert_briefing(db, user, kind="morning", send_time="07:00")
        text = _run(briefings.build_briefing_text(db, user, b, adapter=BoomAdapter()))
    finally:
        db.close()
    assert "Good morning" in text  # template, not an error


def test_build_uses_provider_when_it_succeeds():
    uid = _mk_user(tz="UTC")

    class GoodAdapter:
        async def generate(self, messages, tools, system_instruction=None):
            return type("R", (), {"text": "Polished briefing, Master Wayne. All is in order."})()

    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        b = briefing_service.upsert_briefing(db, user, kind="morning", send_time="07:00")
        text = _run(briefings.build_briefing_text(db, user, b, adapter=GoodAdapter()))
    finally:
        db.close()
    assert text.startswith("Polished briefing")


def test_section_toggle_removes_content():
    uid = _mk_user(tz="UTC")
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatHabit(owner_id=uid, name="Pushups", frequency="daily"))
        db.commit()
        b = briefing_service.upsert_briefing(db, user, kind="morning",
                                             send_time="07:00", include_habits=False)
        text = _run(briefings.build_briefing_text(db, user, b, adapter=None))
    finally:
        db.close()
    assert "Pushups" not in text


# --- news ------------------------------------------------------------------

_SAMPLE_RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Anthropic releases a new model - The Verge</title></item>
<item><title>UN summit on cyber defense concludes - Reuters</title></item>
<item><title>Third story - BBC</title></item>
<item><title>Fourth story - AP</title></item>
</channel></rss>"""


def test_parse_rss_titles_limits():
    titles = briefings._parse_rss_titles(_SAMPLE_RSS, 3)
    assert len(titles) == 3
    assert titles[0].startswith("Anthropic releases")


def test_parse_rss_handles_garbage():
    assert briefings._parse_rss_titles("not xml <<<", 3) == []


def test_fetch_news_degrades_on_http_error(monkeypatch):
    briefings._news_cache.clear()

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url): raise httpx.ConnectError("boom")

    monkeypatch.setattr(briefings.httpx, "AsyncClient", lambda **kw: FakeClient())
    out = _run(briefings.fetch_news(["AI"]))
    assert out == {"AI": []}


def test_fetch_news_parses_and_caches(monkeypatch):
    briefings._news_cache.clear()
    calls = [0]

    class FakeResp:
        text = _SAMPLE_RSS
        def raise_for_status(self): pass

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url):
            calls[0] += 1
            return FakeResp()

    monkeypatch.setattr(briefings.httpx, "AsyncClient", lambda **kw: FakeClient())
    out1 = _run(briefings.fetch_news(["cybersecurity"]))
    out2 = _run(briefings.fetch_news(["cybersecurity"]))  # served from cache
    assert len(out1["cybersecurity"]) == 3
    assert out2 == out1
    assert calls[0] == 1  # second call hit the cache


# --- config service validation ---------------------------------------------

def test_briefing_validation():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        with pytest.raises(ValueError):
            briefing_service.upsert_briefing(db, user, kind="noon", send_time="07:00")
        with pytest.raises(ValueError):
            briefing_service.upsert_briefing(db, user, kind="morning", send_time="25:00")
        with pytest.raises(ValueError):  # news on, no topics
            briefing_service.upsert_briefing(db, user, kind="morning",
                                             send_time="07:00", include_news=True)
        b = briefing_service.upsert_briefing(db, user, kind="morning", send_time="07:00",
                                             include_news=True, news_topics="AI, defense")
        assert b.include_news and b.news_topics == "AI, defense"
    finally:
        db.close()


def test_reminder_validation_and_weekday_normalization():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        with pytest.raises(ValueError):
            briefing_service.create_reminder(db, user, message="x", recurrence="weekly",
                                             send_time="09:00")  # no weekdays
        r = briefing_service.create_reminder(db, user, message="gym", recurrence="weekly",
                                             send_time="09:00", weekdays="Mon, Thursday, 0")
        assert r.weekdays == "0,3"
        with pytest.raises(ValueError):
            briefing_service.create_reminder(db, user, message="x", recurrence="monthly",
                                             send_time="09:00", day_of_month=40)
        with pytest.raises(ValueError):
            briefing_service.create_reminder(db, user, message="x", recurrence="once",
                                             send_time="09:00")  # no run_date
    finally:
        db.close()


def test_upsert_briefing_updates_in_place():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        briefing_service.upsert_briefing(db, user, kind="morning", send_time="07:00")
        briefing_service.upsert_briefing(db, user, kind="morning", send_time="08:30")
        rows = briefing_service.list_briefings(db, user)
        assert len(rows) == 1 and rows[0].send_time == "08:30"
    finally:
        db.close()


# --- cron endpoint guard ----------------------------------------------------

def test_cron_requires_configured_secret(client, monkeypatch):
    # By default CRON_SECRET is unset in tests → 503 (feature dormant).
    r = client.post("/api/internal/cron/tick")
    assert r.status_code == 503


def test_cron_rejects_wrong_secret(client, monkeypatch):
    from routers import cron
    monkeypatch.setattr(cron, "get_settings",
                        lambda: type("S", (), {"cron_secret": "right-secret"})())
    assert client.post("/api/internal/cron/tick",
                       headers={"X-Cron-Secret": "wrong"}).status_code == 401
    assert client.post("/api/internal/cron/tick").status_code == 401


def test_cron_accepts_correct_secret(client, monkeypatch):
    from routers import cron
    monkeypatch.setattr(cron, "get_settings",
                        lambda: type("S", (), {"cron_secret": "right-secret"})())

    async def fake_tick(db, adapter_for=None):
        return {"users": 0, "briefings_sent": 0, "briefings_failed": 0,
                "reminders_sent": 0, "reminders_failed": 0}

    monkeypatch.setattr(cron.scheduler, "run_tick", fake_tick)
    r = client.post("/api/internal/cron/tick", headers={"X-Cron-Secret": "right-secret"})
    assert r.status_code == 200 and r.json()["ok"] is True
