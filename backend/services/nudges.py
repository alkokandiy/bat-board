"""Alfred's attention: proactive, caring check-ins.

The point of this module is that Alfred is a companion, not a reporter. He
notices things about the state of someone's days and says something when it
genuinely deserves a word — then offers to help.

The design is deliberately general rather than a list of canned lines:

  SIGNAL  — a small function that looks at the board and returns a candidate
            nudge (or None). Adding a new kind of noticing = adding a function.
  KEY     — each candidate carries a unique `key` for the specific occasion
            ("countdown:12:7d", "drift:2026-10-08"). A UNIQUE row in
            bat_nudge_log makes an occasion fire exactly once, ever.
  GUARDS  — quiet hours, a daily cap, a global cooldown, and "don't interrupt
            someone who's mid-conversation" apply before anything is sent.
  VOICE   — a factual template is always produced; the user's own model may
            rephrase it warmly, but may never invent facts.

Everything is grounded in data Alfred actually has. He never speculates about
the user's life beyond what's on the board or in his own memory.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple

import structlog

import models
from services import alfred_principles
from services.timezones import day_bounds_utc, local_date, user_tz

log = structlog.get_logger(__name__)

DEFAULT_QUIET_START = "22:00"
DEFAULT_QUIET_END = "08:00"
DEFAULT_PER_DAY = 3
# Minimum gap between any two proactive messages.
GLOBAL_COOLDOWN = timedelta(minutes=90)
# If they've just been talking to Alfred, don't interrupt with a nudge.
RECENT_CHAT_QUIET = timedelta(minutes=60)


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _address(user: models.BatAccount) -> str:
    return (getattr(user, "alfred_address", None) or "").strip() or user.username


def _fmt_hm(minutes: int) -> str:
    h, m = divmod(max(0, int(minutes)), 60)
    if h and m:
        return f"{h}h {m}m"
    return f"{h}h" if h else f"{m}m"


@dataclass
class Nudge:
    """One thing worth saying, and the raw material for saying it.

    `draft` is NOT the message. It is the fallback for users with no model
    configured, and an example of the right register. When a model is
    available, Alfred is handed `facts` and `warrant` and works out what to
    say for himself — which is why two people in the same situation, or the
    same person twice, do not get the same sentence.
    """

    key: str
    kind: str
    priority: int
    draft: str          # fallback wording; never sent verbatim when a model exists
    facts: str          # what is true on the board right now
    warrant: str = ""   # why it matters and what genuinely helps, from the evidence


@dataclass
class Ctx:
    """Everything the signals look at, gathered once."""
    user: models.BatAccount
    local_now: datetime
    today: object
    address: str
    open_missions: list
    overdue: list
    countdowns: list
    events_soon: list
    habits_pending: list
    focus_today_minutes: int
    last_focus_at: Optional[datetime]
    at_work: bool = False
    work_activity_today: bool = False
    # --- the noticing surface -------------------------------------------
    # The fields above are what Alfred CHASES. These are what he can OFFER:
    # the difference between an overseer and a companion.
    notes: list = field(default_factory=list)
    themes: List[Tuple[str, int]] = field(default_factory=list)
    events_this_week: int = 0
    has_used_calendar: bool = False
    briefing_morning: object = None
    briefing_night: object = None
    days_since_capture: Optional[int] = None
    focus_peak_hour: Optional[int] = None
    focus_session_count: int = 0
    account_age_days: int = 0
    habits_all: list = field(default_factory=list)
    late_night_days: int = 0
    late_night_last: Optional[object] = None


# --- gathering --------------------------------------------------------------

def build_context(db, user: models.BatAccount, local_now: datetime) -> Ctx:
    tz = user_tz(user)
    today = local_now.date()
    d_start, d_end = day_bounds_utc(today, tz)

    open_missions = (
        db.query(models.BatMission)
        .filter(models.BatMission.owner_id == user.id,
                models.BatMission.status == "pending",
                models.BatMission.is_dismissed.is_(False))
        .all()
    )
    due_cut = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    overdue = [m for m in open_missions
               if m.due_date is not None and _aware(m.due_date) < due_cut]

    countdowns = (
        db.query(models.BatCountdown)
        .filter(models.BatCountdown.owner_id == user.id,
                models.BatCountdown.target_date >= _naive(d_start))
        .all()
    )
    events_soon = (
        db.query(models.CalendarEvent)
        .filter(models.CalendarEvent.owner_id == user.id,
                models.CalendarEvent.start_time >= _naive(local_now.astimezone(timezone.utc)),
                models.CalendarEvent.start_time < _naive(local_now.astimezone(timezone.utc) + timedelta(hours=24)))
        .order_by(models.CalendarEvent.start_time.asc())
        .all()
    )

    habits = db.query(models.BatHabit).filter(models.BatHabit.owner_id == user.id).all()
    habits_pending = [
        h for h in habits
        if not (h.last_completed and local_date(h.last_completed, tz) == today)
    ]

    focus_rows = (
        db.query(models.BatFocus)
        .filter(models.BatFocus.owner_id == user.id,
                models.BatFocus.start_time >= _naive(d_start),
                models.BatFocus.start_time < _naive(d_end))
        .all()
    )
    focus_today = sum((f.duration_minutes or 0) for f in focus_rows)

    last_done = (
        db.query(models.BatFocus)
        .filter(models.BatFocus.owner_id == user.id,
                models.BatFocus.end_time.isnot(None))
        .order_by(models.BatFocus.end_time.desc())
        .first()
    )

    from services import work_service
    # With the corporate track off, work facts are simply not consulted: the
    # drift nudge then speaks in purely personal terms, which is exactly what it
    # did before work existed. It is never silenced — only worded differently.
    work_on = work_service.is_enabled(db, user)
    at_work = work_on and work_service.is_working_now(
        work_service.get_profile(db, user), local_now)
    # Did the job move at all today? Completing work tasks or writing work notes
    # is working, even when the timer wasn't running.
    work_touched = work_on and (
        db.query(models.BatWorkTask)
        .filter(models.BatWorkTask.owner_id == user.id,
                models.BatWorkTask.updated_at >= _naive(d_start),
                models.BatWorkTask.updated_at < _naive(d_end))
        .first() is not None
        or db.query(models.BatWorkNote)
        .filter(models.BatWorkNote.owner_id == user.id,
                models.BatWorkNote.created_at >= _naive(d_start),
                models.BatWorkNote.created_at < _naive(d_end))
        .first() is not None
    )

    # --- the noticing surface -----------------------------------------
    from services.notes_service import ALFRED_MEMORY_TAG

    all_notes = (
        db.query(models.BatNote)
        .filter(models.BatNote.owner_id == user.id)
        .order_by(models.BatNote.updated_at.desc())
        .limit(100)
        .all()
    )
    # Alfred's own memory notes are HIS record, not their writing — noticing a
    # "theme" in what he wrote about them would be noticing himself.
    notes = [n for n in all_notes
             if ALFRED_MEMORY_TAG not in (n.tags or "").lower()]

    week_end = _naive(local_now.astimezone(timezone.utc) + timedelta(days=7))
    events_this_week = (
        db.query(models.CalendarEvent)
        .filter(models.CalendarEvent.owner_id == user.id,
                models.CalendarEvent.start_time >= _naive(d_start),
                models.CalendarEvent.start_time < week_end)
        .count()
    )
    # "Empty week" only means something for someone who uses the calendar at
    # all; for everyone else an empty calendar is simply their normal.
    has_used_calendar = (
        db.query(models.CalendarEvent.id)
        .filter(models.CalendarEvent.owner_id == user.id)
        .first() is not None
    )

    briefings_by_kind = {
        b.kind: b for b in db.query(models.BatBriefing)
        .filter(models.BatBriefing.owner_id == user.id).all()
    }

    # How long since anything new went on the board at all.
    newest = []
    for model, col in ((models.BatMission, models.BatMission.created_at),
                       (models.BatNote, models.BatNote.created_at)):
        row = (db.query(col).filter(model.owner_id == user.id)
               .order_by(col.desc()).first())
        if row and row[0]:
            newest.append(_aware(row[0]))
    days_since_capture = None
    if newest:
        days_since_capture = (local_now.astimezone(timezone.utc) - max(newest)).days

    # The hour they actually focus best, from their own history.
    focus_hours = (
        db.query(models.BatFocus.start_time)
        .filter(models.BatFocus.owner_id == user.id,
                models.BatFocus.duration_minutes.isnot(None),
                models.BatFocus.duration_minutes > 0)
        .order_by(models.BatFocus.start_time.desc())
        .limit(80)
        .all()
    )
    hour_counts = Counter(_aware(r[0]).astimezone(tz).hour for r in focus_hours if r[0])
    peak_hour = hour_counts.most_common(1)[0][0] if hour_counts else None

    # Work logged in the small hours. Detected from their own record, raised
    # the NEXT day at a civil time — telling someone at 02:00 that it is late
    # is both useless and exactly the interruption the quiet window exists to
    # prevent.
    week_ago = _naive(local_now.astimezone(timezone.utc) - timedelta(days=7))
    late_dates = set()
    late_last = None
    for (ts,) in (db.query(models.BatFocus.start_time)
                  .filter(models.BatFocus.owner_id == user.id,
                          models.BatFocus.start_time >= week_ago).all()):
        if ts is None:
            continue
        local_ts = _aware(ts).astimezone(tz)
        if local_ts.hour in (0, 1, 2, 3, 4):
            late_dates.add(local_ts.date())
            if late_last is None or local_ts > late_last:
                late_last = local_ts

    created = _aware(getattr(user, "created_at", None))
    account_age_days = ((local_now.astimezone(timezone.utc) - created).days
                        if created else 0)

    return Ctx(
        user=user, local_now=local_now, today=today, address=_address(user),
        open_missions=open_missions, overdue=overdue, countdowns=countdowns,
        events_soon=events_soon, habits_pending=habits_pending,
        focus_today_minutes=focus_today,
        last_focus_at=_aware(last_done.end_time) if last_done else None,
        at_work=at_work,
        work_activity_today=work_touched,
        notes=notes,
        themes=_theme_labels(open_missions, notes),
        events_this_week=events_this_week,
        has_used_calendar=has_used_calendar,
        briefing_morning=briefings_by_kind.get("morning"),
        briefing_night=briefings_by_kind.get("night"),
        days_since_capture=days_since_capture,
        focus_peak_hour=peak_hour,
        focus_session_count=len(focus_hours),
        account_age_days=account_age_days,
        habits_all=habits,
        late_night_days=len(late_dates),
        late_night_last=late_last,
    )


# --- what the board is quietly about ---------------------------------------

# Words that say nothing about what someone cares about. Themes are drawn from
# TAGS and CATEGORIES first — those are labels the user chose deliberately —
# and only then from title words, which are noisier.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "at", "with",
    "my", "me", "i", "it", "is", "be", "do", "go", "get", "new", "more", "all",
    "this", "that", "from", "by", "up", "out", "about", "into", "over", "make",
    "read", "write", "finish", "start", "buy", "call", "check", "review",
    "update", "add", "plan", "work", "task", "todo", "day", "week", "month",
}
MIN_THEME_COUNT = 3


def _theme_labels(missions, notes) -> List[Tuple[str, int]]:
    """Recurring subjects on the board, strongest first.

    Deliberately conservative: a theme must appear at least MIN_THEME_COUNT
    times before Alfred says anything about it, because telling someone they
    are "interested in X" on the strength of one note is a guess, and he does
    not guess about their life.
    """
    counter: Counter = Counter()
    for row in list(missions) + list(notes):
        for raw in (getattr(row, "tags", "") or "").split(","):
            tag = raw.strip().lower()
            if tag and tag != "alfred-memory" and len(tag) > 2:
                counter[tag] += 1
        cat = (getattr(row, "category", "") or "").strip().lower()
        if cat and len(cat) > 2:
            counter[cat] += 1
    if not counter:
        # No labels at all — fall back to title words, which is weaker evidence,
        # so the threshold still has to be met.
        for row in list(missions) + list(notes):
            text = (getattr(row, "title", "") or getattr(row, "name", "") or "")
            for word in text.lower().replace("/", " ").split():
                word = "".join(ch for ch in word if ch.isalpha())
                if len(word) > 3 and word not in _STOPWORDS:
                    counter[word] += 1
    return [(label, n) for label, n in counter.most_common(6) if n >= MIN_THEME_COUNT]


# --- signals ----------------------------------------------------------------
# Each returns a candidate Nudge or None. Add a function to teach Alfred a new
# thing to notice; nothing else needs to change.

COUNTDOWN_MARKS = (30, 14, 7, 3, 1)


def sig_countdown_horizon(ctx: Ctx) -> Optional[Nudge]:
    """A date worth preparing for is approaching. Works for anything the user
    put a countdown on — an exam, a birthday, a deadline, a trip."""
    from services.countdown_service import days_remaining_for

    best = None
    for c in ctx.countdowns:
        days = days_remaining_for(c.target_date)
        if days in COUNTDOWN_MARKS:
            if best is None or days < best[0]:
                best = (days, c)
    if best is None:
        return None
    days, c = best
    when = "tomorrow" if days == 1 else f"in {days} days"
    return Nudge(
        key=f"countdown:{c.id}:{days}d",
        kind="countdown",
        priority=60 + (30 - min(days, 30)),
        draft=(f"{ctx.address} — {c.title} is {when}. "
               f"Is there a plan for it, or shall we put one together?"),
        facts=f"Countdown '{c.title}' is {when} ({days} days).",
    
            warrant=("A fixed date is approaching. The useful move is not urgency but a plan: an unfinished thing keeps intruding on unrelated work, and giving it a specific WHEN discharges that even before it is done. Offer to pin a time, or to break off the first piece. Do not imply they have left it late."),
        )


def sig_event_soon(ctx: Ctx) -> Optional[Nudge]:
    """Something is on the calendar within the day."""
    if not ctx.events_soon:
        return None
    ev = ctx.events_soon[0]
    tz = user_tz(ctx.user)
    when = _aware(ev.start_time).astimezone(tz)
    label = "today" if when.date() == ctx.today else "tomorrow"
    return Nudge(
        key=f"event:{ev.id}",
        kind="event",
        priority=70,
        draft=(f"{ctx.address}, you have {ev.title} {label} at {when.strftime('%H:%M')}. "
               f"Anything you'd like ready beforehand?"),
        facts=f"Calendar event '{ev.title}' {label} at {when.strftime('%H:%M')}.",
    
            warrant=("Something is fixed in the diary soon. This is a seam in their day, which is the cheap moment to reach them. Offer preparation, not pressure — and if nothing needs preparing, a brief acknowledgement is enough."),
        )


def sig_drift(ctx: Ctx) -> Optional[Nudge]:
    """Nothing timed today. The remark is kept whatever the context — it is a
    reminder worth having — but its wording follows where they actually are.
    Telling someone at their desk that they are "drifting" is the failure; going
    silent on them is the opposite failure. So: ask, but ask correctly.

    Focus on a WORK task counts as focus. Once the timer is running on the job,
    this stays quiet of its own accord.
    """
    if ctx.focus_today_minutes > 0:
        return None
    if ctx.local_now.hour < 15:          # give the day a chance first
        return None

    key = f"drift:{ctx.today.isoformat()}"

    # At their desk by their own schedule — offer to time it, don't accuse.
    if ctx.at_work:
        return Nudge(
            key=key, kind="drift", priority=45,
            draft=(f"You're at work by your own schedule, {ctx.address}, but nothing's "
                   f"timed yet today. Shall I start a session on one of your work tasks?"),
            facts="No focus time logged today; currently within their working hours.",
        
            warrant=("They are inside their own stated working hours with no timer running. This is an offer, never an accusation — an untimed day is not a wasted one, and the record is theirs, not a report card. Offer to start the clock on something specific, and let declining be easy."),
        )

    # The job moved today, it just wasn't timed.
    if ctx.work_activity_today:
        return Nudge(
            key=key, kind="drift", priority=45,
            draft=(f"You've moved work along today, {ctx.address}, but timed none of it. "
                   f"Worth running the clock on it — shall I start one?"),
            facts="Work tasks or notes changed today, but no focus time was logged.",
        
            warrant=("The job moved but nothing was timed. The only thing missing is the record, so treat it as such: light, optional, and genuinely droppable. Never suggest the work did not count because it was not measured."),
        )

    if not ctx.open_missions:
        return None
    gap = None
    if ctx.last_focus_at is not None:
        gap = ctx.local_now.astimezone(timezone.utc) - ctx.last_focus_at
        if gap < timedelta(hours=18):
            return None
    since = f" It's been {int(gap.total_seconds() // 3600)} hours." if gap else ""
    return Nudge(
        key=key, kind="drift", priority=45,
        draft=(f"No focus logged today, {ctx.address}.{since} "
               f"Busy elsewhere, or drifting? Say the word and I'll start a session."),
        facts=f"No focus logged today; {len(ctx.open_missions)} missions open.",
    
            warrant=("No timed work today. Ask rather than conclude — you see only what they log, and a quiet board can mean a full day elsewhere. Offer to start something small. Never characterise them as drifting, slipping, or inconsistent."),
        )


def sig_overdue_pileup(ctx: Ctx) -> Optional[Nudge]:
    """Enough has slipped that it's worth offering to clear the decks."""
    if len(ctx.overdue) < 3:
        return None
    names = ", ".join(m.title for m in ctx.overdue[:3])
    return Nudge(
        key=f"overdue:{ctx.today.isoformat()}",
        kind="overdue",
        priority=50,
        draft=(f"{len(ctx.overdue)} missions have slipped past their date, {ctx.address} — "
               f"{names}. Shall we re-date them, or let some go?"),
        facts=f"{len(ctx.overdue)} overdue missions: {names}.",
    
            warrant=("Several things are past their date. The burden here comes from CONFLICT between commitments, not from the number of them, so do not count at them or call the list too long. The best-evidenced offer is a specific WHEN for each one — that alone lifts the nagging weight without anything being finished. Pausing something with a date to look again, or letting it go, are both respectable outcomes worth naming."),
        )


def sig_habit_at_risk(ctx: Ctx) -> Optional[Nudge]:
    """A streak worth protecting is still open late in the day."""
    if ctx.local_now.hour < 19:
        return None
    at_risk = [h for h in ctx.habits_pending if (h.streak or 0) >= 3]
    if not at_risk:
        return None
    h = max(at_risk, key=lambda x: x.streak or 0)
    return Nudge(
        key=f"habit:{h.id}:{ctx.today.isoformat()}",
        kind="habit",
        priority=55,
        draft=(f"Your {h.name} streak stands at {h.streak} days, {ctx.address}, and today "
               f"isn't marked yet. Tell me when it's done and I'll log it."),
        facts=f"Habit '{h.name}' streak {h.streak} days, not yet done today.",
    
            warrant=("A habit with a real run behind it is unmarked today. Do NOT invoke the chain or imply a streak is about to be destroyed — the harm comes from believing the run is ruined, not from one missed day, and a broken count reduces people's willingness to continue even when the miss was out of their hands. Mention the habit, make the only ask the next single repetition, and offer a smaller version if today is already gone."),
        )


def sig_stalled_mission(ctx: Ctx) -> Optional[Nudge]:
    """Real time went into something, then it went quiet."""
    invested = [m for m in ctx.open_missions if (m.focus_minutes or 0) >= 30]
    if not invested:
        return None
    m = max(invested, key=lambda x: x.focus_minutes or 0)
    week = ctx.local_now.isocalendar()
    return Nudge(
        key=f"stalled:{m.id}:{week[0]}-{week[1]}",
        kind="stalled",
        priority=40,
        draft=(f"You've put {_fmt_hm(m.focus_minutes)} into {m.title}, {ctx.address}. "
               f"Still worth your time, or shall we set it down?"),
        facts=f"Mission '{m.title}' has {_fmt_hm(m.focus_minutes)} invested and is still open.",
    
            warrant=("Real hours went into this and then it went quiet. Ask whether it still matters, genuinely — pausing it with a date to revisit, or setting it down for good, are both legitimate answers and should be offered as such. Do not treat the invested time as a reason they owe it anything."),
        )


def sig_good_day(ctx: Ctx) -> Optional[Nudge]:
    """Credit where it's due — a companion notices the good days too."""
    if ctx.focus_today_minutes < 90:
        return None
    return Nudge(
        key=f"welldone:{ctx.today.isoformat()}",
        kind="praise",
        priority=35,
        draft=(f"{_fmt_hm(ctx.focus_today_minutes)} of focus today, {ctx.address}. "
               f"Quietly impressive. Shall I leave you to it?"),
        facts=f"{_fmt_hm(ctx.focus_today_minutes)} of focus logged today.",
    
            warrant=("A genuinely good day. Name the specific thing they did, not what kind of person it makes them — praising the trait rather than the work measurably reduces persistence after the next setback. Never mention points or levels. Keep it brief; then get out of the way."),
        )


def sig_clear_board(ctx: Ctx) -> Optional[Nudge]:
    """Nothing to do at all is either deliberate rest or a drift — worth asking."""
    if ctx.open_missions or ctx.local_now.hour < 11:
        return None
    return Nudge(
        key=f"clearboard:{ctx.today.isoformat()}",
        kind="clear",
        priority=30,
        draft=(f"Your board is clear, {ctx.address}. Deliberate rest, "
               f"or shall we set the next thing?"),
        facts="No open missions on the board.",
    
            warrant=("Nothing open at all. Deliberate rest is a real and good answer, and should be offered first rather than treated as a gap to fill. Only then offer to set the next thing."),
        )


# --- signals: what he can OFFER --------------------------------------------
# Everything above notices what is going wrong. These notice what could go
# better, which is the difference between being chased and being helped.
# Each one must be grounded in data already on the board, must offer something
# Alfred can genuinely DO with a tool he has, and must fire rarely.

def sig_news_topic_offer(ctx: Ctx) -> Optional[Nudge]:
    """The board keeps circling a subject. Offer to follow it in the news.

    Only for a theme they labelled themselves, repeatedly, and only if they
    already receive a briefing — otherwise this is an advertisement, not an
    observation.
    """
    # An offer to add headlines to a briefing they have switched OFF would be
    # an offer to put news somewhere they will never read it.
    live = [b for b in (ctx.briefing_morning, ctx.briefing_night)
            if b is not None and b.enabled]
    if not live or not ctx.themes:
        return None
    briefing = live[0]
    existing = {t.strip().lower()
                for t in (getattr(briefing, "news_topics", "") or "").split(",")}
    for label, count in ctx.themes:
        if label in existing:
            continue
        return Nudge(
            key=f"newstopic:{label}",
            kind="offer_news",
            priority=34,
            draft=(f"{count} things on your board come back to {label}, {ctx.address}. "
                   f"Shall I add {label} headlines to your {briefing.kind} briefing?"),
            facts=(f"{count} missions/notes are tagged or categorised '{label}'. "
                   f"Their {briefing.kind} briefing does not currently include "
                   f"'{label}' in its news topics."),
        
            warrant=("A subject keeps recurring in what they have labelled themselves. This is an observation about their board, not a claim about their soul — say what you saw, offer the headlines, and drop it cleanly if they decline."),
        )
    return None


def sig_night_briefing_offer(ctx: Ctx) -> Optional[Nudge]:
    """They take the morning briefing but nothing closes the day."""
    if ctx.briefing_morning is None or not ctx.briefing_morning.enabled:
        return None
    if ctx.briefing_night is not None and ctx.briefing_night.enabled:
        return None
    if ctx.account_age_days < 7:
        return None
    return Nudge(
        key="offer:nightbriefing",
        kind="offer_briefing",
        priority=32,
        draft=(f"You hear from me each morning, {ctx.address}, but nothing closes "
               f"the day. Shall I add an evening word — what got done, what you "
               f"focused on, and a line back from you if you feel like it?"),
        facts=("A morning briefing is enabled; no night briefing is enabled. "
               "A night briefing covers completed missions, focus and reflection."),
    
            warrant=("They hear from you in the morning but nothing closes the day. Reviewing what actually happened is one of the few genuinely well-supported habits in this whole field. Offer it as a short evening word, with room for a line back from them if they want it — never as homework."),
        )


def sig_first_briefing_offer(ctx: Ctx) -> Optional[Nudge]:
    """Settled in, but never set up a standing briefing at all."""
    if ctx.briefing_morning is not None or ctx.briefing_night is not None:
        return None
    if ctx.account_age_days < 5:
        return None
    if not (ctx.open_missions or ctx.notes):
        return None
    return Nudge(
        key="offer:firstbriefing",
        kind="offer_briefing",
        priority=33,
        draft=(f"I could bring you the board each morning before you start, "
               f"{ctx.address} — what's due, what's at risk, and headlines on "
               f"anything you follow. Shall I set that up?"),
        facts="No briefing of any kind is configured for this user.",
    
            warrant=("They have a board but no standing briefing. Offer it plainly as a service you could perform, say roughly what it would contain, and make refusing costless."),
        )


def sig_empty_week(ctx: Ctx) -> Optional[Nudge]:
    """A calendar user with a completely clear week ahead."""
    if not ctx.has_used_calendar or ctx.events_this_week > 0:
        return None
    week = ctx.local_now.isocalendar()
    return Nudge(
        key=f"emptyweek:{week[0]}-{week[1]}",
        kind="offer_rest",
        priority=28,
        draft=(f"There's nothing in your calendar for the next seven days, "
               f"{ctx.address}. Deliberate quiet, or shall we put something in "
               f"it — somewhere to go, or an evening kept for nothing at all?"),
        facts="No calendar events in the next 7 days; this user does use the calendar.",
    
            warrant=("A clear week for someone who does use their calendar. Deliberate quiet is the first and best interpretation — rest genuinely restores, and it works better little and often than saved up. Offer either: something to look forward to, or an evening deliberately kept empty."),
        )


def sig_note_followup(ctx: Ctx) -> Optional[Nudge]:
    """Something they wrote down and never returned to.

    Titles only. Their notes are theirs to keep; he may notice one exists
    without reading it back at them.
    """
    cutoff = ctx.local_now.astimezone(timezone.utc) - timedelta(days=21)
    stale = [n for n in ctx.notes
             if n.title and not n.is_pinned and _aware(n.updated_at) < cutoff]
    if not stale:
        return None
    # The least-stale of the stale ones: three weeks cold is still probably
    # live, whereas the note from two years ago is usually just history.
    n = stale[0]
    weeks = max(3, (ctx.local_now.astimezone(timezone.utc)
                    - _aware(n.updated_at)).days // 7)
    return Nudge(
        key=f"notefollow:{n.id}",
        kind="offer_note",
        priority=26,
        draft=(f"Your note {n.title} has sat untouched about {weeks} weeks, "
               f"{ctx.address}. Shall I set a reminder to come back to it, or "
               f"has it done its job?"),
        facts=f"Note titled '{n.title}' last updated roughly {weeks} weeks ago.",
    
            warrant=("Something they wrote down and have not returned to. Titles only — you have not read it back at them and should not pretend to know what it says. Offer a reminder, or offer to let it be; both are fine."),
        )


def sig_capture_prompt(ctx: Ctx) -> Optional[Nudge]:
    """Nothing new has been written down in a while."""
    if ctx.days_since_capture is None or ctx.days_since_capture < 6:
        return None
    week = ctx.local_now.isocalendar()
    return Nudge(
        key=f"capture:{week[0]}-{week[1]}",
        kind="offer_capture",
        priority=24,
        draft=(f"Nothing new has gone on the board in {ctx.days_since_capture} days, "
               f"{ctx.address}. Anything on your mind worth writing down before "
               f"it goes? I'll take it as a note or a mission, whichever it is."),
        facts=f"No mission or note has been created for {ctx.days_since_capture} days.",
    
            warrant=("Nothing new has been written down for a while. This is an invitation, not an audit — a quiet board often means a busy life. Offer to take whatever is on their mind, in whatever shape it arrives."),
        )


def sig_focus_rhythm(ctx: Ctx) -> Optional[Nudge]:
    """Their own history says when they work best. Offer to protect it."""
    if ctx.focus_session_count < 12 or ctx.focus_peak_hour is None:
        return None
    hour = ctx.focus_peak_hour
    if ctx.local_now.hour >= hour:        # offer it ahead of the hour, not after
        return None
    quarter = f"{ctx.local_now.year}Q{(ctx.local_now.month - 1) // 3 + 1}"
    return Nudge(
        key=f"rhythm:{hour}:{quarter}",
        kind="offer_rhythm",
        priority=27,
        draft=(f"Looking back at your sessions, {ctx.address}, you do your best "
               f"work around {hour:02d}:00. Shall I keep that hour for you today "
               f"and start the clock when it comes?"),
        facts=(f"Across {ctx.focus_session_count} recorded focus sessions, the most "
               f"common start hour is {hour:02d}:00 local time."),
    
            warrant=("Their own record shows when they actually do their best work. That personal history is worth far more than any general rule about session lengths, and there is no correct number of minutes to recommend. Offer to hold that hour and start the clock when it comes."),
        )


def sig_long_open_mission(ctx: Ctx) -> Optional[Nudge]:
    """On the board for months with no time ever put into it.

    Distinct from `stalled`, which is about something they DID invest in. This
    is the honest question about something that may simply not be real.
    """
    cutoff = ctx.local_now.astimezone(timezone.utc) - timedelta(days=60)
    forgotten = [m for m in ctx.open_missions
                 if not (m.focus_minutes or 0)
                 and m.created_at and _aware(m.created_at) < cutoff]
    if not forgotten:
        return None
    m = min(forgotten, key=lambda x: _aware(x.created_at))
    since = _aware(m.created_at).strftime("%B")
    return Nudge(
        key=f"longopen:{m.id}",
        kind="offer_prune",
        priority=25,
        draft=(f"{m.title} has been on your board since {since} without an hour "
               f"against it, {ctx.address}. Still something you mean to do, or "
               f"shall we take it off?"),
        facts=(f"Mission '{m.title}' created in {since}, still open, zero focus "
               f"minutes recorded."),
    
            warrant=("On the board for months with no time ever against it. Ask the honest question without a trace of reproach: things stop being true, and taking one off the board is a decision, not a defeat. Offer removal, a pause with a date, or shrinking it to something that would actually happen."),
        )


def sig_habit_without_cue(ctx: Ctx) -> Optional[Nudge]:
    """A habit nobody has decided WHEN to do.

    Attaching a specific trigger is the best-evidenced thing anyone can do for
    a habit, and bat-board can see exactly which habits lack one. Offered only
    where it would actually help — a habit already running well does not need
    rescuing.
    """
    candidates = [h for h in ctx.habits_all
                  if not (getattr(h, "cue", None) or "").strip()
                  and (h.streak or 0) < 5]
    if not candidates:
        return None
    # The one with the most ground to make up.
    h = min(candidates, key=lambda x: x.streak or 0)
    return Nudge(
        key=f"cue:{h.id}",
        kind="offer_cue",
        priority=31,
        draft=(f"{h.name} has no particular moment attached to it, {ctx.address}. "
               f"What usually happens just before you would do it? I'll pin it "
               f"to that."),
        facts=(f"Habit '{h.name}' has no cue recorded and a current run of "
               f"{h.streak or 0}."),
        warrant=("Naming when and where a habit happens — tied to something that "
                 "already reliably occurs in their day — is the strongest single "
                 "lever there is, and far more useful than more willpower or more "
                 "reminding. Ask what already happens around that time and offer "
                 "to attach the habit to it. Keep the trigger fixed but never "
                 "impose a narrow clock window: people held to a rigid slot do "
                 "WORSE than people who choose their moment."),
    )


def sig_late_night_work(ctx: Ctx) -> Optional[Nudge]:
    """Work logged in the small hours, raised the following day.

    Deliberately never fired at the time. Saying "it's late" at 02:00 is the
    interruption itself, and the person is in the worst state to hear it.
    """
    if ctx.late_night_days < 2 or ctx.late_night_last is None:
        return None
    # Only the day after, and only at a civil hour.
    if not (9 <= ctx.local_now.hour <= 20):
        return None
    if ctx.late_night_last.date() == ctx.today:
        return None
    week = ctx.local_now.isocalendar()
    nights = ctx.late_night_days
    return Nudge(
        key=f"latenight:{week[0]}-{week[1]}",
        kind="care_sleep",
        priority=48,
        draft=(f"That's {nights} nights this week with the clock running after "
               f"midnight, {ctx.address}. Would it help to move one of those "
               f"blocks into the morning instead?"),
        facts=(f"Focus sessions were logged between midnight and 05:00 on "
               f"{nights} separate days in the last week; the most recent was "
               f"{ctx.late_night_last.strftime('%A at %H:%M')}."),
        warrant=("Repeated small-hours work carries three separate costs worth "
                 "knowing: the work itself is done at the body's lowest point, "
                 "the deficit accumulates night after night rather than levelling "
                 "off, and the following day's patience is measurably shorter. "
                 "Raise it ONCE, kindly, naming at most one mechanism, and offer "
                 "something concrete — moving a block earlier, or protecting a "
                 "morning hour. They may have excellent reasons, so ask rather "
                 "than assume, and never moralise about discipline or bedtimes. "
                 "You see only what they logged, not their life."),
    )


def sig_loose_ends(ctx: Ctx) -> Optional[Nudge]:
    """Things on the board missing the one field that gives them traction.

    Offered as a batch of ONE kind, because the point is to close a gap, not
    to hand someone an audit of their own shortcomings.
    """
    from services import completeness

    missions = [m for m in ctx.open_missions
                if m.due_date is None and m.created_at
                and _aware(m.created_at) < ctx.local_now.astimezone(timezone.utc)
                - timedelta(days=completeness.MISSION_SETTLE_DAYS)]
    if len(missions) < 3:
        return None
    names = ", ".join(m.title for m in missions[:3])
    month = ctx.local_now.strftime("%Y-%m")
    return Nudge(
        key=f"loose:missions:{month}",
        kind="offer_when",
        priority=29,
        draft=(f"{len(missions)} things on your board have no date on them, "
               f"{ctx.address} — {names} among them. Shall we put a when "
               f"against a few, or are they fine as they are?"),
        facts=(f"{len(missions)} open missions have no due date and are more "
               f"than {completeness.MISSION_SETTLE_DAYS} days old. The oldest "
               f"are: {names}."),
        warrant=("An open thing with no when keeps intruding on unrelated work, "
                 "and giving it a specific date discharges that cost even "
                 "before it is done — which is why this is worth a word at all. "
                 "Offer to put dates against them, and say plainly that some "
                 "things genuinely have no deadline so leaving them is a real "
                 "answer. Name a few by title rather than only counting, and "
                 "never imply the count itself is a failing."),
    )


SIGNALS: List[Callable[[Ctx], Optional[Nudge]]] = [
    sig_event_soon,
    sig_countdown_horizon,
    sig_habit_at_risk,
    sig_overdue_pileup,
    sig_drift,
    sig_stalled_mission,
    sig_good_day,
    sig_clear_board,
    # ...and what he can offer.
    sig_late_night_work,
    sig_loose_ends,
    sig_habit_without_cue,
    sig_news_topic_offer,
    sig_first_briefing_offer,
    sig_night_briefing_offer,
    sig_focus_rhythm,
    sig_empty_week,
    sig_note_followup,
    sig_long_open_mission,
    sig_capture_prompt,
]


# --- guards -----------------------------------------------------------------

def _parse_hhmm(value: Optional[str], fallback: str) -> time:
    try:
        hh, mm = (value or fallback).split(":")
        return time(int(hh), int(mm))
    except (ValueError, AttributeError):
        hh, mm = fallback.split(":")
        return time(int(hh), int(mm))


def in_quiet_hours(user: models.BatAccount, local_now: datetime) -> bool:
    """Quiet window wraps midnight (e.g. 22:00 → 08:00)."""
    start = _parse_hhmm(getattr(user, "nudge_quiet_start", None), DEFAULT_QUIET_START)
    end = _parse_hhmm(getattr(user, "nudge_quiet_end", None), DEFAULT_QUIET_END)
    now_t = local_now.time()
    if start <= end:
        return start <= now_t < end
    return now_t >= start or now_t < end


def may_nudge(db, user: models.BatAccount, local_now: datetime) -> bool:
    """All the "don't be annoying" rules, in one place."""
    if not getattr(user, "nudges_enabled", True):
        return False
    if in_quiet_hours(user, local_now):
        return False

    today = local_now.date().isoformat()
    cap = getattr(user, "nudges_per_day", None) or DEFAULT_PER_DAY
    sent_today = (
        db.query(models.BatNudgeLog)
        .filter(models.BatNudgeLog.owner_id == user.id,
                models.BatNudgeLog.local_date == today)
        .count()
    )
    if sent_today >= cap:
        return False

    now_utc = local_now.astimezone(timezone.utc)
    last = (
        db.query(models.BatNudgeLog)
        .filter(models.BatNudgeLog.owner_id == user.id)
        .order_by(models.BatNudgeLog.sent_at.desc())
        .first()
    )
    if last is not None and now_utc - _aware(last.sent_at) < GLOBAL_COOLDOWN:
        return False

    # Mid-conversation? Leave them be.
    last_msg = (
        db.query(models.BatAlfredMessage)
        .filter(models.BatAlfredMessage.owner_id == user.id)
        .order_by(models.BatAlfredMessage.created_at.desc())
        .first()
    )
    if last_msg is not None and now_utc - _aware(last_msg.created_at) < RECENT_CHAT_QUIET:
        return False
    return True


def already_sent(db, user: models.BatAccount, key: str) -> bool:
    return db.query(models.BatNudgeLog.id).filter(
        models.BatNudgeLog.owner_id == user.id,
        models.BatNudgeLog.nudge_key == key).first() is not None


# --- variety ----------------------------------------------------------------
# A unique key stops the same OCCASION repeating. These stop the same KIND of
# remark repeating, which is the thing that actually makes a companion tiring:
# being asked about drifting every single afternoon is noise, however true it is.

KIND_MIN_GAP_DAYS: Dict[str, int] = {
    # Tied to a real date — if a countdown hits 7 days, that is worth hearing.
    "countdown": 0,
    "event": 0,
    # Accountability: true often, welcome rarely.
    "habit": 2,
    "drift": 4,
    "overdue": 6,
    "stalled": 10,
    "clear": 6,
    "praise": 5,
    # Offers: these are invitations, and an invitation repeated is pestering.
    # A kind word about sleep, not a campaign: rarely, and never twice running.
    "care_sleep": 10,
    "offer_cue": 8,
    "offer_when": 14,
    "offer_prune": 9,
    "offer_news": 12,
    "offer_note": 12,
    "offer_capture": 12,
    "offer_rest": 16,
    "offer_rhythm": 30,
    "offer_briefing": 28,
}
DEFAULT_KIND_GAP_DAYS = 6
# How far back "recently" reaches when rotating between kinds.
ROTATION_WINDOW_DAYS = 21
# Each recent use of a kind costs it this much priority, so attention moves on.
ROTATION_PENALTY = 14
# FATIGUE. The single most important rule here. A fixed gap is not enough: a
# signal that stays true — an unbroken streak, a board that stays overdue —
# would otherwise fire on its gap forever, which is precisely how a companion
# becomes a notification you learn to ignore. So every recent use widens the
# gap for the next one: say it, say it again later, then let it rest.
FATIGUE_MULTIPLIER = 1
# However tired a kind becomes, it may always return eventually.
MAX_KIND_GAP_DAYS = 45
# Chasing and offering should alternate rather than clump.
FAMILY_PENALTY = 6
# How many of his own recent messages Alfred is shown before writing a new one.
RECENT_TEXTS_SHOWN = 6


def _family(kind: str) -> str:
    return "offer" if kind.startswith("offer_") else "chase"


def recent_history(db, user: models.BatAccount, local_now: datetime,
                   days: int = ROTATION_WINDOW_DAYS) -> List[models.BatNudgeLog]:
    cutoff = _naive(local_now.astimezone(timezone.utc) - timedelta(days=days))
    return (
        db.query(models.BatNudgeLog)
        .filter(models.BatNudgeLog.owner_id == user.id,
                models.BatNudgeLog.sent_at >= cutoff)
        .order_by(models.BatNudgeLog.sent_at.desc())
        .all()
    )


def recent_texts(db, user: models.BatAccount, local_now: datetime,
                 limit: int = RECENT_TEXTS_SHOWN) -> List[str]:
    """The words he has actually used lately, newest first."""
    return [r.sent_text for r in recent_history(db, user, local_now, days=30)
            if r.sent_text][:limit]


def evaluate(db, user: models.BatAccount, local_now: datetime) -> Optional[Nudge]:
    """The single best thing worth saying right now, or None."""
    if not may_nudge(db, user, local_now):
        return None
    ctx = build_context(db, user, local_now)
    candidates = []
    for signal in SIGNALS:
        try:
            n = signal(ctx)
        except Exception as exc:          # one bad signal must not kill the rest
            log.warning("nudge_signal_failed", signal=signal.__name__, error=str(exc))
            continue
        if n is not None and not already_sent(db, user, n.key):
            candidates.append(n)
    if not candidates:
        return None

    history = recent_history(db, user, local_now)
    now_utc = local_now.astimezone(timezone.utc)
    last_by_kind: Dict[str, datetime] = {}
    kind_counts: Counter = Counter()
    family_counts: Counter = Counter()
    for row in history:
        sent = _aware(row.sent_at)
        if row.kind not in last_by_kind or sent > last_by_kind[row.kind]:
            last_by_kind[row.kind] = sent
        kind_counts[row.kind] += 1
        family_counts[_family(row.kind)] += 1

    fresh = []
    for n in candidates:
        base_gap = KIND_MIN_GAP_DAYS.get(n.kind, DEFAULT_KIND_GAP_DAYS)
        if base_gap == 0:
            # Date-bound: a countdown reaching its mark, an appointment within
            # the day. These are not opinions he is repeating — they are facts
            # with a deadline, so neither fatigue nor rotation may bury them.
            fresh.append((n.priority, n))
            continue
        # Each recent use widens the next gap, so a permanently-true signal
        # fades out instead of repeating itself to death.
        gap = min(base_gap * (1 + FATIGUE_MULTIPLIER * kind_counts[n.kind]),
                  MAX_KIND_GAP_DAYS)
        last = last_by_kind.get(n.kind)
        if last is not None and now_utc - last < timedelta(days=gap):
            continue
        score = (n.priority
                 - ROTATION_PENALTY * kind_counts[n.kind]
                 - FAMILY_PENALTY * family_counts[_family(n.kind)])
        fresh.append((score, n))
    if not fresh:
        return None

    # Ties go to whatever has been silent longest, so nothing is permanently
    # outranked by a signal that merely happens to sort first.
    def _rank(item):
        score, n = item
        last = last_by_kind.get(n.kind)
        age = (now_utc - last).total_seconds() if last else float("inf")
        return (score, age)

    return max(fresh, key=_rank)[1]


# --- voice ------------------------------------------------------------------

# Alfred is not handed a sentence to reword — he is handed a situation and the
# knowledge to reason about it, and writes something for THIS moment. That is
# the whole difference between a companion and a notification template.
_NUDGE_BRIEF = """You are Alfred Pennyworth — butler and chief of staff to {addr}. \
Dry, warm, composed, formal British. You are writing ONE short unprompted \
message because you have noticed something. Not a report. Not an alert. The \
kind of remark a person who has been paying attention makes in passing.

{voice}

{knowledge}

{limits}

{folklore}

HOW TO WRITE THIS ONE
- Read what you have noticed and what you know about it, then work out what is \
actually going on for THEM, today. Say that. The situation is specific, so your \
words should be too.
- Two sentences; three only if the third is short. Plain text — no Markdown, no \
asterisks, no bullet points.
- Open with what you noticed, not with a greeting, and not with their name every \
time. You already have their attention.
- Use a mechanism to explain only where it genuinely helps, in plain words, with \
no numbers and no citations. Most of the time it is better left unsaid.
- Finish where they can act or decline with equal ease.
- If, having thought about it, there is nothing worth saying, reply with exactly: \
NOTHING"""

_VARIETY_RULE = (
    "You have recently said these things to them. Do NOT reuse the opening words, "
    "the sentence shape, or the turn of phrase of any of them — and if this one "
    "would land as the same remark again, say NOTHING instead:\n{recent}"
)

# Alfred may decline to speak. Honouring that is the point: a companion that
# must produce a sentence every time it is invoked is a notification engine.
DECLINED = "NOTHING"


def _brief(user: models.BatAccount) -> str:
    return _NUDGE_BRIEF.format(
        addr=_address(user),
        voice=alfred_principles.VOICE_RULES,
        knowledge=alfred_principles.HUMAN_KNOWLEDGE,
        limits=alfred_principles.LIMITS,
        folklore=alfred_principles.FOLKLORE,
    )


async def polish(adapter, user: models.BatAccount, nudge: Nudge,
                 recent: Optional[List[str]] = None) -> str:
    system = _brief(user)
    if recent:
        system += "\n\n" + _VARIETY_RULE.format(
            recent="\n".join(f"- {t}" for t in recent))

    parts = [f"WHAT YOU HAVE NOTICED:\n{nudge.facts}"]
    if nudge.warrant:
        parts.append(f"WHAT YOU KNOW ABOUT THIS KIND OF SITUATION:\n{nudge.warrant}")
    # Included for register only. Reusing its wording is the failure mode this
    # whole design exists to avoid, so the instruction is explicit.
    parts.append(
        f"A SERVICEABLE BUT DULL VERSION (for tone only — do NOT reuse its "
        f"wording or its structure):\n{nudge.draft}")

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(parts)},
    ]
    resp = await adapter.generate(messages, [], system)
    text = (resp.text or "").strip()
    if text.upper().strip(" .!") == DECLINED:
        raise Declined()
    if len(text) < 12 or len(text) > 600:
        raise ValueError("unusable composition")
    return text


class Declined(Exception):
    """Alfred judged that nothing was worth saying. Not an error."""


async def compose(user: models.BatAccount, nudge: Nudge, adapter=None,
                  recent: Optional[List[str]] = None) -> Optional[str]:
    """What to send, or None if Alfred decided against speaking.

    A template draft is used only when no model is configured — otherwise he
    writes it himself from the facts and the warrant.
    """
    if adapter is not None:
        try:
            return await polish(adapter, user, nudge, recent=recent)
        except Declined:
            log.info("nudge_declined_by_alfred", kind=nudge.kind)
            return None
        except Exception as exc:
            log.info("nudge_compose_fallback", error=str(exc))
    return nudge.draft


def remember_text(db, user: models.BatAccount, key: str, text: str) -> None:
    """Store the words that actually went out, so the next one can differ.

    Best-effort: failing to remember a phrasing must never cost the user a
    message that was already delivered.
    """
    try:
        row = (db.query(models.BatNudgeLog)
               .filter(models.BatNudgeLog.owner_id == user.id,
                       models.BatNudgeLog.nudge_key == key).first())
        if row is not None:
            row.sent_text = (text or "")[:1000]
            db.commit()
    except Exception as exc:
        db.rollback()
        log.warning("nudge_remember_failed", error=str(exc))


def record(db, user: models.BatAccount, nudge: Nudge, local_now: datetime) -> bool:
    """Claim the occasion. False if another tick already sent it."""
    from sqlalchemy.exc import IntegrityError

    row = models.BatNudgeLog(
        owner_id=user.id, nudge_key=nudge.key, kind=nudge.kind,
        local_date=local_now.date().isoformat(),
    )
    db.add(row)
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False
