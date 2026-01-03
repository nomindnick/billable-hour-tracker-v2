"""
Calendar utilities for calculating workdays.

This module provides functions for determining workdays (Monday-Friday)
while accounting for holidays and vacation days. These utilities are
used by the planning and calculator services to distribute annual
billing targets and calculate daily goals.

Key concepts:
- Workday: A weekday (Mon-Fri) that is not a holiday or vacation day
- Weekend: Saturday or Sunday (never a workday)
- Holiday: A firm-recognized holiday when no billing is expected
- Vacation: A planned day off for the user
"""

import calendar
import datetime
from typing import Set, List


def is_workday(
    date: datetime.date,
    holidays: Set[datetime.date],
    vacation_days: Set[datetime.date]
) -> bool:
    """
    Check if a given date is a workday.

    A workday is Monday-Friday and not a holiday or vacation day.

    Args:
        date: The date to check
        holidays: Set of holiday dates to exclude
        vacation_days: Set of vacation dates to exclude

    Returns:
        True if the date is a workday, False otherwise

    Examples:
        >>> is_workday(datetime.date(2025, 1, 6), set(), set())  # Monday
        True
        >>> is_workday(datetime.date(2025, 1, 4), set(), set())  # Saturday
        False
    """
    # Monday = 0, Sunday = 6 in Python's weekday()
    is_weekend = date.weekday() >= 5

    if is_weekend:
        return False

    if date in holidays:
        return False

    if date in vacation_days:
        return False

    return True


def get_workdays_in_month(
    year: int,
    month: int,
    holidays: Set[datetime.date],
    vacation_days: Set[datetime.date]
) -> List[datetime.date]:
    """
    Get all workdays in a given month.

    Returns a list of all dates that are workdays (Mon-Fri, not holidays
    or vacation days) in the specified month.

    Args:
        year: Calendar year (e.g., 2025)
        month: Month number (1-12)
        holidays: Set of holiday dates to exclude
        vacation_days: Set of vacation dates to exclude

    Returns:
        List of datetime.date objects for all workdays, sorted chronologically

    Raises:
        ValueError: If month is not between 1 and 12

    Examples:
        >>> len(get_workdays_in_month(2025, 1, set(), set()))  # January 2025
        23  # 23 weekdays in January 2025
    """
    if not 1 <= month <= 12:
        raise ValueError(f"Month must be between 1 and 12, got {month}")

    # Get the first and last day of the month
    first_day = datetime.date(year, month, 1)
    _, last_day_num = calendar.monthrange(year, month)
    last_day = datetime.date(year, month, last_day_num)

    return get_workdays_in_range(first_day, last_day, holidays, vacation_days)


def get_workdays_in_range(
    start_date: datetime.date,
    end_date: datetime.date,
    holidays: Set[datetime.date],
    vacation_days: Set[datetime.date]
) -> List[datetime.date]:
    """
    Get all workdays in a date range (inclusive).

    Returns a list of all dates that are workdays between start_date
    and end_date, including both endpoints.

    Args:
        start_date: First date in the range (inclusive)
        end_date: Last date in the range (inclusive)
        holidays: Set of holiday dates to exclude
        vacation_days: Set of vacation dates to exclude

    Returns:
        List of datetime.date objects for all workdays, sorted chronologically.
        Returns empty list if start_date > end_date.

    Examples:
        >>> start = datetime.date(2025, 1, 6)  # Monday
        >>> end = datetime.date(2025, 1, 10)   # Friday
        >>> len(get_workdays_in_range(start, end, set(), set()))
        5  # Mon, Tue, Wed, Thu, Fri
    """
    # Handle reversed dates gracefully
    if start_date > end_date:
        return []

    workdays = []
    current_date = start_date
    one_day = datetime.timedelta(days=1)

    while current_date <= end_date:
        if is_workday(current_date, holidays, vacation_days):
            workdays.append(current_date)
        current_date += one_day

    return workdays


def get_remaining_workdays_in_month(
    from_date: datetime.date,
    holidays: Set[datetime.date],
    vacation_days: Set[datetime.date]
) -> List[datetime.date]:
    """
    Get remaining workdays from a date to the end of its month (inclusive).

    This is useful for calculating how many workdays remain in the current
    month for daily target recalculation.

    Args:
        from_date: Starting date (inclusive)
        holidays: Set of holiday dates to exclude
        vacation_days: Set of vacation dates to exclude

    Returns:
        List of datetime.date objects for remaining workdays, sorted chronologically.
        Includes from_date if it is a workday.

    Examples:
        >>> date = datetime.date(2025, 1, 27)  # Monday
        >>> len(get_remaining_workdays_in_month(date, set(), set()))
        5  # Mon 27, Tue 28, Wed 29, Thu 30, Fri 31
    """
    # Get the last day of the month
    _, last_day_num = calendar.monthrange(from_date.year, from_date.month)
    last_day = datetime.date(from_date.year, from_date.month, last_day_num)

    return get_workdays_in_range(from_date, last_day, holidays, vacation_days)


def get_weekend_days_in_range(
    start_date: datetime.date,
    end_date: datetime.date
) -> List[datetime.date]:
    """
    Get all weekend days (Saturday/Sunday) in a date range (inclusive).

    Used for catch-up sprints where weekend billing is optional.
    Does not require holidays/vacation parameters since weekend billing
    is voluntary - users choose whether to bill on weekends.

    Args:
        start_date: First date in the range (inclusive)
        end_date: Last date in the range (inclusive)

    Returns:
        List of datetime.date objects for all weekend days, sorted chronologically.
        Returns empty list if start_date > end_date.

    Examples:
        >>> start = datetime.date(2025, 1, 6)   # Monday
        >>> end = datetime.date(2025, 1, 12)    # Sunday
        >>> weekends = get_weekend_days_in_range(start, end)
        >>> len(weekends)
        2  # Saturday Jan 11 and Sunday Jan 12
    """
    # Handle reversed dates gracefully
    if start_date > end_date:
        return []

    weekend_days = []
    current_date = start_date
    one_day = datetime.timedelta(days=1)

    while current_date <= end_date:
        # Saturday = 5, Sunday = 6 in Python's weekday()
        if current_date.weekday() >= 5:
            weekend_days.append(current_date)
        current_date += one_day

    return weekend_days
