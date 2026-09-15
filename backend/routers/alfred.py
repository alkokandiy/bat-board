"""In-app Alfred chat. Thin handler — the same run_turn() brain as Telegram,
resolved to the JWT user instead of a chat_id. Memory, confirmation gate,
and usage cap are shared automatically (same tables, same user)."""

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from dependencies import get_current_active_user, get_db, limiter
from services import alfred_agent

logger = structlog.get_logger()

router = APIRouter(tags=["alfred"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


@router.post("/api/alfred/chat")
@limiter.limit("20/minute")
async def alfred_chat(
    request: Request,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    try:
        reply = await alfred_agent.run_turn(db, current_user, payload.message)
    except Exception as exc:
        logger.error("alfred_chat_failed", error_type=type(exc).__name__, error=str(exc))
        reply = alfred_agent.SNAG_REPLY
    return {"reply": reply}
