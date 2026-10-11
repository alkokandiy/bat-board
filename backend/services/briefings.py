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
# This reads as something Alfred SAYS, not a form he files. The old version
# emitted "Missions:" / "Habits:" headers with bulleted children, which arrived
# looking like a database dump and gave the polish pass a shape it simply
# re-bulleted. Prose in means prose out.

_NUMBER_WORDS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five",
                 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine"}


def _num(n: int) -> str:
    return _NUMBER_WORDS.get(n, str(n))


def _oxford(items: List[str]) -> str:
    """'a', 'a and b', 'a, b and c' — how a person reads a list aloud."""
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" and {items[-1]}"


def _names(rows, limit: int, attr: str = "title") -> str:
    """Up to `limit` names, with any remainder folded in as 'and N more' so the
    sentence never turns into an unbounded wall."""
    shown = [getattr(r, attr) for r in rows[:limit]]
    rest = len(rows) - len(shown)
    if rest > 0:
        shown.append(f"{rest} more")
    return _oxford(shown)


def _fmt_event(ev, tz, today) -> str:
    """'the dentist, tomorrow at 20:00' — a phrase that fits inside a sentence."""
    d = local_date(ev.start_time, tz)
    if d == today:
        when = "today"
    elif d == today + timedelta(days=1):
        when = "tomorrow"
    else:
        when = d.strftime("%A")
    t = ev.start_time.astimezone(tz).strftime("%H:%M") if ev.start_time else ""
    return f"{ev.title}, {when} at {t}" if t else f"{ev.title}, {when}"


def _missions_sentence(kind: str, data: dict) -> str:
    done, pending, overdue = data["due_done"], data["due_pending"], data["overdue"]
    if kind == "morning":
        if pending:
            verb = "is" if len(pending) == 1 else "are"
            noun = "mission" if len(pending) == 1 else "missions"
            text = f"{_num(len(pending))} {noun} {verb} due today — {_names(pending, 4)}."
        elif done:
            text = "Everything due today is already settled."
        elif not overdue:
            return "Nothing is due today, and nothing is overdue."
        else:
            text = "Nothing falls due today."
        if overdue:
            verb = "remains" if len(overdue) == 1 else "remain"
            text += f" {_names(overdue, 3)} {verb} overdue."
        return text

    # night
    noun = "mission" if len(done) == 1 else "missions"
    if done and pending:
        text = (f"{_num(len(done))} {noun} closed today, which leaves "
                f"{_names(pending, 4)} open.")
    elif done:
        text = f"{_num(len(done))} {noun} closed today, and nothing left open."
    elif pending:
        text = f"Nothing closed today. {_names(pending, 4)} still stands."
    else:
        text = "No missions were due today."
    if overdue:
        text += f" {_names(overdue, 3)} is still past its date." if len(overdue) == 1 \
            else f" {_names(overdue, 3)} are still past their dates."
    return text


def _habits_sentence(kind: str, data: dict) -> str:
    left, kept, habits = data["habits_left"], data["habits_done"], data["habits"]
    if not habits:
        return ""
    if kind == "morning":
        if not left:
            return "Every habit is already kept. Quietly impressive."
        text = (f"{_num(len(left))} habit{'' if len(left) == 1 else 's'} still to keep — "
                f"{_names(left, 6, attr='name')}.")
        # A streak worth protecting is the single most motivating fact here, so
        # it earns its own clause rather than a column in a table.
        best = max((h for h in left if (h.streak or 0) >= 3),
                   key=lambda h: h.streak, default=None)
        if best is not None:
            # "Meditate. Meditate is on a 3-day run" reads like a stutter when it
            # is the only one left, so name it only when the list has company.
            subject = "It" if len(left) == 1 else best.name
            text += f" {subject} is on a {best.streak}-day run; worth protecting."
        return text
    if not left:
        return "Every habit kept today — the whole set."
    if kept:
        return (f"{_num(len(kept))} habit{'' if len(kept) == 1 else 's'} kept, "
                f"{_names(left, 6, attr='name')} missed.")
    return f"{_names(left, 6, attr='name')} went unkept today."


def _horizon_sentence(kind: str, data: dict) -> str:
    tz, today = data["tz"], data["today"]
    events, countdowns = data["events"], data["countdowns"]
    parts: List[str] = []
    if kind == "morning" and events:
        phrases = [_fmt_event(ev, tz, today) for ev in events[:4]]
        parts.append(("Ahead of you: " if len(phrases) > 1 else "One thing ahead: ")
                     + _oxford(phrases) + ".")
    if countdowns:
        from services.countdown_service import days_remaining_for
        near = [c for c in countdowns if days_remaining_for(c.target_date) <= 14]
        if near:
            phrases = [f"{c.title} in {days_remaining_for(c.target_date)} days"
                       for c in near[:3]]
            parts.append(_oxford(phrases).capitalize() + ".")
    return " ".join(parts)


def _focus_sentence(kind: str, data: dict) -> str:
    ft = data["focus_total"]
    if kind == "morning":
        if not ft:
            return "Yesterday's focus went unlogged."
        return f"You logged {ft} minutes of focus yesterday."
    if not ft:
        return "No focus was logged today."
    return f"{ft} minutes of focus logged today."


def render_template(user: models.BatAccount, kind: str, data: dict,
                    news: Optional[Dict[str, List[str]]] = None) -> str:
    """A complete briefing in Alfred's voice, built only from `data`/`news`.

    Paragraphs, not sections: each sentence that has something to say gets a
    line, and anything with nothing to say is simply left out rather than
    announced as empty.
    """
    today = data["today"]
    addr = _address(user)

    if kind == "morning":
        opening = f"Good morning, {addr}. {today.strftime('%A, %-d %B')}."
    else:
        opening = f"Good evening, {addr}. The day in review."

    body = [s for s in (
        _missions_sentence(kind, data),
        _habits_sentence(kind, data),
        _horizon_sentence(kind, data),
        _focus_sentence(kind, data),
    ) if s]

    text = opening + "\n\n" + "\n\n".join(body) if body else opening
    if kind == "night":
        text += "\n\nThe board is secured."
    news_block = render_news(news)
    if news_block:
        text += "\n\n" + news_block
    return text.strip()


# --- news rendering --------------------------------------------------------

def render_news(news: Optional[Dict[str, List[str]]]) -> str:
    """Headlines, verbatim, with their publisher intact.

    Kept deliberately separate from the prose above because this block is NOT
    passed through the polish pass: a model asked to 'rewrite' a headline
    compresses it into something that was never published, which is how a
    briefing ends up asserting things no outlet actually said.
    """
    if not news:
        return ""
    reported = {t: hs for t, hs in news.items() if hs}
    if not reported:
        return ""
    lines = ["Headlines, as published:"]
    for topic, headlines in reported.items():
        lines.append("")
        # Capitalise the user's own topic word, but leave acronyms like "AI"
        # and "NATO" exactly as they typed them.
        lines.append(topic if topic.isupper() else topic[:1].upper() + topic[1:])
        for h in headlines:
            # Google News titles arrive as "Headline - Publisher"; an em dash
            # reads better and survives being shown as plain text.
            head, sep, publisher = h.rpartition(" - ")
            lines.append(f"- {head} — {publisher}" if sep else f"- {h}")
    return "\n".join(lines)


# --- optional provider polish ----------------------------------------------

_POLISH_SYSTEM = (
    "You are Alfred Pennyworth — butler and chief of staff — giving {addr} a short "
    "spoken briefing over Telegram. Dry, composed, formal British, warm but never "
    "wordy.\n\n"
    "Rewrite the briefing below as something you would SAY, standing by the desk. "
    "Use ONLY the facts given: invent nothing, add no news, no numbers and no names "
    "that are not already there, and drop nothing that is.\n\n"
    "Rules you must not break:\n"
    "- Plain text only. No Markdown whatsoever — no asterisks, no underscores, no "
    "backticks, no hash headings. Every character you type is shown literally, so a "
    "stray asterisk is simply rubbish on their screen.\n"
    "- No section headers and no bullet points. Not 'Missions:', not 'Habits:', not a "
    "line beginning with a dash or a dot. Write sentences in short paragraphs.\n"
    "- Lead with whatever actually matters most — what is late, what is close, what "
    "went well. Let the rest follow.\n"
    "- Join the facts up where they genuinely connect. One observation that shows you "
    "were paying attention is worth more than a tidy inventory.\n"
    "- Keep it under about 120 words, and end with at most one short question or "
    "offer, only if one is actually earned."
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

    # The personal half is polished; the headlines are appended afterwards,
    # untouched. Letting the model rewrite a headline is how "Anthropic
    # published X" becomes an assertion no outlet ever made.
    draft = render_template(user, briefing.kind, data)
    text = draft
    if adapter is not None:
        try:
            text = await polish_with_provider(adapter, user, draft)
        except Exception as exc:  # any provider/parse failure → template
            log.info("briefing_polish_fallback", user_id=user.id, error=str(exc))
    news_block = render_news(news)
    return f"{text}\n\n{news_block}".strip() if news_block else text


# --- reminders -------------------------------------------------------------

def render_reminder(user: models.BatAccount, reminder: models.BatReminder) -> str:
    """A reminder in Alfred's voice. Templated — short and user-authored."""
    return f"A reminder, {_address(user)}: {reminder.message}"
