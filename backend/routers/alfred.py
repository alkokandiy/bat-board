"""In-app Alfred chat with session support.

Thin handler — the same run_turn() brain as Telegram, resolved to the JWT
user instead of a chat_id. Memory, confirmation gate, and usage cap are
shared (same tables, same user). Each surface (web vs Telegram) tracks its
own "currently active" session independently."""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from dependencies import get_current_active_user, get_db, limiter
from services import alfred_agent, provider_config_service


class ProviderKeyRequest(BaseModel):
    provider: str = Field(..., min_length=1, max_length=32)
    model_name: str = Field(..., min_length=1, max_length=128)
    api_key: str = Field(..., min_length=1, max_length=512)

logger = structlog.get_logger()

router = APIRouter(tags=["alfred"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: int


class CreateSessionRequest(BaseModel):
    title: str = "New conversation"


@router.post("/api/alfred/chat")
@limiter.limit("20/minute")
async def alfred_chat(
    request: Request,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    # Verify session ownership
    session = (
        db.query(models.BatAlfredSession)
        .filter_by(id=payload.session_id, owner_id=current_user.id)
        .first()
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    try:
        reply = await alfred_agent.run_turn(db, current_user, payload.message, session_id=payload.session_id)
    except Exception as exc:
        logger.error("alfred_chat_failed", error_type=type(exc).__name__, error=str(exc))
        reply = alfred_agent.SNAG_REPLY
    return {"reply": reply}


@router.get("/api/alfred/sessions")
def list_sessions(
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    sessions = (
        db.query(models.BatAlfredSession)
        .filter_by(owner_id=current_user.id)
        .order_by(models.BatAlfredSession.updated_at.desc())
        .all()
    )
    return [{"id": s.id, "title": s.title, "updated_at": s.updated_at.isoformat()} for s in sessions]


@router.post("/api/alfred/sessions", status_code=status.HTTP_201_CREATED)
def create_session(
    payload: CreateSessionRequest,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    session = alfred_agent.create_session(db, current_user, payload.title)
    return {"id": session.id, "title": session.title}


@router.get("/api/alfred/sessions/{session_id}/messages")
def get_session_messages(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    session = (
        db.query(models.BatAlfredSession)
        .filter_by(id=session_id, owner_id=current_user.id)
        .first()
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    messages = (
        db.query(models.BatAlfredMessage)
        .filter_by(session_id=session_id)
        .order_by(models.BatAlfredMessage.created_at.asc())
        .all()
    )
    return [{"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()} for m in messages]


@router.get("/api/alfred/provider")
def provider_status(
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    """Status only — never the key."""
    return provider_config_service.get_config_status(db, current_user)


@router.post("/api/alfred/provider/test")
@limiter.limit("10/minute")
async def provider_test(
    request: Request,
    payload: ProviderKeyRequest,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    """Validate a key without saving. Returns {ok, message}."""
    ok, message = await provider_config_service.test_config(
        payload.provider, payload.model_name, payload.api_key
    )
    return {"ok": ok, "message": message}


@router.post("/api/alfred/provider")
@limiter.limit("10/minute")
async def provider_save(
    request: Request,
    payload: ProviderKeyRequest,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    """Test first; reject the save when the key doesn't work."""
    ok, message = await provider_config_service.test_config(
        payload.provider, payload.model_name, payload.api_key
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    try:
        row = provider_config_service.save_config(
            db, current_user, payload.provider, payload.model_name, payload.api_key
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"provider": row.provider, "model_name": row.model_name, "configured": True}


@router.delete("/api/alfred/provider")
def provider_delete(
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    provider_config_service.delete_config(db, current_user)
    return {"provider": None, "model_name": None, "configured": False}
