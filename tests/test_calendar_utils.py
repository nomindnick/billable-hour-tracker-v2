"""
Unit tests for calendar utilities.

Tests the workday calculation functions in app/services/calendar_utils.py.
"""

import datetime
import pytest

from app.services.calendar_utils import (
    is_workday,
    get_workdays_in_month,
    get_workdays_in_range,
    get_remaining_workdays_in_month,
    get_weekend_days_in_range,
)


class TestIsWorkday:
    """Tests for the is_workday function."""

    def test_monday_is_workday(self):
        """Monday should be a workday."""
        # January 6, 2025 is a Monday
        monday = datetime.date(2025, 1, 6)
        assert is_workday(monday, set(), set()) is True

    def test_friday_is_workday(self):
        """Friday should be a workday."""
        # January 10, 2025 is a Friday
        friday = datetime.date(2025, 1, 10)
        assert is_workday(friday, set(), set()) is True

    def test_saturday_is_not_workday(self):
        """Saturday should not be a workday."""
        # January 4, 2025 is a Saturday
        saturday = datetime.date(2025, 1, 4)
        assert is_workday(saturday, set(), set()) is False

    def test_sunday_is_not_workday(self):
        """Sunday should not be a workday."""
        # January 5, 2025 is a Sunday
        sunday = datetime.date(2025, 1, 5)
        assert is_workday(sunday, set(), set()) is False

    def test_holiday_is_not_workday(self):
        """A weekday that is a holiday should not be a workday."""
        # January 1, 2025 is a Wednesday (New Year's Day)
        new_years = datetime.date(2025, 1, 1)
        holidays = {new_years}
        assert is_workday(new_years, holidays, set()) is False

    def test_vacation_day_is_not_workday(self):
        """A weekday that is a vacation day should not be a workday."""
        # January 6, 2025 is a Monday
        vacation_date = datetime.date(2025, 1, 6)
        vacation_days = {vacation_date}
        assert is_workday(vacation_date, set(), vacation_days) is False

    def test_holiday_and_vacation_on_same_day(self):
        """A day that is both holiday and vacation should not be a workday."""
        date = datetime.date(2025, 1, 6)
        assert is_workday(date, {date}, {date}) is False

    def test_holiday_on_weekend_still_weekend(self):
        """A weekend holiday is still not a workday."""
        # January 4, 2025 is a Saturday
        saturday = datetime.date(2025, 1, 4)
        holidays = {saturday}
        assert is_workday(saturday, holidays, set()) is False


class TestGetWorkdaysInMonth:
    """Tests for the get_workdays_in_month function."""

    def test_january_2025_has_23_workdays(self):
        """January 2025 has 23 weekdays (no holidays)."""
        workdays = get_workdays_in_month(2025, 1, set(), set())
        assert len(workdays) == 23

    def test_february_2025_has_20_workdays(self):
        """February 2025 has 20 weekdays (non-leap year)."""
        workdays = get_workdays_in_month(2025, 2, set(), set())
        assert len(workdays) == 20

    def test_february_2024_leap_year(self):
        """February 2024 (leap year) has 21 weekdays."""
        workdays = get_workdays_in_month(2024, 2, set(), set())
        assert len(workdays) == 21

    def test_workdays_are_sorted(self):
        """Returned workdays should be sorted chronologically."""
        workdays = get_workdays_in_month(2025, 1, set(), set())
        assert workdays == sorted(workdays)

    def test_first_day_of_month_included(self):
        """First day of month should be included if it's a workday."""
        # January 1, 2025 is a Wednesday
        workdays = get_workdays_in_month(2025, 1, set(), set())
        assert datetime.date(2025, 1, 1) in workdays

    def test_last_day_of_month_included(self):
        """Last day of month should be included if it's a workday."""
        # January 31, 2025 is a Friday
        workdays = get_workdays_in_month(2025, 1, set(), set())
        assert datetime.date(2025, 1, 31) in workdays

    def test_holidays_excluded(self):
        """Holidays should be excluded from workdays."""
        new_years = datetime.date(2025, 1, 1)
        mlk_day = datetime.date(2025, 1, 20)  # Third Monday of January
        holidays = {new_years, mlk_day}

        workdays = get_workdays_in_month(2025, 1, holidays, set())

        assert len(workdays) == 21  # 23 - 2 holidays
        assert new_years not in workdays
        assert mlk_day not in workdays

    def test_vacation_days_excluded(self):
        """Vacation days should be excluded from workdays."""
        vacation = {
            datetime.date(2025, 1, 6),   # Monday
            datetime.date(2025, 1, 7),   # Tuesday
            datetime.date(2025, 1, 8),   # Wednesday
        }

        workdays = get_workdays_in_month(2025, 1, set(), vacation)

        assert len(workdays) == 20  # 23 - 3 vacation days
        for v in vacation:
            assert v not in workdays

    def test_invalid_month_raises_error(self):
        """Month outside 1-12 should raise ValueError."""
        with pytest.raises(ValueError, match="Month must be between 1 and 12"):
            get_workdays_in_month(2025, 0, set(), set())

        with pytest.raises(ValueError, match="Month must be between 1 and 12"):
            get_workdays_in_month(2025, 13, set(), set())

    def test_all_weekdays_are_holidays(self):
        """If all weekdays are holidays, return empty list."""
        # Create holidays for all weekdays in January 2025
        all_weekdays = set()
        for day in range(1, 32):
            date = datetime.date(2025, 1, day)
            if date.weekday() < 5:  # Mon-Fri
                all_weekdays.add(date)

        workdays = get_workdays_in_month(2025, 1, all_weekdays, set())
        assert workdays == []


class TestGetWorkdaysInRange:
    """Tests for the get_workdays_in_range function."""

    def test_full_week(self):
        """A full Mon-Fri week should have 5 workdays."""
        start = datetime.date(2025, 1, 6)   # Monday
        end = datetime.date(2025, 1, 10)    # Friday

        workdays = get_workdays_in_range(start, end, set(), set())

        assert len(workdays) == 5

    def test_includes_weekend(self):
        """Range including weekend should skip Sat/Sun."""
        start = datetime.date(2025, 1, 6)   # Monday
        end = datetime.date(2025, 1, 12)    # Sunday (next week)

        workdays = get_workdays_in_range(start, end, set(), set())

        # Mon-Fri = 5 workdays, Sat-Sun = 0
        assert len(workdays) == 5

    def test_two_full_weeks(self):
        """Two full weeks should have 10 workdays."""
        start = datetime.date(2025, 1, 6)   # Monday
        end = datetime.date(2025, 1, 17)    # Friday (second week)

        workdays = get_workdays_in_range(start, end, set(), set())

        assert len(workdays) == 10

    def test_cross_month_boundary(self):
        """Range crossing month boundary should work correctly."""
        start = datetime.date(2025, 1, 27)  # Monday
        end = datetime.date(2025, 2, 7)     # Friday

        workdays = get_workdays_in_range(start, end, set(), set())

        # Jan 27-31: 5 days (Mon-Fri)
        # Feb 1-2: 0 days (Sat-Sun)
        # Feb 3-7: 5 days (Mon-Fri)
        assert len(workdays) == 10

    def test_cross_year_boundary(self):
        """Range crossing year boundary should work correctly."""
        start = datetime.date(2024, 12, 30)  # Monday
        end = datetime.date(2025, 1, 3)      # Friday

        workdays = get_workdays_in_range(start, end, set(), set())

        # Dec 30 (Mon), 31 (Tue), Jan 1 (Wed), 2 (Thu), 3 (Fri) = 5 days
        assert len(workdays) == 5

    def test_single_day_range_weekday(self):
        """Single weekday should return list with one date."""
        date = datetime.date(2025, 1, 6)  # Monday

        workdays = get_workdays_in_range(date, date, set(), set())

        assert workdays == [date]

    def test_single_day_range_weekend(self):
        """Single weekend day should return empty list."""
        date = datetime.date(2025, 1, 4)  # Saturday

        workdays = get_workdays_in_range(date, date, set(), set())

        assert workdays == []

    def test_reversed_dates_returns_empty(self):
        """If start > end, return empty list."""
        start = datetime.date(2025, 1, 10)
        end = datetime.date(2025, 1, 6)

        workdays = get_workdays_in_range(start, end, set(), set())

        assert workdays == []

    def test_holidays_excluded_in_range(self):
        """Holidays should be excluded from range."""
        start = datetime.date(2025, 1, 6)   # Monday
        end = datetime.date(2025, 1, 10)    # Friday
        holiday = datetime.date(2025, 1, 8)  # Wednesday

        workdays = get_workdays_in_range(start, end, {holiday}, set())

        assert len(workdays) == 4
        assert holiday not in workdays


class TestGetRemainingWorkdaysInMonth:
    """Tests for the get_remaining_workdays_in_month function."""

    def test_from_first_of_month(self):
        """From first of month should equal get_workdays_in_month."""
        first = datetime.date(2025, 1, 1)

        remaining = get_remaining_workdays_in_month(first, set(), set())
        all_month = get_workdays_in_month(2025, 1, set(), set())

        assert remaining == all_month

    def test_from_last_weekday(self):
        """From last weekday should include only that day."""
        # January 31, 2025 is a Friday
        last_weekday = datetime.date(2025, 1, 31)

        remaining = get_remaining_workdays_in_month(last_weekday, set(), set())

        assert remaining == [last_weekday]

    def test_from_mid_month(self):
        """Mid-month should return correct remaining workdays."""
        # January 27, 2025 is a Monday
        mid_month = datetime.date(2025, 1, 27)

        remaining = get_remaining_workdays_in_month(mid_month, set(), set())

        # Mon 27, Tue 28, Wed 29, Thu 30, Fri 31 = 5 days
        assert len(remaining) == 5
        assert remaining[0] == mid_month
        assert remaining[-1] == datetime.date(2025, 1, 31)

    def test_from_weekend(self):
        """From weekend day should not include that day."""
        # January 25, 2025 is a Saturday
        saturday = datetime.date(2025, 1, 25)

        remaining = get_remaining_workdays_in_month(saturday, set(), set())

        # Sat 25 (not counted), Sun 26 (not counted), Mon 27-Fri 31 = 5 days
        assert len(remaining) == 5
        assert saturday not in remaining

    def test_from_last_saturday(self):
        """From last Saturday should return no workdays."""
        # Find a month that ends on Saturday
        # August 2025 ends on Sunday, so Aug 30 is Saturday
        last_saturday = datetime.date(2025, 8, 30)

        remaining = get_remaining_workdays_in_month(last_saturday, set(), set())

        # Aug 30 (Sat), 31 (Sun) = 0 workdays
        assert remaining == []

    def test_includes_from_date_if_workday(self):
        """If from_date is a workday, it should be included."""
        monday = datetime.date(2025, 1, 27)

        remaining = get_remaining_workdays_in_month(monday, set(), set())

        assert monday in remaining
        assert remaining[0] == monday

    def test_with_holidays(self):
        """Holidays should be excluded from remaining days."""
        mid_month = datetime.date(2025, 1, 27)
        holiday = datetime.date(2025, 1, 29)  # Wednesday

        remaining = get_remaining_workdays_in_month(mid_month, {holiday}, set())

        assert len(remaining) == 4
        assert holiday not in remaining


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_holiday_set(self):
        """Empty holiday set should not affect calculations."""
        workdays = get_workdays_in_month(2025, 1, set(), set())
        assert len(workdays) == 23

    def test_holidays_outside_month_ignored(self):
        """Holidays outside the month should be ignored."""
        feb_holiday = datetime.date(2025, 2, 14)  # Valentine's Day

        workdays = get_workdays_in_month(2025, 1, {feb_holiday}, set())

        # Should still have all 23 January workdays
        assert len(workdays) == 23

    def test_very_short_month_all_weekend(self):
        """Edge case: if workdays fall only on weekends, return empty."""
        # February 2025 starts on Saturday
        # The 1st and 2nd are Sat/Sun
        # What if we marked everything else as holiday?
        # Actually, let's use a simpler test

        # Create a holiday for every weekday in a short period
        start = datetime.date(2025, 2, 1)  # Saturday
        end = datetime.date(2025, 2, 2)    # Sunday

        workdays = get_workdays_in_range(start, end, set(), set())

        assert workdays == []

    def test_december_to_january_range(self):
        """Range from December to January should handle year correctly."""
        start = datetime.date(2024, 12, 30)
        end = datetime.date(2025, 1, 3)

        workdays = get_workdays_in_range(start, end, set(), set())

        # All 5 days are weekdays
        assert len(workdays) == 5
        assert datetime.date(2024, 12, 30) in workdays
        assert datetime.date(2025, 1, 1) in workdays

    def test_february_leap_year_edge(self):
        """Leap year February 29 should be handled correctly."""
        # February 29, 2024 is a Thursday (leap year)
        leap_day = datetime.date(2024, 2, 29)

        assert is_workday(leap_day, set(), set()) is True

        workdays = get_workdays_in_month(2024, 2, set(), set())
        assert leap_day in workdays

    def test_large_holiday_set(self):
        """Many holidays should be handled efficiently."""
        # Create 100 holidays spread across the year
        holidays = {datetime.date(2025, (i % 12) + 1, (i % 28) + 1) for i in range(100)}

        # Should not raise any errors
        workdays = get_workdays_in_month(2025, 1, holidays, set())
        assert isinstance(workdays, list)


class TestGetWeekendDaysInRange:
    """Tests for the get_weekend_days_in_range function."""

    def test_full_week_has_two_weekend_days(self):
        """A full Mon-Sun week should have 2 weekend days."""
        start = datetime.date(2025, 1, 6)   # Monday
        end = datetime.date(2025, 1, 12)    # Sunday

        weekends = get_weekend_days_in_range(start, end)

        assert len(weekends) == 2
        assert datetime.date(2025, 1, 11) in weekends  # Saturday
        assert datetime.date(2025, 1, 12) in weekends  # Sunday

    def test_weekdays_only_range(self):
        """Mon-Fri range should have no weekend days."""
        start = datetime.date(2025, 1, 6)   # Monday
        end = datetime.date(2025, 1, 10)    # Friday

        weekends = get_weekend_days_in_range(start, end)

        assert weekends == []

    def test_weekend_only_range(self):
        """Sat-Sun range should have 2 weekend days."""
        start = datetime.date(2025, 1, 4)   # Saturday
        end = datetime.date(2025, 1, 5)     # Sunday

        weekends = get_weekend_days_in_range(start, end)

        assert len(weekends) == 2
        assert weekends[0] == datetime.date(2025, 1, 4)
        assert weekends[1] == datetime.date(2025, 1, 5)

    def test_two_weeks_has_four_weekend_days(self):
        """Two full weeks should have 4 weekend days."""
        start = datetime.date(2025, 1, 6)   # Monday
        end = datetime.date(2025, 1, 19)    # Sunday (two weeks later)

        weekends = get_weekend_days_in_range(start, end)

        assert len(weekends) == 4

    def test_reversed_dates_returns_empty(self):
        """If start > end, return empty list."""
        start = datetime.date(2025, 1, 12)
        end = datetime.date(2025, 1, 6)

        weekends = get_weekend_days_in_range(start, end)

        assert weekends == []

    def test_single_saturday(self):
        """Single Saturday should return list with one date."""
        saturday = datetime.date(2025, 1, 4)

        weekends = get_weekend_days_in_range(saturday, saturday)

        assert weekends == [saturday]

    def test_single_sunday(self):
        """Single Sunday should return list with one date."""
        sunday = datetime.date(2025, 1, 5)

        weekends = get_weekend_days_in_range(sunday, sunday)

        assert weekends == [sunday]

    def test_single_weekday(self):
        """Single weekday should return empty list."""
        monday = datetime.date(2025, 1, 6)

        weekends = get_weekend_days_in_range(monday, monday)

        assert weekends == []

    def test_six_weeks_for_catch_up_sprint(self):
        """Six weeks (max sprint duration) should have 12 weekend days."""
        start = datetime.date(2025, 1, 6)   # Monday
        end = datetime.date(2025, 2, 16)    # Sunday (6 weeks later)

        weekends = get_weekend_days_in_range(start, end)

        assert len(weekends) == 12

    def test_weekends_are_sorted(self):
        """Weekend days should be returned in chronological order."""
        start = datetime.date(2025, 1, 1)
        end = datetime.date(2025, 1, 31)

        weekends = get_weekend_days_in_range(start, end)

        assert weekends == sorted(weekends)

    def test_cross_month_boundary(self):
        """Range crossing month boundary should work correctly."""
        start = datetime.date(2025, 1, 27)  # Monday
        end = datetime.date(2025, 2, 9)     # Sunday

        weekends = get_weekend_days_in_range(start, end)

        # Jan 27-31: no weekends (Mon-Fri)
        # Feb 1-2: Sat, Sun
        # Feb 3-7: no weekends (Mon-Fri)
        # Feb 8-9: Sat, Sun
        assert len(weekends) == 4


class TestDateEdgeCases:
    """Date handling edge case tests - Sprint 3.11."""

    def test_feb_29_as_holiday_in_leap_year(self):
        """Feb 29 as a holiday in leap year (2024) is excluded from workdays."""
        # Feb 29, 2024 is a Thursday (workday)
        leap_day = datetime.date(2024, 2, 29)
        holidays = {leap_day}

        workdays = get_workdays_in_month(2024, 2, holidays, set())

        # Feb 2024 has 21 weekdays, minus 1 holiday = 20
        assert len(workdays) == 20
        assert leap_day not in workdays

    def test_feb_29_as_vacation_in_leap_year(self):
        """Feb 29 as vacation day in leap year (2024) is excluded from workdays."""
        # Feb 29, 2024 is a Thursday (workday)
        leap_day = datetime.date(2024, 2, 29)
        vacation = {leap_day}

        workdays = get_workdays_in_month(2024, 2, set(), vacation)

        # Feb 2024 has 21 weekdays, minus 1 vacation = 20
        assert len(workdays) == 20
        assert leap_day not in workdays

    def test_april_has_correct_workdays(self):
        """April 2025 (30 days) has correct workday count."""
        # April 2025: starts on Tuesday, ends on Wednesday
        # 22 weekdays
        workdays = get_workdays_in_month(2025, 4, set(), set())

        assert len(workdays) == 22
        assert workdays[0] == datetime.date(2025, 4, 1)  # Tuesday
        assert workdays[-1] == datetime.date(2025, 4, 30)  # Wednesday

    def test_june_has_correct_workdays(self):
        """June 2025 (30 days) has correct workday count."""
        # June 2025: starts on Sunday, ends on Monday
        # 21 weekdays
        workdays = get_workdays_in_month(2025, 6, set(), set())

        assert len(workdays) == 21
        # First workday is Monday June 2 (June 1 is Sunday)
        assert workdays[0] == datetime.date(2025, 6, 2)
        assert workdays[-1] == datetime.date(2025, 6, 30)  # Monday

    def test_jan_1_when_weekday(self):
        """Jan 1 counted when it's a weekday (2025 is Wednesday)."""
        # Jan 1, 2025 is Wednesday
        jan_1 = datetime.date(2025, 1, 1)

        workdays = get_workdays_in_month(2025, 1, set(), set())

        assert jan_1 in workdays
        assert workdays[0] == jan_1

    def test_jan_1_when_weekend(self):
        """Jan 1 excluded when on weekend (2028 is Saturday)."""
        # Jan 1, 2028 is Saturday
        jan_1 = datetime.date(2028, 1, 1)

        workdays = get_workdays_in_month(2028, 1, set(), set())

        assert jan_1 not in workdays
        # First workday is Monday Jan 3
        assert workdays[0] == datetime.date(2028, 1, 3)

    def test_remaining_workdays_on_dec_31(self):
        """get_remaining_workdays_in_month on Dec 31 returns just that day if workday."""
        # Dec 31, 2025 is Wednesday
        dec_31 = datetime.date(2025, 12, 31)

        remaining = get_remaining_workdays_in_month(dec_31, set(), set())

        assert remaining == [dec_31]

    def test_dec_31_when_weekend(self):
        """Dec 31 excluded when on weekend (2028 is Sunday)."""
        # Dec 31, 2028 is Sunday
        dec_31 = datetime.date(2028, 12, 31)

        workdays = get_workdays_in_month(2028, 12, set(), set())

        assert dec_31 not in workdays
        # Last workday is Friday Dec 29
        assert workdays[-1] == datetime.date(2028, 12, 29)

    def test_holiday_on_weekend_no_double_count(self):
        """Holiday falling on weekend doesn't affect workday count."""
        # July 4, 2026 is Saturday
        july_4_saturday = datetime.date(2026, 7, 4)

        # Without holiday in set
        workdays_without = get_workdays_in_month(2026, 7, set(), set())
        # With holiday in set (shouldn't matter - already a weekend)
        workdays_with = get_workdays_in_month(2026, 7, {july_4_saturday}, set())

        # Both should have 23 workdays (July 2026 has 23 weekdays)
        assert len(workdays_without) == 23
        assert len(workdays_with) == 23

    def test_consecutive_holidays_across_weekend(self):
        """Holidays Thu-Tue with weekend in middle counted correctly."""
        # Create holidays for Thu, Fri, Mon, Tue (weekend already excluded)
        # Use Jan 2025 week: Jan 9 Thu, 10 Fri, 13 Mon, 14 Tue
        holidays = {
            datetime.date(2025, 1, 9),   # Thursday
            datetime.date(2025, 1, 10),  # Friday
            datetime.date(2025, 1, 13),  # Monday
            datetime.date(2025, 1, 14),  # Tuesday
        }

        workdays = get_workdays_in_month(2025, 1, holidays, set())

        # January 2025 has 23 weekdays, minus 4 holidays = 19
        assert len(workdays) == 19
        for holiday in holidays:
            assert holiday not in workdays

    def test_entire_month_as_vacation(self):
        """All workdays in month as vacation returns empty list."""
        # Get all February 2025 weekdays and mark as vacation
        all_feb_weekdays = set()
        for day in range(1, 29):  # Feb 2025 has 28 days
            date = datetime.date(2025, 2, day)
            if date.weekday() < 5:  # Mon-Fri
                all_feb_weekdays.add(date)

        workdays = get_workdays_in_month(2025, 2, set(), all_feb_weekdays)

        assert workdays == []

    def test_range_feb_27_to_mar_2_leap_year(self):
        """Range Feb 27 - Mar 2 in leap year includes Feb 29."""
        # Feb 27, 2024 = Tuesday
        # Feb 28, 2024 = Wednesday
        # Feb 29, 2024 = Thursday (leap day!)
        # Mar 1, 2024 = Friday
        # Mar 2, 2024 = Saturday (weekend)
        start = datetime.date(2024, 2, 27)
        end = datetime.date(2024, 3, 2)

        workdays = get_workdays_in_range(start, end, set(), set())

        assert len(workdays) == 4
        assert datetime.date(2024, 2, 29) in workdays

    def test_range_feb_27_to_mar_2_non_leap_year(self):
        """Range Feb 27 - Mar 2 in non-leap year skips Feb 29."""
        # Feb 27, 2025 = Thursday
        # Feb 28, 2025 = Friday
        # (no Feb 29)
        # Mar 1, 2025 = Saturday (weekend)
        # Mar 2, 2025 = Sunday (weekend)
        start = datetime.date(2025, 2, 27)
        end = datetime.date(2025, 3, 2)

        workdays = get_workdays_in_range(start, end, set(), set())

        # Only Feb 27 (Thu) and Feb 28 (Fri) are workdays
        assert len(workdays) == 2
        assert datetime.date(2025, 2, 27) in workdays
        assert datetime.date(2025, 2, 28) in workdays
