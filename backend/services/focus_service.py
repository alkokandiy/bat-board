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

# Timer visual modes: Normal, Flip Clock, Bat-Signal, Batmobile.
FOCUS_MODES = ("normal", "flip", "signal", "batmobile")

# Sessions shorter than this are discarded on end: not logged, not counted,
# no points, no mission/habit minutes. Keeps the record honest — a glance at
# the timer isn't "focus".
MIN_FOCUS_MINUTES = 5


def _owns(db: Session, model, row_id, current_user: models.BatAccount) -> bool:
    if not row_id:
        return False
    return db.query(model.id).filter(
        model.id == row_id, model.owner_id == current_user.id
    ).first() is not None


def active_focus_session(db: Session, current_user: models.BatAccount) -> Optional[models.BatFocus]:
    """The user's currently-open focus session (not yet ended), if any."""
    return (
        db.query(models.BatFocus)
        .filter(models.BatFocus.owner_id == current_user.id,
                models.BatFocus.end_time.is_(None))
        .order_by(models.BatFocus.start_time.desc())
        .first()
    )


def start_focus_session(
    db: Session,
    current_user: models.BatAccount,
    mission_id: Optional[int] = None,
    habit_id: Optional[int] = None,
    mode: Optional[str] = None,
    planned_minutes: Optional[int] = None,
    work_task_id: Optional[int] = None,
) -> models.BatFocus:
    """Raises ValueError("Mission not found") / ValueError("Habit not found")
    for invalid links (route translates to 404); never returns None.

    `mode` is recorded as given at start; switching modes mid-session does
    not change it. `planned_minutes`, when set, makes this a timed session the
    cron tick auto-ends after that many minutes."""
    if mode is not None and mode not in FOCUS_MODES:
        raise ValueError(f"Invalid focus mode: {mode!r}")
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
    if work_task_id:
        # A work task is not addressable while the corporate track is off; the
        # row may still exist, but as far as the rest of the system is
        # concerned it isn't there.
        from services import work_service
        if not work_service.is_enabled(db, current_user):
            raise ValueError("Work task not found")
        if not _owns(db, models.BatWorkTask, work_task_id, current_user):
            raise ValueError("Work task not found")

    session = models.BatFocus(
        start_time=datetime.now(timezone.utc),
        owner_id=current_user.id,
        mission_id=mission_id,
        habit_id=habit_id,
        mode=mode,
        planned_minutes=planned_minutes,
        work_task_id=work_task_id,
    )
    db.add(session)
    db.flush()
    db.refresh(session)

    auto_log_event(db, current_user.id, "focus_session_started", {
        "session_id": session.id,
        "start_time": session.start_time.isoformat(),
        "mission_id": session.mission_id,
        "habit_id": session.habit_id,
        "mode": session.mode,
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
    Ending an already-ended session is a no-op that returns it unchanged.
    """
    session = db.query(models.BatFocus).filter(
        models.BatFocus.id == session_id,
        models.BatFocus.owner_id == current_user.id
    ).first()

    if not session:
        return None

    # Ending is idempotent: a session that already has an end_time keeps its
    # recorded result. Re-ending used to re-award points and re-add focus
    # minutes on every repeated PUT.
    if session.end_time is not None:
        return session

    now = datetime.now(timezone.utc)
    if end_time is not _UNSET and end_time is not None:
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
        session.end_time = min(max(end_time, session.start_time), now)
    else:
        session.end_time = now

    for field, value in (("soundtrack_metadata", soundtrack_metadata),):
        if value is not _UNSET:
            setattr(session, field, value)
    # Links can be set at end time, but only to the caller's own rows.
    if mission_id is not _UNSET:
        session.mission_id = mission_id if _owns(db, models.BatMission, mission_id, current_user) else None
    if habit_id is not _UNSET:
        session.habit_id = habit_id if _owns(db, models.BatHabit, habit_id, current_user) else None

    # Credited minutes come from the client (it excludes paused time) but can
    # never exceed the wall-clock span of the session, nor go negative —
    # otherwise points could be minted with an arbitrary duration_minutes.
    elapsed = max(0, int((session.end_time - session.start_time).total_seconds() // 60))
    if duration_minutes is not _UNSET and duration_minutes is not None:
        session.duration_minutes = max(0, min(int(duration_minutes), elapsed + 1))
    else:
        session.duration_minutes = elapsed

    # Too short to count — discard entirely: no points, no mission/habit
    # minutes, no stored row. Return a transient copy flagged `discarded` so
    # the caller can tell the user it wasn't logged.
    if session.duration_minutes < MIN_FOCUS_MINUTES:
        result = models.BatFocus(
            id=session.id, start_time=session.start_time, end_time=session.end_time,
            duration_minutes=session.duration_minutes, mission_id=session.mission_id,
            habit_id=session.habit_id, mode=session.mode, owner_id=current_user.id,
        )
        result.discarded = True
        db.delete(session)
        db.commit()
        return result

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
        if session.work_task_id:
            task = db.query(models.BatWorkTask).filter(
                models.BatWorkTask.id == session.work_task_id,
                models.BatWorkTask.owner_id == current_user.id
            ).first()
            if task:
                task.focus_minutes = (task.focus_minutes or 0) + session.duration_minutes

    # Work time is logged but NEVER rewarded: Bat Points measure the person,
    # not the job. A session attached to a work task earns nothing.
    reward = 0 if session.work_task_id else (session.duration_minutes or 0)
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

    session.discarded = False
    return session
