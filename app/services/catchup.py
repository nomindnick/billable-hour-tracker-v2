"""
Catch-up sprint service for recovery planning.

This module provides functions for calculating and managing catch-up sprints,
which are time-limited intensive billing periods to help users recover from
being behind on their billing plans.

Key features:
- Preview sprint parameters before creation
- Calculate feasible daily targets
- Support for optional weekend billing
- Supportive messaging that encourages recovery without judgment
"""

import datetime
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from app import db
from app.models import CatchUpSprint, PlanConfig, PlanType, SprintStatus, YearConfig
from app.services.calculator import calculate_plan_status, PlanStatus
from app.services.calendar_utils import (
    get_workdays_in_range,
    get_weekend_days_in_range,
)
from app.services.planner import extract_holidays_and_vacations, MAX_DAILY_HOURS


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

# Maximum hours for weekend days during sprints
MAX_WEEKEND_HOURS = 4.0

# Thresholds for sprint feasibility messaging
COMFORTABLE_TARGET = 7.5   # Daily target considered comfortable
CHALLENGING_TARGET = 9.0   # Daily target that's challenging but doable


# -----------------------------------------------------------------------------
# Data Classes
# -----------------------------------------------------------------------------

@dataclass
class SprintPreview:
    """
    Preview of a potential catch-up sprint before creation.

    This provides users with full visibility into what a sprint would
    require before they commit to it.

    Attributes:
        hours_behind: How far behind the target plan (positive value)
        target_hours: Total hours to bill during sprint
        weekday_target: Daily target for weekdays
        weekend_target: Daily target for weekends (0 if not included)
        total_workdays: Number of weekdays in sprint
        total_weekend_days: Number of weekend days in sprint
        is_feasible: True if weekday_target <= MAX_DAILY_HOURS
        message: User-friendly message about the sprint
        message_type: Type of message ('success', 'warning', 'error')
        start_date: When the sprint would begin
        end_date: When the sprint would end
    """
    hours_behind: float
    target_hours: float
    weekday_target: float
    weekend_target: float
    total_workdays: int
    total_weekend_days: int
    is_feasible: bool
    message: str
    message_type: str  # 'success', 'warning', 'error'
    start_date: datetime.date
    end_date: datetime.date


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def get_plan_config_by_type(
    year_config: YearConfig,
    plan_type: PlanType
) -> Optional[PlanConfig]:
    """
    Get the PlanConfig for a specific plan type.

    Args:
        year_config: The year configuration
        plan_type: The type of plan to find

    Returns:
        The matching PlanConfig, or None if not found
    """
    for plan in year_config.plan_configs:
        if plan.plan_type == plan_type:
            return plan
    return None


def get_sprint_message(
    weekday_target: float,
    is_feasible: bool,
    hours_behind: float
) -> tuple[str, str]:
    """
    Generate an encouraging message based on sprint parameters.

    Args:
        weekday_target: The calculated daily target for weekdays
        is_feasible: Whether the sprint is feasible
        hours_behind: How many hours behind the user is

    Returns:
        Tuple of (message, message_type)
    """
    if not is_feasible:
        return (
            "This sprint would require more than 9.5 hours per day on weekdays. "
            "Try a longer duration or include weekend billing to make it achievable.",
            "error"
        )

    if weekday_target <= COMFORTABLE_TARGET:
        return (
            f"Very manageable at {weekday_target:.1f} hours/day. "
            "You'll be caught up in no time!",
            "success"
        )

    if weekday_target <= CHALLENGING_TARGET:
        return (
            f"Challenging but doable at {weekday_target:.1f} hours/day. "
            "You've got this!",
            "warning"
        )

    # Between 9.0 and 9.5 - maximum stretch
    return (
        f"This is a stretch at {weekday_target:.1f} hours/day, "
        "but it's within reach. Consider adding weekend hours to ease the load.",
        "warning"
    )


# -----------------------------------------------------------------------------
# Core Functions
# -----------------------------------------------------------------------------

def calculate_sprint_preview(
    year_config: YearConfig,
    plan_type: PlanType,
    duration_weeks: int,
    weekend_hours: float = 0.0,
    as_of_date: Optional[datetime.date] = None
) -> SprintPreview:
    """
    Calculate a preview of what a catch-up sprint would require.

    This function does not create a sprint - it only calculates what
    the sprint parameters would be, allowing users to adjust before
    committing.

    Args:
        year_config: The year configuration
        plan_type: Which plan to catch up to (OPTIMISTIC or REALISTIC)
        duration_weeks: How many weeks the sprint should last (1-6)
        weekend_hours: Hours to bill per weekend day (0-4), 0 to exclude weekends
        as_of_date: Calculate from this date (defaults to today)

    Returns:
        SprintPreview with all calculated parameters and feasibility assessment

    Examples:
        >>> preview = calculate_sprint_preview(year_config, PlanType.REALISTIC, 2, 3.0)
        >>> preview.is_feasible
        True
        >>> preview.weekday_target
        8.2
    """
    if as_of_date is None:
        as_of_date = datetime.date.today()

    # Validate inputs
    duration_weeks = max(1, min(6, duration_weeks))
    weekend_hours = max(0.0, min(MAX_WEEKEND_HOURS, weekend_hours))

    # Get the plan config
    plan_config = get_plan_config_by_type(year_config, plan_type)
    if plan_config is None:
        # Return an error preview if plan not found
        return SprintPreview(
            hours_behind=0.0,
            target_hours=0.0,
            weekday_target=0.0,
            weekend_target=0.0,
            total_workdays=0,
            total_weekend_days=0,
            is_feasible=False,
            message="Plan configuration not found.",
            message_type="error",
            start_date=as_of_date,
            end_date=as_of_date
        )

    # Calculate how far behind
    plan_status = calculate_plan_status(year_config, plan_config, as_of_date)
    hours_behind = abs(min(0.0, plan_status.hours_ahead_or_behind))

    # If not behind, no sprint needed
    if hours_behind <= 0:
        return SprintPreview(
            hours_behind=0.0,
            target_hours=0.0,
            weekday_target=0.0,
            weekend_target=0.0,
            total_workdays=0,
            total_weekend_days=0,
            is_feasible=True,
            message="You're on track! No catch-up sprint needed.",
            message_type="success",
            start_date=as_of_date,
            end_date=as_of_date
        )

    # Calculate sprint dates
    start_date = as_of_date
    end_date = as_of_date + timedelta(weeks=duration_weeks) - timedelta(days=1)

    # Get workdays and weekend days in the sprint period
    holidays, vacation_days = extract_holidays_and_vacations(year_config)
    workdays = get_workdays_in_range(start_date, end_date, holidays, vacation_days)
    weekend_days = get_weekend_days_in_range(start_date, end_date)

    total_workdays = len(workdays)
    total_weekend_days = len(weekend_days)

    # Calculate targets
    include_weekends = weekend_hours > 0
    total_weekend_hours = total_weekend_days * weekend_hours if include_weekends else 0.0
    weekday_hours_needed = hours_behind - total_weekend_hours

    # Handle edge case: weekend hours alone cover the deficit
    if weekday_hours_needed <= 0:
        weekday_target = 0.0
        is_feasible = True
    elif total_workdays == 0:
        # No workdays in sprint period
        weekday_target = float('inf')
        is_feasible = False
    else:
        weekday_target = weekday_hours_needed / total_workdays
        is_feasible = weekday_target <= MAX_DAILY_HOURS

    # Round for display
    weekday_target = round(weekday_target, 2) if weekday_target != float('inf') else 99.9

    # Generate message
    message, message_type = get_sprint_message(weekday_target, is_feasible, hours_behind)

    return SprintPreview(
        hours_behind=round(hours_behind, 2),
        target_hours=round(hours_behind, 2),  # Target is to eliminate the deficit
        weekday_target=weekday_target,
        weekend_target=weekend_hours if include_weekends else 0.0,
        total_workdays=total_workdays,
        total_weekend_days=total_weekend_days if include_weekends else 0,
        is_feasible=is_feasible,
        message=message,
        message_type=message_type,
        start_date=start_date,
        end_date=end_date
    )


def create_catch_up_sprint(
    year_config: YearConfig,
    plan_type: PlanType,
    duration_weeks: int,
    weekend_hours: float = 0.0,
    as_of_date: Optional[datetime.date] = None
) -> CatchUpSprint:
    """
    Create a new catch-up sprint and save it to the database.

    This marks any existing active sprint as 'revised' before creating
    the new one.

    Args:
        year_config: The year configuration
        plan_type: Which plan to catch up to (OPTIMISTIC or REALISTIC)
        duration_weeks: How many weeks the sprint should last (1-6)
        weekend_hours: Hours to bill per weekend day (0-4), 0 to exclude weekends
        as_of_date: Start date for the sprint (defaults to today)

    Returns:
        The newly created CatchUpSprint

    Raises:
        ValueError: If the sprint is not feasible or plan type is invalid

    Examples:
        >>> sprint = create_catch_up_sprint(year_config, PlanType.REALISTIC, 2, 3.0)
        >>> sprint.status
        SprintStatus.ACTIVE
    """
    if as_of_date is None:
        as_of_date = datetime.date.today()

    # Validate plan type
    if plan_type == PlanType.FIRM:
        raise ValueError("Cannot create catch-up sprint for Firm plan. Use Optimistic or Realistic.")

    # Get the preview to calculate parameters
    preview = calculate_sprint_preview(
        year_config,
        plan_type,
        duration_weeks,
        weekend_hours,
        as_of_date
    )

    if not preview.is_feasible:
        raise ValueError(
            f"Sprint is not feasible: {preview.message}. "
            "Try a longer duration or include weekend billing."
        )

    if preview.hours_behind <= 0:
        raise ValueError("No catch-up needed - you're on track!")

    # Mark any existing active sprint as revised
    existing_active = CatchUpSprint.query.filter_by(
        year_config_id=year_config.id,
        status=SprintStatus.ACTIVE
    ).first()

    if existing_active:
        existing_active.status = SprintStatus.REVISED
        existing_active.completed_at = datetime.datetime.utcnow()

    # Create the new sprint
    sprint = CatchUpSprint(
        year_config_id=year_config.id,
        target_plan=plan_type,
        start_date=preview.start_date,
        end_date=preview.end_date,
        target_hours=preview.target_hours,
        status=SprintStatus.ACTIVE
    )

    db.session.add(sprint)
    db.session.commit()

    return sprint


def get_active_sprint(year_config: YearConfig) -> Optional[CatchUpSprint]:
    """
    Get the currently active catch-up sprint, if any.

    Args:
        year_config: The year configuration

    Returns:
        The active CatchUpSprint, or None if no sprint is active
    """
    return CatchUpSprint.query.filter_by(
        year_config_id=year_config.id,
        status=SprintStatus.ACTIVE
    ).first()


def get_plan_statuses(
    year_config: YearConfig,
    as_of_date: Optional[datetime.date] = None
) -> dict[PlanType, PlanStatus]:
    """
    Get the status for all plans (Optimistic and Realistic).

    Args:
        year_config: The year configuration
        as_of_date: Calculate status as of this date (defaults to today)

    Returns:
        Dict mapping PlanType to PlanStatus for Optimistic and Realistic plans
    """
    if as_of_date is None:
        as_of_date = datetime.date.today()

    statuses = {}

    for plan_config in year_config.plan_configs:
        if plan_config.plan_type in (PlanType.OPTIMISTIC, PlanType.REALISTIC):
            statuses[plan_config.plan_type] = calculate_plan_status(
                year_config,
                plan_config,
                as_of_date
            )

    return statuses
