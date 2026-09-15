"""Telegram linking endpoints + inbound webhook. Thin handlers only.

The webhook proves the auth chain (Telegram → secret validation → chat_id
→ user resolution → reply) with a static placeholder. No LLM in this pass.
"""

import re
import secrets as secrets_lib

import structlog
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import models
from config import get_settings
from dependencies import (
    get_current_active_user,
    get_db,
    get_user_by_telegram_chat_id,
    limiter,
)
from services import telegram_service

logger = structlog.get_logger()

router = APIRouter(tags=["telegram"])

LINK_CODE_RE = re.compile(r"^\d{6}$")

PLACEHOLDER_REPLY = (
    "Alfred received your message. "
    "The response engine isn't wired up yet — coming in the next update."
)
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
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()

    # FIRST: secret validation. No body parsing, no DB, no payload logging
    # before this passes. Fail closed when unconfigured.
    expected = settings.telegram_webhook_secret
    provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not expected or not provided or not secrets_lib.compare_digest(provided, expected):
        return _forbidden()

    try:
        payload = await request.json()
    except Exception:
        return {"ok": True}

    message = payload.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()
    if chat_id is None:
        return {"ok": True}
    chat_id = str(chat_id)

    if LINK_CODE_RE.match(text):
        user = telegram_service.exchange_link_code(db, text, chat_id)
        if user is not None:
            logger.info("telegram_linked", username=user.username)
            _reply(settings, chat_id, LINK_SUCCESS_REPLY)
        else:
            _reply(settings, chat_id, UNLINKED_REPLY)
        return {"ok": True}

    user = get_user_by_telegram_chat_id(chat_id, db)
    if user is None:
        _reply(settings, chat_id, UNLINKED_REPLY)
    else:
        _reply(settings, chat_id, PLACEHOLDER_REPLY)
    return {"ok": True}


def _forbidden() -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": "Forbidden"})


def _reply(settings, chat_id: str, text: str) -> None:
    if not settings.telegram_bot_token:
        logger.error("telegram_not_configured", hint="Set TELEGRAM_BOT_TOKEN in Railway.")
        return
    telegram_service.send_telegram_message(settings.telegram_bot_token, chat_id, text)
