"""Lists REST endpoints. Thin handlers only — logic lives in list_service."""

from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

import models
from dependencies import get_current_active_user, get_db, limiter
from schemas.lists import ListCreate, ListReorder, ListResponse, ListUpdate
from services import list_service

router = APIRouter(prefix="/api/lists", tags=["lists"])


def _to_response(row: models.BatList, counts: Dict[str, int]) -> ListResponse:
    return ListResponse(
        id=row.id,
        name=row.name,
        color=row.color,
        icon=row.icon,
        position=row.position,
        archived=row.archived,
        created_at=row.created_at,
        open_missions=counts.get(str(row.id), 0),
    )


@router.get("", response_model=List[ListResponse])
def get_lists(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    counts = list_service.open_counts(db, current_user)
    rows = list_service.list_lists(db, current_user, include_archived=include_archived)
    return [_to_response(row, counts) for row in rows]


@router.get("/counts", response_model=Dict[str, int])
def get_counts(
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    """Open missions per list, with the Inbox under its sentinel key."""
    return list_service.open_counts(db, current_user)


@router.post("", response_model=ListResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_list(
    request: Request,
    payload: ListCreate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    try:
        row = list_service.create_list(
            db, current_user, name=payload.name, color=payload.color, icon=payload.icon,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _to_response(row, list_service.open_counts(db, current_user))


@router.put("/{list_id}", response_model=ListResponse)
@limiter.limit("60/minute")
def update_list(
    request: Request,
    list_id: int,
    payload: ListUpdate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    # Only the fields actually sent are passed on, so an omitted colour is
    # left alone and an explicit null clears it.
    sent = {f: getattr(payload, f) for f in payload.model_fields_set}
    try:
        row = list_service.update_list(db, current_user, list_id, **sent)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if row is None:
        raise HTTPException(status_code=404, detail="List not found")
    return _to_response(row, list_service.open_counts(db, current_user))


@router.post("/reorder", response_model=List[ListResponse])
@limiter.limit("60/minute")
def reorder_lists(
    request: Request,
    payload: ListReorder,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    rows = list_service.reorder(db, current_user, payload.ordered_ids)
    counts = list_service.open_counts(db, current_user)
    return [_to_response(row, counts) for row in rows]


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
def delete_list(
    request: Request,
    list_id: int,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    """The list goes; its missions are refiled to the Inbox."""
    if not list_service.delete_list(db, current_user, list_id):
        raise HTTPException(status_code=404, detail="List not found")
    return None
