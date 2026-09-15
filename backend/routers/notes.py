"""Notes REST endpoints. Thin handlers only — business logic lives in services."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

import models
from dependencies import get_current_active_user, get_db, limiter
from schemas.notes import NoteCreate, NoteResponse, NoteUpdate
from services import notes_service
from services.notes_service import VALID_SORTS

router = APIRouter(prefix="/api/notes", tags=["notes"])


@router.get("", response_model=List[NoteResponse])
def list_notes(
    search: Optional[str] = None,
    sort: str = "updated",
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    if sort not in VALID_SORTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid sort. Must be one of: {', '.join(VALID_SORTS)}",
        )
    return notes_service.list_notes(db, current_user, search=search, sort=sort)


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_note(
    request: Request,
    payload: NoteCreate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    return notes_service.create_note(
        db,
        current_user,
        title=payload.title,
        body=payload.body,
        category=payload.category,
        tags=payload.tags,
        is_pinned=payload.is_pinned,
    )


@router.put("/{note_id}", response_model=NoteResponse)
@limiter.limit("30/minute")
def update_note(
    request: Request,
    note_id: int,
    payload: NoteUpdate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    note = notes_service.update_note(
        db,
        current_user,
        note_id,
        title=payload.title,
        body=payload.body,
        category=payload.category,
        tags=payload.tags,
        is_pinned=payload.is_pinned,
    )
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    if not notes_service.delete_note(db, current_user, note_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return None
