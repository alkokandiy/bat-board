"""Telegram linking + messaging helpers.

Plain importable functions — no FastAPI request/response objects.
Phase 2B will reuse send_telegram_message for Alfred's actual responses.
"""

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import httpx
import structlog
from sqlalchemy.orm import Session

import models

logger = structlog.get_logger()

LINK_CODE_TTL = timedelta(minutes=5)
# Brute-force guard for 6-digit codes: failed attempts per chat per window.
LINK_MAX_FAILURES = 5
LINK_FAILURE_WINDOW = timedelta(minutes=10)


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

    # One active link per chat: a chat that is already linked (to this or
    # another account) used to hit the unique telegram_chat_id constraint
    # and crash the exchange. Re-linking moves the chat to the new account.
    for previous in (
        db.query(models.BatPersonalAccessToken)
        .filter(models.BatPersonalAccessToken.telegram_chat_id == telegram_chat_id)
        .all()
    ):
        previous.revoked = True
        previous.telegram_chat_id = None
    db.flush()

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


def link_attempts_blocked(db: Session, telegram_chat_id: str) -> bool:
    """True while this chat has used up its failed-attempt budget."""
    row = db.get(models.BatTelegramLinkAttempt, telegram_chat_id)
    if row is None or _as_aware(row.window_started_at) + LINK_FAILURE_WINDOW <= _utcnow():
        return False
    return row.failures >= LINK_MAX_FAILURES


def record_link_failure(db: Session, telegram_chat_id: str) -> None:
    row = db.get(models.BatTelegramLinkAttempt, telegram_chat_id)
    now = _utcnow()
    if row is None:
        db.add(models.BatTelegramLinkAttempt(chat_id=telegram_chat_id, failures=1, window_started_at=now))
    elif _as_aware(row.window_started_at) + LINK_FAILURE_WINDOW <= now:
        row.failures = 1
        row.window_started_at = now
    else:
        row.failures += 1
    db.commit()


def clear_link_failures(db: Session, telegram_chat_id: str) -> None:
    row = db.get(models.BatTelegramLinkAttempt, telegram_chat_id)
    if row is not None:
        db.delete(row)
        db.commit()


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


TELEGRAM_MAX_MESSAGE_CHARS = 4096


def _split_message(text: str, limit: int = TELEGRAM_MAX_MESSAGE_CHARS) -> List[str]:
    """Split text into Telegram-sized chunks, preferring line/word boundaries."""
    text = text or ""
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    chunks.append(text)
    return [c for c in chunks if c] or [""]


def send_telegram_message(bot_token: str, chat_id: str, text: str, timeout: float = 10.0, reply_markup: dict = None) -> bool:
    """POST a sendMessage to Telegram's Bot API. Returns True on success.

    Text over Telegram's 4096-character limit is sent as several messages
    (it used to be rejected with a 400 and the reply silently lost); the
    reply markup goes on the last one.
    """
    chunks = _split_message(text)
    ok = True
    for i, chunk in enumerate(chunks):
        markup = reply_markup if i == len(chunks) - 1 else None
        ok = _send_one(bot_token, chat_id, chunk, timeout, markup) and ok
    return ok


def _send_one(bot_token: str, chat_id: str, text: str, timeout: float, reply_markup: Optional[dict]) -> bool:
    try:
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup)
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


def get_file_path(bot_token: str, file_id: str, timeout: float = 10.0) -> Optional[str]:
    """Resolve a Telegram file_id to its download path via getFile. None on failure."""
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{bot_token}/getFile",
            json={"file_id": file_id},
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.warning("telegram_getfile_failed", status_code=resp.status_code)
            return None
        return (resp.json().get("result") or {}).get("file_path")
    except Exception as exc:
        logger.warning("telegram_getfile_error", error_type=type(exc).__name__, error=str(exc))
        return None


def download_file(bot_token: str, file_path: str, max_bytes: int, timeout: float = 20.0) -> Optional[bytes]:
    """Download a Telegram file by path, streamed. None on failure or if it
    exceeds max_bytes (so a hostile/huge file can't exhaust memory)."""
    try:
        url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        with httpx.stream("GET", url, timeout=timeout) as resp:
            if resp.status_code != 200:
                logger.warning("telegram_download_failed", status_code=resp.status_code)
                return None
            buf = bytearray()
            for chunk in resp.iter_bytes():
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    logger.warning("telegram_download_too_large")
                    return None
            return bytes(buf)
    except Exception as exc:
        logger.warning("telegram_download_error", error_type=type(exc).__name__, error=str(exc))
        return None


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


def delete_telegram_message(bot_token: str, chat_id: str, message_id: int, timeout: float = 10.0) -> bool:
    """Delete a message via deleteMessage. False on any failure — log, never raise."""
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{bot_token}/deleteMessage",
            json={"chat_id": chat_id, "message_id": message_id},
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.warning("telegram_delete_failed", status_code=resp.status_code, body=resp.text[:200])
            return False
        return True
    except Exception as exc:
        logger.warning("telegram_delete_error", error_type=type(exc).__name__, error=str(exc))
        return False
