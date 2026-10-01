"""Habit business logic.

Plain importable functions — no FastAPI request/response objects.
Alfred's tool layer will call these directly later.
"""

from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

import models
from services.common import auto_log_event, calculate_bat_level


def list_habits(
    db: Session,
    current_user: models.BatAccount,
) -> List[models.BatHabit]:
    return db.query(models.BatHabit).filter(models.BatHabit.owner_id == current_user.id).all()


def create_habit(
    db: Session,
    current_user: models.BatAccount,
    name: str,
    description: Optional[str] = None,
    frequency: str = "daily",
) -> models.BatHabit:
    habit = models.BatHabit(
        name=name,
        description=description,
        frequency=frequency,
        streak=0,
        owner_id=current_user.id,
    )
    db.add(habit)
    db.flush()
    db.refresh(habit)

    auto_log_event(db, current_user.id, "habit_created", {
        "habit_id": habit.id,
        "name": habit.name,
        "frequency": habit.frequency,
    })
    db.commit()

    return habit


def _period_index(frequency: str, day: date) -> int:
    """Monotonic period number, so consecutive periods differ by exactly 1."""
    if frequency == "weekly":
        return (day.toordinal() - 1) // 7  # ordinal 1 is a Monday: buckets are Mon–Sun
    if frequency == "monthly":
        return day.year * 12 + day.month
    return day.toordinal()


def check_in_habit(
    db: Session,
    current_user: models.BatAccount,
    habit_id: int,
) -> Optional[models.BatHabit]:
    """Check in to a habit: streak rollover, points, and log fan-out.

    Idempotent per period (day / ISO week / month, by frequency) — a repeat
    within the same period logs history without re-applying streak/reward.
    The streak continues when the previous check-in was in the immediately
    preceding period. Returns None for unknown/foreign habits.
    """
    habit = db.query(models.BatHabit).filter(
        models.BatHabit.id == habit_id,
        models.BatHabit.owner_id == current_user.id
    ).first()

    if not habit:
        return None

    now = datetime.now(timezone.utc)
    current_period = _period_index(habit.frequency, now.date())
    last_period = (
        _period_index(habit.frequency, habit.last_completed.date())
        if habit.last_completed else None
    )
    is_new_completion = last_period != current_period

    completion = models.HabitCompletionLog(habit_id=habit.id, completed_at=now)
    db.add(completion)

    if is_new_completion:
        if last_period is not None and current_period - last_period == 1:
            habit.streak += 1
        else:
            habit.streak = 1

        habit.last_completed = now

        streak_bonus = min(habit.streak, 10)
        reward = 5 + streak_bonus

        current_user.points += reward
        old_level = current_user.bat_level
        current_user.bat_level = calculate_bat_level(current_user.points)

        auto_log_event(db, current_user.id, "points_modified", {
            "reason": f"Completed habit '{habit.name}' (Streak: {habit.streak})",
            "points_delta": reward,
            "old_points": current_user.points - reward,
            "new_points": current_user.points,
            "old_level": old_level,
            "new_level": current_user.bat_level
        })

        auto_log_event(db, current_user.id, "habit_checkin", {
            "habit_id": habit.id,
            "name": habit.name,
            "streak": habit.streak,
            "points_awarded": reward
        })
    else:
        auto_log_event(db, current_user.id, "habit_completion_history_logged", {
            "habit_id": habit.id,
            "name": habit.name,
            "note": "Logged completion but streak/reward not re-applied for this period"
        })

    db.commit()
    db.refresh(habit)
    db.refresh(current_user)
    return habit


def update_habit(
    db: Session,
    current_user: models.BatAccount,
    habit_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    frequency: Optional[str] = None,
    target_date: Optional[datetime] = None,
) -> Optional[models.BatHabit]:
    """Update an existing habit. Returns None if not found."""
    habit = db.query(models.BatHabit).filter(
        models.BatHabit.id == habit_id,
        models.BatHabit.owner_id == current_user.id,
    ).first()
    if habit is None:
        return None

    if name is not None:
        habit.name = name
    if description is not None:
        habit.description = description
    if frequency is not None:
        habit.frequency = frequency
    if target_date is not None:
        habit.target_date = target_date

    db.flush()
    db.refresh(habit)
    db.commit()
    return habit


def delete_habit(
    db: Session,
    current_user: models.BatAccount,
    habit_id: int,
) -> Optional[models.BatHabit]:
    """Delete a habit. Returns the deleted habit, or None if not found."""
    habit = db.query(models.BatHabit).filter(
        models.BatHabit.id == habit_id,
        models.BatHabit.owner_id == current_user.id,
    ).first()
    if habit is None:
        return None
    name = habit.name
    db.delete(habit)
    db.flush()
    auto_log_event(db, current_user.id, "habit_deleted", {
        "habit_id": habit_id,
        "name": name,
    })
    db.commit()
    return habit
