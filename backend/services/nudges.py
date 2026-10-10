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

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Callable, List, Optional

import structlog

import models
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
    key: str
    kind: str
    priority: int
    draft: str          # the message, already in Alfred's voice
    facts: str          # the bare facts, for the optional model rephrase


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

    return Ctx(
        user=user, local_now=local_now, today=today, address=_address(user),
        open_missions=open_missions, overdue=overdue, countdowns=countdowns,
        events_soon=events_soon, habits_pending=habits_pending,
        focus_today_minutes=focus_today,
        last_focus_at=_aware(last_done.end_time) if last_done else None,
        at_work=at_work,
        work_activity_today=work_touched,
    )


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
        )

    # The job moved today, it just wasn't timed.
    if ctx.work_activity_today:
        return Nudge(
            key=key, kind="drift", priority=45,
            draft=(f"You've moved work along today, {ctx.address}, but timed none of it. "
                   f"Worth running the clock on it — shall I start one?"),
            facts="Work tasks or notes changed today, but no focus time was logged.",
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
    return max(candidates, key=lambda n: n.priority)


# --- voice ------------------------------------------------------------------

_POLISH_SYSTEM = (
    "You are Alfred Pennyworth sending ONE short unprompted message to {addr} — "
    "dry, warm, composed, formal British. You are a companion who notices things, "
    "not a reporter. Rewrite the message below in your own voice. Use ONLY the "
    "facts given; invent nothing. Two sentences at most. End by offering help or "
    "asking a question, never by scolding or lecturing. Plain text."
)


async def polish(adapter, user: models.BatAccount, nudge: Nudge) -> str:
    system = _POLISH_SYSTEM.format(addr=_address(user))
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Facts: {nudge.facts}\n\nDraft: {nudge.draft}"},
    ]
    resp = await adapter.generate(messages, [], system)
    text = (resp.text or "").strip()
    if len(text) < 12 or len(text) > 600:
        raise ValueError("unusable polish")
    return text


async def compose(user: models.BatAccount, nudge: Nudge, adapter=None) -> str:
    """The message to send: template always, model rephrase when available."""
    if adapter is not None:
        try:
            return await polish(adapter, user, nudge)
        except Exception as exc:
            log.info("nudge_polish_fallback", error=str(exc))
    return nudge.draft


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
