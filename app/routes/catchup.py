"""
Catch-up sprint routes for the Billable Hours Planner.

This module contains the routes for creating and managing catch-up sprints,
which help users recover from being behind on their billing plans.
"""

import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.models import PlanType, SprintStatus, YearConfig
from app.services.catchup import (
    calculate_sprint_preview,
    create_catch_up_sprint,
    get_active_sprint,
    get_plan_statuses,
)


# Create the catchup blueprint
catchup_bp = Blueprint('catchup', __name__)


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
    plan_type_str = request.form.get('plan_type', '')
    duration_weeks = request.form.get('duration', type=int, default=2)
    weekend_hours = request.form.get('weekend_hours', type=float, default=0.0)
    include_weekends = request.form.get('include_weekends') == 'on'

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

    # Don't include weekend hours if checkbox not checked
    if not include_weekends:
        weekend_hours = 0.0

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
    plan_type_str = request.form.get('plan_type', '')
    duration_weeks = request.form.get('duration', type=int, default=2)
    weekend_hours = request.form.get('weekend_hours', type=float, default=0.0)
    include_weekends = request.form.get('include_weekends') == 'on'

    # Parse plan type
    try:
        plan_type = PlanType(plan_type_str)
    except ValueError:
        flash("Please select a valid plan to catch up on.", "error")
        return redirect(url_for('catchup.new_sprint'))

    # Don't include weekend hours if checkbox not checked
    if not include_weekends:
        weekend_hours = 0.0

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
