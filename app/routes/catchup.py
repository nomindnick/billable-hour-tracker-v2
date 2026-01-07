"""
Catch-up sprint routes for the Billable Hours Planner.

This module contains the routes for creating and managing catch-up sprints,
which help users recover from being behind on their billing plans.
"""

import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models import CatchUpSprint, PlanType, SprintStatus, YearConfig
from app.services.catchup import (
    calculate_sprint_preview,
    calculate_sprint_progress,
    create_catch_up_sprint,
    get_active_sprint,
    get_plan_statuses,
    mark_sprint_completed,
    mark_sprint_dismissed,
)


# Create the catchup blueprint
catchup_bp = Blueprint('catchup', __name__)


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

DEFAULT_SPRINT_DURATION = 2  # Default duration in weeks for new sprints
MIN_SPRINT_WEEKS = 1  # Minimum sprint duration
MAX_SPRINT_WEEKS = 6  # Maximum sprint duration


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def get_current_year_config():
    """Get the YearConfig for the current year."""
    current_year = datetime.date.today().year
    return YearConfig.query.filter_by(year=current_year).first()


def get_plan_display_name(plan_type: PlanType) -> str:
    """Get human-readable name for a plan type."""
    return {
        PlanType.FIRM: "Firm Requirements",
        PlanType.OPTIMISTIC: "Optimistic",
        PlanType.REALISTIC: "Realistic"
    }.get(plan_type, str(plan_type.value))


def _parse_sprint_form() -> tuple[str, int, float, bool]:
    """
    Parse sprint form values from the request.

    Returns:
        Tuple of (plan_type_str, duration_weeks, weekend_hours, include_weekends)
    """
    plan_type_str = request.form.get('plan_type', '')
    duration_weeks = request.form.get(
        'duration', type=int, default=DEFAULT_SPRINT_DURATION
    )
    weekend_hours = request.form.get('weekend_hours', type=float, default=0.0)
    include_weekends = request.form.get('include_weekends') == 'on'

    # Don't include weekend hours if checkbox not checked
    if not include_weekends:
        weekend_hours = 0.0

    return plan_type_str, duration_weeks, weekend_hours, include_weekends


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@catchup_bp.route('/new', methods=['GET'])
def new_sprint():
    """
    Display the catch-up sprint creation form.

    Shows current plan statuses and allows users to configure
    a catch-up sprint with live preview of what it would require.
    """
    year_config = get_current_year_config()

    if not year_config:
        flash("Please set up your year configuration first.", "info")
        return redirect(url_for('setup.index'))

    # Check for existing active sprint
    active_sprint = get_active_sprint(year_config)
    if active_sprint:
        flash(
            "You already have an active catch-up sprint. "
            "Complete or dismiss it before starting a new one.",
            "info"
        )
        return redirect(url_for('dashboard.index'))

    # Get current plan statuses
    plan_statuses = get_plan_statuses(year_config)

    # Check if user is behind on any plan
    any_behind = any(
        status.hours_ahead_or_behind < 0
        for status in plan_statuses.values()
    )

    if not any_behind:
        flash(
            "Great news! You're on track with all your plans. "
            "No catch-up sprint needed right now.",
            "success"
        )
        return redirect(url_for('dashboard.index'))

    # Prepare plan options (only show plans user is behind on)
    plan_options = []
    for plan_type, status in plan_statuses.items():
        if status.hours_ahead_or_behind < 0:
            plan_options.append({
                'type': plan_type,
                'name': get_plan_display_name(plan_type),
                'hours_behind': abs(status.hours_ahead_or_behind),
                'status_label': status.status_label
            })

    # Sort by hours behind (most behind first)
    plan_options.sort(key=lambda x: x['hours_behind'], reverse=True)

    return render_template(
        'catchup/create.html',
        year_config=year_config,
        plan_options=plan_options,
        plan_statuses=plan_statuses,
        PlanType=PlanType
    )


@catchup_bp.route('/preview', methods=['POST'])
def preview_sprint():
    """
    HTMX endpoint to calculate and return sprint preview.

    Called when user changes form options to show live preview
    of what the sprint would require.
    """
    year_config = get_current_year_config()

    if not year_config:
        return render_template(
            'catchup/partials/sprint_preview.html',
            preview=None,
            error="Year configuration not found."
        )

    # Get form values
    plan_type_str, duration_weeks, weekend_hours, _ = _parse_sprint_form()

    # Parse plan type
    try:
        plan_type = PlanType(plan_type_str)
    except ValueError:
        return render_template(
            'catchup/partials/sprint_preview.html',
            preview=None,
            error=None,
            show_placeholder=True
        )

    # Calculate preview
    preview = calculate_sprint_preview(
        year_config,
        plan_type,
        duration_weeks,
        weekend_hours
    )

    return render_template(
        'catchup/partials/sprint_preview.html',
        preview=preview,
        error=None,
        plan_name=get_plan_display_name(plan_type)
    )


@catchup_bp.route('/', methods=['POST'])
def create_sprint():
    """
    Create a new catch-up sprint.

    Validates the input, creates the sprint, and redirects to dashboard
    with a success message.
    """
    year_config = get_current_year_config()

    if not year_config:
        flash("Please set up your year configuration first.", "error")
        return redirect(url_for('setup.index'))

    # Get form values
    plan_type_str, duration_weeks, weekend_hours, _ = _parse_sprint_form()

    # Parse plan type
    try:
        plan_type = PlanType(plan_type_str)
    except ValueError:
        flash("Please select a valid plan to catch up on.", "error")
        return redirect(url_for('catchup.new_sprint'))

    # Validate plan type
    if plan_type == PlanType.FIRM:
        flash("Cannot create catch-up sprint for Firm plan. Please select Optimistic or Realistic.", "error")
        return redirect(url_for('catchup.new_sprint'))

    # Try to create the sprint
    try:
        sprint = create_catch_up_sprint(
            year_config,
            plan_type,
            duration_weeks,
            weekend_hours
        )

        plan_name = get_plan_display_name(plan_type)
        flash(
            f"Catch-up sprint started! You're targeting {sprint.target_hours:.1f} hours "
            f"to get back on track with the {plan_name} plan by {sprint.end_date.strftime('%B %d')}.",
            "success"
        )
        return redirect(url_for('dashboard.index'))

    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for('catchup.new_sprint'))
    except SQLAlchemyError:
        db.session.rollback()
        flash("Something went wrong creating your sprint. Please try again.", "error")
        return redirect(url_for('catchup.new_sprint'))


@catchup_bp.route('/<int:sprint_id>/dismiss', methods=['POST'])
def dismiss_sprint(sprint_id):
    """
    Dismiss (cancel) an active catch-up sprint.

    This marks the sprint as dismissed and returns the user to the dashboard.
    Used when circumstances change and the sprint is no longer needed.
    """
    year_config = get_current_year_config()

    if not year_config:
        flash("Year configuration not found.", "error")
        return redirect(url_for('dashboard.index'))

    # Find the sprint
    sprint = CatchUpSprint.query.filter_by(
        id=sprint_id,
        year_config_id=year_config.id,
        status=SprintStatus.ACTIVE
    ).first()

    if not sprint:
        flash("Sprint not found or already completed.", "error")
        return redirect(url_for('dashboard.index'))

    # Mark as dismissed
    try:
        mark_sprint_dismissed(sprint)
    except SQLAlchemyError:
        db.session.rollback()
        flash("Something went wrong dismissing your sprint. Please try again.", "error")
        return redirect(url_for('dashboard.index'))

    flash(
        "Sprint dismissed. You can start a new one whenever you're ready.",
        "info"
    )
    return redirect(url_for('dashboard.index'))


@catchup_bp.route('/<int:sprint_id>/complete', methods=['POST'])
def complete_sprint(sprint_id):
    """
    Manually mark a catch-up sprint as completed.

    This is typically called automatically when the target is hit,
    but can also be triggered manually if needed.
    """
    year_config = get_current_year_config()

    if not year_config:
        flash("Year configuration not found.", "error")
        return redirect(url_for('dashboard.index'))

    # Find the sprint
    sprint = CatchUpSprint.query.filter_by(
        id=sprint_id,
        year_config_id=year_config.id,
        status=SprintStatus.ACTIVE
    ).first()

    if not sprint:
        flash("Sprint not found or already completed.", "error")
        return redirect(url_for('dashboard.index'))

    # Mark as completed
    try:
        mark_sprint_completed(sprint)
    except SQLAlchemyError:
        db.session.rollback()
        flash("Something went wrong completing your sprint. Please try again.", "error")
        return redirect(url_for('dashboard.index'))

    flash(
        "Sprint completed! Great work on hitting your target!",
        "success"
    )
    return redirect(url_for('dashboard.index'))


@catchup_bp.route('/<int:sprint_id>/revise', methods=['GET'])
def revise_sprint(sprint_id):
    """
    Show the sprint creation form pre-filled with current sprint parameters.

    This allows users to adjust their sprint (longer duration, add weekend hours, etc.)
    when the current one isn't working out.
    """
    year_config = get_current_year_config()

    if not year_config:
        flash("Please set up your year configuration first.", "info")
        return redirect(url_for('setup.index'))

    # Find the active sprint
    sprint = CatchUpSprint.query.filter_by(
        id=sprint_id,
        year_config_id=year_config.id,
        status=SprintStatus.ACTIVE
    ).first()

    if not sprint:
        flash("Sprint not found or already completed.", "error")
        return redirect(url_for('dashboard.index'))

    # Get current progress
    progress = calculate_sprint_progress(sprint, year_config)

    # Get plan statuses
    plan_statuses = get_plan_statuses(year_config)

    # Prepare plan options
    plan_options = []
    for plan_type, status in plan_statuses.items():
        plan_options.append({
            'type': plan_type,
            'name': get_plan_display_name(plan_type),
            'hours_behind': abs(min(0, status.hours_ahead_or_behind)),
            'status_label': status.status_label
        })

    # Sort by hours behind (most behind first)
    plan_options.sort(key=lambda x: x['hours_behind'], reverse=True)

    # Calculate remaining weeks
    days_total = (sprint.end_date - datetime.date.today()).days + 1
    suggested_weeks = max(MIN_SPRINT_WEEKS, min(MAX_SPRINT_WEEKS, (days_total // 7) + 1))

    return render_template(
        'catchup/create.html',
        year_config=year_config,
        plan_options=plan_options,
        plan_statuses=plan_statuses,
        PlanType=PlanType,
        # Pre-fill values for revision
        revising=True,
        current_sprint=sprint,
        current_progress=progress,
        suggested_duration=suggested_weeks,
        selected_plan_type=sprint.target_plan
    )
