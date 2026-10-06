"""Internal cron endpoint for proactive briefings and reminders.

Meant to be called about once a minute by a scheduler outside the app process
(a Railway cron service, an external pinger). It is guarded by a shared secret
compared in constant time, NOT by user auth. It does the firing itself and is
safe to call repeatedly: every due item is sent at most once per local day.

Setup steps for the operator live in docs/ROADMAP.md / README.
"""

import secrets as secrets_lib

import structlog
from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from config import get_settings
from dependencies import get_db
from services import scheduler

logger = structlog.get_logger()

router = APIRouter(prefix="/api/internal", tags=["internal"])


def _secret_ok(provided: str | None) -> bool:
    configured = (get_settings().cron_secret or "").strip()
    if not configured:
        return False  # feature dormant until a secret is configured
    return bool(provided) and secrets_lib.compare_digest(provided, configured)


@router.post("/cron/tick")
async def cron_tick(
    request: Request,
    x_cron_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    configured = (get_settings().cron_secret or "").strip()
    if not configured:
        return JSONResponse(
            {"detail": "Cron is not configured (set CRON_SECRET)."},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if not _secret_ok(x_cron_secret):
        return JSONResponse(
            {"detail": "Invalid or missing cron secret."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    summary = await scheduler.run_tick(db)
    logger.info("cron_tick", **summary)
    return {"ok": True, **summary}
