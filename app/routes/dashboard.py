"""
Dashboard routes for the Billable Hours Planner.

This module contains the main dashboard view that users see when they
open the application. It displays today's target, progress, and plan statuses.
"""

import datetime
from typing import Optional

from flask import Blueprint, flash, redirect, render_template, url_for

from app.models import CatchUpSprint, PlanConfig, PlanType, SprintStatus, YearConfig
from app.services.calculator import (
    DailyTargetResult,
    PlanStatus,
    calculate_daily_target,
    calculate_plan_status,
    get_hours_billed_in_month,
    get_hours_billed_to_date,
)
from app.services.calendar_utils import (
    get_remaining_workdays_in_month,
    get_workdays_in_month,
    get_workdays_in_range,
)
from app.services.planner import (
    calculate_monthly_targets_for_plan,
    extract_holidays_and_vacations,
)
from app.services.catchup import (
    calculate_sprint_progress,
    mark_sprint_completed,
)


# Create the dashboard blueprint
dashboard_bp = Blueprint('dashboard', __name__)


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def get_week_boundaries(date: datetime.date) -> tuple[datetime.date, datetime.date]:
    """
    Get Monday and Sunday of the week containing the given date.

    Args:
        date: Any date within the target week

    Returns:
        Tuple of (monday, sunday) dates for that week
    """
    # weekday() returns 0 for Monday, 6 for Sunday
    days_since_monday = date.weekday()
    monday = date - datetime.timedelta(days=days_since_monday)
    sunday = monday + datetime.timedelta(days=6)
    return monday, sunday


def calculate_weekly_progress(
    year_config: YearConfig,
    plan_config: PlanConfig,
    today: datetime.date
) -> dict:
    """
    Calculate hours billed and target for the current week.

    Args:
        year_config: The year configuration with entries
        plan_config: The plan to calculate against (usually Realistic)
        today: Current date

    Returns:
        Dict with hours_billed, target, and days_remaining
    """
    monday, sunday = get_week_boundaries(today)
    holidays, vacation_days = extract_holidays_and_vacations(year_config)

    # Get hours billed this week
    hours_billed = sum(
        entry.hours_billed
        for entry in year_config.daily_entries
        if monday <= entry.date <= sunday
    )

    # Get workdays in this week
    workdays_this_week = get_workdays_in_range(monday, sunday, holidays, vacation_days)

    # Calculate weekly target based on daily target for each workday
    # For simplicity, use the plan's average daily target for the month
    monthly_targets = calculate_monthly_targets_for_plan(year_config, plan_config)
    month_target = monthly_targets.get(today.month, 0.0)
    month_workdays = get_workdays_in_month(today.year, today.month, holidays, vacation_days)

    if len(month_workdays) > 0:
        avg_daily_target = month_target / len(month_workdays)
    else:
        avg_daily_target = 0.0

    weekly_target = avg_daily_target * len(workdays_this_week)

    # Count remaining workdays in week (including today if it's a workday)
    remaining_workdays = [d for d in workdays_this_week if d >= today]

    return {
        'hours_billed': round(hours_billed, 1),
        'target': round(weekly_target, 1),
        'days_remaining': len(remaining_workdays),
    }


def calculate_monthly_progress(
    year_config: YearConfig,
    plan_config: PlanConfig,
    today: datetime.date
) -> dict:
    """
    Calculate monthly progress including hours billed, target, and percentage.

    Args:
        year_config: The year configuration with entries
        plan_config: The plan to calculate against
        today: Current date

    Returns:
        Dict with hours_billed, target, progress_pct, days_elapsed, days_total
    """
    holidays, vacation_days = extract_holidays_and_vacations(year_config)

    # Get hours billed this month
    hours_billed = get_hours_billed_in_month(year_config, today.year, today.month)

    # Get monthly target
    monthly_targets = calculate_monthly_targets_for_plan(year_config, plan_config)
    target = monthly_targets.get(today.month, 0.0)

    # Get workday counts
    month_start = datetime.date(today.year, today.month, 1)
    all_workdays = get_workdays_in_month(today.year, today.month, holidays, vacation_days)
    elapsed_workdays = get_workdays_in_range(month_start, today, holidays, vacation_days)

    # Calculate progress percentage (based on target, not time)
    if target > 0:
        progress_pct = min(100.0, (hours_billed / target) * 100)
    else:
        progress_pct = 100.0 if hours_billed > 0 else 0.0

    return {
        'hours_billed': round(hours_billed, 1),
        'target': round(target, 1),
        'progress_pct': round(progress_pct, 1),
        'days_elapsed': len(elapsed_workdays),
        'days_total': len(all_workdays),
    }


def get_plan_display_name(plan_type: PlanType) -> str:
    """Get human-readable name for a plan type."""
    names = {
        PlanType.FIRM: "Firm Requirements",
        PlanType.REALISTIC: "Realistic",
        PlanType.OPTIMISTIC: "Optimistic",
    }
    return names.get(plan_type, str(plan_type.value))


def get_status_color_classes(status_label: str) -> dict:
    """
    Get Tailwind CSS classes for status display.

    Returns dict with 'bg', 'text', and 'border' classes.
    """
    if status_label in ("Ahead", "On track"):
        return {
            'bg': 'bg-green-50',
            'text': 'text-green-700',
            'border': 'border-green-200',
            'badge_bg': 'bg-green-100',
            'badge_text': 'text-green-800',
        }
    elif status_label == "Slightly behind":
        return {
            'bg': 'bg-amber-50',
            'text': 'text-amber-700',
            'border': 'border-amber-200',
            'badge_bg': 'bg-amber-100',
            'badge_text': 'text-amber-800',
        }
    else:  # Catch-up recommended
        return {
            'bg': 'bg-red-50',
            'text': 'text-red-700',
            'border': 'border-red-200',
            'badge_bg': 'bg-red-100',
            'badge_text': 'text-red-800',
        }


def get_chart_data(year_config: YearConfig, today: datetime.date) -> dict:
    """
    Prepare data for the monthly Chart.js visualization.

    Returns dict with labels (days) and datasets for actual hours and targets.
    """
    import calendar

    holidays, vacation_days = extract_holidays_and_vacations(year_config)

    # Get all days in the current month
    _, days_in_month = calendar.monthrange(today.year, today.month)

    # Create a map of date -> hours billed
    hours_by_date = {
        entry.date: entry.hours_billed
        for entry in year_config.daily_entries
        if entry.date.year == today.year and entry.date.month == today.month
    }

    # Get workdays for this month (to identify which days are workdays)
    workdays = set(get_workdays_in_month(today.year, today.month, holidays, vacation_days))

    labels = []
    actual_hours = []
    is_workday = []

    for day in range(1, days_in_month + 1):
        date = datetime.date(today.year, today.month, day)
        labels.append(day)

        if date <= today:
            actual_hours.append(hours_by_date.get(date, 0))
        else:
            actual_hours.append(None)  # Future days have no data

        is_workday.append(date in workdays)

    return {
        'labels': labels,
        'actual_hours': actual_hours,
        'is_workday': is_workday,
        'today_day': today.day,
    }


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@dashboard_bp.route('/')
def index():
    """
    Display the main dashboard.

    This is the primary view users interact with daily. It shows:
    - Today's billing target
    - Weekly and monthly progress
    - Status for each plan (Firm, Optimistic, Realistic)
    - Quick entry form for logging hours

    Returns:
        Rendered dashboard template, or redirect to setup if not configured
    """
    today = datetime.date.today()

    # Try to get current year's config, or fall back to most recent
    year_config = YearConfig.query.filter_by(year=today.year).first()

    if not year_config:
        # Try to find any existing config
        year_config = YearConfig.query.order_by(YearConfig.year.desc()).first()

    if not year_config:
        # No configuration exists, redirect to setup
        flash('Please complete setup to start tracking your hours.', 'info')
        return redirect(url_for('setup.index'))

    # Get all plan configs
    plan_configs = {
        pc.plan_type: pc
        for pc in year_config.plan_configs
    }

    # Build plan data for each plan type
    # Order: Firm, Realistic (primary), Optimistic
    plan_order = [PlanType.FIRM, PlanType.REALISTIC, PlanType.OPTIMISTIC]
    plans = []

    realistic_plan = plan_configs.get(PlanType.REALISTIC)

    for plan_type in plan_order:
        plan_config = plan_configs.get(plan_type)
        if not plan_config:
            continue

        daily_target = calculate_daily_target(year_config, plan_config, today)
        status = calculate_plan_status(year_config, plan_config, today)
        colors = get_status_color_classes(status.status_label)

        plans.append({
            'plan_config': plan_config,
            'plan_name': get_plan_display_name(plan_type),
            'plan_type': plan_type.value,
            'daily_target': daily_target,
            'status': status,
            'is_primary': plan_type == PlanType.REALISTIC,
            'colors': colors,
        })

    # Calculate weekly and monthly progress using Realistic plan
    if realistic_plan:
        weekly = calculate_weekly_progress(year_config, realistic_plan, today)
        monthly = calculate_monthly_progress(year_config, realistic_plan, today)
    else:
        # Fallback if no realistic plan
        weekly = {'hours_billed': 0, 'target': 0, 'days_remaining': 0}
        monthly = {'hours_billed': 0, 'target': 0, 'progress_pct': 0,
                   'days_elapsed': 0, 'days_total': 0}

    # Check for active catch-up sprint and calculate progress
    active_sprint = CatchUpSprint.query.filter_by(
        year_config_id=year_config.id,
        status=SprintStatus.ACTIVE
    ).first()

    sprint_progress = None
    if active_sprint:
        sprint_progress = calculate_sprint_progress(active_sprint, year_config, today)

        # Auto-complete if target achieved
        if sprint_progress.is_completed:
            try:
                mark_sprint_completed(active_sprint)
                flash(
                    f"Sprint complete! You hit your target of {active_sprint.target_hours:.1f} hours!",
                    "success"
                )
                active_sprint = None
                sprint_progress = None
            except Exception:
                db.session.rollback()
                # Continue showing the page even if auto-complete fails

    # Get chart data
    chart_data = get_chart_data(year_config, today)

    # Get today's hours if already entered
    today_entry = next(
        (e for e in year_config.daily_entries if e.date == today),
        None
    )

    return render_template(
        'dashboard.html',
        year_config=year_config,
        today=today,
        plans=plans,
        weekly=weekly,
        monthly=monthly,
        active_sprint=active_sprint,
        sprint_progress=sprint_progress,
        chart_data=chart_data,
        today_entry=today_entry,
    )
