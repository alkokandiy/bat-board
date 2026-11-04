"""Which days a habit is actually due.

"If I choose every week, it's just guess? Which day of the week?"

It was. `frequency` was the only scheduling field, so "weekly" meant no more
than "one check-in somewhere in a Mon-Sun bucket" — the screen could not say
which day because nothing in the record knew.

These cover the arithmetic in isolation: no database, no clock, because
schedule maths is where off-by-ones live.
"""

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from services import habit_schedule as hs


def _h(frequency="daily", created=date(2026, 11, 2), **kw):
    """A habit-like object. 2 Nov 2026 is a Monday.

    Defaults first, then the overrides on top — passing both to
    SimpleNamespace at once is a duplicate-keyword error.
    """
    fields = {"frequency": frequency, "weekdays": None, "day_of_month": None,
              "interval_days": None,
              "created_at": datetime(created.year, created.month, created.day,
                                     tzinfo=timezone.utc)}
    fields.update(kw)
    return SimpleNamespace(**fields)


MON = date(2026, 11, 2)
TUE = date(2026, 11, 3)
THU = date(2026, 11, 5)
SUN = date(2026, 11, 8)


class TestNothingChangesForExistingHabits:
    """Every row in the database today has all three columns NULL."""

    def test_a_daily_habit_is_due_every_day(self):
        h = _h("daily")
        assert all(hs.is_due_on(h, d) for d in (MON, TUE, THU, SUN))

    def test_a_weekly_habit_with_no_days_is_still_due_any_day(self):
        h = _h("weekly")
        assert all(hs.is_due_on(h, d) for d in (MON, TUE, THU, SUN))

    def test_a_monthly_habit_with_no_date_is_still_due_any_day(self):
        h = _h("monthly")
        assert hs.is_due_on(h, TUE) is True

    def test_an_unscheduled_habit_describes_itself_as_before(self):
        assert hs.describe(_h("weekly")) == "once a week"
        assert hs.describe(_h("monthly")) == "once a month"


class TestSpecificWeekdays:
    def test_it_is_due_only_on_the_days_chosen(self):
        h = _h("weekly", weekdays="0,3")          # Mon + Thu
        assert hs.is_due_on(h, MON) is True
        assert hs.is_due_on(h, THU) is True
        assert hs.is_due_on(h, TUE) is False
        assert hs.is_due_on(h, SUN) is False

    def test_names_are_accepted_as_well_as_numbers(self):
        assert hs.normalize_weekdays("Mon,Thu") == "0,3"
        assert hs.normalize_weekdays(["monday", "THURSDAY"]) == "0,3"
        assert hs.normalize_weekdays("3,0") == "0,3"       # sorted
        assert hs.normalize_weekdays("0,0,3") == "0,3"     # de-duplicated

    def test_nonsense_is_refused(self):
        with pytest.raises(ValueError, match="Unrecognized weekday"):
            hs.normalize_weekdays("Blursday")
        with pytest.raises(ValueError, match="0 \\(Mon\\) to 6"):
            hs.normalize_weekdays("9")

    def test_empty_means_no_particular_day(self):
        assert hs.normalize_weekdays("") is None
        assert hs.normalize_weekdays(None) is None

    def test_it_reads_back_in_words(self):
        assert hs.describe(_h("weekly", weekdays="0,3")) == "every Mon, Thu"


class TestMonthlyByDate:
    def test_it_is_due_on_that_date_only(self):
        h = _h("monthly", day_of_month=1)
        assert hs.is_due_on(h, date(2026, 11, 1)) is True
        assert hs.is_due_on(h, date(2026, 11, 2)) is False
        assert hs.is_due_on(h, date(2026, 12, 1)) is True

    def test_the_31st_still_happens_in_february(self):
        """Clamped to the month's end, or the habit silently skips months."""
        h = _h("monthly", day_of_month=31)
        assert hs.is_due_on(h, date(2027, 2, 28)) is True
        assert hs.is_due_on(h, date(2027, 2, 27)) is False
        assert hs.is_due_on(h, date(2027, 1, 31)) is True

    def test_leap_february_clamps_to_the_29th(self):
        h = _h("monthly", day_of_month=31)
        assert hs.is_due_on(h, date(2028, 2, 29)) is True
        assert hs.is_due_on(h, date(2028, 2, 28)) is False

    def test_it_reads_back_in_words(self):
        assert hs.describe(_h("monthly", day_of_month=1)) == "on the 1st"
        assert hs.describe(_h("monthly", day_of_month=2)) == "on the 2nd"
        assert hs.describe(_h("monthly", day_of_month=3)) == "on the 3rd"
        assert hs.describe(_h("monthly", day_of_month=11)) == "on the 11th"
        assert hs.describe(_h("monthly", day_of_month=22)) == "on the 22nd"


class TestEveryNDays:
    def test_it_counts_from_the_day_it_was_made(self):
        h = _h("interval", created=MON, interval_days=3)
        assert hs.is_due_on(h, MON) is True
        assert hs.is_due_on(h, date(2026, 11, 3)) is False
        assert hs.is_due_on(h, date(2026, 11, 5)) is True
        assert hs.is_due_on(h, date(2026, 11, 8)) is True

    def test_it_is_not_due_before_it_existed(self):
        h = _h("interval", created=MON, interval_days=3)
        assert hs.is_due_on(h, date(2026, 10, 30)) is False

    def test_every_other_day_says_so(self):
        assert hs.describe(_h("interval", interval_days=2)) == "every other day"
        assert hs.describe(_h("interval", interval_days=5)) == "every 5 days"

    def test_an_interval_with_no_number_is_refused(self):
        with pytest.raises(ValueError, match="needs interval_days"):
            hs.validate("interval")

    def test_absurd_intervals_are_refused(self):
        with pytest.raises(ValueError, match="between 1 and"):
            hs.validate("interval", interval_days=0)
        with pytest.raises(ValueError, match="between 1 and"):
            hs.validate("interval", interval_days=10_000)


class TestCountingTheChances:
    def test_a_twice_a_week_habit_had_two_chances_not_fourteen(self):
        """The bug this fixes: "2 of your last 14" when it was two of two."""
        h = _h("weekly", weekdays="0,3")
        # Mon 2 Nov to Sun 8 Nov: one Monday, one Thursday.
        assert hs.opportunities_in(h, MON, SUN) == 2

    def test_a_daily_habit_had_one_chance_a_day(self):
        assert hs.opportunities_in(_h("daily"), MON, SUN) == 7

    def test_a_window_with_no_due_days_still_reports_one(self):
        """Never zero: it is a denominator."""
        h = _h("weekly", weekdays="6")        # Sundays only
        assert hs.opportunities_in(h, MON, THU) == 1

    def test_a_backwards_window_is_empty(self):
        assert hs.due_days_between(_h("daily"), SUN, MON) == []


class TestTheNextOne:
    def test_it_finds_the_following_due_day(self):
        h = _h("weekly", weekdays="0,3")
        assert hs.next_due_after(h, MON) == THU
        assert hs.next_due_after(h, THU) == date(2026, 11, 9)

    def test_a_habit_that_can_never_be_due_returns_nothing(self):
        h = _h("interval", interval_days=None)
        assert hs.next_due_after(h, MON) is None


class TestValidationCleansUpAfterItself:
    def test_switching_frequency_clears_the_other_fields(self):
        """Or stale weekdays come back if it is ever switched again."""
        out = hs.validate("daily", weekdays="0,3", day_of_month=5, interval_days=2)
        assert out == {"weekdays": None, "day_of_month": None, "interval_days": None}

    def test_weekly_keeps_only_its_own_field(self):
        out = hs.validate("weekly", weekdays="Mon,Thu", day_of_month=5)
        assert out == {"weekdays": "0,3", "day_of_month": None, "interval_days": None}

    def test_an_unknown_frequency_is_refused(self):
        with pytest.raises(ValueError, match="must be one of"):
            hs.validate("fortnightly")

    def test_a_day_of_month_out_of_range_is_refused(self):
        with pytest.raises(ValueError, match="between 1 and 31"):
            hs.validate("monthly", day_of_month=0)
