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


def update_event(
    db: Session,
    current_user: models.BatAccount,
    event_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    color: Optional[str] = None,
    mission_id: Optional[int] = None,
) -> Optional[models.CalendarEvent]:
    """Update an existing event. Returns None if not found."""
    event = db.query(models.CalendarEvent).filter(
        models.CalendarEvent.id == event_id,
        models.CalendarEvent.owner_id == current_user.id,
    ).first()
    if event is None:
        return None

    if title is not None:
        event.title = title
    if description is not None:
        event.description = description
    if start_time is not None:
        event.start_time = start_time
    if end_time is not None:
        event.end_time = end_time
    if color is not None:
        event.color = color
    if mission_id is not None:
        event.mission_id = mission_id

    db.commit()
    db.refresh(event)
    return event


def delete_event(
    db: Session,
    current_user: models.BatAccount,
    event_id: int,
) -> Optional[models.CalendarEvent]:
    """Delete an event. Returns the deleted event, or None if not found."""
    event = db.query(models.CalendarEvent).filter(
        models.CalendarEvent.id == event_id,
        models.CalendarEvent.owner_id == current_user.id,
    ).first()
    if event is None:
        return None
    db.delete(event)
    db.commit()
    return event
