"""Sections REST endpoints. Thin handlers only — logic lives in section_service."""

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

import models
from dependencies import get_current_active_user, get_db, limiter
from schemas.sections import (
    SectionCreate, SectionReorder, SectionResponse, SectionUpdate,
)
from services import section_service

router = APIRouter(prefix="/api/sections", tags=["sections"])


def _to_response(row: models.BatSection, counts: Dict[str, int]) -> SectionResponse:
    return SectionResponse(
        id=row.id,
        list_id=row.list_id,
        name=row.name,
        position=row.position,
        created_at=row.created_at,
        open_missions=counts.get(str(row.id), 0),
    )


@router.get("", response_model=List[SectionResponse])
def get_sections(
    list_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    """Every section, or one list's. All of them by default, because the
    client holds one rail and would otherwise ask once per list."""
    counts = section_service.open_counts(db, current_user)
    rows = section_service.list_sections(db, current_user, list_id=list_id)
    return [_to_response(row, counts) for row in rows]


@router.post("", response_model=SectionResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_section(
    request: Request,
    payload: SectionCreate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    try:
        row = section_service.create_section(
            db, current_user, list_id=payload.list_id, name=payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _to_response(row, section_service.open_counts(db, current_user))


@router.put("/{section_id}", response_model=SectionResponse)
@limiter.limit("60/minute")
def rename_section(
    request: Request,
    section_id: int,
    payload: SectionUpdate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    try:
        row = section_service.rename_section(db, current_user, section_id, payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if row is None:
        raise HTTPException(status_code=404, detail="Section not found")
    return _to_response(row, section_service.open_counts(db, current_user))


@router.post("/reorder", response_model=List[SectionResponse])
@limiter.limit("60/minute")
def reorder_sections(
    request: Request,
    payload: SectionReorder,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    rows = section_service.reorder(db, current_user, payload.list_id, payload.ordered_ids)
    counts = section_service.open_counts(db, current_user)
    return [_to_response(row, counts) for row in rows]


@router.delete("/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
def delete_section(
    request: Request,
    section_id: int,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    """The section goes; its missions stay in the list, ungrouped."""
    if not section_service.delete_section(db, current_user, section_id):
        raise HTTPException(status_code=404, detail="Section not found")
    return None
