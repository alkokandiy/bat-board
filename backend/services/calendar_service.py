"""Calendar business logic.

Plain importable functions — no FastAPI request/response objects.
Alfred's tool layer will call these directly later.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

import models


def list_upcoming_events(
    db: Session,
    current_user: models.BatAccount,
) -> List[models.CalendarEvent]:
    """All of the user's events ordered by start_time.

    Mirrors the existing route exactly (full ordered list; the "upcoming"
    slicing stays client-side, as today).
    """
    return db.query(models.CalendarEvent).filter(
        models.CalendarEvent.owner_id == current_user.id
    ).order_by(models.CalendarEvent.start_time).all()


def create_event(
    db: Session,
    current_user: models.BatAccount,
    title: str,
    start_time: datetime,
    description: Optional[str] = None,
    end_time: Optional[datetime] = None,
    color: Optional[str] = None,
    mission_id: Optional[int] = None,
) -> Optional[models.CalendarEvent]:
    """Returns None when mission_id refers to an unknown/foreign mission."""
    if mission_id:
        mission = db.query(models.BatMission).filter(
            models.BatMission.id == mission_id,
            models.BatMission.owner_id == current_user.id
        ).first()
        if not mission:
            return None

    event = models.CalendarEvent(
        title=title,
        description=description,
        start_time=start_time,
        end_time=end_time,
        color=color,
        mission_id=mission_id,
        owner_id=current_user.id
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
