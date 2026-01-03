"""
Export routes for generating and downloading billing progress charts.

This module provides routes for:
- Viewing export options with a chart preview
- Downloading charts as PNG or PDF

The export feature is designed for presenting billing progress in firm meetings.
"""

import datetime

from flask import Blueprint, flash, redirect, render_template, send_file, url_for

from app.models import YearConfig
from app.services.export import (
    generate_chart,
    get_chart_as_base64,
    get_export_data,
)


# Create the blueprint
export_bp = Blueprint('export', __name__)


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@export_bp.route('/')
def index():
    """
    Display export options page with chart preview.

    Shows a preview of the chart and provides download buttons
    for PNG and PDF formats.
    """
    today = datetime.date.today()

    # Get the year config
    year_config = YearConfig.query.filter_by(year=today.year).first()

    if not year_config:
        flash('Please complete setup first to generate exports.', 'info')
        return redirect(url_for('setup.index'))

    # Get export data
    export_data = get_export_data(year_config, today)

    # Generate base64 preview
    chart_base64 = get_chart_as_base64(export_data)

    return render_template(
        'export.html',
        export_data=export_data,
        chart_base64=chart_base64,
        summary=export_data.summary
    )


@export_bp.route('/chart.png')
def download_png():
    """
    Generate and download chart as PNG.

    Returns the chart as a downloadable PNG file with a descriptive filename.
    """
    today = datetime.date.today()

    # Get the year config
    year_config = YearConfig.query.filter_by(year=today.year).first()

    if not year_config:
        flash('Please complete setup first to generate exports.', 'error')
        return redirect(url_for('setup.index'))

    # Generate export data and chart
    export_data = get_export_data(year_config, today)
    chart_buffer = generate_chart(export_data, format='png')

    # Generate filename with date
    filename = f"billable_hours_{year_config.year}_{today.strftime('%Y%m%d')}.png"

    return send_file(
        chart_buffer,
        mimetype='image/png',
        as_attachment=True,
        download_name=filename
    )


@export_bp.route('/chart.pdf')
def download_pdf():
    """
    Generate and download chart as PDF.

    Returns the chart as a downloadable PDF file with a descriptive filename.
    Suitable for printing or sharing in formal settings.
    """
    today = datetime.date.today()

    # Get the year config
    year_config = YearConfig.query.filter_by(year=today.year).first()

    if not year_config:
        flash('Please complete setup first to generate exports.', 'error')
        return redirect(url_for('setup.index'))

    # Generate export data and chart
    export_data = get_export_data(year_config, today)
    chart_buffer = generate_chart(export_data, format='pdf')

    # Generate filename with date
    filename = f"billable_hours_{year_config.year}_{today.strftime('%Y%m%d')}.pdf"

    return send_file(
        chart_buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )
