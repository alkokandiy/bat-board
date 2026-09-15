"""Shared FastAPI dependencies for bat-board routers.

Canonical location for cross-domain dependencies. Re-exports the auth
and database dependencies so routers import from here instead of
reaching into auth.py / database.py directly.
"""

from datetime import datetime, timezone

from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

import models
from auth import get_current_active_user, get_current_user  # noqa: F401
from database import get_db  # noqa: F401

# Single shared Limiter instance. main.py wires this exact object into
# app.state.limiter — slowapi enforces limits via request.app.state.limiter,
# so routers MUST use this instance (not their own) or limits silently no-op.
limiter = Limiter(key_func=get_remote_address)


def get_user_by_telegram_chat_id(chat_id: str, db: Session) -> models.BatAccount | None:
    """Resolve "which bat-board user sent this Telegram message".

    Looks up the active (not revoked) PAT by telegram_chat_id. The security
    boundary is the webhook secret proving Telegram origin plus Telegram's
    own unforgeable chat_id — no per-request bearer validation needed.
    Updates last_used_at on every successful resolution.
    """
    pat = (
        db.query(models.BatPersonalAccessToken)
        .filter(
            models.BatPersonalAccessToken.telegram_chat_id == chat_id,
            models.BatPersonalAccessToken.revoked.is_(False),
        )
        .first()
    )
    if pat is None:
        return None
    user = db.query(models.BatAccount).filter(models.BatAccount.id == pat.owner_id).first()
    if user is None or not user.is_active:
        return None
    pat.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return user
