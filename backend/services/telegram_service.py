"""Telegram linking + messaging helpers.

Plain importable functions — no FastAPI request/response objects.
Phase 2B will reuse send_telegram_message for Alfred's actual responses.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import httpx
import structlog
from sqlalchemy.orm import Session

import models

logger = structlog.get_logger()

LINK_CODE_TTL = timedelta(minutes=5)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime) -> datetime:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def generate_link_code(
    db: Session,
    current_user: models.BatAccount,
) -> Tuple[str, datetime]:
    """Create a 6-digit linking code for the user. Returns (plain_code, expires_at).

    The plain code is returned ONCE to the browser caller; only its
    SHA-256 hash is stored. Any previous codes for this user are replaced.
    """
    db.query(models.BatTelegramLinkCode).filter(
        models.BatTelegramLinkCode.owner_id == current_user.id
    ).delete()

    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = _utcnow() + LINK_CODE_TTL
    db.add(
        models.BatTelegramLinkCode(
            code_hash=hashlib.sha256(code.encode()).hexdigest(),
            expires_at=expires_at,
            owner_id=current_user.id,
        )
    )
    db.commit()
    return code, expires_at


def exchange_link_code(
    db: Session,
    code: str,
    telegram_chat_id: str,
) -> Optional[models.BatAccount]:
    """Exchange a user-supplied linking code for a linked PAT row.

    On success creates the BatPersonalAccessToken (raw token hashed with
    SHA-256, never stored or logged in plaintext), sets telegram_chat_id,
    deletes the used code, and returns the linked user. Returns None when
    the code is unknown or expired.
    """
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    row = (
        db.query(models.BatTelegramLinkCode)
        .filter(models.BatTelegramLinkCode.code_hash == code_hash)
        .first()
    )
    if row is None:
        return None
    if _as_aware(row.expires_at) <= _utcnow():
        db.delete(row)
        db.commit()
        return None

    user = db.query(models.BatAccount).filter(models.BatAccount.id == row.owner_id).first()
    if user is None or not user.is_active:
        db.delete(row)
        db.commit()
        return None

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    # The raw token is deliberately NOT returned, logged, or stored —
    # the Telegram flow authenticates via webhook secret + chat_id, and
    # the stored hash exists as a clean revocation object for the future.
    db.add(
        models.BatPersonalAccessToken(
            name="Telegram — Alfred",
            token_hash=token_hash,
            telegram_chat_id=telegram_chat_id,
            owner_id=user.id,
        )
    )
    db.delete(row)
    db.commit()
    return user


def unlink_telegram(
    db: Session,
    current_user: models.BatAccount,
) -> bool:
    """Revoke the user's Telegram link. Returns True if one was linked."""
    pat = (
        db.query(models.BatPersonalAccessToken)
        .filter(
            models.BatPersonalAccessToken.owner_id == current_user.id,
            models.BatPersonalAccessToken.revoked.is_(False),
            models.BatPersonalAccessToken.telegram_chat_id.isnot(None),
        )
        .first()
    )
    if pat is None:
        return False
    pat.revoked = True
    pat.telegram_chat_id = None
    db.commit()
    return True


def is_telegram_linked(
    db: Session,
    current_user: models.BatAccount,
) -> bool:
    return (
        db.query(models.BatPersonalAccessToken)
        .filter(
            models.BatPersonalAccessToken.owner_id == current_user.id,
            models.BatPersonalAccessToken.revoked.is_(False),
            models.BatPersonalAccessToken.telegram_chat_id.isnot(None),
        )
        .first()
        is not None
    )


def send_telegram_message(bot_token: str, chat_id: str, text: str, timeout: float = 10.0, reply_markup: dict = None) -> bool:
    """POST a sendMessage to Telegram's Bot API. Returns True on success."""
    try:
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            import json as _json
            payload["reply_markup"] = _json.dumps(reply_markup)
        resp = httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json=payload,
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.error("telegram_send_failed", status_code=resp.status_code)
            return False
        return True
    except Exception as exc:
        logger.error("telegram_send_error", error_type=type(exc).__name__, error=str(exc))
        return False


def answer_callback_query(bot_token: str, callback_query_id: str, text: str = "", timeout: float = 10.0) -> bool:
    """Answer a Telegram callback query to stop the button loading spinner."""
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id, "text": text},
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.error("telegram_answer_callback_failed", status_code=resp.status_code)
            return False
        return True
    except Exception as exc:
        logger.error("telegram_answer_callback_error", error_type=type(exc).__name__, error=str(exc))
        return False
