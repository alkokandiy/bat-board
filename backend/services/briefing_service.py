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
RECURRENCES = ("once", "daily", "weekly", "monthly", "relative")
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


def _valid_offset_days(value) -> int:
    """Days of notice: 0 (the morning it is due) up to a year ahead.

    Negative is refused rather than read as "after", because a warning that
    arrives once the deadline has passed is a different feature with a
    different name, and silently accepting -1 would ship it by accident.
    """
    if value is None:
        raise ValueError(
            "A reminder counting back from a due date needs offset_days "
            "(0 = on the day, 1 = the day before).")
    try:
        days = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"offset_days must be a whole number of days, got {value!r}.")
    if not 0 <= days <= 365:
        raise ValueError("offset_days must be between 0 and 365.")
    return days


def when_label(r: models.BatReminder) -> str:
    """How this reminder's timing reads to a person.

    A relative reminder has no time of day on its own worth quoting — "the
    08:00 reminder" is wrong for one that fires the day before whenever the
    mission happens to be due. Anything putting a reminder's schedule into a
    sentence goes through here so there is one answer, not one per caller.
    """
    if r.recurrence != "relative":
        return r.send_time
    if r.offset_days == 0:
        return f"{r.send_time} on the day it is due"
    if r.offset_days == 1:
        return f"{r.send_time} the day before it is due"
    return f"{r.send_time}, {r.offset_days} days before it is due"


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


def _valid_link(db: Session, user: models.BatAccount, *, mission_id=None,
                habit_id=None, work_task_id=None) -> dict:
    """Resolve an optional link, refusing ids that are not the user's.

    A reminder that points at someone else's mission would be both a leak and
    a focus session attached to a stranger's work.
    """
    pairs = (("mission_id", mission_id, models.BatMission),
             ("habit_id", habit_id, models.BatHabit),
             ("work_task_id", work_task_id, models.BatWorkTask))
    given = [(f, v, m) for f, v, m in pairs if v is not None]
    if not given:
        return {}
    if len(given) > 1:
        raise ValueError("A reminder can point at one thing, not several.")

    field, value, model = given[0]
    row = db.query(model).filter(model.id == int(value),
                                 model.owner_id == user.id).first()
    if row is None:
        raise ValueError(f"No such {field[:-3].replace('_', ' ')}.")
    return {field: int(value)}


def create_reminder(db: Session, user: models.BatAccount, *, message: str, recurrence: str,
                    send_time: str, weekdays=None, day_of_month: Optional[int] = None,
                    run_date: Optional[str] = None,
                    ends_on: Optional[str] = None, offset_days: Optional[int] = None,
                    mission_id: Optional[int] = None, habit_id: Optional[int] = None,
                    work_task_id: Optional[int] = None) -> models.BatReminder:
    message = (message or "").strip()
    if not message:
        raise ValueError("A reminder needs a message.")
    if recurrence not in RECURRENCES:
        raise ValueError(f"recurrence must be one of {RECURRENCES}, got {recurrence!r}.")
    send_time = _valid_time(send_time)

    wk, dom, rd, off = None, None, None, None
    if recurrence == "relative":
        # Validated before the link is resolved so the error names the thing
        # the caller actually got wrong, rather than the next thing.
        off = _valid_offset_days(offset_days)
        if mission_id is None:
            raise ValueError(
                "A reminder that counts back from a due date needs a mission "
                "to count back from.")
    elif recurrence == "weekly":
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

    link = _valid_link(db, user, mission_id=mission_id, habit_id=habit_id,
                       work_task_id=work_task_id)

    r = models.BatReminder(owner_id=user.id, message=message, recurrence=recurrence,
                           send_time=send_time, weekdays=wk, day_of_month=dom, run_date=rd,
                           ends_on=end, offset_days=off, **link)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def update_reminder(db: Session, user: models.BatAccount, reminder_id: int, *,
                    message: Optional[str] = None, enabled: Optional[bool] = None,
                    recurrence: Optional[str] = None, send_time: Optional[str] = None,
                    weekdays=None, day_of_month: Optional[int] = None,
                    run_date: Optional[str] = None,
                    ends_on: Optional[str] = None, offset_days: Optional[int] = None,
                    mission_id: Optional[int] = None, habit_id: Optional[int] = None,
                    work_task_id: Optional[int] = None) -> Optional[models.BatReminder]:
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
    # Validated with everything else, before anything is written.
    updates.update(_valid_link(db, user, mission_id=mission_id, habit_id=habit_id,
                               work_task_id=work_task_id))

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
    if new_rec == "relative" and (offset_days is not None or recurrence is not None):
        updates["offset_days"] = _valid_offset_days(
            offset_days if offset_days is not None else r.offset_days)
        # The mission it counts back from may be arriving in this same call,
        # so check what the row will HAVE rather than what it has. Switching
        # an unlinked reminder to `relative` without one would otherwise save
        # a reminder that can never fire and never say why.
        if updates.get("mission_id", r.mission_id) is None:
            raise ValueError(
                "A reminder that counts back from a due date needs a mission "
                "to count back from.")
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
