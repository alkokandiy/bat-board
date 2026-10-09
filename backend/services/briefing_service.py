"""CRUD + validation for briefings and reminders.

Thin persistence layer the Alfred tools wrap (like mission_service etc.).
All writes are scoped to the authenticated user; validation raises ValueError
with a user-facing message the tool turns into an {"error": ...} result.
"""

from __future__ import annotations

import re
from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

import models

BRIEFING_KINDS = ("morning", "night")
RECURRENCES = ("once", "daily", "weekly", "monthly")
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_WEEKDAY_NAMES = {
    "mon": 0, "monday": 0, "tue": 1, "tues": 1, "tuesday": 1, "wed": 2, "weds": 2,
    "wednesday": 2, "thu": 3, "thur": 3, "thurs": 3, "thursday": 3, "fri": 4,
    "friday": 4, "sat": 5, "saturday": 5, "sun": 6, "sunday": 6,
}
_WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# --- validation helpers ----------------------------------------------------

def _valid_time(value: str) -> str:
    value = (value or "").strip()
    if not _HHMM.match(value):
        raise ValueError(f"Time must be HH:MM (24-hour), got {value!r}.")
    return value


def _normalize_weekdays(value) -> str:
    """Accept '0,2,4', 'Mon,Wed' or a list; return canonical CSV of 0-6."""
    if value is None:
        raise ValueError("Weekly reminders need weekdays (e.g. 'Mon,Thu' or '0,3').")
    items = value if isinstance(value, list) else str(value).split(",")
    nums = set()
    for raw in items:
        tok = str(raw).strip().lower()
        if not tok:
            continue
        if tok.isdigit():
            n = int(tok)
            if not 0 <= n <= 6:
                raise ValueError("Weekday numbers are 0 (Mon) to 6 (Sun).")
            nums.add(n)
        elif tok in _WEEKDAY_NAMES:
            nums.add(_WEEKDAY_NAMES[tok])
        else:
            raise ValueError(f"Unrecognized weekday: {raw!r}.")
    if not nums:
        raise ValueError("At least one weekday is required for a weekly reminder.")
    return ",".join(str(n) for n in sorted(nums))


def _valid_run_date(value: str) -> str:
    try:
        return date.fromisoformat((value or "").strip()).isoformat()
    except ValueError:
        raise ValueError(f"run_date must be YYYY-MM-DD, got {value!r}.")


def weekdays_label(csv: Optional[str]) -> str:
    nums = [int(d) for d in (csv or "").split(",") if d.strip().isdigit()]
    return ", ".join(_WEEKDAY_LABELS[n] for n in nums) if nums else ""


# --- briefings -------------------------------------------------------------

def list_briefings(db: Session, user: models.BatAccount) -> List[models.BatBriefing]:
    return (
        db.query(models.BatBriefing)
        .filter(models.BatBriefing.owner_id == user.id)
        .order_by(models.BatBriefing.kind.asc())
        .all()
    )


def get_briefing(db: Session, user: models.BatAccount, kind: str) -> Optional[models.BatBriefing]:
    return (
        db.query(models.BatBriefing)
        .filter(models.BatBriefing.owner_id == user.id, models.BatBriefing.kind == kind)
        .first()
    )


DEFAULT_TIMES = {"morning": "07:00", "night": "21:30"}


def upsert_briefing(db: Session, user: models.BatAccount, *, kind: str,
                    enabled: Optional[bool] = None, send_time: Optional[str] = None,
                    include_missions: Optional[bool] = None, include_habits: Optional[bool] = None,
                    include_events: Optional[bool] = None, include_focus: Optional[bool] = None,
                    include_news: Optional[bool] = None,
                    news_topics: Optional[str] = None) -> models.BatBriefing:
    if kind not in BRIEFING_KINDS:
        raise ValueError(f"kind must be one of {BRIEFING_KINDS}, got {kind!r}.")
    if send_time is not None:
        send_time = _valid_time(send_time)

    existing = get_briefing(db, user, kind)
    b = existing or models.BatBriefing(
        owner_id=user.id, kind=kind,
        enabled=True if enabled is None else enabled,
        send_time=send_time or DEFAULT_TIMES[kind],
    )
    if existing is not None:
        if enabled is not None:
            b.enabled = enabled
        if send_time is not None:
            b.send_time = send_time

    for field, val in (
        ("include_missions", include_missions), ("include_habits", include_habits),
        ("include_events", include_events), ("include_focus", include_focus),
        ("include_news", include_news),
    ):
        if val is not None:
            setattr(b, field, val)
    if news_topics is not None:
        b.news_topics = news_topics.strip() or None

    # News with no topics is pointless — guard before persisting, so a rejected
    # new row never lingers in the session to collide on the next call.
    if b.include_news and not (b.news_topics or "").strip():
        raise ValueError("To include news, give at least one topic (e.g. 'AI, cybersecurity').")

    if existing is None:
        db.add(b)
    db.commit()
    db.refresh(b)
    return b


def delete_briefing(db: Session, user: models.BatAccount, kind: str) -> bool:
    b = get_briefing(db, user, kind)
    if b is None:
        return False
    db.delete(b)
    db.commit()
    return True


# --- reminders -------------------------------------------------------------

def list_reminders(db: Session, user: models.BatAccount) -> List[models.BatReminder]:
    return (
        db.query(models.BatReminder)
        .filter(models.BatReminder.owner_id == user.id)
        .order_by(models.BatReminder.id.asc())
        .all()
    )


def get_reminder(db: Session, user: models.BatAccount, reminder_id: int) -> Optional[models.BatReminder]:
    return (
        db.query(models.BatReminder)
        .filter(models.BatReminder.owner_id == user.id, models.BatReminder.id == reminder_id)
        .first()
    )


def create_reminder(db: Session, user: models.BatAccount, *, message: str, recurrence: str,
                    send_time: str, weekdays=None, day_of_month: Optional[int] = None,
                    run_date: Optional[str] = None,
                    ends_on: Optional[str] = None) -> models.BatReminder:
    message = (message or "").strip()
    if not message:
        raise ValueError("A reminder needs a message.")
    if recurrence not in RECURRENCES:
        raise ValueError(f"recurrence must be one of {RECURRENCES}, got {recurrence!r}.")
    send_time = _valid_time(send_time)

    wk, dom, rd = None, None, None
    if recurrence == "weekly":
        wk = _normalize_weekdays(weekdays)
    elif recurrence == "monthly":
        if day_of_month is None or not 1 <= int(day_of_month) <= 31:
            raise ValueError("Monthly reminders need day_of_month between 1 and 31.")
        dom = int(day_of_month)
    elif recurrence == "once":
        if not run_date:
            raise ValueError("A one-off reminder needs run_date (YYYY-MM-DD).")
        rd = _valid_run_date(run_date)

    end = _valid_run_date(ends_on) if ends_on else None
    if end and recurrence == "once":
        end = None   # a one-off already has its date

    r = models.BatReminder(owner_id=user.id, message=message, recurrence=recurrence,
                           send_time=send_time, weekdays=wk, day_of_month=dom, run_date=rd,
                           ends_on=end)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def update_reminder(db: Session, user: models.BatAccount, reminder_id: int, *,
                    message: Optional[str] = None, enabled: Optional[bool] = None,
                    recurrence: Optional[str] = None, send_time: Optional[str] = None,
                    weekdays=None, day_of_month: Optional[int] = None,
                    run_date: Optional[str] = None,
                    ends_on: Optional[str] = None) -> Optional[models.BatReminder]:
    r = get_reminder(db, user, reminder_id)
    if r is None:
        return None

    # Validate everything into locals FIRST; only mutate the row once all
    # checks pass, so a rejected update never persists partial changes.
    updates: dict = {}
    if message is not None:
        if not message.strip():
            raise ValueError("A reminder needs a message.")
        updates["message"] = message.strip()
    if enabled is not None:
        updates["enabled"] = enabled
    if send_time is not None:
        updates["send_time"] = _valid_time(send_time)

    new_rec = recurrence or r.recurrence
    if recurrence is not None:
        if recurrence not in RECURRENCES:
            raise ValueError(f"recurrence must be one of {RECURRENCES}, got {recurrence!r}.")
        updates["recurrence"] = recurrence
    if new_rec == "weekly" and (weekdays is not None or recurrence is not None):
        updates["weekdays"] = _normalize_weekdays(weekdays if weekdays is not None else r.weekdays)
    if new_rec == "monthly" and (day_of_month is not None or recurrence is not None):
        dom = day_of_month if day_of_month is not None else r.day_of_month
        if dom is None or not 1 <= int(dom) <= 31:
            raise ValueError("Monthly reminders need day_of_month between 1 and 31.")
        updates["day_of_month"] = int(dom)
    if new_rec == "once" and (run_date is not None or recurrence is not None):
        rd = run_date if run_date is not None else r.run_date
        if not rd:
            raise ValueError("A one-off reminder needs run_date (YYYY-MM-DD).")
        updates["run_date"] = _valid_run_date(rd)

    if ends_on is not None:
        # "" / "none" clears the end date (runs indefinitely again)
        cleared = str(ends_on).strip().lower() in ("", "none", "never", "null")
        updates["ends_on"] = None if cleared else _valid_run_date(ends_on)

    for field, val in updates.items():
        setattr(r, field, val)
    db.commit()
    db.refresh(r)
    return r


def delete_reminder(db: Session, user: models.BatAccount, reminder_id: int) -> bool:
    r = get_reminder(db, user, reminder_id)
    if r is None:
        return False
    db.delete(r)
    db.commit()
    return True
