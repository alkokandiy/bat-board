"""Focus-session business logic.

Plain importable functions — no FastAPI request/response objects.
Alfred's tool layer will call these directly later.

End semantics mirror the original route exactly (wall-clock duration,
mission/habit fan-out, point rewards); the route delegates here.
"""

from datetime import datetime, timedelta, timezone
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

# There is no scientifically correct length for a work session. The famous 25
# minutes came from the inventor's kitchen timer, and no trial has ever
# compared 25 against 50 or 90. Attention does fade, but how fast depends
# entirely on the task and the person — so the only defensible recommendation
# is the person's OWN record. This default is used solely until they have one,
# and is deliberately a plain round number rather than a borrowed myth.
DEFAULT_FOCUS_MINUTES = 30
# Below this many completed sessions, their history is too thin to read.
SUGGESTION_MIN_SESSIONS = 5
SUGGESTION_SAMPLE = 30


def suggested_focus_minutes(db: Session, current_user: models.BatAccount) -> dict:
    """How long to suggest this person works for, and why.

    Returns {"minutes", "basis", "sessions"} where `basis` is "history" once
    there is enough of their own record to read, else "default". The caller is
    expected to be honest about which — telling someone a number is personal
    when it is really a guess is exactly the failure this replaces.
    """
    rows = (
        db.query(models.BatFocus.duration_minutes)
        .filter(models.BatFocus.owner_id == current_user.id,
                models.BatFocus.end_time.isnot(None),
                models.BatFocus.duration_minutes.isnot(None),
                models.BatFocus.duration_minutes >= MIN_FOCUS_MINUTES)
        .order_by(models.BatFocus.start_time.desc())
        .limit(SUGGESTION_SAMPLE)
        .all()
    )
    lengths = sorted(r[0] for r in rows)
    if len(lengths) < SUGGESTION_MIN_SESSIONS:
        return {"minutes": DEFAULT_FOCUS_MINUTES, "basis": "default",
                "sessions": len(lengths)}
    # Median, not mean: one abandoned three-hour session should not drag the
    # suggestion away from what they typically actually do.
    mid = len(lengths) // 2
    median = (lengths[mid] if len(lengths) % 2
              else (lengths[mid - 1] + lengths[mid]) // 2)
    return {"minutes": max(MIN_FOCUS_MINUTES, int(median)), "basis": "history",
            "sessions": len(lengths)}


MAX_BACKFILL_MINUTES = 16 * 60      # a day's work is the ceiling for one entry
MAX_BACKFILL_AGE_DAYS = 60


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _overlapping_session(db: Session, current_user: models.BatAccount,
                         start: datetime, end: datetime):
    """An existing session sharing any of this block's time, or None."""
    naive_start = start.astimezone(timezone.utc).replace(tzinfo=None)
    naive_end = end.astimezone(timezone.utc).replace(tzinfo=None)
    rows = (
        db.query(models.BatFocus)
        .filter(models.BatFocus.owner_id == current_user.id,
                models.BatFocus.end_time.isnot(None),
                models.BatFocus.start_time < naive_end,
                models.BatFocus.end_time > naive_start)
        .order_by(models.BatFocus.start_time.asc())
        .all()
    )
    return rows[0] if rows else None


def log_past_session(db: Session, current_user: models.BatAccount, *,
                     minutes: int, when: Optional[datetime] = None,
                     mission_id: Optional[int] = None,
                     habit_id: Optional[int] = None,
                     work_task_id: Optional[int] = None) -> models.BatFocus:
    """Record focus that already happened.

    Someone who worked for two hours yesterday has a real fact about their
    week, and refusing to record it does not make the board more honest — it
    makes it wrong in the other direction, with every report reading zero. The
    entry is marked `logged_manually` so a measured session and a remembered
    one stay distinguishable.

    No Bat Points are awarded. Points track the person's own missions and
    habits through live sessions; minting them from a typed number would turn
    the ledger into a claim rather than a record.
    """
    minutes = int(minutes)
    if minutes < MIN_FOCUS_MINUTES:
        raise ValueError(f"A session needs at least {MIN_FOCUS_MINUTES} minutes.")
    if minutes > MAX_BACKFILL_MINUTES:
        raise ValueError(
            f"That is more than {MAX_BACKFILL_MINUTES // 60} hours in one entry — "
            "split it across the days it actually happened.")

    now = datetime.now(timezone.utc)
    # No time given means "I have just finished", so the block ends now rather
    # than landing on an arbitrary hour somebody has to correct later.
    if when is None:
        when = now - timedelta(minutes=minutes)
    when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
    ends = when + timedelta(minutes=minutes)
    if when > now + timedelta(minutes=5):
        raise ValueError("That is in the future — focus is recorded after it happens.")
    # The END matters too: starting two hours ago and running for four would
    # record work that has not happened yet, and the report would believe it.
    if ends > now + timedelta(minutes=5):
        over = int((ends - now).total_seconds() // 60)
        raise ValueError(
            f"That block would run {over} minutes into the future. Either it "
            f"started earlier than given, or it is shorter than {minutes} minutes.")
    if when < now - timedelta(days=MAX_BACKFILL_AGE_DAYS):
        raise ValueError(f"That is further back than {MAX_BACKFILL_AGE_DAYS} days.")

    targets = [t for t in (mission_id, habit_id, work_task_id) if t]
    if len(targets) > 1:
        raise ValueError("A session belongs to one thing: a mission, a habit, or a work task.")
    if mission_id and not _owns(db, models.BatMission, mission_id, current_user):
        raise ValueError("Mission not found.")
    if habit_id and not _owns(db, models.BatHabit, habit_id, current_user):
        raise ValueError("Habit not found.")
    if work_task_id and not _owns(db, models.BatWorkTask, work_task_id, current_user):
        raise ValueError("Work task not found.")

    # Nobody focuses on two things at once, so an overlap means one of the two
    # entries is wrong. Accepting both silently inflated the total — logging
    # 2h from 14:00 and 4h from 15:00 reported six hours for five hours of
    # day. Refusing names the clash so it can be corrected rather than buried.
    clash = _overlapping_session(db, current_user, when, ends)
    if clash is not None:
        c_start = _as_utc(clash.start_time)
        c_end = _as_utc(clash.end_time) if clash.end_time else c_start
        raise ValueError(
            f"That overlaps focus already recorded from "
            f"{c_start.strftime('%H:%M')} to {c_end.strftime('%H:%M')} UTC "
            f"({clash.duration_minutes or 0} minutes). Two blocks cannot share "
            f"the same time — move one, shorten it, or say which is correct.")

    session = models.BatFocus(
        owner_id=current_user.id,
        start_time=when.astimezone(timezone.utc).replace(tzinfo=None),
        end_time=(when + timedelta(minutes=minutes)).astimezone(timezone.utc).replace(tzinfo=None),
        duration_minutes=minutes,
        logged_manually=True,
        mission_id=mission_id or None,
        habit_id=habit_id or None,
        work_task_id=work_task_id or None,
    )
    db.add(session)

    # Keep the target's own running total in step, exactly as a live session does.
    if mission_id:
        m = db.get(models.BatMission, mission_id)
        if m is not None:
            m.focus_minutes = (m.focus_minutes or 0) + minutes
    if habit_id:
        h = db.get(models.BatHabit, habit_id)
        if h is not None:
            h.focus_minutes = (h.focus_minutes or 0) + minutes

    db.commit()
    db.refresh(session)
    return session


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
