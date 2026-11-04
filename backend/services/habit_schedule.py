"""When a habit is actually due.

Until now a habit had a `frequency` of "daily", "weekly" or "monthly" and
nothing else, so "every week" meant no more than "some single check-in
somewhere in a Monday-to-Sunday bucket". The screen could not say which day,
because nothing in the record knew; a weekly habit therefore showed as still
to keep on all seven days until you ticked it once, and a monthly one for a
whole month. Picking "Every week" in the form was, as the owner put it, a
guess.

This module is the missing half: the rules for which calendar days a habit
is due on, and how many chances it had in a window. Pure functions over a
habit-like object and a date — no database, no clock — because scheduling
arithmetic is where off-by-one errors live and they should be cheap to test.

Supported, each chosen because it is a thing people actually say:

    daily                         every day
    weekly  + weekdays "0,3"      every Monday and Thursday
    weekly  (no weekdays)         once in the week, any day — the old
                                  behaviour, kept so existing habits mean
                                  exactly what they meant before
    monthly + day_of_month 1      the 1st, clamped to the month's last day
    monthly (no day)              once in the month, any day — as before
    interval + interval_days 3    every third day, counted from the start

A habit with nothing set is due every day, which is what "daily" has always
meant and what every row in the database currently is.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from typing import List, Optional

WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_WEEKDAY_NAMES = {name.lower(): i for i, name in enumerate(WEEKDAY_LABELS)}
_WEEKDAY_NAMES.update({
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
})

MAX_INTERVAL_DAYS = 365
# "Twelve times a day" is a timer, not a habit; the cap keeps the streak
# meaning something.
MAX_TIMES_PER_PERIOD = 20


def normalize_weekdays(value) -> Optional[str]:
    """'0,2,4', 'Mon,Wed' or a list -> canonical CSV of 0-6. None/empty -> None.

    None means "no particular day", which is a legitimate weekly habit and
    the one every existing row already is.
    """
    if value is None:
        return None
    items = value if isinstance(value, list) else str(value).split(",")
    nums = set()
    for raw in items:
        tok = str(raw).strip().lower()
        if not tok:
            continue
        if tok.isdigit():
            n = int(tok)
            if not 0 <= n <= 6:
                raise ValueError("Weekday numbers are 0 (Mon) to 6 (Sun).")
            nums.add(n)
        elif tok in _WEEKDAY_NAMES:
            nums.add(_WEEKDAY_NAMES[tok])
        else:
            raise ValueError(f"Unrecognized weekday: {raw!r}.")
    return ",".join(str(n) for n in sorted(nums)) if nums else None


def weekday_list(csv: Optional[str]) -> List[int]:
    return [int(d) for d in (csv or "").split(",") if d.strip().isdigit()]


def weekdays_label(csv: Optional[str]) -> str:
    nums = weekday_list(csv)
    return ", ".join(WEEKDAY_LABELS[n] for n in nums) if nums else ""


def _start_date(habit) -> Optional[date]:
    created = getattr(habit, "created_at", None)
    return created.date() if created else None


def is_explicitly_scheduled(habit) -> bool:
    """Has anyone actually chosen when this happens?

    False for every habit created before migration 029, and for anyone who
    picks "every week" without saying which day. Those keep the old
    any-day-in-the-period behaviour rather than silently becoming something
    stricter.
    """
    frequency = getattr(habit, "frequency", "daily") or "daily"
    if frequency == "weekly":
        return bool(weekday_list(getattr(habit, "weekdays", None)))
    if frequency == "monthly":
        return bool(getattr(habit, "day_of_month", None))
    if frequency == "interval":
        return bool(getattr(habit, "interval_days", None))
    return False


def is_due_on(habit, day: date) -> bool:
    """Is this habit expected on this calendar day?

    Anything not explicitly scheduled is due every day — both because that is
    what "daily" means and because it is what every habit in the database
    currently is, and a migration must not quietly change what they do.
    """
    frequency = getattr(habit, "frequency", "daily") or "daily"

    if frequency == "weekly":
        days = weekday_list(getattr(habit, "weekdays", None))
        # No day chosen: the old "any day in the week" habit.
        return day.weekday() in days if days else True

    if frequency == "monthly":
        dom = getattr(habit, "day_of_month", None)
        if not dom:
            return True
        # The 31st in February is the 28th or 29th, not nothing. A habit set
        # for the last day of the month should happen every month.
        last = monthrange(day.year, day.month)[1]
        return day.day == min(int(dom), last)

    if frequency == "interval":
        every = getattr(habit, "interval_days", None)
        start = _start_date(habit)
        if not every or start is None or day < start:
            return False
        return (day - start).days % int(every) == 0

    return True


def due_days_between(habit, start: date, end: date) -> List[date]:
    """Every day in [start, end] the habit was expected. Inclusive."""
    if end < start:
        return []
    out, cursor = [], start
    while cursor <= end:
        if is_due_on(habit, cursor):
            out.append(cursor)
        cursor += timedelta(days=1)
    return out


def opportunities_in(habit, start: date, end: date) -> int:
    """How many real chances the habit had over a window.

    This is the denominator adherence should use. Counting raw days punished
    a Monday-and-Thursday habit for the five days a week it was never meant
    to happen — "2 of your last 14" when it was really two of two.
    """
    return max(1, len(due_days_between(habit, start, end)))


def next_due_after(habit, day: date, limit_days: int = 400) -> Optional[date]:
    """The first day strictly after `day` that the habit is due.

    Bounded so a misconfigured habit (interval with no start, say) cannot
    spin forever.
    """
    cursor = day + timedelta(days=1)
    for _ in range(limit_days):
        if is_due_on(habit, cursor):
            return cursor
        cursor += timedelta(days=1)
    return None


def describe(habit) -> str:
    """How to say this schedule to a person."""
    frequency = getattr(habit, "frequency", "daily") or "daily"

    if frequency == "weekly":
        label = weekdays_label(getattr(habit, "weekdays", None))
        return f"every {label}" if label else "once a week"

    if frequency == "monthly":
        dom = getattr(habit, "day_of_month", None)
        if not dom:
            return "once a month"
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(
            int(dom) if int(dom) < 20 else int(dom) % 10, "th")
        return f"on the {int(dom)}{suffix}"

    if frequency == "interval":
        every = getattr(habit, "interval_days", None)
        if not every:
            return "on no particular schedule"
        return "every other day" if int(every) == 2 else f"every {int(every)} days"

    return "every day"


def validate(frequency: str, *, weekdays=None, day_of_month=None,
             interval_days=None) -> dict:
    """Check and canonicalise a schedule. Returns the fields to store.

    Anything belonging to another frequency is cleared rather than left
    behind, so switching a habit from weekly to daily cannot leave stale
    weekdays that come back if it is ever switched again.
    """
    out = {"weekdays": None, "day_of_month": None, "interval_days": None}

    if frequency == "weekly":
        out["weekdays"] = normalize_weekdays(weekdays)
    elif frequency == "monthly":
        if day_of_month is not None:
            dom = int(day_of_month)
            if not 1 <= dom <= 31:
                raise ValueError("day_of_month must be between 1 and 31.")
            out["day_of_month"] = dom
    elif frequency == "interval":
        if interval_days is None:
            raise ValueError("An 'every N days' habit needs interval_days.")
        every = int(interval_days)
        if not 1 <= every <= MAX_INTERVAL_DAYS:
            raise ValueError(f"interval_days must be between 1 and {MAX_INTERVAL_DAYS}.")
        out["interval_days"] = every
    elif frequency != "daily":
        raise ValueError(
            "frequency must be one of daily, weekly, monthly, interval; "
            f"got {frequency!r}.")

    return out


# --- Occasions -------------------------------------------------------------
#
# An "occasion" is one chance to do the habit, and it is the unit everything
# else counts in: adherence, the streak and the reward.
#
# Until now two different units were in play at once. Phase 5 moved the
# adherence DENOMINATOR to due days, so a Monday-and-Thursday habit had four
# chances a fortnight — but the NUMERATOR still counted Monday-to-Sunday
# buckets, of which there are only two. The same habit kept perfectly read
# "2 of your last 4", and the Thursday check-in landed in a bucket Monday had
# already filled, so it earned nothing and moved no streak.
#
# One unit, chosen by whether the habit says when it happens:
#
#   schedule given ("Mon and Thu", "the 1st", "every 3 days")
#       → each due calendar day is its own occasion
#   no schedule ("weekly", any day)
#       → the period is the occasion, exactly as before

def occasion_key(habit, day: date) -> int:
    """Which occasion this date belongs to.

    Day ordinals for a scheduled habit, period indices otherwise. The two
    are never compared across habits, so they need not share a space — only
    be stable and ordered for one habit.
    """
    if is_explicitly_scheduled(habit):
        return day.toordinal()
    frequency = getattr(habit, "frequency", "daily") or "daily"
    if frequency == "weekly":
        return (day.toordinal() - 1) // 7   # ordinal 1 is a Monday: Mon–Sun
    if frequency == "monthly":
        return day.year * 12 + day.month
    return day.toordinal()


MAX_LOOKBACK_OCCASIONS = 400


def occasions_missed_between(habit, from_key: int, to_key: int,
                             skipped: frozenset = frozenset(),
                             cap: int = MAX_LOOKBACK_OCCASIONS) -> int:
    """Chances strictly between two occasions that went by untaken.

    Skipped occasions do not count: a rest day the person planned is not a
    day they failed. Capped, so a habit returned to after a year costs one
    bounded loop rather than a scan back to its creation — anything past the
    cap is already far more than a broken run.
    """
    if to_key <= from_key + 1:
        return 0

    if is_explicitly_scheduled(habit):
        missed = 0
        for ordinal in range(from_key + 1, min(to_key, from_key + 1 + cap)):
            day = date.fromordinal(ordinal)
            if is_due_on(habit, day) and ordinal not in skipped:
                missed += 1
                if missed >= cap:
                    break
        return missed

    span = min(to_key - from_key - 1, cap)
    between = range(from_key + 1, from_key + 1 + span)
    return sum(1 for k in between if k not in skipped)


def validate_times(frequency: str, times_per_period, weekdays=None) -> Optional[int]:
    """Check "N times per period". Returns the value to store, or None for 1.

    Refused alongside chosen weekdays, because the two are different answers
    to the same question and together they contradict: "Mon and Thu" already
    says which days and how many, while "3 times a week" deliberately says
    neither. Allowing both would leave the screen to guess which one the
    streak was counting.
    """
    if times_per_period is None:
        return None
    times = int(times_per_period)
    if times < 1:
        raise ValueError("times_per_period must be at least 1.")
    if times == 1:
        return None     # the default; stored as NULL so nothing changes
    if times > MAX_TIMES_PER_PERIOD:
        raise ValueError(
            f"times_per_period must be at most {MAX_TIMES_PER_PERIOD}.")
    if frequency == "weekly" and weekday_list(weekdays):
        raise ValueError(
            "Choose particular days or a number of times a week, not both.")
    if frequency == "weekly" and times > 7:
        raise ValueError("A week has seven days.")
    if frequency == "interval":
        raise ValueError(
            "An 'every N days' habit happens once each time it comes round.")
    return times
