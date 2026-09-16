"""Countdown business logic.

Plain importable functions — no FastAPI request/response objects.
Alfred's tool layer will call these directly later.
"""

import math
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

import models


def days_remaining_for(target_date: datetime, now: Optional[datetime] = None) -> int:
    """Whole days from now until target (floor). Negative when past-due, never crashes."""
    now = now or datetime.now(timezone.utc)
    target = target_date
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    ref = now
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return math.floor((target - ref).total_seconds() / 86400)


def create_countdown(
    db: Session,
    current_user: models.BatAccount,
    title: str,
    target_date: datetime,
) -> models.BatCountdown:
    countdown = models.BatCountdown(
        title=title,
        target_date=target_date,
        owner_id=current_user.id,
    )
    db.add(countdown)
    db.commit()
    db.refresh(countdown)
    return countdown


def list_countdowns(
    db: Session,
    current_user: models.BatAccount,
) -> List[models.BatCountdown]:
    """Soonest target first (how a countdown feature is actually used)."""
    return (
        db.query(models.BatCountdown)
        .filter(models.BatCountdown.owner_id == current_user.id)
        .order_by(models.BatCountdown.target_date.asc())
        .all()
    )


def get_countdown(
    db: Session,
    current_user: models.BatAccount,
    countdown_id: int,
) -> Optional[models.BatCountdown]:
    return (
        db.query(models.BatCountdown)
        .filter(
            models.BatCountdown.id == countdown_id,
            models.BatCountdown.owner_id == current_user.id,
        )
        .first()
    )


def delete_countdown(
    db: Session,
    current_user: models.BatAccount,
    countdown_id: int,
) -> bool:
    countdown = get_countdown(db, current_user, countdown_id)
    if countdown is None:
        return False
    db.delete(countdown)
    db.commit()
    return True


def update_countdown(
    db: Session,
    current_user: models.BatAccount,
    countdown_id: int,
    title: Optional[str] = None,
    target_date: Optional[datetime] = None,
) -> Optional[models.BatCountdown]:
    """Update an existing countdown. Returns None if not found."""
    countdown = get_countdown(db, current_user, countdown_id)
    if countdown is None:
        return None

    if title is not None:
        countdown.title = title
    if target_date is not None:
        countdown.target_date = target_date

    db.commit()
    db.refresh(countdown)
    return countdown
