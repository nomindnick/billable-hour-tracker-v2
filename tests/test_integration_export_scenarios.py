"""
Integration tests for export functionality at various stages (Sprint 4.6).

Tests export chart generation and summary statistics at different points
in the billing year: early year, mid-year, end of year, and edge cases.
"""

import datetime
import io

import pytest

from app import db
from app.models import (
    CatchUpSprint,
    DailyEntry,
    HistoricalMonth,
    IntensityLevel,
    MonthConfig,
    PlanConfig,
    PlanType,
    SprintStatus,
    YearConfig,
)
from app.services.export import (
    get_cumulative_actual_data,
    get_export_data,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def current_year():
    """Return the current year for testing."""
    return datetime.date.today().year


@pytest.fixture
def base_year_config(app, current_year):
    """Create a basic year configuration with plans but no entries."""
    with app.app_context():
        config = YearConfig(year=current_year, annual_target=1800)
        db.session.add(config)
        db.session.flush()

        # Add month configs (all normal intensity)
        for month in range(1, 13):
            month_config = MonthConfig(
                year_config_id=config.id,
                month=month,
                intensity=IntensityLevel.NORMAL,
            )
            db.session.add(month_config)

        # Add plan configs
        firm_plan = PlanConfig(
            year_config_id=config.id,
            plan_type=PlanType.FIRM,
            target_date=datetime.date(current_year, 12, 31),
        )
        realistic_plan = PlanConfig(
            year_config_id=config.id,
            plan_type=PlanType.REALISTIC,
            target_date=datetime.date(current_year, 12, 31),
        )
        optimistic_plan = PlanConfig(
            year_config_id=config.id,
            plan_type=PlanType.OPTIMISTIC,
            target_date=datetime.date(current_year, 11, 27),
        )
        db.session.add_all([firm_plan, realistic_plan, optimistic_plan])
        db.session.commit()
        db.session.refresh(config)
        yield config


@pytest.fixture
def year_config_january_only(app, base_year_config, current_year):
    """Config with entries only in January (~150 hours)."""
    with app.app_context():
        config = db.session.get(YearConfig, base_year_config.id)

        # Add entries for January workdays (approx 22 workdays)
        # Adding 150 hours across 10 entries
        for day in [6, 7, 8, 9, 10, 13, 14, 15, 16, 17]:
            entry = DailyEntry(
                year_config_id=config.id,
                date=datetime.date(current_year, 1, day),
                hours_billed=15.0,  # 15 * 10 = 150 hours
            )
            db.session.add(entry)

        db.session.commit()
        db.session.refresh(config)
        yield config


@pytest.fixture
def year_config_mid_year(app, base_year_config, current_year):
    """Config with entries through June (~900 hours)."""
    with app.app_context():
        config = db.session.get(YearConfig, base_year_config.id)

        # Add 150 hours per month for Jan-June
        for month in range(1, 7):
            # Add one entry per month with 150 hours
            entry = DailyEntry(
                year_config_id=config.id,
                date=datetime.date(current_year, month, 15),
                hours_billed=150.0,
            )
            db.session.add(entry)

        db.session.commit()
        db.session.refresh(config)
        yield config


@pytest.fixture
def year_config_full_year(app, base_year_config, current_year):
    """Config with full year of entries (exactly 1800 hours)."""
    with app.app_context():
        config = db.session.get(YearConfig, base_year_config.id)

        # Add 150 hours per month for all 12 months
        for month in range(1, 13):
            entry = DailyEntry(
                year_config_id=config.id,
                date=datetime.date(current_year, month, 15),
                hours_billed=150.0,
            )
            db.session.add(entry)

        db.session.commit()
        db.session.refresh(config)
        yield config


@pytest.fixture
def year_config_over_target(app, base_year_config, current_year):
    """Config with hours exceeding annual target (2200 hours)."""
    with app.app_context():
        config = db.session.get(YearConfig, base_year_config.id)

        # Add ~183.33 hours per month for all 12 months = 2200 total
        for month in range(1, 13):
            entry = DailyEntry(
                year_config_id=config.id,
                date=datetime.date(current_year, month, 15),
                hours_billed=183.33,
            )
            db.session.add(entry)

        db.session.commit()
        db.session.refresh(config)
        yield config


@pytest.fixture
def year_config_under_target(app, base_year_config, current_year):
    """Config with hours significantly under target (1200 hours)."""
    with app.app_context():
        config = db.session.get(YearConfig, base_year_config.id)

        # Add 100 hours per month for all 12 months = 1200 total
        for month in range(1, 13):
            entry = DailyEntry(
                year_config_id=config.id,
                date=datetime.date(current_year, month, 15),
                hours_billed=100.0,
            )
            db.session.add(entry)

        db.session.commit()
        db.session.refresh(config)
        yield config


@pytest.fixture
def year_config_midyear_start(app, current_year):
    """Config with mid-year start and historical hours."""
    with app.app_context():
        config = YearConfig(
            year=current_year,
            annual_target=1800,
            start_date=datetime.date(current_year, 7, 1),
            hours_pre_start=900.0,  # 900 hours before July
        )
        db.session.add(config)
        db.session.flush()

        # Add month configs
        for month in range(1, 13):
            month_config = MonthConfig(
                year_config_id=config.id,
                month=month,
                intensity=IntensityLevel.NORMAL,
            )
            db.session.add(month_config)

        # Add plan configs
        for plan_type in [PlanType.FIRM, PlanType.REALISTIC, PlanType.OPTIMISTIC]:
            target_date = (
                datetime.date(current_year, 11, 27)
                if plan_type == PlanType.OPTIMISTIC
                else datetime.date(current_year, 12, 31)
            )
            plan = PlanConfig(
                year_config_id=config.id,
                plan_type=plan_type,
                target_date=target_date,
            )
            db.session.add(plan)

        # Add entry for July
        entry = DailyEntry(
            year_config_id=config.id,
            date=datetime.date(current_year, 7, 15),
            hours_billed=150.0,
        )
        db.session.add(entry)

        db.session.commit()
        db.session.refresh(config)
        yield config


# -----------------------------------------------------------------------------
# Early Year Export Tests
# -----------------------------------------------------------------------------


class TestEarlyYearExport:
    """Tests for export with only early-year data (January only)."""

    def test_january_only_shows_single_month_actual(
        self, app, year_config_january_only, current_year
    ):
        """Actual data shows January hours only."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config_january_only.id)
            actual_data = get_cumulative_actual_data(config, through_month=1)

            assert len(actual_data) == 1
            assert actual_data[0].month == 1
            assert actual_data[0].cumulative_hours == 150.0

    def test_early_year_all_three_plan_lines_present(
        self, app, year_config_january_only, current_year
    ):
        """Export data includes all three plan trajectories."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config_january_only.id)
            export_data = get_export_data(config, as_of_date=datetime.date(current_year, 1, 31))

            assert len(export_data.firm_data) == 12
            assert len(export_data.optimistic_data) == 12
            assert len(export_data.realistic_data) == 12

    def test_early_year_summary_statistics_accurate(
        self, app, year_config_january_only, current_year
    ):
        """Summary shows accurate YTD and remaining hours."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config_january_only.id)
            export_data = get_export_data(config, as_of_date=datetime.date(current_year, 1, 31))

            assert export_data.summary.ytd_hours == 150.0
            assert export_data.summary.annual_target == 1800
            assert export_data.summary.hours_remaining == 1650.0

    def test_early_year_png_and_pdf_both_work(
        self, client, app, year_config_january_only
    ):
        """Both PNG and PDF downloads work with early-year data."""
        # PNG download
        png_response = client.get("/export/chart.png")
        assert png_response.status_code == 200
        assert png_response.data[:8] == b'\x89PNG\r\n\x1a\n'

        # PDF download
        pdf_response = client.get("/export/chart.pdf")
        assert pdf_response.status_code == 200
        assert pdf_response.data[:4] == b'%PDF'


# -----------------------------------------------------------------------------
# Mid-Year Export Tests
# -----------------------------------------------------------------------------


class TestMidYearExport:
    """Tests for export with mid-year data (through June)."""

    def test_june_cumulative_hours_accurate(
        self, app, year_config_mid_year, current_year
    ):
        """Cumulative actual through June shows correct total."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config_mid_year.id)
            actual_data = get_cumulative_actual_data(config, through_month=6)

            assert len(actual_data) == 6
            # 150 per month cumulative: 150, 300, 450, 600, 750, 900
            assert actual_data[0].cumulative_hours == 150.0
            assert actual_data[5].cumulative_hours == 900.0

    def test_mid_year_projection_calculation(
        self, app, year_config_mid_year, current_year
    ):
        """Pace projection should extrapolate to full year."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config_mid_year.id)
            export_data = get_export_data(config, as_of_date=datetime.date(current_year, 6, 30))

            # 900 hours in 6 months = 150/month = 1800 projected
            assert export_data.summary.current_pace_projection == pytest.approx(1800.0, rel=0.01)

    def test_mid_year_all_months_in_data(
        self, app, year_config_mid_year, current_year
    ):
        """All 12 months present in plan data."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config_mid_year.id)
            export_data = get_export_data(config, as_of_date=datetime.date(current_year, 6, 30))

            # Plan data always has 12 months
            assert len(export_data.firm_data) == 12
            assert export_data.firm_data[11].month == 12
            assert export_data.firm_data[11].month_name == 'Dec'

    def test_mid_year_summary_shows_progress(
        self, app, year_config_mid_year, current_year
    ):
        """Summary shows approximately 50% progress."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config_mid_year.id)
            export_data = get_export_data(config, as_of_date=datetime.date(current_year, 6, 30))

            # 900/1800 = 50%
            assert export_data.summary.ytd_hours == 900.0
            assert export_data.summary.hours_remaining == 900.0


# -----------------------------------------------------------------------------
# End of Year Export Tests
# -----------------------------------------------------------------------------


class TestEndOfYearExport:
    """Tests for export with full-year data."""

    def test_full_year_totals_match_entries(
        self, app, year_config_full_year, current_year
    ):
        """YTD total matches sum of all entries."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config_full_year.id)
            export_data = get_export_data(config, as_of_date=datetime.date(current_year, 12, 31))

            # 12 months × 150 hours = 1800
            assert export_data.summary.ytd_hours == 1800.0

    def test_end_year_comparison_to_annual_target(
        self, app, year_config_full_year, current_year
    ):
        """Summary correctly compares to annual target."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config_full_year.id)
            export_data = get_export_data(config, as_of_date=datetime.date(current_year, 12, 31))

            assert export_data.summary.ytd_hours == export_data.summary.annual_target
            assert export_data.summary.hours_remaining == 0.0

    def test_december_cumulative_equals_ytd(
        self, app, year_config_full_year, current_year
    ):
        """December cumulative actual equals YTD total."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config_full_year.id)
            actual_data = get_cumulative_actual_data(config, through_month=12)

            # December cumulative should be 1800
            assert actual_data[11].cumulative_hours == 1800.0


# -----------------------------------------------------------------------------
# Edge Cases Tests
# -----------------------------------------------------------------------------


class TestExportEdgeCases:
    """Tests for export edge cases."""

    def test_export_exactly_on_target(
        self, app, year_config_full_year, current_year
    ):
        """Export handles exactly meeting target."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config_full_year.id)
            export_data = get_export_data(config, as_of_date=datetime.date(current_year, 12, 31))

            # Exactly on target
            assert export_data.summary.ytd_hours == 1800.0
            assert export_data.summary.hours_remaining == 0.0
            # Status should indicate on track or ahead (at year end with target met)
            status_lower = export_data.summary.status.lower()
            assert "track" in status_lower or "met" in status_lower or "ahead" in status_lower

    def test_export_significantly_over_target(
        self, app, year_config_over_target, current_year
    ):
        """Export handles exceeding target."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config_over_target.id)
            export_data = get_export_data(config, as_of_date=datetime.date(current_year, 12, 31))

            # Over target (2199.96 due to 183.33 × 12)
            assert export_data.summary.ytd_hours > 1800.0
            # hours_remaining is clamped to 0 when over target
            assert export_data.summary.hours_remaining == 0
            # Status should indicate ahead
            assert "ahead" in export_data.summary.status.lower()

    def test_export_significantly_under_target(
        self, app, year_config_under_target, current_year
    ):
        """Export handles being significantly under target."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config_under_target.id)
            export_data = get_export_data(config, as_of_date=datetime.date(current_year, 12, 31))

            # Under target (1200 hours)
            assert export_data.summary.ytd_hours == 1200.0
            assert export_data.summary.hours_remaining == 600.0

    def test_export_with_midyear_start_and_historical(
        self, app, year_config_midyear_start, current_year
    ):
        """Export includes historical hours from mid-year start."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config_midyear_start.id)
            actual_data = get_cumulative_actual_data(config, through_month=7)

            # Historical 900 + July 150 = 1050
            # First 6 months show historical only (900)
            assert actual_data[0].cumulative_hours == 900.0
            # July shows total
            assert actual_data[6].cumulative_hours == 1050.0

    def test_export_with_active_catchup_sprint(
        self, app, year_config_mid_year, current_year
    ):
        """Export works when there's an active catch-up sprint."""
        with app.app_context():
            config = db.session.get(YearConfig, year_config_mid_year.id)

            # Add an active catch-up sprint
            sprint = CatchUpSprint(
                year_config_id=config.id,
                target_plan=PlanType.REALISTIC,
                start_date=datetime.date(current_year, 6, 1),
                end_date=datetime.date(current_year, 6, 14),
                target_hours=50.0,
                status=SprintStatus.ACTIVE,
            )
            db.session.add(sprint)
            db.session.commit()

            # Export should still work
            export_data = get_export_data(config, as_of_date=datetime.date(current_year, 6, 30))

            assert export_data is not None
            assert export_data.summary.ytd_hours == 900.0


# -----------------------------------------------------------------------------
# File Verification Tests
# -----------------------------------------------------------------------------


class TestFileVerification:
    """Tests for file format verification."""

    def test_png_has_valid_image_dimensions(
        self, client, app, year_config_mid_year
    ):
        """PNG file has valid image dimensions."""
        response = client.get("/export/chart.png")
        assert response.status_code == 200

        # Check PNG magic bytes
        assert response.data[:8] == b'\x89PNG\r\n\x1a\n'

        # Try to parse PNG dimensions from IHDR chunk
        # PNG structure: signature (8) + IHDR length (4) + IHDR type (4) + width (4) + height (4)
        # IHDR chunk starts at byte 8
        ihdr_length = int.from_bytes(response.data[8:12], 'big')
        ihdr_type = response.data[12:16]

        if ihdr_type == b'IHDR':
            width = int.from_bytes(response.data[16:20], 'big')
            height = int.from_bytes(response.data[20:24], 'big')

            # Chart should have reasonable dimensions (at least 100x100)
            assert width >= 100
            assert height >= 100
            # And not unreasonably large (less than 10000x10000)
            assert width < 10000
            assert height < 10000

    def test_pdf_has_multiple_pages_or_content(
        self, client, app, year_config_mid_year
    ):
        """PDF file has valid content."""
        response = client.get("/export/chart.pdf")
        assert response.status_code == 200

        # Check PDF magic bytes
        assert response.data[:4] == b'%PDF'

        # PDF should have reasonable size (more than just header)
        assert len(response.data) > 1000

        # Should contain standard PDF elements
        pdf_content = response.data
        assert b'endobj' in pdf_content  # PDF objects
        assert b'%%EOF' in pdf_content or b'endstream' in pdf_content

    def test_filename_follows_convention_with_date(
        self, client, app, year_config_mid_year, current_year
    ):
        """Filename follows billable_hours_{year}_{date}.ext convention."""
        # PNG filename
        png_response = client.get("/export/chart.png")
        content_disp = png_response.headers.get("Content-Disposition", "")

        assert "billable_hours" in content_disp
        assert str(current_year) in content_disp
        assert ".png" in content_disp

        # PDF filename
        pdf_response = client.get("/export/chart.pdf")
        content_disp = pdf_response.headers.get("Content-Disposition", "")

        assert "billable_hours" in content_disp
        assert str(current_year) in content_disp
        assert ".pdf" in content_disp
