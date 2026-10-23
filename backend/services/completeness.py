"""Loose ends: the things on the board that are missing what makes them work.

Items get created in a hurry — a mission with no date, a habit with no moment
attached, a note written once and never reopened. None of them are broken, but
each is missing the one field that gives it traction, so it sits there feeling
neither urgent nor finished until it is quietly forgotten.

Two findings decide what counts as a loose end here, and they are the reason
this module looks only at a handful of fields rather than every empty box:

- An unfinished thing keeps intruding on unrelated work, and giving it a
  SPECIFIC WHEN discharges that cost even before it is done. So a dateless
  open mission is a real loose end; a missing tag is not.
- Naming when and where a habit happens is the strongest single lever in the
  habit literature. So a cue-less habit is a real loose end; a missing
  description is not.

Everything else is a trimming, and pestering someone for trimmings is exactly
the behaviour the rest of Alfred's design works to avoid. Nothing in here
writes anything: it reports gaps and the question worth asking, and the user
decides.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

import models
from services.timezones import user_tz

# A mission created minutes ago has not been "forgotten" — give it room to be
# finished before suggesting it needs a date.
MISSION_SETTLE_DAYS = 3
# A note nobody has reopened in this long is a candidate for a second look.
NOTE_COLD_DAYS = 30
# Never hand back a wall of them; this is a conversation, not an audit.
MAX_PER_KIND = 5


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def dateless_missions(db: Session, user: models.BatAccount) -> List[models.BatMission]:
    """Open missions with no due date, old enough to have settled."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=MISSION_SETTLE_DAYS)
    return (
        db.query(models.BatMission)
        .filter(models.BatMission.owner_id == user.id,
                models.BatMission.status == "pending",
                models.BatMission.is_dismissed.is_(False),
                models.BatMission.due_date.is_(None),
                models.BatMission.created_at < cutoff.replace(tzinfo=None))
        .order_by(models.BatMission.created_at.asc())
        .limit(MAX_PER_KIND)
        .all()
    )


def cueless_habits(db: Session, user: models.BatAccount) -> List[models.BatHabit]:
    """Habits with no moment attached to them."""
    rows = (
        db.query(models.BatHabit)
        .filter(models.BatHabit.owner_id == user.id)
        .order_by(models.BatHabit.streak.asc())
        .all()
    )
    return [h for h in rows if not (getattr(h, "cue", None) or "").strip()][:MAX_PER_KIND]


def cold_notes(db: Session, user: models.BatAccount) -> List[models.BatNote]:
    """Notes nobody has reopened in a long while. Titles only — never bodies."""
    from services.notes_service import ALFRED_MEMORY_TAG

    cutoff = datetime.now(timezone.utc) - timedelta(days=NOTE_COLD_DAYS)
    rows = (
        db.query(models.BatNote)
        .filter(models.BatNote.owner_id == user.id,
                models.BatNote.is_pinned.is_(False),
                models.BatNote.updated_at < cutoff.replace(tzinfo=None))
        .order_by(models.BatNote.updated_at.asc())
        .limit(MAX_PER_KIND * 2)
        .all()
    )
    return [n for n in rows
            if ALFRED_MEMORY_TAG not in (n.tags or "").lower() and (n.title or "").strip()
            ][:MAX_PER_KIND]


def undated_countdowns_or_events(db: Session, user: models.BatAccount) -> list:
    """Kept deliberately empty: both carry a date by construction.

    Here so the shape of "what can be loose" stays visible to whoever reads
    this next, rather than looking like an oversight.
    """
    return []


# Alfred's own memory notes accumulate and never leave. Some are durable
# ("their name is Al-Kokandiy"); some were only ever true for a week ("once
# bro arrives we do these jobs together"). He cannot tell which from age
# alone, and he must never decide alone — so this hands him the candidates
# and the rule, and the user keeps the final word.
MEMORY_STALE_DAYS = 21


def stale_memory(db: Session, user: models.BatAccount) -> List[models.BatNote]:
    """Alfred's own memory notes he has not revisited in a while."""
    from services.notes_service import ALFRED_MEMORY_TAG

    cutoff = datetime.now(timezone.utc) - timedelta(days=MEMORY_STALE_DAYS)
    rows = (
        db.query(models.BatNote)
        .filter(models.BatNote.owner_id == user.id,
                models.BatNote.updated_at < cutoff.replace(tzinfo=None))
        .order_by(models.BatNote.updated_at.asc())
        .limit(MAX_PER_KIND * 3)
        .all()
    )
    return [n for n in rows
            if ALFRED_MEMORY_TAG in (n.tags or "").lower()][:MAX_PER_KIND]


def review(db: Session, user: models.BatAccount) -> dict:
    """Every loose end on this board, with the question worth asking for each.

    The `question` strings are guidance for Alfred, not text to be sent
    verbatim — he is expected to ask in his own words, about the specific item.
    """
    missions = dateless_missions(db, user)
    habits = cueless_habits(db, user)
    notes = cold_notes(db, user)
    tz = user_tz(user)

    out = {
        "missions_without_a_date": {
            "items": [{"id": m.id, "title": m.title,
                       "age_days": (datetime.now(timezone.utc)
                                    - _aware(m.created_at)).days}
                      for m in missions],
            "why": ("An open thing with no when keeps nagging at unrelated work. "
                    "Pinning a date discharges that even before it is done."),
            "question": "When would you actually do this?",
            "fix": "update_mission with a due_date",
        },
        "habits_without_a_cue": {
            "items": [{"id": h.id, "name": h.name, "streak": h.streak or 0}
                      for h in habits],
            "why": ("A habit tied to something that already happens reliably "
                    "beats one that depends on remembering."),
            "question": "What already happens just before you would do this?",
            "fix": "update_habit with a cue",
        },
        "notes_gone_cold": {
            "items": [{"id": n.id, "title": n.title,
                       "days_since_touched": (datetime.now(timezone.utc)
                                              - _aware(n.updated_at)).days}
                      for n in notes],
            "why": "Something written down once and never reopened is lost in practice.",
            "question": "Still worth keeping, or has it done its job?",
            "fix": "a reminder to revisit it, or delete it",
        },
    }
    memory = stale_memory(db, user)
    out["my_memory_worth_pruning"] = {
        "items": [{"id": n.id, "title": n.title,
                   "days_since_touched": (datetime.now(timezone.utc)
                                          - _aware(n.updated_at)).days}
                  for n in memory],
        "why": ("Things you recorded about them that may have stopped being "
                "true. Carrying a finished arrangement forever makes your "
                "recall worse, not better."),
        "question": "Does this still matter, or has it served its purpose?",
        "fix": "delete_note, but only once they have said so",
        "rule": (
            "KEEP anything describing something not yet started or still "
            "intended — a habit they mean to begin, a plan with a date ahead "
            "of it, a standing preference. Those are not stale merely because "
            "they are old; they are waiting. PROPOSE REMOVING only what was "
            "tied to an occasion that has passed: a visit that happened, a "
            "one-off arrangement, a list for a trip already taken. Name the "
            "specific note and say why you think it is spent. NEVER delete a "
            "memory on your own judgement — ask, and accept 'keep it' without "
            "argument."),
    }
    out["total"] = sum(len(v["items"]) for k, v in out.items() if isinstance(v, dict))
    out["note"] = (
        "These are OFFERS, never demands. Raise at most one kind at a time, "
        "ask about specific items by name, and accept 'leave it' without "
        "pressing. A thing with no date is not a failure — some things "
        "genuinely have no deadline, and saying so is a complete answer."
    )
    return out
