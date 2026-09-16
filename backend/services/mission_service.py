"""Mission business logic.

Plain importable functions — no FastAPI request/response objects.
Alfred's tool layer will call these directly later.
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

import models
from services.common import auto_log_event, calculate_bat_level


def list_missions(
    db: Session,
    current_user: models.BatAccount,
    due_date: Optional[datetime] = None,
) -> List[models.BatMission]:
    q = db.query(models.BatMission).filter(models.BatMission.owner_id == current_user.id)
    if due_date is not None:
        day_start = due_date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start.replace(hour=23, minute=59, second=59, microsecond=999999)
        q = q.filter(models.BatMission.due_date >= day_start, models.BatMission.due_date <= day_end)
    return q.all()


def update_mission(
    db: Session,
    current_user: models.BatAccount,
    mission_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    due_date: Optional[datetime] = None,
    priority: Optional[str] = None,
    tags: Optional[str] = None,
    location: Optional[str] = None,
    notes: Optional[str] = None,
    subtasks: Optional[str] = None,
    is_pinned: Optional[bool] = None,
    is_dismissed: Optional[bool] = None,
) -> Optional[models.BatMission]:
    """Update an existing mission. Returns None if not found."""
    mission = (
        db.query(models.BatMission)
        .filter(
            models.BatMission.id == mission_id,
            models.BatMission.owner_id == current_user.id,
        )
        .first()
    )
    if mission is None:
        return None

    if title is not None:
        mission.title = title
    if description is not None:
        mission.description = description
    if due_date is not None:
        mission.due_date = due_date
    if priority is not None:
        mission.priority = priority
    if tags is not None:
        mission.tags = tags
    if location is not None:
        mission.location = location
    if notes is not None:
        mission.notes = notes
    if subtasks is not None:
        mission.subtasks = subtasks
    if is_pinned is not None:
        mission.is_pinned = is_pinned
    if is_dismissed is not None:
        mission.is_dismissed = is_dismissed

    db.flush()
    db.refresh(mission)
    db.commit()
    return mission


def delete_mission(
    db: Session,
    current_user: models.BatAccount,
    mission_id: int,
) -> Optional[models.BatMission]:
    """Delete a mission. Returns the deleted mission, or None if not found."""
    mission = (
        db.query(models.BatMission)
        .filter(
            models.BatMission.id == mission_id,
            models.BatMission.owner_id == current_user.id,
        )
        .first()
    )
    if mission is None:
        return None
    title = mission.title
    db.delete(mission)
    db.flush()
    auto_log_event(db, current_user.id, "mission_deleted", {
        "mission_id": mission_id,
        "title": title,
    })
    db.commit()
    return mission


def create_mission(
    db: Session,
    current_user: models.BatAccount,
    title: str,
    description: Optional[str] = None,
    due_date: Optional[datetime] = None,
    priority: str = "medium",
    status: str = "pending",
    tags: Optional[str] = None,
    is_pinned: bool = False,
    is_dismissed: bool = False,
    location: Optional[str] = None,
    notes: Optional[str] = None,
    subtasks: Optional[str] = None,
) -> models.BatMission:
    mission = models.BatMission(
        title=title,
        description=description,
        due_date=due_date,
        priority=priority,
        status=status,
        tags=tags,
        is_pinned=is_pinned,
        is_dismissed=is_dismissed,
        location=location,
        notes=notes,
        subtasks=subtasks,
        owner_id=current_user.id,
    )
    db.add(mission)
    db.flush()
    db.refresh(mission)

    auto_log_event(db, current_user.id, "mission_created", {
        "mission_id": mission.id,
        "title": mission.title,
        "priority": mission.priority,
    })
    db.commit()

    return mission


def complete_mission(
    db: Session,
    current_user: models.BatAccount,
    mission_id: int,
) -> Optional[models.BatMission]:
    """Transition a mission to completed, awarding priority-based points.

    Returns None when the mission does not exist or belongs to another user.
    Commits, so it is safe to call standalone (e.g. from Alfred's tools).
    """
    mission = (
        db.query(models.BatMission)
        .filter(
            models.BatMission.id == mission_id,
            models.BatMission.owner_id == current_user.id,
        )
        .first()
    )
    if mission is None:
        return None

    old_status = mission.status
    old_points = current_user.points
    old_level = current_user.bat_level

    mission.status = "completed"
    if old_status != "completed":
        mission.completed_at = datetime.now(timezone.utc)
        reward = 10
        if mission.priority == "high":
            reward = 20
        elif mission.priority == "critical":
            reward = 50
        elif mission.priority == "low":
            reward = 5

        current_user.points += reward
        current_user.bat_level = calculate_bat_level(current_user.points)

        auto_log_event(db, current_user.id, "points_modified", {
            "reason": f"Completed mission '{mission.title}'",
            "points_delta": reward,
            "old_points": old_points,
            "new_points": current_user.points,
            "old_level": old_level,
            "new_level": current_user.bat_level,
        })

    db.flush()
    db.refresh(mission)
    db.refresh(current_user)
    db.commit()
    return mission
