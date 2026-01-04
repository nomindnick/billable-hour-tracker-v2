"""
Setup routes for the Billable Hours Planner.

This module contains the routes for the year setup wizard, where users
configure their annual target, holidays, vacation days, and plan settings.
"""

import datetime

import calendar
import json

from flask import Blueprint, flash, make_response, redirect, render_template, request, url_for

from app import db
from app.models import (
    HistoricalMonth,
    Holiday,
    IntensityLevel,
    MonthConfig,
    PlanConfig,
    PlanType,
    VacationDay,
    YearConfig,
)


# Create the setup blueprint
setup_bp = Blueprint('setup', __name__)


@setup_bp.route('/')
def index():
    """
    Display the year and target configuration form.

    This is the first step of the setup wizard. Users select which year
    to plan and set their annual billable hours target.
    """
    # Get the current year for the default selection
    current_year = datetime.date.today().year

    # Check if there's an existing configuration for the current year
    existing_config = YearConfig.query.filter_by(year=current_year).first()

    # Provide year options: last year, current year, next year
    year_options = [current_year - 1, current_year, current_year + 1]

    return render_template(
        'setup/year.html',
        year_options=year_options,
        current_year=current_year,
        existing_config=existing_config
    )


@setup_bp.route('/year', methods=['POST'])
def save_year():
    """
    Save the year configuration and proceed to holidays.

    Creates a new YearConfig if one doesn't exist for the selected year,
    or updates the existing one. Also creates default MonthConfig records
    (all months set to "normal" intensity) and default PlanConfig records.
    """
    # Get form data
    year = request.form.get('year', type=int)
    annual_target = request.form.get('annual_target', type=int)

    # Validate inputs
    if not year:
        flash('Please select a year.', 'error')
        return redirect(url_for('setup.index'))

    if not annual_target or annual_target < 1000 or annual_target > 3000:
        flash('Annual target must be between 1,000 and 3,000 hours.', 'error')
        return redirect(url_for('setup.index'))

    # Check if a configuration already exists for this year
    year_config = YearConfig.query.filter_by(year=year).first()

    if year_config:
        # Update existing configuration
        year_config.annual_target = annual_target
        flash(f'Updated configuration for {year}.', 'success')
    else:
        # Create new configuration
        year_config = YearConfig(year=year, annual_target=annual_target)
        db.session.add(year_config)
        db.session.flush()  # Get the ID for foreign key references

        # Create default MonthConfig records (all months = normal intensity)
        for month in range(1, 13):
            month_config = MonthConfig(
                year_config_id=year_config.id,
                month=month,
                intensity=IntensityLevel.NORMAL
            )
            db.session.add(month_config)

        # Create default PlanConfig records for all three plans
        year_end = datetime.date(year, 12, 31)

        # Firm plan: fixed target date of Dec 31
        firm_plan = PlanConfig(
            year_config_id=year_config.id,
            plan_type=PlanType.FIRM,
            target_date=year_end
        )
        db.session.add(firm_plan)

        # Realistic plan: target date of Dec 31
        realistic_plan = PlanConfig(
            year_config_id=year_config.id,
            plan_type=PlanType.REALISTIC,
            target_date=year_end
        )
        db.session.add(realistic_plan)

        # Optimistic plan: default to Nov 27 (Thanksgiving area)
        # Users can customize this in Sprint 3.3
        optimistic_target = datetime.date(year, 11, 27)
        optimistic_plan = PlanConfig(
            year_config_id=year_config.id,
            plan_type=PlanType.OPTIMISTIC,
            target_date=optimistic_target
        )
        db.session.add(optimistic_plan)

        flash(f'Created new configuration for {year}.', 'success')

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Something went wrong saving your configuration. Please try again.', 'error')
        return redirect(url_for('setup.index'))

    # Redirect to the mid-year start step
    return redirect(url_for('setup.midyear'))


# -----------------------------------------------------------------------------
# Mid-Year Start Routes
# -----------------------------------------------------------------------------

MONTH_NAMES = [
    (1, "January"), (2, "February"), (3, "March"), (4, "April"),
    (5, "May"), (6, "June"), (7, "July"), (8, "August"),
    (9, "September"), (10, "October"), (11, "November"), (12, "December")
]


@setup_bp.route('/midyear')
def midyear():
    """
    Display the mid-year start configuration form.

    This is step 2 of the setup wizard. Users who started billing before
    using this app can enter their historical hours here.
    """
    # Get the most recently configured year
    year_config = YearConfig.query.order_by(YearConfig.updated_at.desc()).first()

    if not year_config:
        flash('Please set up your year first.', 'error')
        return redirect(url_for('setup.index'))

    # Get today's date for the default start date
    today = datetime.date.today()

    # Check if we have any historical month data
    has_monthly_data = len(year_config.historical_months) > 0

    # Build dict of historical hours by month
    historical_by_month = {
        hm.month: hm.hours_billed
        for hm in year_config.historical_months
    }

    # Determine start month
    if year_config.start_date:
        start_month = year_config.start_date.month
    else:
        start_month = today.month

    # Calculate total historical hours
    total_historical = sum(historical_by_month.values()) + (year_config.hours_pre_start or 0)

    return render_template(
        'setup/midyear.html',
        year_config=year_config,
        today=today.isoformat(),
        has_monthly_data=has_monthly_data,
        months=MONTH_NAMES,
        historical_by_month=historical_by_month,
        start_month=start_month,
        total_historical=total_historical
    )


@setup_bp.route('/midyear', methods=['POST'])
def save_midyear():
    """
    Save mid-year start configuration and proceed to holidays.
    """
    year_config = YearConfig.query.order_by(YearConfig.updated_at.desc()).first()

    if not year_config:
        flash('Please set up your year first.', 'error')
        return redirect(url_for('setup.index'))

    # Get the start date from the form
    start_date_str = request.form.get('start_date')
    if start_date_str:
        year_config.start_date = datetime.datetime.strptime(
            start_date_str, '%Y-%m-%d'
        ).date()
    else:
        year_config.start_date = datetime.date(year_config.year, 1, 1)

    # Get the entry mode
    entry_mode = request.form.get('entry_mode', 'lump')

    if entry_mode == 'lump':
        # Get lump sum hours
        hours_pre_start = request.form.get('hours_pre_start', type=float) or 0.0
        year_config.hours_pre_start = hours_pre_start

        # Clear any existing monthly data
        HistoricalMonth.query.filter_by(year_config_id=year_config.id).delete()

    else:
        # Monthly entry mode
        year_config.hours_pre_start = 0.0  # Clear lump sum

        # Clear existing and add new monthly data
        HistoricalMonth.query.filter_by(year_config_id=year_config.id).delete()

        start_month = year_config.start_date.month
        for month_num in range(1, start_month):
            hours = request.form.get(f'month_{month_num}', type=float) or 0.0
            if hours > 0:
                hist_month = HistoricalMonth(
                    year_config_id=year_config.id,
                    month=month_num,
                    hours_billed=hours
                )
                db.session.add(hist_month)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Something went wrong saving your historical hours. Please try again.', 'error')
        return redirect(url_for('setup.midyear'))
    flash('Historical hours saved.', 'success')
    return redirect(url_for('setup.holidays'))


@setup_bp.route('/midyear/form')
def midyear_form():
    """
    HTMX endpoint to switch between lump sum and monthly entry modes.
    """
    year_config = YearConfig.query.order_by(YearConfig.updated_at.desc()).first()
    entry_mode = request.args.get('entry_mode', 'lump')

    if entry_mode == 'lump':
        # Return lump sum form
        return f'''
        <div>
            <label for="hours_pre_start" class="block text-sm font-medium text-gray-700 mb-1">
                Total hours billed before start date
            </label>
            <div class="relative">
                <input
                    type="number"
                    id="hours_pre_start"
                    name="hours_pre_start"
                    value="{year_config.hours_pre_start or 0}"
                    min="0"
                    max="{year_config.annual_target}"
                    step="0.5"
                    class="block w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                >
                <span class="absolute right-3 top-2 text-gray-500">hours</span>
            </div>
            <p class="mt-1 text-sm text-gray-500">
                Enter the total hours you've billed so far in {year_config.year}.
            </p>
        </div>
        '''
    else:
        # Return monthly entry grid
        return redirect(url_for('setup.midyear_months'))


@setup_bp.route('/midyear/months')
def midyear_months():
    """
    HTMX endpoint to render the monthly entry grid.
    """
    year_config = YearConfig.query.order_by(YearConfig.updated_at.desc()).first()

    # Get start date from query param or year config
    start_date_str = request.args.get('start_date')
    if start_date_str:
        try:
            start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
            start_month = start_date.month
        except ValueError:
            start_month = datetime.date.today().month
    elif year_config.start_date:
        start_month = year_config.start_date.month
    else:
        start_month = datetime.date.today().month

    # Build dict of historical hours by month
    historical_by_month = {
        hm.month: hm.hours_billed
        for hm in year_config.historical_months
    }

    total_historical = sum(historical_by_month.values())

    return render_template(
        'setup/partials/midyear_months.html',
        months=MONTH_NAMES,
        historical_by_month=historical_by_month,
        start_month=start_month,
        total_historical=total_historical
    )


@setup_bp.route('/holidays')
def holidays():
    """
    Display the holidays configuration form.

    This is step 2 of the setup wizard. Users add firm-recognized holidays
    that should be excluded from billing calculations.
    """
    # Get the most recently configured year
    year_config = YearConfig.query.order_by(YearConfig.updated_at.desc()).first()

    if not year_config:
        flash('Please set up your year first.', 'error')
        return redirect(url_for('setup.index'))

    # Get existing holidays for this year, ordered by date
    holidays_list = Holiday.query.filter_by(
        year_config_id=year_config.id
    ).order_by(Holiday.date).all()

    return render_template(
        'setup/holidays.html',
        year_config=year_config,
        holidays=holidays_list
    )


@setup_bp.route('/holidays/add', methods=['POST'])
def add_holiday():
    """
    Add a new holiday via HTMX.

    Returns the partial HTML for the new holiday item.
    """
    # Get the most recently configured year
    year_config = YearConfig.query.order_by(YearConfig.updated_at.desc()).first()

    if not year_config:
        response = make_response('', 400)
        response.headers['HX-Trigger'] = json.dumps({
            'showError': 'No year configuration found'
        })
        return response

    # Parse the date
    date_str = request.form.get('date')
    name = request.form.get('name', '').strip() or None

    if not date_str:
        response = make_response('', 400)
        response.headers['HX-Trigger'] = json.dumps({
            'showError': 'Please select a date'
        })
        return response

    try:
        date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        response = make_response('', 400)
        response.headers['HX-Trigger'] = json.dumps({
            'showError': 'Invalid date format'
        })
        return response

    # Validate the date is within the configured year
    if date.year != year_config.year:
        response = make_response('', 400)
        response.headers['HX-Trigger'] = json.dumps({
            'showError': f'Date must be in {year_config.year}'
        })
        return response

    # Check for duplicate dates
    existing = Holiday.query.filter_by(
        year_config_id=year_config.id,
        date=date
    ).first()

    if existing:
        response = make_response('', 400)
        response.headers['HX-Trigger'] = json.dumps({
            'showError': 'This date is already added as a holiday'
        })
        return response

    # Create the holiday
    holiday = Holiday(
        year_config_id=year_config.id,
        date=date,
        name=name
    )
    db.session.add(holiday)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        response = make_response('', 500)
        response.headers['HX-Trigger'] = json.dumps({
            'showError': 'Something went wrong. Please try again.'
        })
        return response

    # Return the partial HTML for the new item
    return render_template('setup/partials/holiday_item.html', holiday=holiday)


@setup_bp.route('/holidays/<int:holiday_id>', methods=['DELETE'])
def delete_holiday(holiday_id: int):
    """
    Delete a holiday via HTMX.

    Returns an empty response to remove the item from the DOM.
    """
    holiday = Holiday.query.get_or_404(holiday_id)
    db.session.delete(holiday)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return '<div class="text-red-600 text-sm">Failed to delete. Please try again.</div>', 500

    # Return empty string - HTMX will remove the element
    return ''


@setup_bp.route('/holidays/add-common', methods=['POST'])
def add_common_holidays():
    """
    Add common US holidays for the configured year via HTMX.

    Returns the full updated holidays list HTML.
    """
    # Get the most recently configured year
    year_config = YearConfig.query.order_by(YearConfig.updated_at.desc()).first()

    if not year_config:
        response = make_response('', 400)
        response.headers['HX-Trigger'] = json.dumps({
            'showError': 'No year configuration found'
        })
        return response

    year = year_config.year

    # Define common US holidays
    common_holidays = [
        (datetime.date(year, 1, 1), "New Year's Day"),
        (_get_nth_weekday(year, 1, 0, 3), "MLK Day"),  # 3rd Monday of January
        (_get_nth_weekday(year, 2, 0, 3), "Presidents Day"),  # 3rd Monday of February
        (_get_last_weekday(year, 5, 0), "Memorial Day"),  # Last Monday of May
        (datetime.date(year, 7, 4), "Independence Day"),
        (_get_nth_weekday(year, 9, 0, 1), "Labor Day"),  # 1st Monday of September
        (_get_nth_weekday(year, 11, 3, 4), "Thanksgiving"),  # 4th Thursday of November
        (_get_nth_weekday(year, 11, 3, 4) + datetime.timedelta(days=1), "Day After Thanksgiving"),
        (datetime.date(year, 12, 24), "Christmas Eve"),
        (datetime.date(year, 12, 25), "Christmas Day"),
        (datetime.date(year, 12, 31), "New Year's Eve"),
    ]

    # Add each holiday if it doesn't already exist
    for date, name in common_holidays:
        existing = Holiday.query.filter_by(
            year_config_id=year_config.id,
            date=date
        ).first()

        if not existing:
            holiday = Holiday(
                year_config_id=year_config.id,
                date=date,
                name=name
            )
            db.session.add(holiday)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        response = make_response('', 500)
        response.headers['HX-Trigger'] = json.dumps({
            'showError': 'Something went wrong adding holidays. Please try again.'
        })
        return response

    # Get all holidays for this year, ordered by date
    holidays_list = Holiday.query.filter_by(
        year_config_id=year_config.id
    ).order_by(Holiday.date).all()

    # Return all holiday items as HTML
    html_parts = []
    for holiday in holidays_list:
        html_parts.append(render_template('setup/partials/holiday_item.html', holiday=holiday))

    return ''.join(html_parts)


def _get_nth_weekday(year: int, month: int, weekday: int, n: int) -> datetime.date:
    """
    Get the nth occurrence of a weekday in a given month.

    Args:
        year: The year
        month: The month (1-12)
        weekday: The day of week (0=Monday, 6=Sunday)
        n: Which occurrence (1=first, 2=second, etc.)

    Returns:
        The date of the nth weekday in the month
    """
    # Get the first day of the month
    first_day = datetime.date(year, month, 1)

    # Find the first occurrence of the weekday
    days_until_weekday = (weekday - first_day.weekday()) % 7
    first_occurrence = first_day + datetime.timedelta(days=days_until_weekday)

    # Add weeks to get to the nth occurrence
    return first_occurrence + datetime.timedelta(weeks=n - 1)


def _get_last_weekday(year: int, month: int, weekday: int) -> datetime.date:
    """
    Get the last occurrence of a weekday in a given month.

    Args:
        year: The year
        month: The month (1-12)
        weekday: The day of week (0=Monday, 6=Sunday)

    Returns:
        The date of the last weekday in the month
    """
    # Get the last day of the month
    _, last_day_num = calendar.monthrange(year, month)
    last_day = datetime.date(year, month, last_day_num)

    # Find the last occurrence of the weekday
    days_since_weekday = (last_day.weekday() - weekday) % 7
    return last_day - datetime.timedelta(days=days_since_weekday)


# ============================================================================
# Vacation Routes
# ============================================================================


@setup_bp.route('/vacation')
def vacation():
    """
    Display the vacation days configuration form.

    This is step 3 of the setup wizard. Users add vacation days
    that should be excluded from billing calculations.
    """
    # Get the most recently configured year
    year_config = YearConfig.query.order_by(YearConfig.updated_at.desc()).first()

    if not year_config:
        flash('Please set up your year first.', 'error')
        return redirect(url_for('setup.index'))

    # Get existing vacation days for this year, ordered by date
    vacation_days = VacationDay.query.filter_by(
        year_config_id=year_config.id
    ).order_by(VacationDay.date).all()

    return render_template(
        'setup/vacation.html',
        year_config=year_config,
        vacation_days=vacation_days
    )


@setup_bp.route('/vacation/add', methods=['POST'])
def add_vacation():
    """
    Add a new vacation day via HTMX.

    Returns the partial HTML for the new vacation item.
    """
    # Get the most recently configured year
    year_config = YearConfig.query.order_by(YearConfig.updated_at.desc()).first()

    if not year_config:
        response = make_response('', 400)
        response.headers['HX-Trigger'] = json.dumps({
            'showError': 'No year configuration found'
        })
        return response

    # Parse the date
    date_str = request.form.get('date')
    note = request.form.get('note', '').strip() or None

    if not date_str:
        response = make_response('', 400)
        response.headers['HX-Trigger'] = json.dumps({
            'showError': 'Please select a date'
        })
        return response

    try:
        date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        response = make_response('', 400)
        response.headers['HX-Trigger'] = json.dumps({
            'showError': 'Invalid date format'
        })
        return response

    # Validate the date is within the configured year
    if date.year != year_config.year:
        response = make_response('', 400)
        response.headers['HX-Trigger'] = json.dumps({
            'showError': f'Date must be in {year_config.year}'
        })
        return response

    # Check for duplicate dates
    existing = VacationDay.query.filter_by(
        year_config_id=year_config.id,
        date=date
    ).first()

    if existing:
        response = make_response('', 400)
        response.headers['HX-Trigger'] = json.dumps({
            'showError': 'This date is already added as a vacation day'
        })
        return response

    # Create the vacation day
    vacation = VacationDay(
        year_config_id=year_config.id,
        date=date,
        note=note
    )
    db.session.add(vacation)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        response = make_response('', 500)
        response.headers['HX-Trigger'] = json.dumps({
            'showError': 'Something went wrong. Please try again.'
        })
        return response

    # Return the partial HTML for the new item
    return render_template('setup/partials/vacation_item.html', vacation=vacation)


@setup_bp.route('/vacation/<int:vacation_id>', methods=['DELETE'])
def delete_vacation(vacation_id: int):
    """
    Delete a vacation day via HTMX.

    Returns an empty response to remove the item from the DOM.
    """
    vacation = VacationDay.query.get_or_404(vacation_id)
    db.session.delete(vacation)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return '<div class="text-red-600 text-sm">Failed to delete. Please try again.</div>', 500

    # Return empty string - HTMX will remove the element
    return ''


# ============================================================================
# Plans Routes
# ============================================================================


def get_all_plan_warnings(year_config: YearConfig) -> list:
    """
    Get validation warnings for optimistic and realistic plans.

    Checks each plan to see if any month requires more than 9.5 hours/day,
    which would make the plan infeasible.

    Args:
        year_config: The YearConfig to validate plans for.

    Returns:
        A list of PlanWarning objects with plan_type attribute added.
    """
    from app.services.planner import (
        calculate_monthly_targets_for_plan,
        validate_plan_feasibility,
    )

    warnings = []
    for plan_config in year_config.plan_configs:
        # Only validate optimistic and realistic plans (firm is fixed)
        if plan_config.plan_type in (PlanType.OPTIMISTIC, PlanType.REALISTIC):
            monthly_targets = calculate_monthly_targets_for_plan(year_config, plan_config)
            plan_warnings = validate_plan_feasibility(monthly_targets, year_config)
            # Tag each warning with its plan type for display
            for warning in plan_warnings:
                warning.plan_type = plan_config.plan_type
            warnings.extend(plan_warnings)
    return warnings


def calculate_setup_summary(year_config: YearConfig) -> dict:
    """
    Calculate summary statistics for the setup completion page.

    Args:
        year_config: The YearConfig to summarize.

    Returns:
        A dictionary with summary statistics including:
        - holidays_count: Number of holidays configured
        - vacation_count: Number of vacation days configured
        - intensity_counts: Dict of intensity level counts
        - plan_summaries: List of plan summary dicts
    """
    from app.services.planner import calculate_monthly_targets_for_plan
    from app.services.calendar_utils import get_workdays_in_range

    # Count holidays and vacation days
    holidays_count = len(year_config.holidays)
    vacation_count = len(year_config.vacation_days)

    # Count intensity levels
    intensity_counts = {'normal': 0, 'light': 0, 'very_light': 0}
    for month_config in year_config.month_configs:
        intensity_counts[month_config.intensity.value] += 1

    # Calculate plan summaries
    plan_summaries = []

    # Get all holidays and vacation dates as sets
    holiday_dates = {h.date for h in year_config.holidays}
    vacation_dates = {v.date for v in year_config.vacation_days}

    # Calculate total workdays in year
    year_start = datetime.date(year_config.year, 1, 1)
    year_end = datetime.date(year_config.year, 12, 31)
    all_workdays = get_workdays_in_range(year_start, year_end, holiday_dates, vacation_dates)
    total_workdays = len(all_workdays)

    for plan_config in year_config.plan_configs:
        monthly_targets = calculate_monthly_targets_for_plan(year_config, plan_config)
        total_hours = sum(monthly_targets.values())

        # Calculate average daily hours for this plan
        if plan_config.plan_type == PlanType.FIRM:
            avg_daily = year_config.annual_target / total_workdays if total_workdays > 0 else 0
            description = "Fixed 150 hours/month"
        elif plan_config.plan_type == PlanType.OPTIMISTIC:
            # For optimistic, calculate based on workdays until target date
            target_workdays = get_workdays_in_range(
                year_start, plan_config.target_date, holiday_dates, vacation_dates
            )
            if len(target_workdays) > 0:
                # Calculate hours before target
                hours_before = sum(
                    hours for month, hours in monthly_targets.items()
                    if datetime.date(year_config.year, month, 1) <= plan_config.target_date
                )
                avg_daily = hours_before / len(target_workdays)
            else:
                avg_daily = 0
            if plan_config.target_daily_hours_after:
                description = f"Until {plan_config.target_date.strftime('%b %d')}, then {plan_config.target_daily_hours_after:.1f} hrs/day"
            else:
                description = f"Complete by {plan_config.target_date.strftime('%b %d')}"
        else:  # REALISTIC
            avg_daily = total_hours / total_workdays if total_workdays > 0 else 0
            description = "Full year with intensity preferences"

        plan_summaries.append({
            'type': plan_config.plan_type,
            'name': plan_config.plan_type.value.title(),
            'avg_daily_hours': round(avg_daily, 1),
            'description': description,
            'target_date': plan_config.target_date,
        })

    # Calculate historical hours
    historical_hours = year_config.hours_pre_start or 0.0
    for hist_month in year_config.historical_months:
        historical_hours += hist_month.hours_billed

    return {
        'holidays_count': holidays_count,
        'vacation_count': vacation_count,
        'intensity_counts': intensity_counts,
        'plan_summaries': plan_summaries,
        'total_workdays': total_workdays,
        'historical_hours': historical_hours,
    }


@setup_bp.route('/plans')
def plans():
    """
    Display the plans configuration form.

    This is step 4 of the setup wizard where users configure their three
    billing plans (Firm, Optimistic, Realistic) and set monthly intensity
    preferences.
    """
    # Get the most recently configured year
    year_config = YearConfig.query.order_by(YearConfig.updated_at.desc()).first()

    if not year_config:
        flash('Please set up your year first.', 'error')
        return redirect(url_for('setup.index'))

    # Get plan configs as a dict keyed by plan type
    plan_configs = {p.plan_type: p for p in year_config.plan_configs}

    # Get month configs sorted by month
    month_configs = sorted(year_config.month_configs, key=lambda m: m.month)

    # Get validation warnings
    warnings = get_all_plan_warnings(year_config)

    return render_template(
        'setup/plans.html',
        year_config=year_config,
        plan_configs=plan_configs,
        month_configs=month_configs,
        warnings=warnings,
        PlanType=PlanType,  # Pass enum for template access
    )


@setup_bp.route('/plans', methods=['POST'])
def save_plans():
    """
    Save plan configurations and proceed to setup completion.

    Saves the optimistic plan target date and maintenance hours,
    and all monthly intensity settings.
    """
    # Get the most recently configured year
    year_config = YearConfig.query.order_by(YearConfig.updated_at.desc()).first()

    if not year_config:
        flash('Please set up your year first.', 'error')
        return redirect(url_for('setup.index'))

    # Update optimistic plan settings
    optimistic = PlanConfig.query.filter_by(
        year_config_id=year_config.id,
        plan_type=PlanType.OPTIMISTIC
    ).first()

    target_date_str = request.form.get('optimistic_target_date')
    if target_date_str:
        try:
            optimistic.target_date = datetime.datetime.strptime(
                target_date_str, '%Y-%m-%d'
            ).date()
        except ValueError:
            flash('Invalid target date format.', 'error')
            return redirect(url_for('setup.plans'))

    # Parse maintenance hours (optional)
    maintenance_hours_str = request.form.get('maintenance_hours', '').strip()
    if maintenance_hours_str:
        try:
            maintenance_hours = float(maintenance_hours_str)
            if 0 <= maintenance_hours <= 9.5:
                optimistic.target_daily_hours_after = maintenance_hours
            else:
                flash('Maintenance hours must be between 0 and 9.5.', 'error')
                return redirect(url_for('setup.plans'))
        except ValueError:
            flash('Invalid maintenance hours value.', 'error')
            return redirect(url_for('setup.plans'))
    else:
        optimistic.target_daily_hours_after = None

    # Update all month intensities
    for month in range(1, 13):
        intensity_str = request.form.get(f'intensity_{month}', 'normal').lower()
        month_config = MonthConfig.query.filter_by(
            year_config_id=year_config.id,
            month=month
        ).first()
        if month_config and intensity_str in ('normal', 'light', 'very_light'):
            month_config.intensity = IntensityLevel(intensity_str)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Something went wrong saving your plans. Please try again.', 'error')
        return redirect(url_for('setup.plans'))
    flash('Plans configured successfully!', 'success')
    return redirect(url_for('setup.complete'))


@setup_bp.route('/intensity/<int:month>', methods=['POST'])
def update_intensity(month: int):
    """
    Update a single month's intensity via HTMX.

    Returns the updated validation warnings partial.
    """
    # Validate month
    if month < 1 or month > 12:
        response = make_response('', 400)
        response.headers['HX-Trigger'] = json.dumps({
            'showError': 'Invalid month'
        })
        return response

    # Get the most recently configured year
    year_config = YearConfig.query.order_by(YearConfig.updated_at.desc()).first()

    if not year_config:
        response = make_response('', 400)
        response.headers['HX-Trigger'] = json.dumps({
            'showError': 'No year configuration found'
        })
        return response

    # Get intensity from request
    intensity_str = request.form.get('intensity', 'normal').lower()
    if intensity_str not in ('normal', 'light', 'very_light'):
        response = make_response('', 400)
        response.headers['HX-Trigger'] = json.dumps({
            'showError': 'Invalid intensity level'
        })
        return response

    # Update the month config
    month_config = MonthConfig.query.filter_by(
        year_config_id=year_config.id,
        month=month
    ).first()

    if month_config:
        month_config.intensity = IntensityLevel(intensity_str)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            response = make_response('', 500)
            response.headers['HX-Trigger'] = json.dumps({
                'showError': 'Something went wrong. Please try again.'
            })
            return response

    # Return updated warnings
    warnings = get_all_plan_warnings(year_config)
    return render_template('setup/partials/validation_warnings.html', warnings=warnings)


@setup_bp.route('/intensity/preset', methods=['POST'])
def apply_intensity_preset():
    """
    Apply an intensity preset to all months via HTMX.

    Available presets:
    - standard: All months set to NORMAL
    - light_december: December set to VERY_LIGHT, others NORMAL
    - light_nov_dec: November and December set to LIGHT, others NORMAL

    Returns the updated intensity grid partial with warnings.
    """
    # Get the most recently configured year
    year_config = YearConfig.query.order_by(YearConfig.updated_at.desc()).first()

    if not year_config:
        response = make_response('', 400)
        response.headers['HX-Trigger'] = json.dumps({
            'showError': 'No year configuration found'
        })
        return response

    preset = request.form.get('preset', 'standard').lower()

    # Apply preset to all months
    for month_config in year_config.month_configs:
        if preset == 'standard':
            month_config.intensity = IntensityLevel.NORMAL
        elif preset == 'light_december':
            if month_config.month == 12:
                month_config.intensity = IntensityLevel.VERY_LIGHT
            else:
                month_config.intensity = IntensityLevel.NORMAL
        elif preset == 'light_nov_dec':
            if month_config.month >= 11:
                month_config.intensity = IntensityLevel.LIGHT
            else:
                month_config.intensity = IntensityLevel.NORMAL

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        response = make_response('', 500)
        response.headers['HX-Trigger'] = json.dumps({
            'showError': 'Something went wrong. Please try again.'
        })
        return response

    # Get sorted month configs and warnings for the response
    month_configs = sorted(year_config.month_configs, key=lambda m: m.month)
    warnings = get_all_plan_warnings(year_config)

    return render_template(
        'setup/partials/intensity_grid.html',
        month_configs=month_configs,
        warnings=warnings,
        year_config=year_config,
    )


@setup_bp.route('/complete')
def complete():
    """
    Display the setup completion page with a summary of configuration.
    """
    # Get the most recently configured year
    year_config = YearConfig.query.order_by(YearConfig.updated_at.desc()).first()

    if not year_config:
        flash('Please set up your year first.', 'error')
        return redirect(url_for('setup.index'))

    # Calculate summary statistics
    summary = calculate_setup_summary(year_config)

    return render_template(
        'setup/complete.html',
        year_config=year_config,
        summary=summary,
    )
