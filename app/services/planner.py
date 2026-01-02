"""
Planning service for the Billable Hours Planner.

This module contains the core planning algorithm that distributes annual
billing targets across months based on workdays and intensity settings.
It handles all three plan types: Firm, Optimistic, and Realistic.

The planning algorithm:
1. Calculates available workdays per month (excluding weekends, holidays, vacation)
2. Applies intensity weights (normal=1.0, light=0.75, very_light=0.5)
3. Distributes annual target proportionally based on weighted workdays
4. Validates that no month requires more than 9.5 hours/day average
"""

import datetime
from dataclasses import dataclass
from typing import Optional

from app.models import (
    IntensityLevel,
    MonthConfig,
    PlanConfig,
    PlanType,
    YearConfig,
)
from app.services.calendar_utils import get_workdays_in_month


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

# Weight multipliers for billing intensity levels.
# These determine how many hours are allocated to each month relative to others.
INTENSITY_WEIGHTS: dict[IntensityLevel, float] = {
    IntensityLevel.NORMAL: 1.0,      # Full allocation
    IntensityLevel.LIGHT: 0.75,      # 25% reduction
    IntensityLevel.VERY_LIGHT: 0.5,  # 50% reduction
}

# Maximum daily hours before a plan is considered infeasible
MAX_DAILY_HOURS = 9.5


# -----------------------------------------------------------------------------
# Data Classes
# -----------------------------------------------------------------------------

@dataclass
class PlanWarning:
    """
    Warning generated when a plan requires unrealistic daily hours.

    Attributes:
        month: Month number (1-12) that has the issue
        required_daily_hours: Hours/day needed to hit the target
        workdays_in_month: Number of workdays available
        message: Human-readable warning message
    """
    month: int
    required_daily_hours: float
    workdays_in_month: int
    message: str


@dataclass
class MonthlyTarget:
    """
    Complete breakdown of a month's billing target.

    Attributes:
        month: Month number (1-12)
        target_hours: Total hours to bill this month
        workdays: Number of workdays in this month
        daily_target: Average hours per workday to hit the target
        intensity: The intensity level configured for this month
    """
    month: int
    target_hours: float
    workdays: int
    daily_target: float
    intensity: IntensityLevel


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def get_intensity_weight(intensity: IntensityLevel) -> float:
    """
    Get the weight multiplier for an intensity level.

    Args:
        intensity: The intensity level to get the weight for

    Returns:
        The weight multiplier (1.0 for normal, 0.75 for light, 0.5 for very_light)

    Examples:
        >>> get_intensity_weight(IntensityLevel.NORMAL)
        1.0
        >>> get_intensity_weight(IntensityLevel.LIGHT)
        0.75
    """
    return INTENSITY_WEIGHTS[intensity]


def get_month_intensity(year_config: YearConfig, month: int) -> IntensityLevel:
    """
    Get the intensity level configured for a specific month.

    If no MonthConfig record exists for the month, returns NORMAL as the default.

    Args:
        year_config: The year configuration to look up
        month: Month number (1-12)

    Returns:
        The configured intensity level, or NORMAL if not configured
    """
    for month_config in year_config.month_configs:
        if month_config.month == month:
            return month_config.intensity
    # Default to normal intensity if no configuration exists
    return IntensityLevel.NORMAL


def extract_holidays_and_vacations(
    year_config: YearConfig
) -> tuple[set[datetime.date], set[datetime.date]]:
    """
    Extract holiday and vacation dates from a YearConfig as sets.

    Sets are used for O(1) lookup performance when checking if a date
    is a holiday or vacation day.

    Args:
        year_config: The year configuration containing holidays and vacation days

    Returns:
        Tuple of (holidays_set, vacation_days_set)

    Examples:
        >>> holidays, vacations = extract_holidays_and_vacations(year_config)
        >>> datetime.date(2025, 12, 25) in holidays
        True
    """
    holidays = {holiday.date for holiday in year_config.holidays}
    vacation_days = {vacation.date for vacation in year_config.vacation_days}
    return holidays, vacation_days


# -----------------------------------------------------------------------------
# Core Algorithm Functions
# -----------------------------------------------------------------------------

def calculate_monthly_targets(
    year_config: YearConfig,
    end_month: Optional[int] = None,
    target_hours: Optional[float] = None
) -> dict[int, float]:
    """
    Distribute annual target hours across months proportionally.

    The algorithm weights each month by:
    - Number of workdays (excluding weekends, holidays, vacation)
    - Intensity setting (normal=1.0, light=0.75, very_light=0.5)

    Months with more weighted workdays receive proportionally more hours.

    Args:
        year_config: The year configuration with holidays, vacations, and intensities
        end_month: Last month to include (1-12). If None, includes all 12 months.
        target_hours: Total hours to distribute. If None, uses year_config.annual_target.

    Returns:
        Dictionary mapping month number (1-12) to target hours for that month

    Examples:
        >>> targets = calculate_monthly_targets(year_config)
        >>> sum(targets.values())  # Should equal annual_target
        1800.0
    """
    # Determine the range of months to calculate
    start_month = 1
    last_month = end_month if end_month is not None else 12

    # Use provided target or the year's annual target
    total_target = target_hours if target_hours is not None else year_config.annual_target

    # Extract holidays and vacation days for efficient lookup
    holidays, vacation_days = extract_holidays_and_vacations(year_config)

    # Calculate weighted workdays for each month
    monthly_weighted_workdays: dict[int, float] = {}
    monthly_raw_workdays: dict[int, int] = {}

    for month in range(start_month, last_month + 1):
        # Get actual workdays for this month
        workdays = get_workdays_in_month(
            year_config.year,
            month,
            holidays,
            vacation_days
        )
        raw_workday_count = len(workdays)
        monthly_raw_workdays[month] = raw_workday_count

        # Apply intensity weight
        intensity = get_month_intensity(year_config, month)
        weight = get_intensity_weight(intensity)
        weighted_workdays = raw_workday_count * weight

        monthly_weighted_workdays[month] = weighted_workdays

    # Calculate total weighted workdays
    total_weighted = sum(monthly_weighted_workdays.values())

    # Distribute target proportionally
    monthly_targets: dict[int, float] = {}

    if total_weighted == 0:
        # Edge case: no workdays at all (unlikely but handle gracefully)
        # Distribute evenly across months
        hours_per_month = total_target / (last_month - start_month + 1)
        for month in range(start_month, last_month + 1):
            monthly_targets[month] = hours_per_month
    else:
        for month in range(start_month, last_month + 1):
            proportion = monthly_weighted_workdays[month] / total_weighted
            monthly_targets[month] = total_target * proportion

    return monthly_targets


def calculate_monthly_targets_for_plan(
    year_config: YearConfig,
    plan_config: PlanConfig
) -> dict[int, float]:
    """
    Calculate monthly targets for a specific plan type.

    Different plan types have different distribution strategies:
    - Firm: Fixed 150 hours/month regardless of workdays/intensity
    - Realistic: Weighted distribution across the full year
    - Optimistic: Compressed timeline, may end early with maintenance hours after

    Args:
        year_config: The year configuration
        plan_config: The plan configuration specifying type and target date

    Returns:
        Dictionary mapping month number (1-12) to target hours

    Examples:
        >>> targets = calculate_monthly_targets_for_plan(year_config, firm_plan)
        >>> targets[6]  # June
        150.0
    """
    if plan_config.plan_type == PlanType.FIRM:
        # Firm plan: fixed 150 hours per month, all 12 months
        return {month: 150.0 for month in range(1, 13)}

    # For Realistic and Optimistic plans, we need to consider the target date
    target_date = plan_config.target_date
    target_month = target_date.month
    target_year = target_date.year

    # Determine if we're targeting the same year
    if target_year != year_config.year:
        # Target is in a different year, use full year
        target_month = 12

    if plan_config.plan_type == PlanType.REALISTIC:
        # Realistic plan: distribute across full year with intensity weights
        return calculate_monthly_targets(year_config, end_month=12)

    # Optimistic plan: may have early end date and maintenance hours after
    if plan_config.plan_type == PlanType.OPTIMISTIC:
        annual_target = year_config.annual_target

        # Check if there are maintenance hours after the target date
        if plan_config.target_daily_hours_after and target_month < 12:
            # Calculate hours to reserve for post-target maintenance
            holidays, vacation_days = extract_holidays_and_vacations(year_config)
            maintenance_hours = 0.0

            for month in range(target_month + 1, 13):
                workdays = get_workdays_in_month(
                    year_config.year,
                    month,
                    holidays,
                    vacation_days
                )
                maintenance_hours += len(workdays) * plan_config.target_daily_hours_after

            # Distribute remaining hours across months up to target
            hours_before_target = annual_target - maintenance_hours

            # Get the distribution for months before target
            targets = calculate_monthly_targets(
                year_config,
                end_month=target_month,
                target_hours=hours_before_target
            )

            # Add maintenance months
            for month in range(target_month + 1, 13):
                workdays = get_workdays_in_month(
                    year_config.year,
                    month,
                    holidays,
                    vacation_days
                )
                targets[month] = len(workdays) * plan_config.target_daily_hours_after

            return targets
        else:
            # No maintenance hours - just compress into earlier months
            return calculate_monthly_targets(
                year_config,
                end_month=target_month,
                target_hours=annual_target
            )

    # Fallback (shouldn't reach here with valid plan types)
    return calculate_monthly_targets(year_config)


def validate_plan_feasibility(
    monthly_targets: dict[int, float],
    year_config: YearConfig
) -> list[PlanWarning]:
    """
    Check if a plan is achievable without exceeding daily hour limits.

    A plan is considered infeasible if any month would require more than
    9.5 hours/day average to hit the target.

    Args:
        monthly_targets: Dictionary of month number to target hours
        year_config: The year configuration for workday calculation

    Returns:
        List of PlanWarning objects for months that exceed the limit.
        Empty list if the plan is feasible.

    Examples:
        >>> warnings = validate_plan_feasibility(targets, year_config)
        >>> if warnings:
        ...     print("Plan has issues:", warnings[0].message)
    """
    warnings: list[PlanWarning] = []

    holidays, vacation_days = extract_holidays_and_vacations(year_config)

    for month, target_hours in monthly_targets.items():
        workdays = get_workdays_in_month(
            year_config.year,
            month,
            holidays,
            vacation_days
        )
        workday_count = len(workdays)

        if workday_count == 0:
            # No workdays - can't bill anything, but no daily hour issue
            if target_hours > 0:
                warnings.append(PlanWarning(
                    month=month,
                    required_daily_hours=float('inf'),
                    workdays_in_month=0,
                    message=f"Month {month} has no workdays but requires {target_hours:.1f} hours"
                ))
            continue

        required_daily = target_hours / workday_count

        if required_daily > MAX_DAILY_HOURS:
            month_name = datetime.date(year_config.year, month, 1).strftime("%B")
            warnings.append(PlanWarning(
                month=month,
                required_daily_hours=round(required_daily, 2),
                workdays_in_month=workday_count,
                message=(
                    f"{month_name} requires {required_daily:.1f} hours/day "
                    f"({target_hours:.0f} hours over {workday_count} workdays). "
                    f"Consider adjusting your plan to keep daily targets under {MAX_DAILY_HOURS} hours."
                )
            ))

    return warnings


def get_monthly_breakdown(
    year_config: YearConfig,
    plan_config: PlanConfig
) -> list[MonthlyTarget]:
    """
    Get a complete breakdown of monthly targets with all relevant details.

    This is a convenience function that combines target calculation with
    workday counts and daily targets for display purposes.

    Args:
        year_config: The year configuration
        plan_config: The plan configuration

    Returns:
        List of MonthlyTarget objects, one per month (1-12), sorted by month

    Examples:
        >>> breakdown = get_monthly_breakdown(year_config, realistic_plan)
        >>> january = breakdown[0]
        >>> print(f"January: {january.target_hours:.1f} hours over {january.workdays} days")
    """
    monthly_targets = calculate_monthly_targets_for_plan(year_config, plan_config)
    holidays, vacation_days = extract_holidays_and_vacations(year_config)

    breakdown: list[MonthlyTarget] = []

    for month in range(1, 13):
        workdays = get_workdays_in_month(
            year_config.year,
            month,
            holidays,
            vacation_days
        )
        workday_count = len(workdays)

        target_hours = monthly_targets.get(month, 0.0)
        daily_target = target_hours / workday_count if workday_count > 0 else 0.0
        intensity = get_month_intensity(year_config, month)

        breakdown.append(MonthlyTarget(
            month=month,
            target_hours=target_hours,
            workdays=workday_count,
            daily_target=round(daily_target, 2),
            intensity=intensity
        ))

    return breakdown
