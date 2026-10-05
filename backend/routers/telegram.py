"""Telegram linking endpoints + inbound webhook.

Fast path (request scope): secret validation → update_id dedupe → schedule
background processing → HTTP 200. All user resolution, LLM calls, and
replies happen in the background task with its own DB session, so Telegram
never waits on (or retries) slow model calls.
"""

import asyncio
import re
from typing import Optional
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
)
from services import alfred_agent, alfred_memory_reviewer, provider_config_service, setup_wizard, telegram_service

logger = structlog.get_logger()

router = APIRouter(tags=["telegram"])

LINK_CODE_RE = re.compile(r"^\d{6}$")

UNLINKED_REPLY = (
    "This Telegram account isn't linked to a bat-board account yet. "
    "Go to Profile → Link Telegram in the app to get a code."
)
LINK_THROTTLED_REPLY = (
    "Too many incorrect codes. Wait 10 minutes, then generate a fresh code "
    "in Profile → Link Telegram."
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


# No per-IP rate limit here: every update comes from Telegram's own servers,
# so an IP budget throttles all users together. The secret header is the gate,
# and per-user model spend is bounded by Alfred's daily quota.
@router.post("/api/telegram/webhook")
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

    if not isinstance(payload, dict):
        return {"ok": True}

    background_tasks.add_task(_process_update_in_thread, payload, background_tasks)
    return {"ok": True}


def _process_update_in_thread(payload: dict, background_tasks) -> None:
    """Run update processing in a worker thread with its own event loop.

    Processing does synchronous DB queries and synchronous Telegram HTTP
    sends (10s timeouts). Run as an async task on the server's loop, every
    one of those stalled all other requests on the (single) worker. As a
    sync background task Starlette runs this in its threadpool instead.
    """
    asyncio.run(process_telegram_update(payload, background_tasks))


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


async def process_telegram_update(payload: dict, background_tasks) -> None:
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

        try:
            user = get_user_by_telegram_chat_id(chat_id, db)
        except Exception as exc:
            logger.error("telegram_user_lookup_failed", error=str(exc))
            user = None

        if LINK_CODE_RE.match(text):
            if user is None and telegram_service.link_attempts_blocked(db, chat_id):
                _reply(chat_id, LINK_THROTTLED_REPLY)
                return
            linked = telegram_service.exchange_link_code(db, text, chat_id)
            if linked is not None:
                telegram_service.clear_link_failures(db, chat_id)
                logger.info("telegram_linked", username=linked.username)
                _reply(chat_id, LINK_SUCCESS_REPLY)
                return
            if user is None:
                telegram_service.record_link_failure(db, chat_id)
                _reply(chat_id, UNLINKED_REPLY)
                return
            # Already linked and not a valid code: it's just a number meant
            # for Alfred (it used to get the "not linked" reply).

        if user is None:
            _reply(chat_id, UNLINKED_REPLY)
            return

        # --- Voice note: transcribe with the user's own model, then run as text ---
        voice = message.get("voice")
        if voice:
            await _handle_voice(db, user, chat_id, voice, background_tasks)
            return

        # --- Photo / image document: send it to a vision model and answer ---
        image = _extract_image(message)
        if image:
            await _handle_photo(db, user, chat_id, image, message, background_tasks)
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

            if text.startswith("/setkey"):
                parts = text.split(None, 3)
                if len(parts) == 1:
                    # Guided wizard — same destination as the one-shot below.
                    setup_wizard.start(db, user, chat_id)
                    return
                if len(parts) < 4:
                    _reply(chat_id, "Usage: /setkey <provider> <model> <key>\nProviders: gemini, anthropic, openai, deepseek, kimi\nOr send /setkey alone for guided setup.")
                    return
                _, provider, model_name, raw_key = parts
                provider = provider.strip().lower()
                ok, msg = await provider_config_service.test_config(provider, model_name.strip(), raw_key)
                if ok:
                    try:
                        provider_config_service.save_config(db, user, provider, model_name.strip(), raw_key)
                        _reply(chat_id, f"Provider key saved: {provider} / {model_name.strip()}. Alfred is at your service.")
                    except ValueError as exc:
                        _reply(chat_id, f"Not saved: {exc}")
                else:
                    _reply(chat_id, f"Key test failed — not saved. {msg}")
                # Always scrub the raw-key message; deletion failure must not
                # break the flow — the key is already saved encrypted.
                try:
                    message_id = message.get("message_id")
                    if message_id is not None:
                        telegram_service.delete_telegram_message(
                            get_settings().telegram_bot_token, chat_id, message_id
                        )
                except Exception as exc:
                    logger.warning("setkey_message_delete_failed", error=str(exc))
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

        # --- Setup wizard (captures plain-text step replies before the tool loop) ---
        if await setup_wizard.handle_text(db, user, chat_id, text, message.get("message_id")):
            return

        # --- Normal Alfred turn (session-scoped) ---
        active = alfred_agent.get_active_session(db, user)
        session_id = active.id if active else None
        media = []
        reply = await alfred_agent.run_turn(db, user, text, session_id=session_id, media_sink=media)
        _reply(chat_id, reply)
        _deliver_media(chat_id, media)
        # Memory review runs after the reply is already sent — never on
        # quota/setup short-circuits, which need no review and no extra spend.
        if reply not in alfred_agent.NO_REVIEW_REPLIES:
            alfred_memory_reviewer.schedule_memory_review(background_tasks, user.id, text, reply)
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


def _extract_image(message: dict) -> Optional[dict]:
    """Return {file_id, file_size, mime_type} for a photo or image document, else None."""
    photos = message.get("photo")
    if photos:
        largest = max(photos, key=lambda p: p.get("file_size") or (p.get("width", 0) * p.get("height", 0)))
        return {
            "file_id": largest.get("file_id"),
            "file_size": largest.get("file_size") or 0,
            "mime_type": "image/jpeg",  # Telegram re-encodes photos as JPEG
        }
    doc = message.get("document") or {}
    mime = (doc.get("mime_type") or "").lower()
    if mime.startswith("image/"):
        return {"file_id": doc.get("file_id"), "file_size": doc.get("file_size") or 0, "mime_type": mime}
    return None


async def _handle_photo(db: Session, user, chat_id: str, image: dict, message: dict, background_tasks) -> None:
    """Send a Telegram photo to the user's vision model and run the turn.

    Image bytes are fetched, passed to the model and discarded; only a text
    placeholder is stored. Any text inside the image is data to the model, not
    instructions, and a destructive request still hits the confirmation gate.
    """
    settings = get_settings()
    token = settings.telegram_bot_token
    if not token:
        return

    mime = image.get("mime_type") or "image/jpeg"
    if mime not in alfred_agent.ALLOWED_IMAGE_MIMES:
        _reply(chat_id, alfred_agent.IMAGE_BAD_TYPE_REPLY)
        return
    if (image.get("file_size") or 0) > alfred_agent.MAX_IMAGE_BYTES:
        _reply(chat_id, alfred_agent.IMAGE_TOO_LARGE_REPLY)
        return

    precheck = alfred_agent.vision_precheck(db, user)
    if precheck == "setup":
        _reply(chat_id, alfred_agent.SETUP_REPLY)
        return
    if precheck == "unsupported":
        _reply(chat_id, alfred_agent.VISION_UNSUPPORTED_REPLY)
        return

    file_path = telegram_service.get_file_path(token, image.get("file_id"))
    data = (
        telegram_service.download_file(token, file_path, alfred_agent.MAX_IMAGE_BYTES)
        if file_path else None
    )
    if data is None:
        _reply(chat_id, alfred_agent.IMAGE_DOWNLOAD_FAIL_REPLY)
        return

    caption = (message.get("caption") or "").strip()
    content = caption or "(The user sent a photo.)"
    store_text = f"[image: {caption or 'no caption'}]"
    active = alfred_agent.get_active_session(db, user)
    session_id = active.id if active else None
    media = []
    reply = await alfred_agent.run_turn(
        db, user, content, session_id=session_id,
        images=[{"data": data, "mime_type": mime}], store_text=store_text, media_sink=media,
    )
    _reply(chat_id, reply)
    _deliver_media(chat_id, media)
    if reply not in alfred_agent.NO_REVIEW_REPLIES:
        alfred_memory_reviewer.schedule_memory_review(background_tasks, user.id, store_text, reply)


async def _handle_voice(db: Session, user, chat_id: str, voice: dict, background_tasks) -> None:
    """Transcribe a Telegram voice note and run the transcript as a normal turn.

    Audio bytes are fetched, transcribed and discarded; only the transcript is
    stored (by run_turn). The transcript still passes through the confirmation
    gate, so a spoken "delete everything" cannot bypass it.
    """
    settings = get_settings()
    token = settings.telegram_bot_token
    if not token:
        return

    if (voice.get("duration") or 0) > alfred_agent.MAX_VOICE_SECONDS:
        _reply(chat_id, alfred_agent.VOICE_TOO_LONG_REPLY)
        return
    if (voice.get("file_size") or 0) > alfred_agent.MAX_VOICE_BYTES:
        _reply(chat_id, alfred_agent.VOICE_TOO_LARGE_REPLY)
        return

    # Fail fast before downloading if the provider can't transcribe audio.
    precheck = alfred_agent.voice_precheck(db, user)
    if precheck == "setup":
        _reply(chat_id, alfred_agent.SETUP_REPLY)
        return
    if precheck == "unsupported":
        _reply(chat_id, alfred_agent.VOICE_UNSUPPORTED_REPLY)
        return

    file_path = telegram_service.get_file_path(token, voice.get("file_id"))
    audio = (
        telegram_service.download_file(token, file_path, alfred_agent.MAX_VOICE_BYTES)
        if file_path else None
    )
    if audio is None:
        _reply(chat_id, alfred_agent.VOICE_DOWNLOAD_FAIL_REPLY)
        return

    mime = voice.get("mime_type") or "audio/ogg"
    status, transcript = await alfred_agent.transcribe_voice(db, user, audio, mime)
    if status != "ok":
        _reply(chat_id, {
            "setup": alfred_agent.SETUP_REPLY,
            "unsupported": alfred_agent.VOICE_UNSUPPORTED_REPLY,
            "empty": alfred_agent.VOICE_EMPTY_REPLY,
        }.get(status, alfred_agent.SNAG_REPLY))
        return

    # Echo what was heard so a wrong transcription is visible, then run it.
    _reply(chat_id, f"🎙 I heard: {transcript}")
    active = alfred_agent.get_active_session(db, user)
    session_id = active.id if active else None
    media = []
    reply = await alfred_agent.run_turn(db, user, transcript, session_id=session_id, media_sink=media)
    _reply(chat_id, reply)
    _deliver_media(chat_id, media)
    if reply not in alfred_agent.NO_REVIEW_REPLIES:
        alfred_memory_reviewer.schedule_memory_review(background_tasks, user.id, transcript, reply)


async def _handle_callback_query(db: Session, callback: dict) -> None:
    """Handle inline keyboard callbacks (wizard steps, then session switch)."""
    data = callback.get("data", "")

    if data.startswith("wprov:") or data.startswith("wmodel:"):
        from_user = callback.get("from") or {}
        telegram_user_id = str(from_user.get("id", ""))
        if telegram_user_id:
            try:
                cb_user = get_user_by_telegram_chat_id(telegram_user_id, db)
            except Exception:
                cb_user = None
            if cb_user is not None:
                await setup_wizard.handle_callback(db, cb_user, callback)
        return

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


def _deliver_media(chat_id: str, media: list) -> None:
    """Send any images Alfred produced this turn (charts) via sendPhoto."""
    if not media:
        return
    settings = get_settings()
    if not settings.telegram_bot_token:
        return
    for item in media:
        telegram_service.send_telegram_photo(
            settings.telegram_bot_token, chat_id, item["png"], item.get("caption", ""),
        )


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
