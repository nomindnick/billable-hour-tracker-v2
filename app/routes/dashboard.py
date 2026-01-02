"""
Dashboard routes for the Billable Hours Planner.

This module contains the main dashboard view that users see when they
open the application. It displays today's target, progress, and plan statuses.
"""

from flask import Blueprint, render_template


# Create the dashboard blueprint
dashboard_bp = Blueprint('dashboard', __name__)


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
        Rendered dashboard template
    """
    return render_template('dashboard.html')
