"""Telegram linking endpoints + inbound webhook.

Fast path (request scope): secret validation → update_id dedupe → schedule
background processing → HTTP 200. All user resolution, LLM calls, and
replies happen in the background task with its own DB session, so Telegram
never waits on (or retries) slow model calls.
"""

import re
import secrets as secrets_lib

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from config import get_settings
from database import SessionLocal
from dependencies import (
    get_current_active_user,
    get_db,
    get_user_by_telegram_chat_id,
    limiter,
)
from services import alfred_agent, telegram_service

logger = structlog.get_logger()

router = APIRouter(tags=["telegram"])

LINK_CODE_RE = re.compile(r"^\d{6}$")

UNLINKED_REPLY = (
    "This Telegram account isn't linked to a bat-board account yet. "
    "Go to Profile → Link Telegram in the app to get a code."
)
LINK_SUCCESS_REPLY = (
    "Linked ✓ — this Telegram account is now connected to your bat-board account."
)


@router.post("/api/account/telegram-link/generate-code")
def generate_telegram_link_code(
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    code, expires_at = telegram_service.generate_link_code(db, current_user)
    return {"code": code, "expires_at": expires_at.isoformat()}


@router.get("/api/account/telegram-link/status")
def telegram_link_status(
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    return {"linked": telegram_service.is_telegram_linked(db, current_user)}


@router.delete("/api/account/telegram-link", status_code=status.HTTP_204_NO_CONTENT)
def unlink_telegram(
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    telegram_service.unlink_telegram(db, current_user)
    return None


@router.post("/api/telegram/webhook")
@limiter.limit("20/minute")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    return await handle_telegram_webhook(request, background_tasks, db)


async def handle_telegram_webhook(request: Request, background_tasks, db: Session):
    """Undecorated core so tests can call it directly with a stub task queue."""
    settings = get_settings()

    # FIRST: secret validation. No body parsing, no DB, no payload logging
    # before this passes. Fail closed when unconfigured.
    expected = settings.telegram_webhook_secret
    provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not expected or not provided or not secrets_lib.compare_digest(provided, expected):
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": "Forbidden"})

    try:
        payload = await request.json()
    except Exception:
        return {"ok": True}

    update_id = payload.get("update_id")
    if update_id is not None and not _claim_update(db, update_id):
        return {"ok": True}  # duplicate delivery — no-op

    background_tasks.add_task(process_telegram_update, payload)
    return {"ok": True}


def _claim_update(db: Session, update_id: int) -> bool:
    """DB-level dedupe (unique PK, race-safe across workers). False = seen."""
    try:
        db.add(models.BatTelegramSeenUpdate(update_id=int(update_id)))
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False
    except Exception:
        db.rollback()
        return True  # never block delivery on bookkeeping failure


async def process_telegram_update(payload: dict) -> None:
    """Background processing: linking exchange, slash commands, callback queries, or Alfred turn."""
    db = SessionLocal()
    try:
        # --- Callback query (inline keyboard tap) ---
        callback = payload.get("callback_query")
        if callback:
            await _handle_callback_query(db, callback)
            return

        message = payload.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        text = (message.get("text") or "").strip()
        if chat_id is None:
            return
        chat_id = str(chat_id)

        if LINK_CODE_RE.match(text):
            user = telegram_service.exchange_link_code(db, text, chat_id)
            if user is not None:
                logger.info("telegram_linked", username=user.username)
                _reply(chat_id, LINK_SUCCESS_REPLY)
            else:
                _reply(chat_id, UNLINKED_REPLY)
            return

        try:
            user = get_user_by_telegram_chat_id(chat_id, db)
        except Exception as exc:
            logger.error("telegram_user_lookup_failed", error=str(exc))
            user = None
        if user is None:
            _reply(chat_id, UNLINKED_REPLY)
            return

        # --- Slash commands (before pending-confirmation check) ---
        if text.startswith("/"):
            # Cancel any pending destructive action on /-commands
            pending = db.query(models.BatPendingAlfredAction).filter_by(owner_id=user.id).first()
            if pending:
                db.delete(pending)
                db.commit()

            if text == "/new":
                session = alfred_agent.create_session(db, user, "New conversation")
                alfred_agent.set_active_session(db, user, session.id)
                _reply(chat_id, "Started a new conversation.")
                return

            if text.startswith("/chats"):
                query = text[len("/chats"):].strip()
                q = db.query(models.BatAlfredSession).filter(
                    models.BatAlfredSession.owner_id == user.id,
                )
                if query:
                    q = q.filter(models.BatAlfredSession.title.ilike(f"%{query}%"))
                sessions = q.order_by(models.BatAlfredSession.updated_at.desc()).limit(10).all()
                if not sessions:
                    _reply(chat_id, "No conversations found." if query else "No conversations yet.")
                    return
                label = f"Conversations matching '{query}':" if query else "Recent conversations:"
                keyboard = [[{"text": s.title or "Untitled", "callback_data": f"switch:{s.id}"}] for s in sessions]
                _reply_markup(chat_id, label, {"inline_keyboard": keyboard})
                return

            if text.startswith("/rename"):
                new_title = text[len("/rename"):].strip()
                if not new_title:
                    _reply(chat_id, "Usage: /rename <new title>")
                    return
                active = alfred_agent.get_active_session(db, user)
                if active is None:
                    _reply(chat_id, "No active conversation to rename. Start one with /new.")
                    return
                active.title = new_title[:80]
                db.commit()
                _reply(chat_id, f"Conversation renamed to: {active.title}")
                return

            # Unknown command — fall through to Alfred
            pass

        # --- Normal Alfred turn (session-scoped) ---
        active = alfred_agent.get_active_session(db, user)
        session_id = active.id if active else None
        reply = await alfred_agent.run_turn(db, user, text, session_id=session_id)
        _reply(chat_id, reply)
    except Exception as exc:
        logger.error("telegram_process_failed", error_type=type(exc).__name__, error=str(exc))
        try:
            chat = (payload.get("message") or payload.get("callback_query", {}).get("message") or {}).get("chat") or {}
            if chat.get("id") is not None:
                _reply(str(chat.get("id")), alfred_agent.SNAG_REPLY)
        except Exception:
            pass
    finally:
        db.close()


async def _handle_callback_query(db: Session, callback: dict) -> None:
    """Handle inline keyboard callback (session switch)."""
    data = callback.get("data", "")
    if not data.startswith("switch:"):
        return

    settings = get_settings()
    if not settings.telegram_bot_token:
        return

    try:
        session_id = int(data.split(":", 1)[1])
    except (ValueError, IndexError):
        return

    # Resolve the user from the callback's from field
    from_user = callback.get("from") or {}
    telegram_user_id = str(from_user.get("id", ""))
    if not telegram_user_id:
        return

    try:
        user = get_user_by_telegram_chat_id(telegram_user_id, db)
    except Exception:
        user = None
    if user is None:
        return

    # Verify ownership
    session = (
        db.query(models.BatAlfredSession)
        .filter_by(id=session_id, owner_id=user.id)
        .first()
    )
    if session is None:
        telegram_service.answer_callback_query(settings.telegram_bot_token, callback["id"], "Session not found.")
        return

    alfred_agent.set_active_session(db, user, session_id)
    telegram_service.answer_callback_query(settings.telegram_bot_token, callback["id"])

    # Reply confirmation to the chat
    chat_id = str(callback.get("message", {}).get("chat", {}).get("id", ""))
    if chat_id:
        _reply(chat_id, f"Switched to: {session.title}")


def _reply(chat_id: str, text: str) -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.error("telegram_not_configured", hint="Set TELEGRAM_BOT_TOKEN in Railway.")
        return
    telegram_service.send_telegram_message(settings.telegram_bot_token, chat_id, text)


def _reply_markup(chat_id: str, text: str, reply_markup: dict) -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.error("telegram_not_configured", hint="Set TELEGRAM_BOT_TOKEN in Railway.")
        return
    telegram_service.send_telegram_message(settings.telegram_bot_token, chat_id, text, reply_markup=reply_markup)
