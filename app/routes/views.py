"""
Views routes for Monthly and History pages.

This module provides calendar and historical views of billable hours,
complementing the main dashboard with detailed monthly breakdowns
and complete entry history.
"""

import calendar
import datetime
from typing import Optional

from flask import Blueprint, flash, redirect, render_template, url_for

from app.models import PlanConfig, PlanType, YearConfig
from app.services.calculator import (
    calculate_daily_target,
    calculate_plan_status,
    get_hours_billed_in_month,
    get_hours_billed_to_date,
)
from app.services.calendar_utils import (
    get_workdays_in_month,
    is_workday,
)
from app.services.planner import (
    calculate_monthly_targets_for_plan,
    extract_holidays_and_vacations,
)


# Create the views blueprint
views_bp = Blueprint('views', __name__)


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def get_month_name(month: int) -> str:
    """Get the full month name for a month number (1-12)."""
    return calendar.month_name[month]


def get_day_status(
    hours: Optional[float],
    target: Optional[float],
    is_past: bool,
    is_workday_flag: bool
) -> str:
    """
    Determine the status of a day for color-coding.

    Returns one of:
    - 'met': Entry exists and hours >= target
    - 'behind': Entry exists and hours < target
    - 'missed': No entry, past workday
    - 'future': Future workday
    - 'off': Weekend, holiday, or vacation
    """
    if not is_workday_flag:
        return 'off'

    if hours is not None:
        if target is not None and hours >= target:
            return 'met'
        else:
            return 'behind'
    else:
        if is_past:
            return 'missed'
        else:
            return 'future'


def get_day_colors(status: str) -> dict:
    """Get Tailwind CSS classes for a day status."""
    colors = {
        'met': {
            'bg': 'bg-green-100',
            'text': 'text-green-800',
            'border': 'border-green-200',
        },
        'behind': {
            'bg': 'bg-amber-100',
            'text': 'text-amber-800',
            'border': 'border-amber-200',
        },
        'missed': {
            'bg': 'bg-gray-100',
            'text': 'text-gray-500',
            'border': 'border-gray-200',
        },
        'future': {
            'bg': 'bg-white',
            'text': 'text-gray-700',
            'border': 'border-gray-200',
        },
        'off': {
            'bg': 'bg-slate-50',
            'text': 'text-slate-400',
            'border': 'border-slate-100',
        },
    }
    return colors.get(status, colors['future'])


def get_calendar_data(
    year_config: YearConfig,
    year: int,
    month: int,
    plan_config: PlanConfig,
    today: datetime.date
) -> list[list[Optional[dict]]]:
    """
    Build calendar grid with day data for template rendering.

    Uses calendar.monthcalendar() to get week structure, then populates
    each day with hours, target, status, and styling.

    Args:
        year_config: The year configuration with entries and settings
        year: Calendar year to display
        month: Month number (1-12) to display
        plan_config: Plan to use for daily targets
        today: Current date for determining past/future

    Returns:
        List of weeks, each week is a list of 7 day dicts (or None for empty cells).
        Day dicts contain: day, date, hours, target, status, colors, is_today
    """
    weeks = calendar.monthcalendar(year, month)  # 0 = days outside month
    holidays, vacations = extract_holidays_and_vacations(year_config)

    # Build lookup of date -> entry hours
    entries_by_date = {
        entry.date: entry.hours_billed
        for entry in year_config.daily_entries
        if entry.date.year == year and entry.date.month == month
    }

    # Get monthly targets for calculating daily target
    monthly_targets = calculate_monthly_targets_for_plan(year_config, plan_config)
    month_target = monthly_targets.get(month, 0.0)
    workdays = get_workdays_in_month(year, month, holidays, vacations)
    workday_count = len(workdays)

    # Calculate average daily target for the month
    if workday_count > 0:
        avg_daily_target = month_target / workday_count
    else:
        avg_daily_target = 0.0

    result = []
    for week in weeks:
        week_data = []
        for day_num in week:
            if day_num == 0:
                week_data.append(None)  # Outside month
            else:
                date_obj = datetime.date(year, month, day_num)
                hours = entries_by_date.get(date_obj)
                is_work = is_workday(date_obj, holidays, vacations)
                is_past = date_obj < today
                is_today_flag = date_obj == today

                # Target is only relevant for workdays
                target = round(avg_daily_target, 1) if is_work else None

                status = get_day_status(hours, target, is_past, is_work)
                colors = get_day_colors(status)

                # Calculate difference for display
                if hours is not None and target is not None:
                    diff = round(hours - target, 1)
                else:
                    diff = None

                week_data.append({
                    'day': day_num,
                    'date': date_obj,
                    'hours': hours,
                    'target': target,
                    'diff': diff,
                    'status': status,
                    'colors': colors,
                    'is_today': is_today_flag,
                    'is_workday': is_work,
                    'is_holiday': date_obj in holidays,
                    'is_vacation': date_obj in vacations,
                    'is_weekend': date_obj.weekday() >= 5,
                })
        result.append(week_data)
    return result


def get_month_summary(
    year_config: YearConfig,
    year: int,
    month: int,
    plan_config: PlanConfig,
    today: datetime.date
) -> dict:
    """
    Calculate summary statistics for a month.

    Args:
        year_config: The year configuration
        year: Calendar year
        month: Month number (1-12)
        plan_config: Plan to use for targets
        today: Current date

    Returns:
        Dict with: month_name, year, target, actual, diff, progress_pct,
                   workdays_total, workdays_elapsed
    """
    holidays, vacations = extract_holidays_and_vacations(year_config)

    # Get hours billed
    actual = get_hours_billed_in_month(year_config, year, month)

    # Get monthly target
    monthly_targets = calculate_monthly_targets_for_plan(year_config, plan_config)
    target = monthly_targets.get(month, 0.0)

    # Get workday counts
    workdays = get_workdays_in_month(year, month, holidays, vacations)
    workdays_total = len(workdays)

    # Count elapsed workdays
    if year == today.year and month == today.month:
        workdays_elapsed = sum(1 for d in workdays if d <= today)
    elif datetime.date(year, month, 1) < today:
        workdays_elapsed = workdays_total
    else:
        workdays_elapsed = 0

    # Calculate progress percentage
    if target > 0:
        progress_pct = min(100.0, (actual / target) * 100)
    else:
        progress_pct = 100.0 if actual > 0 else 0.0

    # Calculate difference
    diff = actual - target

    return {
        'month_name': get_month_name(month),
        'month': month,
        'year': year,
        'target': round(target, 1),
        'actual': round(actual, 1),
        'diff': round(diff, 1),
        'progress_pct': round(progress_pct, 1),
        'workdays_total': workdays_total,
        'workdays_elapsed': workdays_elapsed,
    }


def get_history_data(
    year_config: YearConfig,
    plan_config: PlanConfig,
    today: datetime.date
) -> dict:
    """
    Get all entries with targets for history view.

    Args:
        year_config: The year configuration
        plan_config: Plan to use for targets
        today: Current date

    Returns:
        Dict with:
        - 'entries': List of entry dicts sorted by date descending
        - 'monthly_subtotals': List of monthly summary dicts
        - 'ytd': Dict with YTD totals
    """
    holidays, vacations = extract_holidays_and_vacations(year_config)
    monthly_targets = calculate_monthly_targets_for_plan(year_config, plan_config)

    # Build entries list
    entries = []
    for entry in year_config.daily_entries:
        month = entry.date.month
        workdays = get_workdays_in_month(entry.date.year, month, holidays, vacations)
        month_target = monthly_targets.get(month, 0.0)

        if len(workdays) > 0:
            daily_target = month_target / len(workdays)
        else:
            daily_target = 0.0

        diff = entry.hours_billed - daily_target

        # Determine status
        if entry.hours_billed >= daily_target:
            status = 'met'
        else:
            status = 'behind'

        entries.append({
            'id': entry.id,
            'date': entry.date,
            'day_name': entry.date.strftime('%a'),
            'hours': entry.hours_billed,
            'target': round(daily_target, 1),
            'diff': round(diff, 1),
            'status': status,
            'month': month,
        })

    # Sort by date descending
    entries.sort(key=lambda x: x['date'], reverse=True)

    # Build monthly subtotals
    monthly_subtotals = []
    for month in range(1, 13):
        actual = get_hours_billed_in_month(year_config, year_config.year, month)
        target = monthly_targets.get(month, 0.0)
        workdays = get_workdays_in_month(year_config.year, month, holidays, vacations)

        # Only include months with entries or if month is in the past
        month_start = datetime.date(year_config.year, month, 1)
        if actual > 0 or month_start <= today:
            if target > 0:
                progress_pct = min(100.0, (actual / target) * 100)
            else:
                progress_pct = 100.0 if actual > 0 else 0.0

            monthly_subtotals.append({
                'month': month,
                'month_name': get_month_name(month),
                'workdays': len(workdays),
                'target': round(target, 1),
                'actual': round(actual, 1),
                'diff': round(actual - target, 1),
                'progress_pct': round(progress_pct, 1),
            })

    # YTD totals
    ytd_actual = get_hours_billed_to_date(year_config, today)
    annual_target = year_config.annual_target

    if annual_target > 0:
        ytd_pct = (ytd_actual / annual_target) * 100
    else:
        ytd_pct = 0.0

    ytd = {
        'actual': round(ytd_actual, 1),
        'target': annual_target,
        'remaining': round(annual_target - ytd_actual, 1),
        'progress_pct': round(ytd_pct, 1),
    }

    return {
        'entries': entries,
        'monthly_subtotals': monthly_subtotals,
        'ytd': ytd,
    }


def get_current_year_config() -> Optional[YearConfig]:
    """
    Get the current year's config or the most recent one.

    Returns:
        YearConfig if found, None otherwise
    """
    today = datetime.date.today()
    year_config = YearConfig.query.filter_by(year=today.year).first()

    if not year_config:
        year_config = YearConfig.query.order_by(YearConfig.year.desc()).first()

    return year_config


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@views_bp.route('/monthly')
def monthly():
    """
    Display current month calendar view.

    Redirects to monthly_specific with current year/month.
    """
    today = datetime.date.today()
    return redirect(url_for('views.monthly_specific', year=today.year, month=today.month))


@views_bp.route('/monthly/<int:year>/<int:month>')
def monthly_specific(year: int, month: int):
    """
    Display calendar view for a specific month.

    Shows a calendar grid with each day displaying:
    - Hours billed (if any)
    - Daily target
    - Color coding based on status

    Args:
        year: Calendar year to display
        month: Month number (1-12)

    Returns:
        Rendered monthly template or redirect to setup
    """
    # Validate month
    if not 1 <= month <= 12:
        flash('Invalid month. Please select a month between 1 and 12.', 'error')
        return redirect(url_for('views.monthly'))

    year_config = get_current_year_config()

    if not year_config:
        flash('Please complete setup to start tracking your hours.', 'info')
        return redirect(url_for('setup.index'))

    # Get realistic plan for target calculations
    realistic_plan = next(
        (pc for pc in year_config.plan_configs if pc.plan_type == PlanType.REALISTIC),
        None
    )

    if not realistic_plan:
        flash('No Realistic plan configured. Please complete setup.', 'error')
        return redirect(url_for('setup.index'))

    today = datetime.date.today()

    # Build calendar data
    calendar_weeks = get_calendar_data(year_config, year, month, realistic_plan, today)

    # Build month summary
    summary = get_month_summary(year_config, year, month, realistic_plan, today)

    # Calculate navigation - prev/next months
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    # Limit navigation to reasonable range (configured year ± 1)
    min_year = year_config.year - 1
    max_year = year_config.year + 1

    can_go_prev = prev_year >= min_year
    can_go_next = next_year <= max_year

    return render_template(
        'monthly.html',
        year_config=year_config,
        year=year,
        month=month,
        month_name=get_month_name(month),
        calendar_weeks=calendar_weeks,
        summary=summary,
        today=today,
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        can_go_prev=can_go_prev,
        can_go_next=can_go_next,
    )


@views_bp.route('/history')
def history():
    """
    Display complete entry history.

    Shows all daily entries in a table format with:
    - Monthly subtotals
    - YTD totals
    - Color coding for met/behind status

    Returns:
        Rendered history template or redirect to setup
    """
    year_config = get_current_year_config()

    if not year_config:
        flash('Please complete setup to start tracking your hours.', 'info')
        return redirect(url_for('setup.index'))

    # Get realistic plan for target calculations
    realistic_plan = next(
        (pc for pc in year_config.plan_configs if pc.plan_type == PlanType.REALISTIC),
        None
    )

    if not realistic_plan:
        flash('No Realistic plan configured. Please complete setup.', 'error')
        return redirect(url_for('setup.index'))

    today = datetime.date.today()

    # Get history data
    history_data = get_history_data(year_config, realistic_plan, today)

    # Get plan status for summary
    plan_status = calculate_plan_status(year_config, realistic_plan, today)

    return render_template(
        'history.html',
        year_config=year_config,
        entries=history_data['entries'],
        monthly_subtotals=history_data['monthly_subtotals'],
        ytd=history_data['ytd'],
        plan_status=plan_status,
        today=today,
    )
