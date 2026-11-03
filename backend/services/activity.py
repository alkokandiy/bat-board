"""When this person was actually about, from what they actually did.

The research the owner gathered assumes a device: HealthKit, motion state,
geofencing, battery, ambient noise. bat-board has none of that and is not
going to. But "no biometrics" is not the same as "no context", and treating
it that way was lazy of me.

Every one of these is already in the database, timestamped, and is a genuine
observation rather than an inference about someone's body:

  - a message the user sent Alfred       — they were awake and reachable
  - a focus session they ran             — they were working
  - a work journal entry                 — they were working
  - a habit check-in                     — they were up and doing something
  - a mission they completed             — same

What this gives is an *observed active window*: the first and last moments
there is evidence of the person, and how much of the day between them the
board can account for. That is enough to ask a useful question at the end of
a day — "you were about from 09:12 to 18:40 and nothing is recorded" — which
is a far better prompt than a blank "what did you do today?".

What it deliberately does NOT do: infer mood, energy, sleep quality or
readiness. Absence of evidence here means the person was not using the app,
not that they were resting. The only safe reading of a quiet stretch is "we
do not know", and every caller has to treat it that way.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

import models
from services.timezones import day_bounds_utc, user_tz


@dataclass
class ActiveWindow:
    """What the record shows about one local day."""

    day: date
    first_seen: Optional[datetime] = None     # local
    last_seen: Optional[datetime] = None      # local
    signals: int = 0                          # how many distinct traces
    tracked_minutes: int = 0                  # focus actually recorded

    @property
    def observed(self) -> bool:
        return self.signals > 0

    @property
    def span_minutes(self) -> int:
        """First to last trace. NOT time worked — only time present."""
        if not (self.first_seen and self.last_seen):
            return 0
        return max(0, int((self.last_seen - self.first_seen).total_seconds() // 60))

    @property
    def unaccounted_minutes(self) -> int:
        """Span the board cannot explain. Never negative."""
        return max(0, self.span_minutes - self.tracked_minutes)

    def summary(self) -> dict:
        return {
            "day": self.day.isoformat(),
            "observed": self.observed,
            "first_seen": self.first_seen.strftime("%H:%M") if self.first_seen else None,
            "last_seen": self.last_seen.strftime("%H:%M") if self.last_seen else None,
            "signals": self.signals,
            "tracked_minutes": self.tracked_minutes,
            "unaccounted_minutes": self.unaccounted_minutes,
        }


# A day with one stray trace says nothing. Several spread across hours is a
# day someone actually spent doing things.
MIN_SIGNALS_FOR_A_DAY = 3
# Below this, the gap is rounding and noise rather than unrecorded work.
MIN_GAP_WORTH_MENTIONING = 90


def observed_day(db: Session, user: models.BatAccount, day: date) -> ActiveWindow:
    """Every trace of this person on one of their own local days."""
    tz = user_tz(user)
    start, end = day_bounds_utc(day, tz)
    s, e = start.replace(tzinfo=None), end.replace(tzinfo=None)

    stamps: List[datetime] = []

    # Only the user's own messages. Alfred's replies prove nothing about
    # whether anyone was there to read them — a briefing fires into an empty
    # room just as happily as into a conversation.
    stamps += [r[0] for r in db.query(models.BatAlfredMessage.created_at).filter(
        models.BatAlfredMessage.owner_id == user.id,
        models.BatAlfredMessage.role == "user",
        models.BatAlfredMessage.created_at >= s,
        models.BatAlfredMessage.created_at < e).all() if r[0]]

    focus_rows = db.query(models.BatFocus.start_time, models.BatFocus.end_time,
                          models.BatFocus.duration_minutes).filter(
        models.BatFocus.owner_id == user.id,
        models.BatFocus.start_time >= s,
        models.BatFocus.start_time < e).all()
    tracked = 0
    for st, en, mins in focus_rows:
        if st:
            stamps.append(st)
        if en:
            stamps.append(en)
        tracked += int(mins or 0)

    stamps += [r[0] for r in db.query(models.BatWorkNote.created_at).filter(
        models.BatWorkNote.owner_id == user.id,
        models.BatWorkNote.created_at >= s,
        models.BatWorkNote.created_at < e).all() if r[0]]

    stamps += [r[0] for r in db.query(models.HabitCompletionLog.completed_at).join(
        models.BatHabit, models.HabitCompletionLog.habit_id == models.BatHabit.id).filter(
        models.BatHabit.owner_id == user.id,
        models.HabitCompletionLog.completed_at >= s,
        models.HabitCompletionLog.completed_at < e).all() if r[0]]

    if not stamps:
        return ActiveWindow(day=day, tracked_minutes=tracked)

    aware = [d.replace(tzinfo=timezone.utc).astimezone(tz) for d in stamps]
    return ActiveWindow(
        day=day,
        first_seen=min(aware),
        last_seen=max(aware),
        signals=len(aware),
        tracked_minutes=tracked,
    )


def looks_like_an_untracked_day(window: ActiveWindow) -> bool:
    """A day with plenty of evidence of a person and none of their work.

    This is the owner's first problem, stated as something the system can
    see: "I was just working, in the job and in personal missions" — and the
    board read zero, because recording required remembering to.
    """
    return (
        window.signals >= MIN_SIGNALS_FOR_A_DAY
        and window.unaccounted_minutes >= MIN_GAP_WORTH_MENTIONING
    )
