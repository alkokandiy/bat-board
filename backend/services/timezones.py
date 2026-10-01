"""Per-user timezone helpers.

Timestamps are stored in UTC; anything that depends on "which day is it"
(habit periods, daily stats, Alfred's clock and daily quota) is evaluated
in the account's own IANA timezone. Accounts without one fall back to UTC.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

DEFAULT_TIMEZONE = "UTC"


def validate_timezone(name: str) -> str:
    """Return the canonical name, or raise ValueError for unknown zones."""
    name = (name or "").strip()
    if not name or name not in available_timezones():
        raise ValueError(f"Unknown timezone: {name!r}. Use an IANA name such as 'Asia/Tashkent'.")
    return name


def tz_for(name: Optional[str]) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def user_tz(user) -> ZoneInfo:
    return tz_for(getattr(user, "timezone", None))


def local_now(user) -> datetime:
    return datetime.now(user_tz(user))


def local_today(user) -> date:
    return local_now(user).date()


def local_date(dt: datetime, tz: ZoneInfo) -> date:
    """Calendar date of a stored (UTC) timestamp in the given zone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz).date()


def day_bounds_utc(day: date, tz: ZoneInfo) -> Tuple[datetime, datetime]:
    """[start, end) of a local calendar day, as UTC instants (DST-safe)."""
    start = datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)
    return start, end
