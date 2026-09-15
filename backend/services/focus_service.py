"""Focus-session business logic.

Plain importable functions — no FastAPI request/response objects.
Alfred's tool layer will call these directly later.

End semantics mirror the original route exactly (wall-clock duration,
mission/habit fan-out, point rewards); the route delegates here.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

import models
from services.common import auto_log_event, calculate_bat_level

_UNSET = object()


def start_focus_session(
    db: Session,
    current_user: models.BatAccount,
    mission_id: Optional[int] = None,
    habit_id: Optional[int] = None,
) -> models.BatFocus:
    """Raises ValueError("Mission not found") / ValueError("Habit not found")
    for invalid links (route translates to 404); never returns None."""
    if mission_id:
        mission = db.query(models.BatMission).filter(
            models.BatMission.id == mission_id,
            models.BatMission.owner_id == current_user.id
        ).first()
        if not mission:
            raise ValueError("Mission not found")
    if habit_id:
        habit = db.query(models.BatHabit).filter(
            models.BatHabit.id == habit_id,
            models.BatHabit.owner_id == current_user.id
        ).first()
        if not habit:
            raise ValueError("Habit not found")

    session = models.BatFocus(
        start_time=datetime.now(timezone.utc),
        owner_id=current_user.id,
        mission_id=mission_id,
        habit_id=habit_id,
    )
    db.add(session)
    db.flush()
    db.refresh(session)

    auto_log_event(db, current_user.id, "focus_session_started", {
        "session_id": session.id,
        "start_time": session.start_time.isoformat(),
        "mission_id": session.mission_id,
        "habit_id": session.habit_id,
    })
    db.commit()

    return session


def end_focus_session(
    db: Session,
    current_user: models.BatAccount,
    session_id: int,
    end_time=_UNSET,
    duration_minutes=_UNSET,
    soundtrack_metadata=_UNSET,
    mission_id=_UNSET,
    habit_id=_UNSET,
) -> Optional[models.BatFocus]:
    """Returns None when the session does not exist or belongs to another user.

    Omitted keyword arguments mean "not provided" (mirrors the route's
    model_fields_set semantics); end_time defaults to now when unset.
    """
    session = db.query(models.BatFocus).filter(
        models.BatFocus.id == session_id,
        models.BatFocus.owner_id == current_user.id
    ).first()

    if not session:
        return None

    if end_time is not _UNSET:
        session.end_time = end_time.replace(tzinfo=None) if end_time else None
    elif not session.end_time:
        session.end_time = datetime.now(timezone.utc)

    provided = {
        "duration_minutes": duration_minutes,
        "soundtrack_metadata": soundtrack_metadata,
        "mission_id": mission_id,
        "habit_id": habit_id,
    }
    for field, value in provided.items():
        if value is not _UNSET:
            setattr(session, field, value)

    if session.duration_minutes is None and session.end_time:
        delta = session.end_time - session.start_time
        session.duration_minutes = int(delta.total_seconds() / 60)

    if session.duration_minutes:
        if session.mission_id:
            mission = db.query(models.BatMission).filter(
                models.BatMission.id == session.mission_id,
                models.BatMission.owner_id == current_user.id
            ).first()
            if mission:
                mission.focus_minutes = (mission.focus_minutes or 0) + session.duration_minutes
                mission.completed_focus_sessions = (mission.completed_focus_sessions or 0) + 1
        if session.habit_id:
            habit = db.query(models.BatHabit).filter(
                models.BatHabit.id == session.habit_id,
                models.BatHabit.owner_id == current_user.id
            ).first()
            if habit:
                habit.focus_minutes = (habit.focus_minutes or 0) + session.duration_minutes

    reward = session.duration_minutes if session.duration_minutes else 0
    current_user.points += reward
    old_level = current_user.bat_level
    current_user.bat_level = calculate_bat_level(current_user.points)

    db.flush()
    db.refresh(session)
    db.refresh(current_user)

    auto_log_event(db, current_user.id, "focus_session_ended", {
        "session_id": session.id,
        "duration_minutes": session.duration_minutes,
        "mission_id": session.mission_id,
        "habit_id": session.habit_id,
        "points_awarded": reward,
        "old_level": old_level,
        "new_level": current_user.bat_level
    })
    db.commit()

    return session
