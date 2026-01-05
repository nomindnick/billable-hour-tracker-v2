"""
Export service for generating billing progress charts.

This module provides functionality to generate professional charts showing
billing progress against the three plans (Firm, Optimistic, Realistic).
Charts can be exported as PNG or PDF for use in firm meetings.

The chart shows cumulative hours over the year with:
- Three plan trajectory lines (what should have been billed by each month)
- Actual hours billed line (overlaid on the plan trajectories)
- Summary statistics (YTD hours, target, pace projection)
"""

import datetime
import io
from dataclasses import dataclass
from typing import Optional

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for server-side rendering
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from app.models import PlanConfig, PlanType, YearConfig
from app.services.calculator import (
    calculate_plan_status,
    get_historical_hours,
    get_hours_billed_in_month,
    get_hours_billed_to_date,
)
from app.services.planner import calculate_monthly_targets_for_plan


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

# Chart colors matching Tailwind color palette
CHART_COLORS = {
    'firm': '#6B7280',       # gray-500
    'optimistic': '#3B82F6',  # blue-500
    'realistic': '#10B981',   # green-500
    'actual': '#8B5CF6',      # purple-500
}

# Month names for x-axis labels
MONTH_NAMES = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
]

# Chart styling
FIGURE_SIZE = (10, 8)  # inches, suitable for printing
TITLE_FONTSIZE = 16
LABEL_FONTSIZE = 12
LEGEND_FONTSIZE = 10


# -----------------------------------------------------------------------------
# Data Classes
# -----------------------------------------------------------------------------

@dataclass
class ChartDataPoint:
    """
    A single data point for the chart.

    Attributes:
        month: Month number (1-12)
        month_name: Short month name (e.g., "Jan")
        cumulative_hours: Cumulative hours through this month
    """
    month: int
    month_name: str
    cumulative_hours: float


@dataclass
class ExportSummary:
    """
    Summary statistics for the export.

    Attributes:
        ytd_hours: Total hours billed year-to-date
        annual_target: Annual billing target
        hours_remaining: Hours remaining to hit annual target
        current_pace_projection: Projected year-end hours if current pace continues
        status: Status label (e.g., "On track", "Ahead", "Behind")
        generated_date: Date the export was generated
    """
    ytd_hours: float
    annual_target: int
    hours_remaining: float
    current_pace_projection: float
    status: str
    generated_date: str


@dataclass
class ExportData:
    """
    All data needed to generate an export chart.

    Attributes:
        year: The billing year
        annual_target: Annual target hours
        firm_data: Cumulative targets for Firm plan (12 points)
        optimistic_data: Cumulative targets for Optimistic plan (12 points)
        realistic_data: Cumulative targets for Realistic plan (12 points)
        actual_data: Actual hours billed (up to current month)
        summary: Summary statistics
    """
    year: int
    annual_target: int
    firm_data: list[ChartDataPoint]
    optimistic_data: list[ChartDataPoint]
    realistic_data: list[ChartDataPoint]
    actual_data: list[ChartDataPoint]
    summary: ExportSummary


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def get_cumulative_data_for_plan(
    year_config: YearConfig,
    plan_config: PlanConfig
) -> list[ChartDataPoint]:
    """
    Calculate cumulative monthly targets for a plan.

    Args:
        year_config: The year configuration
        plan_config: The plan configuration

    Returns:
        List of 12 ChartDataPoints with cumulative hours through each month
    """
    monthly_targets = calculate_monthly_targets_for_plan(year_config, plan_config)

    data_points: list[ChartDataPoint] = []
    cumulative = 0.0

    for month in range(1, 13):
        cumulative += monthly_targets.get(month, 0.0)
        data_points.append(ChartDataPoint(
            month=month,
            month_name=MONTH_NAMES[month - 1],
            cumulative_hours=round(cumulative, 2)
        ))

    return data_points


def get_cumulative_actual_data(
    year_config: YearConfig,
    through_month: int
) -> list[ChartDataPoint]:
    """
    Calculate cumulative actual hours billed through each month.

    Includes historical hours (from mid-year start) in the cumulative total,
    ensuring the chart accurately reflects total hours billed.

    Args:
        year_config: The year configuration with daily entries
        through_month: Last month to include (1-12)

    Returns:
        List of ChartDataPoints with cumulative actual hours
    """
    data_points: list[ChartDataPoint] = []

    # Start with historical hours for mid-year starts
    # This ensures the chart shows total hours including pre-tracking data
    cumulative = get_historical_hours(year_config)

    for month in range(1, through_month + 1):
        month_hours = get_hours_billed_in_month(year_config, year_config.year, month)
        cumulative += month_hours
        data_points.append(ChartDataPoint(
            month=month,
            month_name=MONTH_NAMES[month - 1],
            cumulative_hours=round(cumulative, 2)
        ))

    return data_points


def calculate_pace_projection(
    ytd_hours: float,
    current_month: int,
    year_config: YearConfig
) -> float:
    """
    Project year-end hours based on current billing pace.

    Uses simple linear projection: (YTD hours / months elapsed) * 12

    Args:
        ytd_hours: Hours billed year-to-date
        current_month: Current month number (1-12)
        year_config: The year configuration

    Returns:
        Projected total hours at year end
    """
    if current_month == 0:
        return 0.0

    # Simple linear projection
    monthly_average = ytd_hours / current_month
    return round(monthly_average * 12, 2)


# -----------------------------------------------------------------------------
# Core Functions
# -----------------------------------------------------------------------------

def get_export_data(
    year_config: YearConfig,
    as_of_date: Optional[datetime.date] = None
) -> ExportData:
    """
    Gather all data needed for chart generation.

    This function collects cumulative targets for all three plans and
    actual hours billed, plus calculates summary statistics.

    Args:
        year_config: The year configuration with all related data
        as_of_date: Date to calculate data as of (defaults to today)

    Returns:
        ExportData containing all chart data and summary statistics

    Examples:
        >>> export_data = get_export_data(year_config)
        >>> len(export_data.firm_data)  # Always 12 months
        12
        >>> export_data.summary.status
        "On track"
    """
    if as_of_date is None:
        as_of_date = datetime.date.today()

    # Get plan configs
    firm_plan = next(
        (pc for pc in year_config.plan_configs if pc.plan_type == PlanType.FIRM),
        None
    )
    optimistic_plan = next(
        (pc for pc in year_config.plan_configs if pc.plan_type == PlanType.OPTIMISTIC),
        None
    )
    realistic_plan = next(
        (pc for pc in year_config.plan_configs if pc.plan_type == PlanType.REALISTIC),
        None
    )

    # Get cumulative data for each plan
    firm_data = get_cumulative_data_for_plan(year_config, firm_plan) if firm_plan else []
    optimistic_data = get_cumulative_data_for_plan(year_config, optimistic_plan) if optimistic_plan else []
    realistic_data = get_cumulative_data_for_plan(year_config, realistic_plan) if realistic_plan else []

    # Get actual data through current month
    current_month = as_of_date.month if as_of_date.year == year_config.year else 12
    actual_data = get_cumulative_actual_data(year_config, current_month)

    # Calculate summary statistics
    ytd_hours = get_hours_billed_to_date(year_config, as_of_date)
    hours_remaining = max(0, year_config.annual_target - ytd_hours)
    pace_projection = calculate_pace_projection(ytd_hours, current_month, year_config)

    # Get status from realistic plan (primary plan)
    status = "No data"
    if realistic_plan:
        plan_status = calculate_plan_status(year_config, realistic_plan, as_of_date)
        status = plan_status.status_label

    summary = ExportSummary(
        ytd_hours=round(ytd_hours, 2),
        annual_target=year_config.annual_target,
        hours_remaining=round(hours_remaining, 2),
        current_pace_projection=pace_projection,
        status=status,
        generated_date=as_of_date.strftime("%B %d, %Y")
    )

    return ExportData(
        year=year_config.year,
        annual_target=year_config.annual_target,
        firm_data=firm_data,
        optimistic_data=optimistic_data,
        realistic_data=realistic_data,
        actual_data=actual_data,
        summary=summary
    )


def generate_chart(
    export_data: ExportData,
    format: str = 'png'
) -> io.BytesIO:
    """
    Generate a matplotlib chart from export data.

    Creates a line chart showing all three plan trajectories with the
    actual hours overlaid. Includes a summary text box below the chart.

    Args:
        export_data: The data to chart
        format: Output format ('png' or 'pdf')

    Returns:
        BytesIO buffer containing the chart in the specified format

    Examples:
        >>> buffer = generate_chart(export_data, format='png')
        >>> # Write to file or send as HTTP response
    """
    # Create figure with space for summary below
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)

    # Prepare x-axis data (months)
    months = list(range(1, 13))
    month_labels = MONTH_NAMES

    # Plot plan trajectories
    if export_data.firm_data:
        firm_hours = [dp.cumulative_hours for dp in export_data.firm_data]
        ax.plot(months, firm_hours,
                color=CHART_COLORS['firm'],
                linewidth=2,
                linestyle='--',
                label='Firm Requirements',
                marker='o',
                markersize=4)

    if export_data.optimistic_data:
        optimistic_hours = [dp.cumulative_hours for dp in export_data.optimistic_data]
        ax.plot(months, optimistic_hours,
                color=CHART_COLORS['optimistic'],
                linewidth=2,
                label='Optimistic Plan',
                marker='s',
                markersize=4)

    if export_data.realistic_data:
        realistic_hours = [dp.cumulative_hours for dp in export_data.realistic_data]
        ax.plot(months, realistic_hours,
                color=CHART_COLORS['realistic'],
                linewidth=2,
                label='Realistic Plan',
                marker='^',
                markersize=4)

    # Plot actual hours (thicker line, only up to current month)
    if export_data.actual_data:
        actual_months = [dp.month for dp in export_data.actual_data]
        actual_hours = [dp.cumulative_hours for dp in export_data.actual_data]
        ax.plot(actual_months, actual_hours,
                color=CHART_COLORS['actual'],
                linewidth=3,
                label='Actual Hours',
                marker='D',
                markersize=6)

    # Configure axes
    ax.set_xlabel('Month', fontsize=LABEL_FONTSIZE)
    ax.set_ylabel('Cumulative Hours', fontsize=LABEL_FONTSIZE)
    ax.set_title(
        f'Billable Hours Progress - {export_data.year}',
        fontsize=TITLE_FONTSIZE,
        fontweight='bold'
    )

    # Set x-axis ticks to month names
    ax.set_xticks(months)
    ax.set_xticklabels(month_labels)

    # Set y-axis limits with buffer
    y_max = export_data.annual_target * 1.1
    ax.set_ylim(0, y_max)

    # Add horizontal line at annual target
    ax.axhline(y=export_data.annual_target,
               color='#DC2626',  # red-600
               linestyle=':',
               linewidth=1.5,
               label=f'Annual Target ({export_data.annual_target}h)')

    # Add grid
    ax.grid(True, linestyle='--', alpha=0.3)

    # Add legend
    ax.legend(loc='upper left', fontsize=LEGEND_FONTSIZE)

    # Add summary text box
    summary = export_data.summary
    summary_text = (
        f"YTD Hours: {summary.ytd_hours:,.1f}  |  "
        f"Target: {summary.annual_target:,}  |  "
        f"Remaining: {summary.hours_remaining:,.1f}  |  "
        f"Pace Projection: {summary.current_pace_projection:,.0f}  |  "
        f"Status: {summary.status}"
    )

    # Add text below the chart
    fig.text(0.5, 0.02, summary_text,
             ha='center',
             fontsize=10,
             style='italic',
             bbox=dict(boxstyle='round', facecolor='#F3F4F6', alpha=0.8))

    # Add generation date
    fig.text(0.98, 0.02, f"Generated: {summary.generated_date}",
             ha='right',
             fontsize=8,
             color='#6B7280')

    # Adjust layout to make room for summary
    plt.tight_layout()
    plt.subplots_adjust(bottom=0.12)

    # Save to buffer
    buffer = io.BytesIO()
    fig.savefig(buffer, format=format, dpi=150, bbox_inches='tight')
    buffer.seek(0)

    # Clean up
    plt.close(fig)

    return buffer


def get_chart_as_base64(export_data: ExportData) -> str:
    """
    Generate chart and return as base64-encoded string for embedding in HTML.

    Args:
        export_data: The data to chart

    Returns:
        Base64-encoded PNG image string (without data URI prefix)

    Examples:
        >>> base64_str = get_chart_as_base64(export_data)
        >>> # Use in HTML: <img src="data:image/png;base64,{base64_str}">
    """
    import base64
    buffer = generate_chart(export_data, format='png')
    return base64.b64encode(buffer.getvalue()).decode('utf-8')
