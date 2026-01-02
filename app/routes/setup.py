"""
Setup routes for the Billable Hours Planner.

This module contains the routes for the year setup wizard, where users
configure their annual target, holidays, vacation days, and plan settings.
"""

import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db
from app.models import IntensityLevel, MonthConfig, PlanConfig, PlanType, YearConfig


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

    This is a placeholder for Sprint 3.2. For now, redirects to dashboard.
    """
    # Placeholder: redirect to dashboard until Sprint 3.2 implements this
    flash('Holidays setup coming soon! Redirecting to dashboard.', 'info')
    return redirect(url_for('dashboard.index'))
