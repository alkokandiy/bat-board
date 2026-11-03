"""What happened after a reminder went out.

Until now, nothing. `BatReminderLog` recorded that an occurrence was sent and
stopped there, the message carried no buttons, and the scheduler fired on
schedule for ever. A reminder the user never acted on and a reminder they
relied on every day were indistinguishable to the system, so it treated both
the same way — which is why a month of ignored medicine reminders kept
arriving unchanged.

This module is the return path. It is deliberately small: record the answer,
count the silence, and say when a reminder has stopped working. What to *do*
about that belongs to the scheduler and to Alfred.
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

import models
from services.timezones import local_date, user_tz

OUTCOMES = ("done", "skipped", "snoozed")

# How many unanswered occurrences before the reminder suspends itself and
# Alfred asks about it instead. Three is a run, not an accident — one missed
# evening says nothing, three in a row says the reminder is not reaching them.
IGNORED_LIMIT = 3


def latest_occurrence(db: Session, reminder_id: int, owner_id: int) -> Optional[models.BatReminderLog]:
    return (
        db.query(models.BatReminderLog)
        .filter(models.BatReminderLog.reminder_id == reminder_id,
                models.BatReminderLog.owner_id == owner_id)
        .order_by(models.BatReminderLog.sent_at.desc())
        .first()
    )


def record_outcome(db: Session, current_user: models.BatAccount,
                   reminder_id: int, outcome: str) -> Optional[models.BatReminderLog]:
    """Answer the most recent occurrence of a reminder.

    Returns the row, or None for an unknown/foreign reminder or one that was
    never actually sent. Answering twice is harmless — the last answer wins,
    because a user who taps "not today" and then takes the medicine anyway is
    telling the truth the second time.
    """
    if outcome not in OUTCOMES:
        raise ValueError(f"Unknown outcome {outcome!r}. One of: {', '.join(OUTCOMES)}")

    reminder = (
        db.query(models.BatReminder)
        .filter(models.BatReminder.id == reminder_id,
                models.BatReminder.owner_id == current_user.id)
        .first()
    )
    if reminder is None:
        return None

    row = latest_occurrence(db, reminder_id, current_user.id)
    if row is None:
        return None

    row.outcome = outcome
    row.responded_at = datetime.now(timezone.utc)

    # Any answer at all breaks the run. "Not today" is engagement: it tells
    # the system the cue arrived and was considered, which is exactly what a
    # silent month did not.
    reminder.consecutive_ignored = 0
    reminder.suspended_at = None

    db.commit()
    db.refresh(row)
    return row


def note_unanswered(db: Session, reminder: models.BatReminder) -> None:
    """Called when an occurrence is superseded without ever being answered."""
    reminder.consecutive_ignored = (reminder.consecutive_ignored or 0) + 1
    if reminder.consecutive_ignored >= IGNORED_LIMIT and reminder.suspended_at is None:
        reminder.suspended_at = datetime.now(timezone.utc)
    db.commit()


def is_suspended(reminder: models.BatReminder) -> bool:
    return reminder.suspended_at is not None


def history(db: Session, current_user: models.BatAccount, reminder_id: int,
            limit: int = 30) -> List[dict]:
    """Recent occurrences, newest first, as Alfred needs to see them."""
    tz = user_tz(current_user)
    rows = (
        db.query(models.BatReminderLog)
        .filter(models.BatReminderLog.reminder_id == reminder_id,
                models.BatReminderLog.owner_id == current_user.id)
        .order_by(models.BatReminderLog.sent_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "date": r.local_date,
            # NULL has always meant "sent, never answered". Saying so plainly
            # keeps Alfred from reading silence as success.
            "outcome": r.outcome or "ignored",
            "answered_on": local_date(r.responded_at, tz).isoformat() if r.responded_at else None,
        }
        for r in rows
    ]


def summary(db: Session, current_user: models.BatAccount, reminder_id: int,
            limit: int = 30) -> dict:
    """Counts over the recent window, for deciding whether this is working."""
    rows = history(db, current_user, reminder_id, limit)
    counts = {"done": 0, "skipped": 0, "snoozed": 0, "ignored": 0}
    for r in rows:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1

    reminder = (
        db.query(models.BatReminder)
        .filter(models.BatReminder.id == reminder_id,
                models.BatReminder.owner_id == current_user.id)
        .first()
    )
    return {
        "sent": len(rows),
        **counts,
        "consecutive_ignored": (reminder.consecutive_ignored or 0) if reminder else 0,
        "suspended": is_suspended(reminder) if reminder else False,
    }
