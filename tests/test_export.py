"""
Tests for the export service.

Tests chart data generation and chart creation functionality.
"""

import datetime

import pytest

from app import create_app, db
from app.models import (
    DailyEntry,
    HistoricalMonth,
    IntensityLevel,
    MonthConfig,
    PlanConfig,
    PlanType,
    YearConfig,
)
from app.services.export import (
    ChartDataPoint,
    ExportData,
    ExportSummary,
    calculate_pace_projection,
    generate_chart,
    get_chart_as_base64,
    get_cumulative_actual_data,
    get_cumulative_data_for_plan,
    get_export_data,
)


# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a test application instance."""
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def year_config(app):
    """Create a basic year configuration for testing."""
    with app.app_context():
        config = YearConfig(year=2025, annual_target=1800)
        db.session.add(config)

        # Add month configs (all normal intensity)
        for month in range(1, 13):
            month_config = MonthConfig(
                year_config=config,
                month=month,
                intensity=IntensityLevel.NORMAL
            )
            db.session.add(month_config)

        # Add plan configs
        firm_plan = PlanConfig(
            year_config=config,
            plan_type=PlanType.FIRM,
            target_date=datetime.date(2025, 12, 31)
        )
        realistic_plan = PlanConfig(
            year_config=config,
            plan_type=PlanType.REALISTIC,
            target_date=datetime.date(2025, 12, 31)
        )
        optimistic_plan = PlanConfig(
            year_config=config,
            plan_type=PlanType.OPTIMISTIC,
            target_date=datetime.date(2025, 11, 27)
        )
        db.session.add_all([firm_plan, realistic_plan, optimistic_plan])

        db.session.commit()

        # Re-fetch to ensure relationships are loaded
        config = db.session.get(YearConfig, config.id)
        yield config


# -----------------------------------------------------------------------------
# Tests for Helper Functions
# -----------------------------------------------------------------------------

class TestGetCumulativeDataForPlan:
    """Tests for get_cumulative_data_for_plan function."""

    def test_returns_12_data_points(self, app, year_config):
        """Should return 12 data points, one per month."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config.id)
            firm_plan = next(
                pc for pc in config.plan_configs if pc.plan_type == PlanType.FIRM
            )
            data = get_cumulative_data_for_plan(config, firm_plan)

            assert len(data) == 12

    def test_data_is_cumulative(self, app, year_config):
        """Each month should have cumulative hours, not monthly."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config.id)
            firm_plan = next(
                pc for pc in config.plan_configs if pc.plan_type == PlanType.FIRM
            )
            data = get_cumulative_data_for_plan(config, firm_plan)

            # For firm plan, cumulative should be month * 150
            for i, point in enumerate(data, 1):
                assert point.cumulative_hours == pytest.approx(i * 150, rel=0.01)

    def test_month_names_are_correct(self, app, year_config):
        """Month names should be abbreviated correctly."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config.id)
            firm_plan = next(
                pc for pc in config.plan_configs if pc.plan_type == PlanType.FIRM
            )
            data = get_cumulative_data_for_plan(config, firm_plan)

            assert data[0].month_name == 'Jan'
            assert data[5].month_name == 'Jun'
            assert data[11].month_name == 'Dec'


class TestGetCumulativeActualData:
    """Tests for get_cumulative_actual_data function."""

    def test_returns_data_through_specified_month(self, app, year_config):
        """Should return data only up to the specified month."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config.id)

            # Add some entries
            entry = DailyEntry(
                year_config=config,
                date=datetime.date(2025, 1, 15),
                hours_billed=8.0
            )
            db.session.add(entry)
            db.session.commit()

            data = get_cumulative_actual_data(config, through_month=3)

            assert len(data) == 3
            assert data[0].cumulative_hours == 8.0  # January

    def test_cumulative_across_months(self, app, year_config):
        """Hours should accumulate across months."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config.id)

            # Add entries in multiple months
            jan_entry = DailyEntry(
                year_config=config,
                date=datetime.date(2025, 1, 15),
                hours_billed=100.0
            )
            feb_entry = DailyEntry(
                year_config=config,
                date=datetime.date(2025, 2, 15),
                hours_billed=50.0
            )
            db.session.add_all([jan_entry, feb_entry])
            db.session.commit()

            data = get_cumulative_actual_data(config, through_month=2)

            assert data[0].cumulative_hours == 100.0  # January
            assert data[1].cumulative_hours == 150.0  # Cumulative through Feb

    def test_includes_historical_hours_lump_sum(self, app, year_config):
        """Historical hours (lump sum) should be included in cumulative total."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config.id)

            # Set up mid-year start with historical lump sum
            config.start_date = datetime.date(2025, 6, 1)
            config.hours_pre_start = 500.0

            # Add entry in June
            june_entry = DailyEntry(
                year_config=config,
                date=datetime.date(2025, 6, 15),
                hours_billed=50.0
            )
            db.session.add(june_entry)
            db.session.commit()

            data = get_cumulative_actual_data(config, through_month=6)

            # First 5 months should show 500 (historical only, no daily entries)
            for i in range(5):
                assert data[i].cumulative_hours == 500.0

            # June should show 500 + 50 = 550
            assert data[5].cumulative_hours == 550.0

    def test_includes_historical_hours_by_month(self, app, year_config):
        """Historical hours (monthly breakdown) should be included in cumulative total."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config.id)

            # Set up mid-year start with monthly historical data
            config.start_date = datetime.date(2025, 3, 1)

            # Add historical months for Jan and Feb
            jan_hist = HistoricalMonth(
                year_config=config,
                month=1,
                hours_billed=150.0
            )
            feb_hist = HistoricalMonth(
                year_config=config,
                month=2,
                hours_billed=160.0
            )
            db.session.add_all([jan_hist, feb_hist])

            # Add entry in March
            march_entry = DailyEntry(
                year_config=config,
                date=datetime.date(2025, 3, 15),
                hours_billed=40.0
            )
            db.session.add(march_entry)
            db.session.commit()

            data = get_cumulative_actual_data(config, through_month=3)

            # Historical total is 310 (150 + 160)
            # Jan cumulative: 310 + 0 (no daily entry in Jan) = 310
            assert data[0].cumulative_hours == 310.0
            # Feb cumulative: 310 + 0 (no daily entry in Feb) = 310
            assert data[1].cumulative_hours == 310.0
            # March cumulative: 310 + 40 = 350
            assert data[2].cumulative_hours == 350.0


class TestCalculatePaceProjection:
    """Tests for calculate_pace_projection function."""

    def test_projects_based_on_monthly_average(self, app, year_config):
        """Projection should be (YTD hours / months) * 12."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config.id)

            # 300 hours in 2 months = 150/month = 1800 projected
            projection = calculate_pace_projection(300.0, 2, config)
            assert projection == 1800.0

    def test_handles_zero_months(self, app, year_config):
        """Should return 0 if no months have elapsed."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config.id)
            projection = calculate_pace_projection(0.0, 0, config)
            assert projection == 0.0


# -----------------------------------------------------------------------------
# Tests for Core Functions
# -----------------------------------------------------------------------------

class TestGetExportData:
    """Tests for get_export_data function."""

    def test_returns_export_data_structure(self, app, year_config):
        """Should return a properly structured ExportData object."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config.id)
            export_data = get_export_data(config)

            assert isinstance(export_data, ExportData)
            assert export_data.year == 2025
            assert export_data.annual_target == 1800

    def test_includes_all_plan_data(self, app, year_config):
        """Should include data for all three plans."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config.id)
            export_data = get_export_data(config)

            assert len(export_data.firm_data) == 12
            assert len(export_data.optimistic_data) == 12
            assert len(export_data.realistic_data) == 12

    def test_includes_summary(self, app, year_config):
        """Should include summary statistics."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config.id)
            export_data = get_export_data(config)

            assert isinstance(export_data.summary, ExportSummary)
            assert export_data.summary.annual_target == 1800


class TestGenerateChart:
    """Tests for generate_chart function."""

    def test_generates_png_buffer(self, app, year_config):
        """Should generate a PNG image buffer."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config.id)
            export_data = get_export_data(config)
            buffer = generate_chart(export_data, format='png')

            assert buffer is not None
            assert buffer.getvalue()[:8] == b'\x89PNG\r\n\x1a\n'  # PNG magic bytes

    def test_generates_pdf_buffer(self, app, year_config):
        """Should generate a PDF buffer."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config.id)
            export_data = get_export_data(config)
            buffer = generate_chart(export_data, format='pdf')

            assert buffer is not None
            assert buffer.getvalue()[:4] == b'%PDF'  # PDF magic bytes


class TestGetChartAsBase64:
    """Tests for get_chart_as_base64 function."""

    def test_returns_base64_string(self, app, year_config):
        """Should return a base64-encoded string."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config.id)
            export_data = get_export_data(config)
            base64_str = get_chart_as_base64(export_data)

            assert isinstance(base64_str, str)
            assert len(base64_str) > 0

            # Should be valid base64 (decodable)
            import base64
            decoded = base64.b64decode(base64_str)
            assert decoded[:8] == b'\x89PNG\r\n\x1a\n'  # PNG magic bytes
