"""Content for Alfred's proactive briefings.

Pure content generation: gather the user's own bat-board data, optionally add
a few real news headlines, and turn it into a short message in Alfred's voice.
Scheduling and delivery live in services/scheduler.py — this module never
touches Telegram or the clock-driven firing logic, which keeps it easy to test.

Text is produced in two layers:
  1. a template written in Alfred's voice — always available, free, factual;
  2. an optional provider "polish" pass that rephrases the SAME facts more
     naturally. Any failure in layer 2 falls back to layer 1, so a briefing is
     never silently skipped.
"""

from __future__ import annotations

import time as _time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from urllib.parse import quote

import httpx
import structlog

import models
from services.timezones import user_tz, local_today, local_date, day_bounds_utc

log = structlog.get_logger(__name__)


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None)


def _address(user: models.BatAccount) -> str:
    return (getattr(user, "alfred_address", None) or "").strip() or user.username


# --- news ------------------------------------------------------------------
# Google News RSS aggregates reputable outlets, needs no API key, and returns
# "Headline - Publisher" titles — enough to *acknowledge* the day's news
# without a web-search-capable model. Results are cached briefly so a tick that
# briefs several users on the same topic hits Google once.

NEWS_TTL_SECONDS = 600
MAX_NEWS_TOPICS = 4
NEWS_PER_TOPIC = 3
_news_cache: Dict[str, tuple] = {}  # topic -> (fetched_at, [headlines])


def parse_news_topics(raw: Optional[str]) -> List[str]:
    topics = [t.strip() for t in (raw or "").split(",")]
    return [t for t in topics if t][:MAX_NEWS_TOPICS]


def _rss_url(topic: str) -> str:
    # when:1d keeps it to the last day — we want "today's news", not an archive.
    q = quote(f"{topic} when:1d")
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def _parse_rss_titles(xml_text: str, limit: int) -> List[str]:
    import xml.etree.ElementTree as ET

    titles: List[str] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return titles
    for item in root.iter("item"):
        t = item.findtext("title")
        if t and t.strip():
            titles.append(" ".join(t.split()))
        if len(titles) >= limit:
            break
    return titles


async def fetch_news(topics: List[str]) -> Dict[str, List[str]]:
    """Map each topic to a few recent headlines. Never raises; a failed topic
    simply yields no headlines, so news degrades to 'nothing to report'."""
    out: Dict[str, List[str]] = {}
    now = _time.time()
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        for topic in topics:
            cached = _news_cache.get(topic)
            if cached and now - cached[0] < NEWS_TTL_SECONDS:
                out[topic] = cached[1]
                continue
            try:
                resp = await client.get(_rss_url(topic))
                resp.raise_for_status()
                titles = _parse_rss_titles(resp.text, NEWS_PER_TOPIC)
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("briefing_news_fetch_failed", topic=topic, error=str(exc))
                titles = []
            _news_cache[topic] = (now, titles)
            out[topic] = titles
    return out


# --- data gathering --------------------------------------------------------

def gather_briefing_data(db, user: models.BatAccount, kind: str) -> dict:
    """Collect the facts for a briefing. Pure DB reads, timezone-aware."""
    tz = user_tz(user)
    today = local_today(user)
    d_start, d_end = day_bounds_utc(today, tz)
    y_start, _ = day_bounds_utc(today - timedelta(days=1), tz)

    # Due dates are calendar dates stored as UTC midnight — match on UTC date.
    due_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    due_end = due_start + timedelta(days=1)

    due = (
        db.query(models.BatMission)
        .filter(models.BatMission.owner_id == user.id,
                models.BatMission.due_date >= _naive(due_start),
                models.BatMission.due_date < _naive(due_end))
        .all()
    )
    overdue = (
        db.query(models.BatMission)
        .filter(models.BatMission.owner_id == user.id,
                models.BatMission.status == "pending",
                models.BatMission.due_date.isnot(None),
                models.BatMission.due_date < _naive(due_start))
        .order_by(models.BatMission.due_date.asc())
        .all()
    )

    habits = db.query(models.BatHabit).filter(models.BatHabit.owner_id == user.id).all()
    habits_done, habits_left = [], []
    for h in habits:
        done = bool(h.last_completed and local_date(h.last_completed, tz) == today)
        (habits_done if done else habits_left).append(h)

    # events from now through the next 48h
    horizon = _naive(d_start + timedelta(hours=48))
    events = (
        db.query(models.CalendarEvent)
        .filter(models.CalendarEvent.owner_id == user.id,
                models.CalendarEvent.start_time >= _naive(d_start),
                models.CalendarEvent.start_time < horizon)
        .order_by(models.CalendarEvent.start_time.asc())
        .all()
    )
    countdowns = (
        db.query(models.BatCountdown)
        .filter(models.BatCountdown.owner_id == user.id,
                models.BatCountdown.target_date >= _naive(d_start))
        .order_by(models.BatCountdown.target_date.asc())
        .limit(3)
        .all()
    )

    # focus minutes: yesterday (morning brief) or today so far (night brief)
    f_start = _naive(y_start) if kind == "morning" else _naive(d_start)
    f_end = _naive(d_start) if kind == "morning" else _naive(d_end)
    focus_minutes = (
        db.query(models.BatFocus)
        .filter(models.BatFocus.owner_id == user.id,
                models.BatFocus.start_time >= f_start,
                models.BatFocus.start_time < f_end)
        .with_entities(models.BatFocus.duration_minutes)
        .all()
    )
    focus_total = sum((m[0] or 0) for m in focus_minutes)

    return {
        "today": today,
        "tz": tz,
        "due": due,
        "due_done": [m for m in due if m.status == "completed"],
        "due_pending": [m for m in due if m.status != "completed"],
        "overdue": overdue,
        "habits": habits,
        "habits_done": habits_done,
        "habits_left": habits_left,
        "events": events,
        "countdowns": countdowns,
        "focus_total": focus_total,
    }


# --- templating (Alfred's voice, always available) -------------------------

def _fmt_event(ev, tz, today) -> str:
    d = local_date(ev.start_time, tz)
    when = "today" if d == today else d.strftime("%a %-d")
    t = ev.start_time.astimezone(tz).strftime("%H:%M") if ev.start_time else ""
    return f"{ev.title} · {when} {t}".strip()


def render_template(user: models.BatAccount, kind: str, data: dict,
                    news: Optional[Dict[str, List[str]]] = None) -> str:
    """A complete briefing in Alfred's voice, built only from `data`/`news`."""
    tz, today = data["tz"], data["today"]
    addr = _address(user)
    lines: List[str] = []

    if kind == "morning":
        lines.append(f"Good morning, {addr}. {today.strftime('%A, %-d %B')}.")
    else:
        lines.append(f"Good evening, {addr}. The day in review.")

    due, done, pending, overdue = data["due"], data["due_done"], data["due_pending"], data["overdue"]
    if kind == "morning":
        if due or overdue:
            bits = []
            if pending:
                bits.append(f"{len(pending)} due today")
            if overdue:
                bits.append(f"{len(overdue)} overdue")
            lines.append("")
            lines.append("Missions: " + (", ".join(bits) if bits else "all today's are settled") + ".")
            for m in pending[:5]:
                lines.append(f"  • {m.title}")
            for m in overdue[:3]:
                lines.append(f"  • {m.title} (overdue)")
        else:
            lines.append("")
            lines.append("Missions: nothing due today, and nothing overdue.")
    else:
        lines.append("")
        lines.append(f"Missions: {len(done)} completed today"
                     + (f", {len(pending)} still open" if pending else "") + ".")
        for m in pending[:5]:
            lines.append(f"  • still open: {m.title}")

    habits_left, habits_done, habits = data["habits_left"], data["habits_done"], data["habits"]
    if habits:
        if kind == "morning":
            if habits_left:
                lines.append("")
                lines.append(f"Habits to keep today ({len(habits_left)}):")
                for h in habits_left[:6]:
                    streak = f" — {h.streak}-day streak" if h.streak else ""
                    lines.append(f"  • {h.name}{streak}")
            else:
                lines.append("")
                lines.append("Habits: all kept already. Quietly impressive.")
        else:
            if habits_left:
                lines.append("")
                lines.append(f"Habits missed today ({len(habits_left)}): "
                             + ", ".join(h.name for h in habits_left[:6]) + ".")
            else:
                lines.append("")
                lines.append("Habits: every one kept today.")

    events, countdowns = data["events"], data["countdowns"]
    if kind == "morning" and events:
        lines.append("")
        lines.append("On the horizon (48h):")
        for ev in events[:5]:
            lines.append(f"  • {_fmt_event(ev, tz, today)}")
    if countdowns:
        from services.countdown_service import days_remaining_for
        near = [c for c in countdowns if days_remaining_for(c.target_date) <= 14]
        if near:
            lines.append("")
            lines.append("Countdowns: " + "; ".join(
                f"{c.title} in {days_remaining_for(c.target_date)}d" for c in near[:3]) + ".")

    ft = data["focus_total"]
    lines.append("")
    if kind == "morning":
        lines.append(f"Focus yesterday: {ft} min." if ft else "Focus yesterday: none logged.")
    else:
        lines.append(f"Focus today: {ft} min." if ft else "Focus today: none logged.")

    if news:
        reported = {t: hs for t, hs in news.items() if hs}
        if reported:
            lines.append("")
            lines.append("Worth noting:")
            for topic, headlines in reported.items():
                lines.append(f"  {topic}:")
                for h in headlines:
                    lines.append(f"    • {h}")

    return "\n".join(lines).strip()


# --- optional provider polish ----------------------------------------------

_POLISH_SYSTEM = (
    "You are Alfred Pennyworth delivering a short spoken briefing to {addr} over "
    "Telegram — dry, composed, formal British, warm but never wordy. Rewrite the "
    "briefing below in your own voice. Use ONLY the facts given; invent nothing, add "
    "no news or numbers not present. Keep it tight — a quiet word, not a speech. "
    "Plain text only, short bullet lines are fine."
)


async def polish_with_provider(adapter, user: models.BatAccount, draft: str) -> str:
    """Rephrase the template through the user's provider. Caller handles failure."""
    system = _POLISH_SYSTEM.format(addr=_address(user))
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": draft},
    ]
    resp = await adapter.generate(messages, [], system)
    text = (resp.text or "").strip()
    if len(text) < 20:  # provider returned nothing useful — keep the template
        raise ValueError("provider returned too little")
    return text


async def build_briefing_text(db, user: models.BatAccount, briefing: models.BatBriefing,
                              adapter=None) -> str:
    """Full briefing text: gather data, add news, template, optional polish."""
    data = gather_briefing_data(db, user, briefing.kind)

    # Null out sections the user turned off.
    if not briefing.include_missions:
        data["due"] = data["due_done"] = data["due_pending"] = data["overdue"] = []
    if not briefing.include_habits:
        data["habits"] = data["habits_done"] = data["habits_left"] = []
    if not briefing.include_events:
        data["events"] = data["countdowns"] = []
    if not briefing.include_focus:
        data["focus_total"] = 0

    news = None
    if briefing.include_news:
        topics = parse_news_topics(briefing.news_topics)
        if topics:
            news = await fetch_news(topics)

    draft = render_template(user, briefing.kind, data, news)
    if adapter is not None:
        try:
            return await polish_with_provider(adapter, user, draft)
        except Exception as exc:  # any provider/parse failure → template
            log.info("briefing_polish_fallback", user_id=user.id, error=str(exc))
    return draft


# --- reminders -------------------------------------------------------------

def render_reminder(user: models.BatAccount, reminder: models.BatReminder) -> str:
    """A reminder in Alfred's voice. Templated — short and user-authored."""
    return f"A reminder, {_address(user)}: {reminder.message}"
