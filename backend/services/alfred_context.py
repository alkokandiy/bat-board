"""What Alfred said, and what the user was replying to.

Two gaps, both structural rather than failures of wording in the prompt.

**He could not see his own messages.** Everything Alfred sent on his own
initiative — a reminder, a briefing, a nudge, the work report — went from the
scheduler straight to Telegram. None of it was written to the message table,
so his conversation history held only the turns the user began. An hour after
telling somebody their medication reminder had been suspended, he had no
record of having said it. The symptom looked like forgetfulness; the cause
was that nothing was ever written down.

**He could not see what a reply pointed at.** Telegram puts
`reply_to_message` on the update when somebody replies to a specific message.
The webhook never read it, so replying to one message out of twenty was
exactly the same as typing the words cold. "Change it's time" therefore
arrived with no referent, and was answered by searching the board for
something plausible — which found a mission about learning dots.

So: record outbound messages here, resolve inbound replies here, and hand
the model the referent instead of making it guess at one.

A note on what is NOT done here. When a reply resolves to something concrete
the model is told the id and told not to search for it. That is deliberate.
The guessing is the bug; a known answer should never be re-derived.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy.orm import Session

import models
from services.timezones import user_tz

log = structlog.get_logger(__name__)

# How much of a quoted message to show the model. Enough to identify it
# beyond doubt; not so much that a long briefing crowds out the conversation.
MAX_QUOTE_CHARS = 400

# Message origins. "chat" is a turn the user began; the rest are Alfred
# speaking first.
CHAT = "chat"
PROACTIVE_ORIGINS = ("reminder", "briefing", "nudge", "work_report", "focus")

# What an `about` link may point at, and how to read the thing it names.
_ABOUT_MODELS = {
    "reminder": (models.BatReminder, "message"),
    "mission": (models.BatMission, "title"),
    "habit": (models.BatHabit, "name"),
    "work_task": (models.BatWorkTask, "title"),
    "event": (models.CalendarEvent, "title"),
}


@dataclass
class Quoted:
    """An earlier message a user is replying to."""

    text: str
    role: str                       # "assistant" (Alfred) or "user"
    when: Optional[datetime] = None
    origin: Optional[str] = None
    about_kind: Optional[str] = None
    about_id: Optional[int] = None
    about_label: Optional[str] = None
    # False when Telegram told us the quoted text but we hold no record of
    # the message — anything sent before this was built, or by another bot.
    recognised: bool = True

    @property
    def about(self) -> Optional[tuple]:
        if self.about_kind and self.about_id:
            return (self.about_kind, self.about_id)
        return None


def _active_session_id(db: Session, user: models.BatAccount) -> Optional[int]:
    """The session an unprompted message belongs to, created if there is none.

    Imported lazily: alfred_agent imports the tool layer, which imports half
    the services, and the scheduler is one of them.
    """
    from services import alfred_agent

    session = alfred_agent.get_active_session(db, user)
    if session is None:
        session = alfred_agent.create_session(db, user, "Alfred")
        alfred_agent.set_active_session(db, user, session.id)
    return session.id


def record_outbound(
    db: Session,
    user: models.BatAccount,
    text: str,
    *,
    origin: str,
    telegram_message_id: Optional[int] = None,
    about: Optional[tuple] = None,
) -> Optional[models.BatAlfredMessage]:
    """Write down something Alfred said on his own initiative.

    Never raises. A bookkeeping failure must not stop a reminder going out —
    the message being delivered matters more than the record of it, and the
    old behaviour (no record at all) is what a failure degrades back to.

    It commits, and rolls back on failure, so the caller must have nothing
    uncommitted when it is called. Every scheduler path already does: each
    one claims its (owner, kind, day) log row and commits it BEFORE sending,
    so the send — and this — always run on a clean session.
    """
    try:
        session_id = _active_session_id(db, user)
        row = models.BatAlfredMessage(
            owner_id=user.id,
            session_id=session_id,
            role="assistant",
            content=text,
            origin=origin,
            telegram_message_id=telegram_message_id or None,
            about_kind=about[0] if about else None,
            about_id=about[1] if about else None,
        )
        db.add(row)
        session = db.query(models.BatAlfredSession).filter_by(id=session_id).first()
        if session:
            # It is a real message in that thread, so the thread is active.
            session.updated_at = datetime.now(timezone.utc)
        db.commit()
        return row
    except Exception as exc:  # pragma: no cover - defensive
        db.rollback()
        log.warning("alfred_outbound_not_recorded",
                    origin=origin, error_type=type(exc).__name__)
        return None


def describe_about(db: Session, user: models.BatAccount,
                   kind: Optional[str], ident: Optional[int]) -> Optional[str]:
    """How to name the thing a message was about, scoped to its owner."""
    if not kind or not ident or kind not in _ABOUT_MODELS:
        return None
    model, field = _ABOUT_MODELS[kind]
    row = (
        db.query(model)
        .filter(model.id == ident, model.owner_id == user.id)
        .first()
    )
    return getattr(row, field, None) if row else None


def _truncate(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= MAX_QUOTE_CHARS:
        return text
    return text[:MAX_QUOTE_CHARS].rstrip() + "…"


def resolve_reply(db: Session, user: models.BatAccount,
                  reply_to: Optional[dict]) -> Optional[Quoted]:
    """What the user is replying to, from Telegram's `reply_to_message`.

    Two levels of knowledge, and the weaker one is worth having. If we hold
    the message, the reply inherits everything we know about it, including
    what it was about. If we do not — it predates this, or Telegram sent only
    its own copy — the quoted text alone still tells the model what is being
    answered, which is most of the value and costs nothing.
    """
    if not reply_to:
        return None

    message_id = reply_to.get("message_id")
    quoted_text = (reply_to.get("text") or reply_to.get("caption") or "").strip()

    row = None
    if message_id is not None:
        row = (
            db.query(models.BatAlfredMessage)
            .filter(models.BatAlfredMessage.owner_id == user.id,
                    models.BatAlfredMessage.telegram_message_id == int(message_id))
            .order_by(models.BatAlfredMessage.id.desc())
            .first()
        )

    if row is None:
        if not quoted_text:
            return None
        # Telegram labels a reply to the bot's own message; anything else is
        # the user quoting themselves.
        from_bot = bool(((reply_to.get("from") or {}).get("is_bot")))
        return Quoted(text=_truncate(quoted_text),
                      role="assistant" if from_bot else "user",
                      recognised=False)

    return Quoted(
        text=_truncate(row.content),
        role=row.role,
        when=row.created_at,
        origin=row.origin,
        about_kind=row.about_kind,
        about_id=row.about_id,
        about_label=describe_about(db, user, row.about_kind, row.about_id),
        recognised=True,
    )


def annotate(user: models.BatAccount, text: str,
             quoted: Optional[Quoted]) -> Optional[str]:
    """The user's message, with the thing they replied to attached.

    Returns None when there is nothing to add, so the caller can pass the
    plain text through untouched rather than wrapping every message in
    scaffolding the model has to read past.
    """
    if quoted is None:
        return None

    when = ""
    if quoted.when is not None:
        stamp = quoted.when
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        when = f" at {stamp.astimezone(user_tz(user)).strftime('%H:%M on %d %b')}"

    who = "You sent" if quoted.role == "assistant" else "They said"
    lines = [
        "[REPLY CONTEXT — the user used Telegram's reply function. The message "
        "below is what they are answering. It is the subject of their message; "
        "do not search for some other thing they might have meant.]",
        f"[{who}{when}:]",
    ]
    for line in quoted.text.splitlines() or [""]:
        lines.append(f"> {line}")

    if quoted.about:
        kind, ident = quoted.about
        label = f' "{quoted.about_label}"' if quoted.about_label else ""
        lines.append(
            f"[That message is about {kind} id {ident}{label}. That IS the "
            f"thing they mean. Use this id directly — do not call "
            f"find_on_board, and do not offer them anything else.]")
    elif not quoted.recognised:
        lines.append(
            "[Only the quoted text is known — there is no record of this "
            "message, so nothing else about it can be assumed.]")

    lines.append("")
    lines.append("[Their reply:]")
    lines.append(text)
    return "\n".join(lines)


def attach_reply_id(db: Session, user: models.BatAccount, reply_text: str,
                    telegram_message_id: Optional[int]) -> None:
    """Record what Telegram called the reply Alfred just sent.

    The row is written by store_turn before the message leaves, so the id
    can only be filled in afterwards. Matched on the most recent assistant
    row with no id yet rather than by content, because a reply repeated
    verbatim ("Done, sir.") is common and matching on text would attach the
    id to the wrong one. The turn lock means only one turn per user is in
    flight, so "most recent" is unambiguous.
    """
    if not telegram_message_id:
        return
    try:
        row = (
            db.query(models.BatAlfredMessage)
            .filter(models.BatAlfredMessage.owner_id == user.id,
                    models.BatAlfredMessage.role == "assistant",
                    models.BatAlfredMessage.telegram_message_id.is_(None))
            .order_by(models.BatAlfredMessage.id.desc())
            .first()
        )
        if row is None or row.content != reply_text:
            # Not the turn we just ran (a short-circuit reply that was never
            # stored, say). Attaching the id to an older message would make a
            # future reply resolve to the wrong thing, so do nothing.
            return
        row.telegram_message_id = int(telegram_message_id)
        db.commit()
    except Exception as exc:  # pragma: no cover - defensive
        db.rollback()
        log.warning("alfred_reply_id_not_recorded", error_type=type(exc).__name__)


def record_action(db: Session, user: models.BatAccount, text: str, *,
                  about: Optional[tuple] = None) -> Optional[models.BatAlfredMessage]:
    """Write down something the user DID rather than said.

    Tapping "Done" on a reminder is an answer to it. It left no trace in the
    conversation, so Alfred could ask about the very thing he had just been
    told was finished — the complaint was that he did not know "what sent
    last time and what received", and the taps are half of the received.

    Stored as a user message because that is whose action it was, phrased as
    a bracketed note so it never reads as something they typed.
    """
    try:
        session_id = _active_session_id(db, user)
        row = models.BatAlfredMessage(
            owner_id=user.id,
            session_id=session_id,
            role="user",
            content=text,
            origin="button",
            about_kind=about[0] if about else None,
            about_id=about[1] if about else None,
        )
        db.add(row)
        db.commit()
        return row
    except Exception as exc:  # pragma: no cover - defensive
        db.rollback()
        log.warning("alfred_action_not_recorded", error_type=type(exc).__name__)
        return None
