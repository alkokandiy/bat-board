"""Habit business logic.

Plain importable functions — no FastAPI request/response objects.
Alfred's tool layer will call these directly later.
"""

from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

import models
from services import habit_schedule
from services.common import auto_log_event, calculate_bat_level
from services.timezones import local_date, user_tz


def list_habits(
    db: Session,
    current_user: models.BatAccount,
) -> List[models.BatHabit]:
    habits = db.query(models.BatHabit).filter(models.BatHabit.owner_id == current_user.id).all()
    return attach_adherence(db, current_user, habits)


def create_habit(
    db: Session,
    current_user: models.BatAccount,
    name: str,
    description: Optional[str] = None,
    frequency: str = "daily",
    cue: Optional[str] = None,
    minimum_viable: Optional[str] = None,
    weekdays=None,
    day_of_month: Optional[int] = None,
    interval_days: Optional[int] = None,
    times_per_period: Optional[int] = None,
) -> models.BatHabit:
    schedule = habit_schedule.validate(
        frequency, weekdays=weekdays, day_of_month=day_of_month,
        interval_days=interval_days)
    schedule["times_per_period"] = habit_schedule.validate_times(
        frequency, times_per_period, weekdays=schedule.get("weekdays"))
    habit = models.BatHabit(
        name=name,
        description=description,
        frequency=frequency,
        cue=(cue or "").strip() or None,
        minimum_viable=(minimum_viable or "").strip() or None,
        **schedule,
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
    """Monotonic period number, so consecutive periods differ by exactly 1.

    Kept for habits with no stated schedule. Anything that needs to know
    which OCCASION a date belongs to should ask habit_schedule.occasion_key,
    which is the same thing for these and the due day itself for a habit
    that says when it happens.
    """
    if frequency == "weekly":
        return (day.toordinal() - 1) // 7  # ordinal 1 is a Monday: buckets are Mon–Sun
    if frequency == "monthly":
        return day.year * 12 + day.month
    return day.toordinal()


def target_of(habit) -> int:
    """How many check-ins make one occasion count as kept."""
    return max(1, int(getattr(habit, "times_per_period", None) or 1))


def _skip_keys(db: Session, current_user: models.BatAccount, habit,
               tz) -> frozenset:
    """The occasions this habit was deliberately rested, as occasion keys.

    A rest the person chose is not a day they failed, so these leave the
    denominator rather than entering it as a miss — and the run steps over
    them instead of breaking on them.
    """
    rows = (
        db.query(models.BatHabitSkip.local_date)
        .filter(models.BatHabitSkip.habit_id == habit.id,
                models.BatHabitSkip.owner_id == current_user.id)
        .all()
    )
    return _keys_from_skip_rows(habit, [r[0] for r in rows])


def _keys_from_skip_rows(habit, iso_days) -> frozenset:
    keys = set()
    for iso in iso_days:
        try:
            keys.add(habit_schedule.occasion_key(habit, date.fromisoformat(iso)))
        except (TypeError, ValueError):
            continue
    return frozenset(keys)


ADHERENCE_WINDOW_DAYS = 14

# What one kept occasion is worth. Flat, on purpose.
#
# It used to be 5 + min(recent adherence, 10), which was itself a fix for a
# worse thing — a reward scaled to the consecutive streak, so one missed day
# cost the count AND collapsed the earning rate. Scaling by adherence stopped
# that double punishment, but it kept the premise: that the number of points
# should argue with you about how you are doing.
#
# It should not. The adherence figure already says how it is going, in words,
# on the screen; making the points say it again turned a record into a second
# opinion. Flat is honest and legible — a check-in is a check-in — and it
# removes the last reason for the reward to care about the streak.
#
# 10 is the midpoint of the old 5-15 range and the default mission reward, so
# nobody's level pace moves noticeably in either direction.
HABIT_REWARD = 10

# One missed period inside a run is forgiven. A second is the run genuinely
# ending, and pretending otherwise would make the number mean nothing.
GRACE_PER_RUN = 1
# ...and only for a habit that is actually being kept. A habit done twice
# ever has no run worth protecting, and protecting it would turn the count
# into a participation trophy.
GRACE_MIN_ADHERENCE = 0.5


def recent_adherence(db: Session, current_user: models.BatAccount,
                     habit: models.BatHabit, days: int = ADHERENCE_WINDOW_DAYS) -> dict:
    """How often this habit has actually happened lately.

    Returns {"done", "window", "rate"}. This — not the consecutive streak — is
    the honest headline measure: a run of 20 broken once is not worse than a run
    of 3, and "5 of your last 7" survives a missed Tuesday where a chain does
    not. Counted in the user's own days, so a late-night check-in lands on the
    day they think it did.
    """
    tz = user_tz(current_user)
    today = local_date(datetime.now(timezone.utc), tz)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(models.HabitCompletionLog.completed_at)
        .filter(models.HabitCompletionLog.habit_id == habit.id,
                models.HabitCompletionLog.completed_at >= since.replace(tzinfo=None))
        .all()
    )
    skipped = _skip_keys(db, current_user, habit, tz)
    counts = _counts_by_occasion(habit, [r[0] for r in rows], tz)
    done, window = _met_and_window(habit, counts, skipped, today, days)
    return {"done": done, "window": window, "rate": round(done / window, 2)}


def _counts_by_occasion(habit, completed_ats, tz) -> dict:
    """How many check-ins landed in each occasion."""
    counts: dict = {}
    for completed_at in completed_ats:
        if not completed_at:
            continue
        key = habit_schedule.occasion_key(habit, local_date(completed_at, tz))
        counts[key] = counts.get(key, 0) + 1
    return counts


def _met_and_window(habit, counts: dict, skipped: frozenset,
                    today: date, days: int) -> tuple:
    """Occasions kept, out of occasions that counted.

    Both sides are in the same unit, which they were not: the denominator
    moved to due days while the numerator stayed on Monday-to-Sunday
    buckets, so a Monday-and-Thursday habit kept perfectly read "2 of your
    last 4". An occasion is kept once its target is reached, so "three times
    a week" is one kept week, not three.
    """
    target = target_of(habit)
    met = sum(1 for key, n in counts.items()
              if n >= target and key not in skipped)
    window = _window_for(habit, today, days)
    # A rest the person chose was never a chance they had.
    window = max(1, window - len([k for k in skipped if _within_window(
        habit, k, today, days)]))
    return min(met, window), window


def _within_window(habit, key: int, today: date, days: int) -> bool:
    first = habit_schedule.occasion_key(habit, today - timedelta(days=days - 1))
    return first <= key <= habit_schedule.occasion_key(habit, today)


def attach_adherence(db: Session, current_user: models.BatAccount,
                     habits: List[models.BatHabit],
                     days: int = ADHERENCE_WINDOW_DAYS) -> List[models.BatHabit]:
    """Hang "done of window" on each habit so the API can report it.

    `recent_adherence` is the honest headline measure, but it only ever
    reached the user through a check-in response — so the board could show the
    consecutive streak and nothing else, which is the one number the evidence
    says not to lead with. One query for the whole list, because somebody with
    forty habits should not pay forty round trips for it.

    These are plain attributes, not columns, so they must be set after the last
    commit: an expire-on-commit wipes the instance dict.
    """
    if not habits:
        return habits

    tz = user_tz(current_user)
    now = datetime.now(timezone.utc)
    today = local_date(now, tz)
    since = now - timedelta(days=days)
    ids = [h.id for h in habits]

    done_rows = (
        db.query(models.HabitCompletionLog.habit_id,
                 models.HabitCompletionLog.completed_at)
        .filter(models.HabitCompletionLog.habit_id.in_(ids),
                models.HabitCompletionLog.completed_at >= since.replace(tzinfo=None))
        .all()
    )
    # Not date-filtered: a rest day is a handful of rows per habit, and
    # filtering ISO strings by range in SQL is a worse trade than the read.
    skip_rows = (
        db.query(models.BatHabitSkip.habit_id, models.BatHabitSkip.local_date)
        .filter(models.BatHabitSkip.habit_id.in_(ids),
                models.BatHabitSkip.owner_id == current_user.id)
        .all()
    )
    completions: dict = {i: [] for i in ids}
    for habit_id, completed_at in done_rows:
        completions[habit_id].append(completed_at)
    skips: dict = {i: [] for i in ids}
    for habit_id, iso in skip_rows:
        skips[habit_id].append(iso)

    # Minutes focused on each habit IN THE CURRENT OCCASION. The lifetime
    # total answers "how much have I ever put into this", which is not the
    # question in front of someone deciding whether today is done. It also
    # never went down, so the number grew for ever and meant less each day.
    focus_rows = (
        db.query(models.BatFocus.habit_id,
                 models.BatFocus.start_time,
                 models.BatFocus.duration_minutes)
        .filter(models.BatFocus.habit_id.in_(ids),
                models.BatFocus.owner_id == current_user.id,
                models.BatFocus.end_time.isnot(None),
                models.BatFocus.start_time >= since.replace(tzinfo=None))
        .all()
    )
    focus_by_habit: dict = {i: [] for i in ids}
    for habit_id, start_time, minutes in focus_rows:
        if start_time and minutes:
            focus_by_habit[habit_id].append((start_time, minutes))

    today_iso = today.isoformat()
    for habit in habits:
        counts = _counts_by_occasion(habit, completions[habit.id], tz)
        skipped = _keys_from_skip_rows(habit, skips[habit.id])
        done, window = _met_and_window(habit, counts, skipped, today, days)
        habit.adherence_done = done
        habit.adherence_window = window
        # Computed here so the API and the screen never re-derive the
        # schedule and disagree with the service about it.
        habit.due_today = habit_schedule.is_due_on(habit, today)
        habit.schedule_label = habit_schedule.describe(habit)
        habit.times_target = target_of(habit)
        habit.done_this_period = counts.get(
            habit_schedule.occasion_key(habit, today), 0)
        habit.resting_today = today_iso in skips[habit.id]
        this_occasion = habit_schedule.occasion_key(habit, today)
        habit.focus_minutes_period = sum(
            minutes for start_time, minutes in focus_by_habit[habit.id]
            if habit_schedule.occasion_key(habit, local_date(start_time, tz)) == this_occasion
        )
    return habits



def _window_for(habit, today, days: int) -> int:
    """How many chances this habit genuinely had over the last `days`.

    Raw day counting punished a habit for the days it was never meant to
    happen: a Monday-and-Thursday habit kept perfectly read as "2 of your
    last 14" instead of two of two. For a habit with no explicit schedule
    this falls back to the old period arithmetic, so nothing that exists
    today changes meaning.
    """
    if habit_schedule.is_explicitly_scheduled(habit):
        start = today - timedelta(days=days - 1)
        return habit_schedule.opportunities_in(habit, start, today)
    return max(1, _periods_in(habit.frequency, days))


def _periods_in(frequency: str, days: int) -> int:
    """How many opportunities a habit of this frequency had in `days` days."""
    if frequency == "weekly":
        return max(1, days // 7)
    if frequency == "monthly":
        return max(1, days // 30)
    return days


def check_in_habit(
    db: Session,
    current_user: models.BatAccount,
    habit_id: int,
) -> Optional[models.BatHabit]:
    """Check in to a habit: streak rollover, points, and log fan-out.

    Idempotent per period (day / ISO week / month by frequency, in the
    user's timezone) — a repeat within the same period logs history
    without re-applying streak/reward.
    The streak continues when the previous check-in was in the immediately
    preceding period. Returns None for unknown/foreign habits.
    """
    habit = db.query(models.BatHabit).filter(
        models.BatHabit.id == habit_id,
        models.BatHabit.owner_id == current_user.id
    ).first()

    if not habit:
        return None

    # Occasions are the user's local days/weeks/months, not UTC ones: in
    # Tashkent a 01:00 check-in used to count toward the previous day.
    now = datetime.now(timezone.utc)
    tz = user_tz(current_user)
    today = local_date(now, tz)
    current_period = habit_schedule.occasion_key(habit, today)
    target = target_of(habit)

    # How far along this occasion already is. With a target above one the
    # first two of three check-ins in a week each count and each earn; only
    # the third makes the week kept.
    done_before = (
        db.query(models.HabitCompletionLog.completed_at)
        .filter(models.HabitCompletionLog.habit_id == habit.id,
                models.HabitCompletionLog.completed_at
                >= (now - timedelta(days=40)).replace(tzinfo=None))
        .all()
    )
    already = _counts_by_occasion(
        habit, [r[0] for r in done_before], tz).get(current_period, 0)

    completion = models.HabitCompletionLog(habit_id=habit.id, completed_at=now)
    db.add(completion)

    done_now = already + 1
    is_new_completion = done_now <= target

    if is_new_completion:
        used_grace = False
        if done_now == target:
            # The occasion is kept. Only now does the run move.
            last_met = habit.last_met_period
            if last_met is None and habit.last_completed:
                # Nothing recorded it before this existed, and after a
                # schedule change the key means something new — so the last
                # thing they did stands as their last kept occasion.
                last_met = habit_schedule.occasion_key(
                    habit, local_date(habit.last_completed, tz))

            if last_met is None or last_met >= current_period:
                missed = 0 if last_met is not None else None
            else:
                missed = habit_schedule.occasions_missed_between(
                    habit, last_met, current_period,
                    _skip_keys(db, current_user, habit, tz))

            if missed is None:
                habit.streak = 1           # the first one ever
                habit.grace_used_in_run = 0
            elif missed == 0:
                habit.streak += 1
                # A clean run: the allowance is whole again for the next gap.
                habit.grace_used_in_run = 0
            elif (missed == 1
                  and (habit.grace_used_in_run or 0) < GRACE_PER_RUN
                  and recent_adherence(db, current_user, habit)["rate"] >= GRACE_MIN_ADHERENCE):
                # Exactly one occasion missed, by somebody who is otherwise
                # keeping this. The run survives and the allowance is spent.
                habit.streak += 1
                habit.grace_used_in_run = (habit.grace_used_in_run or 0) + 1
                used_grace = True
            else:
                habit.streak = 1
                habit.grace_used_in_run = 0

            habit.last_met_period = current_period
            # The run can break; the best run never does. A miss should cost
            # the current count, not the achievement behind it.
            if habit.streak > (habit.best_streak or 0):
                habit.best_streak = habit.streak

        habit.last_completed = now

        # The session is autoflush=False, so until now the check-in just
        # made was invisible to every query below it, and the adherence
        # written into the log read one short — as though today had not
        # happened. Flushed HERE and not earlier on purpose: the grace
        # decision above asks whether the habit was being kept BEFORE
        # today, and counting the check-in being made right now as evidence
        # for forgiving the gap it follows would be circular.
        db.flush()

        # A kept occasion is worth the same whatever kind of week it has
        # been. See HABIT_REWARD. The adherence figure is still read, but
        # only to SAY how it is going in the log — never to price it.
        adherence = recent_adherence(db, current_user, habit)
        reward = HABIT_REWARD

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
            "grace_used": used_grace,
            "best_streak": habit.best_streak,
            "adherence": f"{adherence['done']} of the last {adherence['window']}",
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
    # After the commit: the refresh above would have cleared it.
    return attach_adherence(db, current_user, [habit])[0]


def update_habit(
    db: Session,
    current_user: models.BatAccount,
    habit_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    frequency: Optional[str] = None,
    target_date: Optional[datetime] = None,
    cue: Optional[str] = None,
    minimum_viable: Optional[str] = None,
    weekdays=None,
    day_of_month: Optional[int] = None,
    interval_days: Optional[int] = None,
    times_per_period: Optional[int] = None,
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
    if cue is not None:
        # "" clears the cue rather than storing an empty string.
        habit.cue = cue.strip() or None
    if minimum_viable is not None:
        habit.minimum_viable = minimum_viable.strip() or None
    if any(v is not None for v in (frequency, weekdays, day_of_month,
                                   interval_days, times_per_period)):
        # Validated against the frequency the habit will HAVE, and applied as
        # a set: switching weekly -> daily must not leave weekdays behind.
        fields = habit_schedule.validate(
            frequency or habit.frequency,
            weekdays=weekdays if weekdays is not None else habit.weekdays,
            day_of_month=day_of_month if day_of_month is not None else habit.day_of_month,
            interval_days=interval_days if interval_days is not None else habit.interval_days,
        )
        fields["times_per_period"] = habit_schedule.validate_times(
            frequency or habit.frequency,
            times_per_period if times_per_period is not None else habit.times_per_period,
            weekdays=fields.get("weekdays"),
        )
        for field, value in fields.items():
            setattr(habit, field, value)
        # The occasion key means something different under a new schedule, so
        # a stored one would be comparing days against week numbers. Cleared
        # rather than converted: the next check-in derives it from
        # last_completed, which is the same calendar fact read the new way.
        habit.last_met_period = None
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


# --- Planned rest ----------------------------------------------------------

def _owned_habit(db: Session, current_user: models.BatAccount, habit_id: int):
    return (
        db.query(models.BatHabit)
        .filter(models.BatHabit.id == habit_id,
                models.BatHabit.owner_id == current_user.id)
        .first()
    )


def _resolve_day(current_user: models.BatAccount, on: Optional[str]) -> date:
    """The local day a rest applies to. Their day, never UTC's."""
    if not on:
        return local_date(datetime.now(timezone.utc), user_tz(current_user))
    try:
        return date.fromisoformat(str(on))
    except ValueError:
        raise ValueError("A date must look like 2026-11-04.")


def skip_habit(db: Session, current_user: models.BatAccount, habit_id: int,
               on: Optional[str] = None, note: Optional[str] = None) -> Optional[dict]:
    """Rest this habit for a day, on purpose.

    Resting and failing used to be the same event — the occasion counted
    against adherence and broke the run either way, so the only way to
    protect a run was to not need the rest. Saying so takes the occasion out
    of the denominator and lets the run step over it.

    Idempotent: resting twice is resting once, which matters because the tap
    and the Alfred tool reach the same row.
    """
    habit = _owned_habit(db, current_user, habit_id)
    if habit is None:
        return None
    day = _resolve_day(current_user, on)
    iso = day.isoformat()

    existing = (
        db.query(models.BatHabitSkip)
        .filter(models.BatHabitSkip.habit_id == habit.id,
                models.BatHabitSkip.local_date == iso)
        .first()
    )
    if existing is None:
        db.add(models.BatHabitSkip(
            habit_id=habit.id, owner_id=current_user.id, local_date=iso,
            note=(note or "").strip() or None))
        auto_log_event(db, current_user.id, "habit_rest_day", {
            "habit_id": habit.id, "name": habit.name, "date": iso,
            "note": (note or "").strip() or None,
        })
        db.commit()
    elif note:
        existing.note = note.strip() or None
        db.commit()

    return {"habit_id": habit.id, "name": habit.name, "date": iso,
            "resting": True}


def unskip_habit(db: Session, current_user: models.BatAccount, habit_id: int,
                 on: Optional[str] = None) -> Optional[dict]:
    """Take back a rest day. The occasion counts again."""
    habit = _owned_habit(db, current_user, habit_id)
    if habit is None:
        return None
    iso = _resolve_day(current_user, on).isoformat()
    removed = (
        db.query(models.BatHabitSkip)
        .filter(models.BatHabitSkip.habit_id == habit.id,
                models.BatHabitSkip.owner_id == current_user.id,
                models.BatHabitSkip.local_date == iso)
        .delete()
    )
    if removed:
        auto_log_event(db, current_user.id, "habit_rest_day_cleared", {
            "habit_id": habit.id, "name": habit.name, "date": iso,
        })
    db.commit()
    return {"habit_id": habit.id, "name": habit.name, "date": iso,
            "resting": False, "was_resting": bool(removed)}


def rest_days(db: Session, current_user: models.BatAccount, habit_id: int,
              limit: int = 60) -> Optional[List[dict]]:
    habit = _owned_habit(db, current_user, habit_id)
    if habit is None:
        return None
    rows = (
        db.query(models.BatHabitSkip)
        .filter(models.BatHabitSkip.habit_id == habit.id,
                models.BatHabitSkip.owner_id == current_user.id)
        .order_by(models.BatHabitSkip.local_date.desc())
        .limit(limit)
        .all()
    )
    return [{"date": r.local_date, "note": r.note} for r in rows]
