"""Countdowns REST endpoints. Thin handlers only — business logic lives in services."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

import models
from dependencies import get_current_active_user, get_db, limiter
from schemas.countdown import CountdownCreate, CountdownResponse
from services import countdown_service

router = APIRouter(prefix="/api/countdowns", tags=["countdowns"])


def _to_response(countdown: models.BatCountdown) -> CountdownResponse:
    return CountdownResponse(
        id=countdown.id,
        title=countdown.title,
        target_date=countdown.target_date,
        created_at=countdown.created_at,
        days_remaining=countdown_service.days_remaining_for(countdown.target_date),
    )


@router.get("", response_model=List[CountdownResponse])
def list_countdowns(
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    return [_to_response(c) for c in countdown_service.list_countdowns(db, current_user)]


@router.post("", response_model=CountdownResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_countdown(
    request: Request,
    payload: CountdownCreate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    countdown = countdown_service.create_countdown(
        db, current_user, title=payload.title, target_date=payload.target_date
    )
    return _to_response(countdown)


@router.delete("/{countdown_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
def delete_countdown(
    request: Request,
    countdown_id: int,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    if not countdown_service.delete_countdown(db, current_user, countdown_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Countdown not found")
    return None
