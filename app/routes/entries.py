"""
Daily entry routes for the Billable Hours Planner.

This module contains routes for logging and editing daily billable hours.
The entry form is the primary interaction point for daily use.
"""

import datetime
from typing import Optional

from flask import Blueprint, flash, jsonify, make_response, redirect, render_template, request, url_for

from app import db
from app.models import DailyEntry, PlanConfig, PlanType, YearConfig
from app.services.calculator import (
    calculate_daily_target,
    calculate_plan_status,
    get_hours_billed_in_month,
)
from app.services.planner import calculate_monthly_targets_for_plan


# Create the entries blueprint
entries_bp = Blueprint('entries', __name__, url_prefix='/entries')


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def get_current_year_config() -> Optional[YearConfig]:
    """
    Get the current year's configuration, or most recent if current year doesn't exist.

    Returns:
        YearConfig if found, None otherwise
    """
    today = datetime.date.today()
    year_config = YearConfig.query.filter_by(year=today.year).first()

    if not year_config:
        year_config = YearConfig.query.order_by(YearConfig.year.desc()).first()

    return year_config


def get_entry_feedback(year_config: YearConfig, date: datetime.date, hours_billed: float) -> dict:
    """
    Generate encouraging feedback after logging hours.

    Compares the user's position against the Realistic plan to provide
    supportive feedback that motivates continued tracking.

    Args:
        year_config: The year configuration with entries
        date: The date of the entry
        hours_billed: Hours billed for this entry

    Returns:
        Dict with 'message', 'type' (success/info/warning), and 'hours_diff'
    """
    # Get the Realistic plan for status calculation
    realistic_plan = next(
        (pc for pc in year_config.plan_configs if pc.plan_type == PlanType.REALISTIC),
        None
    )

    if not realistic_plan:
        return {
            'message': f"Logged {hours_billed:.1f} hours!",
            'type': 'success',
            'hours_diff': 0
        }

    # Calculate status after this entry
    status = calculate_plan_status(year_config, realistic_plan, date)
    daily_target = calculate_daily_target(year_config, realistic_plan, date)

    hours_diff = status.hours_ahead_or_behind

    # Generate appropriate message based on status
    if hours_diff > 0:
        if hours_diff >= 10:
            message = f"Excellent! You're {hours_diff:.1f} hours ahead of pace!"
        elif hours_diff >= 5:
            message = f"Great work! You're {hours_diff:.1f} hours ahead this month."
        else:
            message = f"Nice! You're {hours_diff:.1f} hours ahead of schedule."
        msg_type = 'success'
    elif hours_diff > -5:
        if hours_billed >= daily_target.daily_target:
            message = f"Solid day! {hours_billed:.1f} hours logged."
        else:
            message = f"Logged {hours_billed:.1f} hours. You're on track!"
        msg_type = 'info'
    else:
        remaining = daily_target.remaining_hours_this_month
        message = f"Logged {hours_billed:.1f} hours. {remaining:.1f} hours left this month."
        msg_type = 'warning'

    return {
        'message': message,
        'type': msg_type,
        'hours_diff': hours_diff
    }


def get_recent_entries(year_config: YearConfig, days: int = 7) -> list[dict]:
    """
    Get recent entries with their daily targets for display.

    Args:
        year_config: The year configuration
        days: Number of days to look back (default 7)

    Returns:
        List of dicts with entry info, target, and status for each day
    """
    today = datetime.date.today()

    # Get Realistic plan for target calculation
    realistic_plan = next(
        (pc for pc in year_config.plan_configs if pc.plan_type == PlanType.REALISTIC),
        None
    )

    # Get entries from the last N days
    start_date = today - datetime.timedelta(days=days - 1)

    # Create a map of date -> entry
    entries_by_date = {
        entry.date: entry
        for entry in year_config.daily_entries
        if start_date <= entry.date <= today
    }

    recent = []
    for i in range(days):
        date = today - datetime.timedelta(days=i)
        entry = entries_by_date.get(date)

        # Calculate target for this date
        if realistic_plan:
            target_result = calculate_daily_target(year_config, realistic_plan, date)
            target = target_result.daily_target
        else:
            target = 7.5  # Default fallback

        is_weekend = date.weekday() >= 5

        recent.append({
            'date': date,
            'entry': entry,
            'hours': entry.hours_billed if entry else None,
            'target': target,
            'met_target': entry and entry.hours_billed >= target if not is_weekend else None,
            'is_today': date == today,
            'is_weekend': is_weekend,
        })

    return recent


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@entries_bp.route('/', methods=['POST'])
def create_entry():
    """
    Create or update a daily entry.

    If an entry already exists for the given date, it updates the hours.
    Otherwise, creates a new entry.

    Form Parameters:
        date: Date string (YYYY-MM-DD), defaults to today
        hours: Hours billed (0-24, step 0.5)

    Returns:
        HTMX partial with updated quick entry result and feedback,
        or full redirect if not an HTMX request
    """
    year_config = get_current_year_config()

    if not year_config:
        if request.headers.get('HX-Request'):
            return '<div class="text-red-600">Please complete setup first.</div>', 400
        flash('Please complete setup first.', 'error')
        return redirect(url_for('setup.index'))

    # Parse form data
    date_str = request.form.get('date', '')
    hours_str = request.form.get('hours', '')

    # Validate date
    try:
        if date_str:
            entry_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            entry_date = datetime.date.today()
    except ValueError:
        if request.headers.get('HX-Request'):
            return '<div class="text-red-600">Invalid date format.</div>', 400
        flash('Invalid date format.', 'error')
        return redirect(url_for('dashboard.index'))

    # Validate hours
    try:
        hours = float(hours_str)
        if hours < 0 or hours > 24:
            raise ValueError("Hours must be between 0 and 24")
    except (ValueError, TypeError):
        if request.headers.get('HX-Request'):
            return '<div class="text-red-600">Please enter valid hours (0-24).</div>', 400
        flash('Please enter valid hours (0-24).', 'error')
        return redirect(url_for('dashboard.index'))

    # Check if entry exists for this date
    entry = DailyEntry.query.filter_by(
        year_config_id=year_config.id,
        date=entry_date
    ).first()

    if entry:
        # Update existing entry
        entry.hours_billed = hours
    else:
        # Create new entry
        entry = DailyEntry(
            year_config_id=year_config.id,
            date=entry_date,
            hours_billed=hours
        )
        db.session.add(entry)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        if request.headers.get('HX-Request'):
            return '<div class="text-red-600 p-4">Something went wrong saving your entry. Please try again.</div>', 500
        flash('Something went wrong saving your entry. Please try again.', 'error')
        return redirect(url_for('dashboard.index'))

    # Generate feedback
    feedback = get_entry_feedback(year_config, entry_date, hours)

    # Get recent entries for the list update
    recent_entries = get_recent_entries(year_config)

    # Determine if this is for today
    is_today = entry_date == datetime.date.today()

    if request.headers.get('HX-Request'):
        # Return HTMX partial with HX-Refresh to update all dashboard sections
        # (Weekly/Monthly progress, Plan Status Cards, YTD Summary, Chart)
        response = make_response(render_template(
            'dashboard/partials/quick_entry_result.html',
            entry=entry,
            feedback=feedback,
            is_today=is_today,
            recent_entries=recent_entries,
        ))
        response.headers['HX-Refresh'] = 'true'
        return response

    # Non-HTMX request - redirect with flash message
    flash(feedback['message'], feedback['type'])
    return redirect(url_for('dashboard.index'))


@entries_bp.route('/<int:entry_id>', methods=['PUT', 'POST'])
def update_entry(entry_id: int):
    """
    Update an existing entry.

    Uses PUT method (or POST with _method=PUT for HTML forms).

    Args:
        entry_id: The ID of the entry to update

    Form Parameters:
        hours: Updated hours billed

    Returns:
        HTMX partial with updated entry row,
        or redirect if not an HTMX request
    """
    year_config = get_current_year_config()

    if not year_config:
        if request.headers.get('HX-Request'):
            return '<div class="text-red-600">Configuration not found.</div>', 400
        flash('Configuration not found.', 'error')
        return redirect(url_for('dashboard.index'))

    # Find the entry
    entry = DailyEntry.query.filter_by(
        id=entry_id,
        year_config_id=year_config.id
    ).first()

    if not entry:
        if request.headers.get('HX-Request'):
            return '<div class="text-red-600">Entry not found.</div>', 404
        flash('Entry not found.', 'error')
        return redirect(url_for('dashboard.index'))

    # Validate hours
    hours_str = request.form.get('hours', '')
    try:
        hours = float(hours_str)
        if hours < 0 or hours > 24:
            raise ValueError("Hours must be between 0 and 24")
    except (ValueError, TypeError):
        if request.headers.get('HX-Request'):
            return '<div class="text-red-600">Please enter valid hours (0-24).</div>', 400
        flash('Please enter valid hours (0-24).', 'error')
        return redirect(url_for('dashboard.index'))

    # Update the entry
    entry.hours_billed = hours
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        if request.headers.get('HX-Request'):
            return '<div class="text-red-600 p-4">Something went wrong updating your entry. Please try again.</div>', 500
        flash('Something went wrong updating your entry. Please try again.', 'error')
        return redirect(url_for('dashboard.index'))

    # Get target for this entry's date
    realistic_plan = next(
        (pc for pc in year_config.plan_configs if pc.plan_type == PlanType.REALISTIC),
        None
    )
    if realistic_plan:
        target_result = calculate_daily_target(year_config, realistic_plan, entry.date)
        target = target_result.daily_target
    else:
        target = 7.5

    is_weekend = entry.date.weekday() >= 5
    is_today = entry.date == datetime.date.today()

    if request.headers.get('HX-Request'):
        # If editing today's entry (quick entry context), return the result partial
        if is_today:
            feedback = get_entry_feedback(year_config, entry.date, hours)
            recent_entries = get_recent_entries(year_config)
            response = make_response(render_template(
                'dashboard/partials/quick_entry_result.html',
                entry=entry,
                feedback=feedback,
                is_today=True,
                recent_entries=recent_entries,
            ))
            response.headers['HX-Refresh'] = 'true'
            return response

        # Return updated row partial for recent entries list with refresh
        # to update all dashboard sections (progress bars, YTD, etc.)
        response = make_response(render_template(
            'dashboard/partials/entry_row.html',
            item={
                'date': entry.date,
                'entry': entry,
                'hours': entry.hours_billed,
                'target': target,
                'met_target': entry.hours_billed >= target if not is_weekend else None,
                'is_today': is_today,
                'is_weekend': is_weekend,
            }
        ))
        response.headers['HX-Refresh'] = 'true'
        return response

    flash(f'Updated entry for {entry.date} to {hours} hours.', 'success')
    return redirect(url_for('dashboard.index'))


@entries_bp.route('/recent')
def recent_entries():
    """
    Get the recent entries partial for HTMX loading.

    Returns:
        HTMX partial with recent entries list
    """
    year_config = get_current_year_config()

    if not year_config:
        return '<div class="text-gray-500 text-sm">No data yet.</div>'

    recent = get_recent_entries(year_config)

    return render_template(
        'dashboard/partials/recent_entries.html',
        recent_entries=recent,
    )


@entries_bp.route('/<int:entry_id>/edit')
def edit_entry_form(entry_id: int):
    """
    Get the inline edit form for an entry.

    Uses query param 'context' to determine which template to use:
    - 'quick': For editing today's entry from the hero section
    - (default): For editing from the recent entries list

    Args:
        entry_id: The ID of the entry to edit

    Returns:
        HTMX partial with inline edit form
    """
    year_config = get_current_year_config()

    if not year_config:
        return '<div class="text-red-600">Configuration not found.</div>', 400

    entry = DailyEntry.query.filter_by(
        id=entry_id,
        year_config_id=year_config.id
    ).first()

    if not entry:
        return '<div class="text-red-600">Entry not found.</div>', 404

    # Get target for context
    realistic_plan = next(
        (pc for pc in year_config.plan_configs if pc.plan_type == PlanType.REALISTIC),
        None
    )
    if realistic_plan:
        target_result = calculate_daily_target(year_config, realistic_plan, entry.date)
        target = target_result.daily_target
    else:
        target = 7.5

    # Check if this is a quick entry edit (from hero section)
    context = request.args.get('context', '')
    is_today = entry.date == datetime.date.today()

    if context == 'quick' or is_today:
        # Use the quick entry edit template
        return render_template(
            'dashboard/partials/quick_entry_edit.html',
            entry=entry,
            target=target,
        )

    return render_template(
        'dashboard/partials/entry_edit_form.html',
        entry=entry,
        target=target,
    )
