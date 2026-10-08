"""Clock-driven firing of briefings and reminders.

Driven by a protected cron endpoint (POST /api/internal/cron/tick) hit about
once a minute — NOT an in-process scheduler, so it is correct at any worker
count (see docs/ROADMAP.md). Each due item is fired at most once per local day
via an insert-first on a *_log table with a UNIQUE constraint: if the insert
conflicts (a concurrent tick, a retry), we roll back and skip. A missed window
is skipped rather than fired late, so a morning brief never lands at noon.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Optional

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from config import get_settings
from services import briefings, telegram_service
from services.timezones import user_tz

log = structlog.get_logger(__name__)

# How late an item may still fire after its scheduled minute. Beyond this the
# occurrence is skipped (the next day's will fire normally).
LATE_WINDOW = timedelta(hours=3)

# An untimed focus session still open after this long is treated as abandoned
# (tab closed) and closed without credit.
STALE_FOCUS_HOURS = 12


def _parse_hhmm(value: str) -> Optional[time]:
    try:
        hh, mm = (value or "").strip().split(":")
        return time(int(hh), int(mm))
    except (ValueError, AttributeError):
        return None


def _chat_id_for(db: Session, user: models.BatAccount) -> Optional[str]:
    """The user's linked Telegram chat id, via any live personal access token."""
    row = (
        db.query(models.BatPersonalAccessToken)
        .filter(models.BatPersonalAccessToken.owner_id == user.id,
                models.BatPersonalAccessToken.revoked.is_(False),
                models.BatPersonalAccessToken.telegram_chat_id.isnot(None))
        .first()
    )
    return row.telegram_chat_id if row else None


def _within_window(local_now: datetime, scheduled: time) -> bool:
    """True if now is at or just past the scheduled local time (within LATE_WINDOW)."""
    today_at = local_now.replace(hour=scheduled.hour, minute=scheduled.minute,
                                 second=0, microsecond=0)
    delta = local_now - today_at
    return timedelta(0) <= delta <= LATE_WINDOW


def _reminder_due_today(reminder: models.BatReminder, local_now: datetime) -> bool:
    """Does this reminder's recurrence land on today's local date?"""
    today = local_now.date()
    rec = reminder.recurrence
    if rec == "daily":
        return True
    if rec == "weekly":
        days = {int(d) for d in (reminder.weekdays or "").split(",") if d.strip().isdigit()}
        return today.weekday() in days
    if rec == "monthly":
        dom = reminder.day_of_month or 1
        # Clamp to the month's last day so e.g. the 31st fires in February.
        if local_now.day == dom:
            return True
        import calendar
        last = calendar.monthrange(today.year, today.month)[1]
        return dom > last and local_now.day == last
    if rec == "once":
        return (reminder.run_date or "") == today.isoformat()
    return False


def _send(db: Session, user: models.BatAccount, chat_id: str, text: str) -> bool:
    settings = get_settings()
    if not settings.telegram_bot_token:
        log.warning("scheduler_no_bot_token")
        return False
    return telegram_service.send_telegram_message(settings.telegram_bot_token, chat_id, text)


async def _fire_briefings(db: Session, user: models.BatAccount, chat_id: str,
                          local_now: datetime, adapter, summary: dict) -> None:
    briefs = (
        db.query(models.BatBriefing)
        .filter(models.BatBriefing.owner_id == user.id,
                models.BatBriefing.enabled.is_(True))
        .all()
    )
    for b in briefs:
        scheduled = _parse_hhmm(b.send_time)
        if not scheduled or not _within_window(local_now, scheduled):
            continue
        local_date = local_now.date().isoformat()

        # Insert-first: claim this (owner, kind, day) before doing any work.
        logrow = models.BatBriefingLog(owner_id=user.id, kind=b.kind, local_date=local_date)
        db.add(logrow)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # already sent today (or a concurrent tick won)
            continue

        try:
            text = await briefings.build_briefing_text(db, user, b, adapter=adapter)
            ok = _send(db, user, chat_id, text)
        except Exception as exc:
            ok = False
            log.warning("briefing_build_failed", user_id=user.id, kind=b.kind, error=str(exc))
        summary["briefings_sent" if ok else "briefings_failed"] += 1
        if not ok:
            # Delivery failed — release the claim so a later tick can retry today.
            db.delete(logrow)
            db.commit()


def _fire_reminders(db: Session, user: models.BatAccount, chat_id: str,
                    local_now: datetime, summary: dict) -> None:
    rems = (
        db.query(models.BatReminder)
        .filter(models.BatReminder.owner_id == user.id,
                models.BatReminder.enabled.is_(True))
        .all()
    )
    for r in rems:
        scheduled = _parse_hhmm(r.send_time)
        if not scheduled or not _within_window(local_now, scheduled):
            continue
        if not _reminder_due_today(r, local_now):
            continue
        local_date = local_now.date().isoformat()

        logrow = models.BatReminderLog(reminder_id=r.id, owner_id=user.id, local_date=local_date)
        db.add(logrow)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue

        try:
            ok = _send(db, user, chat_id, briefings.render_reminder(user, r))
        except Exception as exc:
            ok = False
            log.warning("reminder_send_failed", reminder_id=r.id, error=str(exc))

        if ok:
            summary["reminders_sent"] += 1
            if r.recurrence == "once":
                r.enabled = False  # one-shot: don't fire again
                db.commit()
        else:
            summary["reminders_failed"] += 1
            db.delete(logrow)
            db.commit()


def _focus_target_name(db: Session, session: models.BatFocus) -> Optional[str]:
    if session.mission_id:
        m = db.get(models.BatMission, session.mission_id)
        return m.title if m else None
    if session.habit_id:
        h = db.get(models.BatHabit, session.habit_id)
        return h.name if h else None
    return None


def _fire_due_focus(db: Session, now_utc: datetime, summary: dict) -> None:
    """Auto-end any timed focus session whose time is up, then ping the user.

    Runs for every user regardless of briefings/reminders — a timer is a timer.
    """
    from services import focus_service

    open_timed = (
        db.query(models.BatFocus)
        .filter(models.BatFocus.end_time.is_(None),
                models.BatFocus.planned_minutes.isnot(None))
        .all()
    )
    for s in open_timed:
        start = s.start_time if s.start_time.tzinfo else s.start_time.replace(tzinfo=timezone.utc)
        if now_utc < start + timedelta(minutes=s.planned_minutes):
            continue  # not finished yet
        owner = db.get(models.BatAccount, s.owner_id)
        if owner is None:
            continue
        target = _focus_target_name(db, s)
        planned = s.planned_minutes
        ended = focus_service.end_focus_session(db, owner, s.id, duration_minutes=planned)
        if ended is None:
            continue
        summary["focus_autoended"] += 1
        chat_id = _chat_id_for(db, owner)
        if not chat_id:
            continue
        addr = (getattr(owner, "alfred_address", None) or "").strip() or owner.username
        tgt = f" on {target}" if target else ""
        if _send(db, owner, chat_id, f"Focus complete, {addr} — {planned} minutes logged{tgt}. Well done."):
            summary["focus_pings_sent"] += 1

    # Abandoned untimed sessions (browser tab closed without stopping) would
    # otherwise stay "open" forever and shadow the real active session. We
    # can't know how much of that was real focus, so they're closed with no
    # credit rather than inflating the record.
    stale_before = now_utc - timedelta(hours=STALE_FOCUS_HOURS)
    stale = (
        db.query(models.BatFocus)
        .filter(models.BatFocus.end_time.is_(None),
                models.BatFocus.planned_minutes.is_(None),
                models.BatFocus.start_time < stale_before.replace(tzinfo=None))
        .all()
    )
    for s in stale:
        owner = db.get(models.BatAccount, s.owner_id)
        if owner is None:
            continue
        focus_service.end_focus_session(db, owner, s.id, duration_minutes=0)  # <5 min → discarded
        summary["focus_stale_closed"] += 1


async def _fire_nudges(db: Session, user: models.BatAccount, chat_id: str,
                       local_now: datetime, adapter, summary: dict) -> None:
    """One proactive check-in, if anything genuinely deserves a word."""
    from services import nudges

    nudge = nudges.evaluate(db, user, local_now)
    if nudge is None:
        return
    if not nudges.record(db, user, nudge, local_now):
        return  # another tick claimed it
    try:
        text = await nudges.compose(user, nudge, adapter=adapter)
        ok = _send(db, user, chat_id, text)
    except Exception as exc:
        ok = False
        log.warning("nudge_send_failed", user_id=user.id, kind=nudge.kind, error=str(exc))
    if ok:
        summary["nudges_sent"] += 1
    else:
        # Release the claim so a later tick can try again.
        db.query(models.BatNudgeLog).filter(
            models.BatNudgeLog.owner_id == user.id,
            models.BatNudgeLog.nudge_key == nudge.key).delete()
        db.commit()


async def run_tick(db: Session, adapter_for=None) -> dict:
    """Fire every briefing/reminder due right now, for every eligible user,
    and auto-end any timed focus session whose time is up.

    `adapter_for(db, user)` returns that user's LLM adapter or None; it is a
    parameter so tests can stub provider behaviour. Users without a linked
    Telegram chat are skipped silently.
    """
    summary = {"users": 0, "briefings_sent": 0, "briefings_failed": 0,
               "reminders_sent": 0, "reminders_failed": 0,
               "focus_autoended": 0, "focus_pings_sent": 0,
               "focus_stale_closed": 0, "nudges_sent": 0}

    # Timed focus sessions auto-end on their own clock, for everyone.
    _fire_due_focus(db, datetime.now(timezone.utc), summary)

    if adapter_for is None:
        from services import alfred_agent

        def adapter_for(_db, _user):
            try:
                return alfred_agent.resolve_adapter_for_user(_db, _user)
            except Exception:
                return None

    # Users with an enabled briefing or reminder — plus everyone who can be
    # checked in on proactively (any Telegram-linked account with nudges on).
    owner_ids = set()
    owner_ids.update(oid for (oid,) in db.query(models.BatBriefing.owner_id)
                     .filter(models.BatBriefing.enabled.is_(True)).distinct())
    owner_ids.update(oid for (oid,) in db.query(models.BatReminder.owner_id)
                     .filter(models.BatReminder.enabled.is_(True)).distinct())
    owner_ids.update(
        oid for (oid,) in db.query(models.BatPersonalAccessToken.owner_id)
        .filter(models.BatPersonalAccessToken.revoked.is_(False),
                models.BatPersonalAccessToken.telegram_chat_id.isnot(None)).distinct()
    )
    if not owner_ids:
        return summary

    users = db.query(models.BatAccount).filter(models.BatAccount.id.in_(owner_ids)).all()
    for user in users:
        chat_id = _chat_id_for(db, user)
        if not chat_id:
            continue  # no linked Telegram — nothing to deliver to
        summary["users"] += 1
        local_now = datetime.now(user_tz(user))
        adapter = adapter_for(db, user)
        await _fire_briefings(db, user, chat_id, local_now, adapter, summary)
        _fire_reminders(db, user, chat_id, local_now, summary)
        await _fire_nudges(db, user, chat_id, local_now, adapter, summary)

    return summary
