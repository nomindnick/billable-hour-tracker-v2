"""
Calculator service for dynamic daily target calculations.

This module provides functions for calculating daily billing targets
that adjust based on actual hours billed. It works in conjunction with
the planner service to provide real-time guidance on how much to bill
each day to stay on track with monthly and annual goals.

Key features:
- Dynamic daily targets that recalculate as hours are logged
- Plan status tracking (ahead, on track, behind)
- Catch-up recommendations when falling behind
- Hours banked calculation for buffer tracking
"""

import datetime
from dataclasses import dataclass
from typing import Optional

from app.models import PlanConfig, YearConfig
from app.services.calendar_utils import (
    get_remaining_workdays_in_month,
    get_workdays_in_month,
    get_workdays_in_range,
)
from app.services.planner import (
    MAX_DAILY_HOURS,
    calculate_monthly_targets_for_plan,
    extract_holidays_and_vacations,
)


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

# Thresholds for determining plan status
# Users within this range of "behind" are still considered on track
SLIGHTLY_BEHIND_THRESHOLD = 5.0   # hours behind before "slightly behind" status
CATCH_UP_THRESHOLD = 15.0         # hours behind before catch-up is suggested

# Status labels for display
STATUS_ON_TRACK = "On track"
STATUS_AHEAD = "Ahead"
STATUS_SLIGHTLY_BEHIND = "Slightly behind"
STATUS_CATCH_UP_RECOMMENDED = "Consider a catch-up sprint"


# -----------------------------------------------------------------------------
# Data Classes
# -----------------------------------------------------------------------------

@dataclass
class DailyTargetResult:
    """
    Result of daily target calculation.

    Attributes:
        daily_target: Hours to bill today to stay on track (0.0 to 9.5)
        catch_up_recommended: True if hitting target requires more than 9.5 hours/day
        remaining_hours_this_month: Hours left to bill to hit monthly target
        remaining_workdays: Workdays left in the month (including today if workday)
    """
    daily_target: float
    catch_up_recommended: bool
    remaining_hours_this_month: float
    remaining_workdays: int


@dataclass
class PlanStatus:
    """
    Status of a plan at a point in time.

    Attributes:
        hours_ahead_or_behind: Positive = ahead, negative = behind
        status_label: Human-readable status ("On track", "Ahead", etc.)
        expected_hours_to_date: Hours the plan says should be billed by now
        actual_hours_to_date: Hours actually billed
    """
    hours_ahead_or_behind: float
    status_label: str
    expected_hours_to_date: float
    actual_hours_to_date: float


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def get_historical_hours(year_config: YearConfig) -> float:
    """
    Get total historical hours billed before the user started tracking.

    Combines both the lump sum (hours_pre_start) and any monthly breakdown
    entries (historical_months). Users can use either or both methods.

    Args:
        year_config: The year configuration with historical data

    Returns:
        Total historical hours (0.0 if no historical data)

    Examples:
        >>> # User entered 500 hours lump sum + 100 hours in historical January
        >>> get_historical_hours(year_config)
        600.0
    """
    total = 0.0

    # Add lump sum if provided
    if year_config.hours_pre_start:
        total += year_config.hours_pre_start

    # Add historical month entries
    for hist_month in year_config.historical_months:
        total += hist_month.hours_billed

    return total


def get_hours_billed_in_month(
    year_config: YearConfig,
    year: int,
    month: int
) -> float:
    """
    Sum hours from daily entries for a specific month.

    Args:
        year_config: The year configuration containing daily entries
        year: Calendar year to filter by
        month: Month number (1-12) to filter by

    Returns:
        Total hours billed in the specified month

    Examples:
        >>> get_hours_billed_in_month(year_config, 2025, 1)
        120.5
    """
    return sum(
        entry.hours_billed
        for entry in year_config.daily_entries
        if entry.date.year == year and entry.date.month == month
    )


def get_hours_billed_to_date(
    year_config: YearConfig,
    as_of_date: datetime.date
) -> float:
    """
    Sum all hours billed up to and including a specific date.

    Includes historical hours (from before start_date) in the total.
    Historical hours are only included if the as_of_date is on or after
    the start_date (or if no start_date is set, meaning Jan 1 start).

    Args:
        year_config: The year configuration containing daily entries
        as_of_date: Include entries up to and including this date

    Returns:
        Total hours billed through the specified date (including historical)

    Examples:
        >>> # 450 from daily entries + 500 historical = 950
        >>> get_hours_billed_to_date(year_config, datetime.date(2025, 3, 15))
        950.0
    """
    # Sum daily entries
    daily_hours = sum(
        entry.hours_billed
        for entry in year_config.daily_entries
        if entry.date <= as_of_date
    )

    # Add historical hours if we're past the start date
    # (Historical hours represent hours billed before start_date)
    start_date = year_config.start_date or datetime.date(year_config.year, 1, 1)
    if as_of_date >= start_date:
        return daily_hours + get_historical_hours(year_config)

    return daily_hours


def get_expected_hours_to_date(
    year_config: YearConfig,
    plan_config: PlanConfig,
    as_of_date: datetime.date
) -> float:
    """
    Calculate expected hours based on plan through a specific date.

    For completed months (after start_date), adds the full monthly target.
    For the current month, prorates based on workdays elapsed.
    Months before start_date have 0 expected hours.

    For mid-year starts, this returns expected hours only from start_date
    forward. Historical hours are added in get_hours_billed_to_date(),
    so the comparison (actual - expected) gives correct plan status.

    Args:
        year_config: The year configuration
        plan_config: The plan configuration to calculate against
        as_of_date: Calculate expected hours through this date

    Returns:
        Expected hours that should have been billed by as_of_date

    Examples:
        >>> # Mid-March, should have ~2.5 months of hours
        >>> get_expected_hours_to_date(year_config, plan, datetime.date(2025, 3, 15))
        375.0
    """
    monthly_targets = calculate_monthly_targets_for_plan(year_config, plan_config)
    holidays, vacation_days = extract_holidays_and_vacations(year_config)

    # Determine the start date (default to Jan 1 if not set)
    start_date = year_config.start_date or datetime.date(year_config.year, 1, 1)

    # If as_of_date is before start_date, no expected hours yet
    if as_of_date < start_date:
        return 0.0

    expected = 0.0

    # Determine which months to include (start from start_date's month)
    start_month = start_date.month

    # Add full targets for completed months (after start_month, before current month)
    for month in range(start_month, as_of_date.month):
        expected += monthly_targets.get(month, 0.0)

    # Special handling for start month if it's a past month
    # (start month is fully expected only after the start_date portion)
    if start_month < as_of_date.month:
        # Start month is already included in the loop above
        # But we need to adjust for partial month if start_date wasn't the 1st
        if start_date.day > 1:
            # Subtract the portion of start month before start_date
            total_workdays_start = get_workdays_in_month(
                start_date.year,
                start_month,
                holidays,
                vacation_days
            )
            workdays_before_start = get_workdays_in_range(
                datetime.date(start_date.year, start_month, 1),
                start_date - datetime.timedelta(days=1),
                holidays,
                vacation_days
            )
            if len(total_workdays_start) > 0:
                pre_start_proportion = len(workdays_before_start) / len(total_workdays_start)
                month_target = monthly_targets.get(start_month, 0.0)
                expected -= month_target * pre_start_proportion

    # Prorate current month based on workdays elapsed
    month_start = datetime.date(as_of_date.year, as_of_date.month, 1)

    # If this is the start month, start counting from start_date, not month start
    if as_of_date.month == start_month:
        effective_start = start_date
    else:
        effective_start = month_start

    total_workdays = get_workdays_in_month(
        as_of_date.year,
        as_of_date.month,
        holidays,
        vacation_days
    )

    # Count workdays from effective start to as_of_date
    elapsed_workdays = get_workdays_in_range(
        effective_start,
        as_of_date,
        holidays,
        vacation_days
    )

    # For current month, calculate based on workdays from effective start
    if as_of_date.month == start_month:
        # Only count workdays from start_date to end of month
        workdays_from_start = get_workdays_in_range(
            start_date,
            datetime.date(start_date.year, start_month, 1) + datetime.timedelta(days=31),
            holidays,
            vacation_days
        )
        # Filter to only include days in this month
        workdays_from_start = [d for d in workdays_from_start if d.month == start_month]
        if len(workdays_from_start) > 0:
            month_target = monthly_targets.get(as_of_date.month, 0.0)
            proportion = len(elapsed_workdays) / len(workdays_from_start)
            expected += month_target * proportion
    else:
        if len(total_workdays) > 0:
            month_target = monthly_targets.get(as_of_date.month, 0.0)
            proportion = len(elapsed_workdays) / len(total_workdays)
            expected += month_target * proportion

    return expected


# -----------------------------------------------------------------------------
# Core Functions
# -----------------------------------------------------------------------------

def calculate_daily_target(
    year_config: YearConfig,
    plan_config: PlanConfig,
    target_date: datetime.date
) -> DailyTargetResult:
    """
    Calculate today's target based on remaining hours and workdays.

    The algorithm:
    1. Gets the monthly target for the current month
    2. Subtracts hours already billed this month
    3. Divides remaining hours by remaining workdays
    4. Caps the result at 9.5 hours (MAX_DAILY_HOURS)

    If the uncapped target exceeds 9.5 hours, catch_up_recommended is set
    to True, indicating the user should consider a catch-up sprint.

    Args:
        year_config: The year configuration with entries and settings
        plan_config: The plan to calculate targets for
        target_date: The date to calculate the target for

    Returns:
        DailyTargetResult with the calculated target and metadata

    Examples:
        >>> result = calculate_daily_target(year_config, plan, datetime.date(2025, 1, 15))
        >>> result.daily_target
        7.5
        >>> result.catch_up_recommended
        False
    """
    # Get the monthly target for this month
    monthly_targets = calculate_monthly_targets_for_plan(year_config, plan_config)
    month_target = monthly_targets.get(target_date.month, 0.0)

    # Sum hours already billed this month
    hours_billed = get_hours_billed_in_month(
        year_config,
        target_date.year,
        target_date.month
    )

    # Get remaining workdays (includes target_date if it's a workday)
    holidays, vacation_days = extract_holidays_and_vacations(year_config)
    remaining_workdays = get_remaining_workdays_in_month(
        target_date,
        holidays,
        vacation_days
    )
    remaining_workday_count = len(remaining_workdays)

    # Calculate remaining hours needed
    remaining_hours = month_target - hours_billed

    # Handle edge cases
    if remaining_hours <= 0:
        # Already met or exceeded monthly target
        return DailyTargetResult(
            daily_target=0.0,
            catch_up_recommended=False,
            remaining_hours_this_month=remaining_hours,
            remaining_workdays=remaining_workday_count
        )

    if remaining_workday_count == 0:
        # No workdays left but hours remain - need catch-up
        return DailyTargetResult(
            daily_target=0.0,
            catch_up_recommended=True,
            remaining_hours_this_month=remaining_hours,
            remaining_workdays=0
        )

    # Calculate raw daily target
    raw_target = remaining_hours / remaining_workday_count

    # Check if catch-up is needed (would require more than max hours/day)
    catch_up_recommended = raw_target > MAX_DAILY_HOURS

    # Cap at maximum daily hours
    daily_target = min(raw_target, MAX_DAILY_HOURS)

    return DailyTargetResult(
        daily_target=round(daily_target, 2),
        catch_up_recommended=catch_up_recommended,
        remaining_hours_this_month=round(remaining_hours, 2),
        remaining_workdays=remaining_workday_count
    )


def calculate_plan_status(
    year_config: YearConfig,
    plan_config: PlanConfig,
    as_of_date: Optional[datetime.date] = None
) -> PlanStatus:
    """
    Calculate the current status of a plan (ahead, on track, behind).

    Compares actual hours billed to expected hours based on the plan.
    Status thresholds:
    - Ahead: actual > expected
    - On track: actual >= expected OR within 5 hours behind
    - Slightly behind: 5-15 hours behind
    - Catch-up recommended: more than 15 hours behind

    Args:
        year_config: The year configuration with entries
        plan_config: The plan to check status against
        as_of_date: Date to calculate status as of (defaults to today)

    Returns:
        PlanStatus with hours ahead/behind and status label

    Examples:
        >>> status = calculate_plan_status(year_config, realistic_plan)
        >>> status.status_label
        "On track"
        >>> status.hours_ahead_or_behind
        2.5
    """
    if as_of_date is None:
        as_of_date = datetime.date.today()

    # Calculate expected and actual hours
    expected = get_expected_hours_to_date(year_config, plan_config, as_of_date)
    actual = get_hours_billed_to_date(year_config, as_of_date)

    # Positive = ahead, negative = behind
    difference = actual - expected

    # Determine status label
    if difference >= 0:
        if difference > 0:
            status_label = STATUS_AHEAD
        else:
            status_label = STATUS_ON_TRACK
    elif difference > -SLIGHTLY_BEHIND_THRESHOLD:
        # Within tolerance, still considered on track
        status_label = STATUS_ON_TRACK
    elif difference > -CATCH_UP_THRESHOLD:
        status_label = STATUS_SLIGHTLY_BEHIND
    else:
        status_label = STATUS_CATCH_UP_RECOMMENDED

    return PlanStatus(
        hours_ahead_or_behind=round(difference, 2),
        status_label=status_label,
        expected_hours_to_date=round(expected, 2),
        actual_hours_to_date=round(actual, 2)
    )


def calculate_hours_banked(
    year_config: YearConfig,
    plan_config: PlanConfig,
    as_of_date: Optional[datetime.date] = None
) -> float:
    """
    Calculate hours "banked" (buffer) compared to plan expectations.

    Banked hours represent how far ahead the user is from where they
    need to be. If behind, banked hours is 0 (can't have negative buffer).

    This is a simplified calculation: max(0, actual - expected).
    A more sophisticated version could track daily surpluses, but
    this approach is clearer and gives the same practical guidance.

    Args:
        year_config: The year configuration with entries
        plan_config: The plan to compare against
        as_of_date: Date to calculate as of (defaults to today)

    Returns:
        Hours banked (0 if behind or exactly on track)

    Examples:
        >>> calculate_hours_banked(year_config, plan)
        15.5  # 15.5 hours ahead of schedule
    """
    if as_of_date is None:
        as_of_date = datetime.date.today()

    expected = get_expected_hours_to_date(year_config, plan_config, as_of_date)
    actual = get_hours_billed_to_date(year_config, as_of_date)

    return max(0.0, round(actual - expected, 2))
