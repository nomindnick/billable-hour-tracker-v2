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

    db.session.commit()

    # Redirect to the holidays setup step
    return redirect(url_for('setup.holidays'))


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
    db.session.commit()

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
    db.session.commit()

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

    db.session.commit()

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
    db.session.commit()

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
    db.session.commit()

    # Return empty string - HTMX will remove the element
    return ''


# ============================================================================
# Plans Route (Placeholder for Sprint 3.3)
# ============================================================================


@setup_bp.route('/plans')
def plans():
    """
    Display the plans configuration form.

    This is step 4 of the setup wizard. Placeholder for Sprint 3.3.
    """
    # Get the most recently configured year
    year_config = YearConfig.query.order_by(YearConfig.updated_at.desc()).first()

    if not year_config:
        flash('Please set up your year first.', 'error')
        return redirect(url_for('setup.index'))

    # Placeholder: redirect to dashboard until Sprint 3.3 implements this
    flash('Plans configuration coming in the next update! Your setup is complete for now.', 'info')
    return redirect(url_for('dashboard.index'))
