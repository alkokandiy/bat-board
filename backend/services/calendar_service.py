"""Calendar business logic.

Plain importable functions — no FastAPI request/response objects.
Alfred's tool layer will call these directly later.
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

import models


def list_all_events(
    db: Session,
    current_user: models.BatAccount,
) -> List[models.CalendarEvent]:
    """All of the user's events ordered by start_time — past included.

    Named for what it does. As `list_upcoming_events` it read as a filtered
    list, and Alfred's tool of the same name handed him the account's entire
    history under the word "upcoming". The filtering lives with the caller
    that wants it.
    """
    return db.query(models.CalendarEvent).filter(
        models.CalendarEvent.owner_id == current_user.id
    ).order_by(models.CalendarEvent.start_time).all()


def _naive_utc(dt: datetime) -> datetime:
    """UTC with no tzinfo — how these columns are stored."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def ensure_time_order(start: Optional[datetime], end: Optional[datetime]) -> None:
    """An event cannot end before it begins.

    Nothing checked this: the form, the API and Alfred all accepted an end
    before the start, and the result sorted and rendered as a zero- or
    negative-length block that no screen could draw sensibly. Lives here so
    the web API and Alfred's tools enforce the same rule rather than one of
    them disagreeing.
    """
    # Both sides normalised first. These columns are naive, but the API
    # serialises them with a "Z", so a client that reads an event and sends
    # it back is handing us an AWARE datetime to compare against a naive
    # stored one — which is a TypeError and a 500, not a wrong answer. The
    # rule is about order, and it should not care how the time was spelt.
    if start is not None and end is not None and _naive_utc(end) < _naive_utc(start):
        raise ValueError("An event cannot end before it starts.")


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
    ensure_time_order(start_time, end_time)
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
    """Update an existing event. Returns None if not found.

    Raises ValueError when mission_id is not one of the user's missions.
    """
    event = db.query(models.CalendarEvent).filter(
        models.CalendarEvent.id == event_id,
        models.CalendarEvent.owner_id == current_user.id,
    ).first()
    if event is None:
        return None

    # Against the times the event will HAVE, not only the ones passed in:
    # moving the start past an untouched end is the same mistake.
    ensure_time_order(
        start_time if start_time is not None else event.start_time,
        end_time if end_time is not None else event.end_time,
    )

    if title is not None:
        event.title = title
    if description is not None:
        event.description = description
    if start_time is not None:
        event.start_time = _naive_utc(start_time)
    if end_time is not None:
        event.end_time = _naive_utc(end_time)
    if color is not None:
        event.color = color
    if mission_id is not None:
        mission = db.query(models.BatMission).filter(
            models.BatMission.id == mission_id,
            models.BatMission.owner_id == current_user.id,
        ).first()
        if mission is None:
            raise ValueError("Mission not found")
        event.mission_id = mission_id

    db.commit()
    db.refresh(event)
    return event


def move_event(
    db: Session,
    current_user: models.BatAccount,
    event_id: int,
    new_start: datetime,
) -> Optional[models.CalendarEvent]:
    """Move an event to a new start, keeping how long it lasts.

    A drag is one gesture and means one thing: *this happens later now*,
    not *this is shorter now*. Setting `start_time` alone through
    `update_event` would leave `end_time` where it was, so dragging a
    90-minute meeting two hours later would silently shorten it — or push
    the start past the end, where `ensure_time_order` would reject the
    whole move with a message about time order that says nothing about
    what the person actually did.

    So the end moves by the same delta. An event with no end has no
    duration to keep and simply starts later.

    Here rather than in the drag handler because Alfred must mean the same
    thing by "move my 3pm to 5pm" as the calendar does by a drag.
    """
    event = db.query(models.CalendarEvent).filter(
        models.CalendarEvent.id == event_id,
        models.CalendarEvent.owner_id == current_user.id,
    ).first()
    if event is None:
        return None

    # Normalised before any arithmetic. The column is a naive DateTime, but
    # a client may send an offset ("...T14:00:00+05:00") and subtracting an
    # aware datetime from a naive one is a TypeError, not a wrong answer —
    # the drag would fail with a 500 rather than land in the wrong place.
    # Naive is read as UTC, which is the convention the rest of the
    # services use for these columns.
    start = _naive_utc(new_start)
    if event.end_time is not None:
        event.end_time = _naive_utc(event.end_time) + (start - _naive_utc(event.start_time))
    event.start_time = start

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
