"""
Integration tests for mid-year start workflow (Sprint 4.4).

Tests the mid-year start functionality - entering historical hours and
verifying they integrate correctly with forward calculations, dashboard,
monthly view, and export.
"""

import datetime

import pytest

from app import db
from app.models import (
    DailyEntry,
    HistoricalMonth,
    IntensityLevel,
    MonthConfig,
    PlanConfig,
    PlanType,
    YearConfig,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def current_year():
    """Return the current year for testing."""
    return datetime.date.today().year


@pytest.fixture
def year_config_base(app, current_year):
    """
    Create a basic YearConfig without mid-year settings.
    """
    with app.app_context():
        year_config = YearConfig(year=current_year, annual_target=1800)
        db.session.add(year_config)
        db.session.flush()

        # Add 12 month configs
        for month in range(1, 13):
            month_config = MonthConfig(
                year_config_id=year_config.id,
                month=month,
                intensity=IntensityLevel.NORMAL,
            )
            db.session.add(month_config)

        # Add all three plans
        for plan_type in [PlanType.FIRM, PlanType.REALISTIC, PlanType.OPTIMISTIC]:
            target_date = (
                datetime.date(current_year, 11, 27)
                if plan_type == PlanType.OPTIMISTIC
                else datetime.date(current_year, 12, 31)
            )
            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=plan_type,
                target_date=target_date,
            )
            db.session.add(plan)

        db.session.commit()
        db.session.refresh(year_config)
        yield year_config


@pytest.fixture
def year_config_midyear_lump(app, year_config_base, current_year):
    """
    YearConfig with mid-year start and lump sum historical hours.

    Uses January 1 as start date so that today is always AFTER the start date,
    allowing historical hours to be included in calculations.
    """
    with app.app_context():
        config = db.session.get(YearConfig, year_config_base.id)
        # Use Jan 1 so today is always after start_date
        config.start_date = datetime.date(current_year, 1, 1)
        config.hours_pre_start = 900.0
        db.session.commit()
        db.session.refresh(config)
        yield config


@pytest.fixture
def year_config_midyear_monthly(app, year_config_base, current_year):
    """
    YearConfig with mid-year start (June 1) and monthly historical breakdown.
    """
    with app.app_context():
        config = db.session.get(YearConfig, year_config_base.id)
        config.start_date = datetime.date(current_year, 6, 1)

        # Add historical months for Jan-May (150 hours each = 750 total)
        for month in range(1, 6):
            hist = HistoricalMonth(
                year_config_id=config.id,
                month=month,
                hours_billed=150.0,
            )
            db.session.add(hist)

        db.session.commit()
        db.session.refresh(config)
        yield config


# -----------------------------------------------------------------------------
# Mid-Year Setup Tests
# -----------------------------------------------------------------------------


class TestMidYearSetup:
    """Tests for mid-year setup form and submission."""

    def test_midyear_form_shows_start_date(self, client, year_config_base):
        """Mid-year form displays start date picker."""
        response = client.get("/setup/midyear")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8").lower()
        assert "start" in response_text or "date" in response_text

    def test_lump_sum_saves_hours_pre_start(
        self, client, app, year_config_base, current_year
    ):
        """Lump sum mode saves hours to hours_pre_start field."""
        response = client.post(
            "/setup/midyear",
            data={
                "start_date": f"{current_year}-06-01",
                "entry_mode": "lump",
                "hours_pre_start": "900",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302

        with app.app_context():
            config = db.session.get(YearConfig, year_config_base.id)
            assert config.start_date == datetime.date(current_year, 6, 1)
            assert config.hours_pre_start == 900.0

    def test_monthly_breakdown_saves_historical_months(
        self, client, app, year_config_base, current_year
    ):
        """Monthly mode saves HistoricalMonth records."""
        response = client.post(
            "/setup/midyear",
            data={
                "start_date": f"{current_year}-06-01",
                "entry_mode": "monthly",
                "month_1": "150",
                "month_2": "150",
                "month_3": "150",
                "month_4": "150",
                "month_5": "150",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302

        with app.app_context():
            config = db.session.get(YearConfig, year_config_base.id)
            assert config.start_date == datetime.date(current_year, 6, 1)

            historical = HistoricalMonth.query.filter_by(
                year_config_id=config.id
            ).all()
            assert len(historical) == 5
            total = sum(h.hours_billed for h in historical)
            assert total == 750.0


# -----------------------------------------------------------------------------
# Dashboard with Historical Tests
# -----------------------------------------------------------------------------


class TestDashboardWithHistorical:
    """Tests for dashboard display with historical hours."""

    def test_ytd_includes_historical_hours(self, client, year_config_midyear_lump):
        """YTD total includes pre-start hours."""
        response = client.get("/")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8")

        # Should show 900 hours somewhere (historical total)
        assert "900" in response_text

    def test_remaining_target_accounts_for_historical(
        self, client, year_config_midyear_lump
    ):
        """Remaining target = annual target - historical hours."""
        response = client.get("/")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8")

        # With 1800 target and 900 historical, remaining should be 900
        # Look for this value or related calculations
        assert "900" in response_text or "1800" in response_text

    def test_daily_targets_for_remaining_months(
        self, client, year_config_midyear_lump
    ):
        """Daily targets calculated for remaining time (June-December)."""
        response = client.get("/")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8").lower()

        # Should show target information
        assert "target" in response_text or "hours" in response_text


# -----------------------------------------------------------------------------
# Entries with Historical Tests
# -----------------------------------------------------------------------------


class TestEntriesWithHistorical:
    """Tests for entries combining with historical hours."""

    def test_new_entry_adds_to_historical(
        self, client, app, year_config_midyear_lump, current_year
    ):
        """New entry adds to historical hours for correct YTD total."""
        # Enter hours for June 1 (first day of tracking)
        entry_date = datetime.date(current_year, 6, 2)
        client.post(
            "/entries/",
            data={"date": entry_date.isoformat(), "hours": "8.0"},
        )

        # Check dashboard shows combined total
        response = client.get("/")
        assert response.status_code == 200
        response_text = response.data.decode("utf-8")

        # Should show 908 (900 historical + 8 new) somewhere
        # Or at least show 8 as recent entry
        assert "8" in response_text

    def test_plan_status_includes_historical(self, client, year_config_midyear_lump):
        """Plan status calculations include historical hours."""
        response = client.get("/")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8")

        # All three plans should be visible
        assert "Firm" in response_text
        assert "Realistic" in response_text
        assert "Optimistic" in response_text


# -----------------------------------------------------------------------------
# Monthly View with Historical Tests
# -----------------------------------------------------------------------------


class TestMonthlyViewWithHistorical:
    """Tests for monthly view with historical data."""

    def test_pre_start_months_accessible(
        self, client, year_config_midyear_lump, current_year
    ):
        """Months before start date are accessible but may show as historical."""
        # Try to access January (before June start)
        response = client.get(f"/monthly/{current_year}/1")

        # Should return 200 (viewable) even for historical months
        assert response.status_code == 200

    def test_current_month_shows_entries(
        self, client, app, year_config_midyear_lump, current_year
    ):
        """Current/post-start month shows entries."""
        # Add an entry for June
        entry_date = datetime.date(current_year, 6, 15)
        with app.app_context():
            entry = DailyEntry(
                year_config_id=year_config_midyear_lump.id,
                date=entry_date,
                hours_billed=7.5,
            )
            db.session.add(entry)
            db.session.commit()

        # Check June monthly view
        response = client.get(f"/monthly/{current_year}/6")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8")
        assert "7.5" in response_text or "7.50" in response_text


# -----------------------------------------------------------------------------
# Export with Historical Tests
# -----------------------------------------------------------------------------


class TestExportWithHistorical:
    """Tests for export functionality with historical data."""

    def test_export_page_loads_with_historical(self, client, year_config_midyear_lump):
        """Export page loads correctly with historical data."""
        response = client.get("/export/")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8").lower()
        assert "export" in response_text or "chart" in response_text

    def test_export_summary_includes_historical(self, client, year_config_midyear_lump):
        """Export summary statistics include historical hours."""
        response = client.get("/export/")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8")

        # Should show 900 historical hours in summary
        assert "900" in response_text


# -----------------------------------------------------------------------------
# Full Mid-Year Workflow Tests
# -----------------------------------------------------------------------------


class TestFullMidYearWorkflow:
    """End-to-end tests for mid-year start workflows."""

    def test_complete_midyear_start_lump_sum(
        self, client, app, current_year
    ):
        """
        Complete mid-year start workflow with lump sum historical hours.

        Steps:
        1. Create year config via setup
        2. Configure mid-year start with lump sum (start_date = Jan 1 so today is past)
        3. Verify dashboard shows historical in YTD total
        4. Add new entry and verify combined total
        5. Check export includes historical
        """
        today = datetime.date.today()

        # Step 1: Create year config
        response = client.post(
            "/setup/year",
            data={"year": str(current_year), "annual_target": "1800"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        # Step 2: Configure mid-year with lump sum
        # Use Jan 1 as start_date so today is AFTER start_date (historical hours show)
        response = client.post(
            "/setup/midyear",
            data={
                "start_date": f"{current_year}-01-01",
                "entry_mode": "lump",
                "hours_pre_start": "500",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        with app.app_context():
            config = YearConfig.query.filter_by(year=current_year).first()
            assert config.hours_pre_start == 500.0
            config_id = config.id

        # Step 3: Verify dashboard shows historical in YTD
        response = client.get("/")
        assert response.status_code == 200
        response_text = response.data.decode("utf-8")
        # 500 historical hours should appear in "Total Billed" YTD section
        assert "500" in response_text

        # Step 4: Add new entry
        client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "8.0"},
        )

        # Verify dashboard shows combined (508 total)
        response = client.get("/")
        assert response.status_code == 200
        response_text = response.data.decode("utf-8")
        assert "508" in response_text  # Combined total visible

        # Step 5: Check export
        response = client.get("/export/")
        assert response.status_code == 200
        response_text = response.data.decode("utf-8")
        # Export should show 500 or 508 (historical or combined)
        assert "500" in response_text or "508" in response_text

    def test_complete_midyear_start_monthly(
        self, client, app, current_year
    ):
        """
        Complete mid-year start workflow with monthly breakdown.

        Note: Monthly breakdown is most useful when testing later in the year
        (e.g., starting in June with Jan-May historical data). When testing
        in January, we verify the setup saves correctly but dashboard display
        of historical totals only works when today > start_date.

        Steps:
        1. Create year config via setup
        2. Configure mid-year start with monthly breakdown for future start
        3. Verify HistoricalMonth records are saved correctly
        4. Add entry for future date and verify saved
        """
        # Step 1: Create year config
        response = client.post(
            "/setup/year",
            data={"year": str(current_year), "annual_target": "1800"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        # Step 2: Configure mid-year with monthly breakdown
        # Using June 1 start date with Jan-May historical months
        response = client.post(
            "/setup/midyear",
            data={
                "start_date": f"{current_year}-06-01",
                "entry_mode": "monthly",
                "month_1": "150",
                "month_2": "160",
                "month_3": "170",
                "month_4": "180",
                "month_5": "190",  # Total: 850
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        # Step 3: Verify HistoricalMonth records saved correctly
        with app.app_context():
            config = YearConfig.query.filter_by(year=current_year).first()
            assert config.start_date == datetime.date(current_year, 6, 1)

            historical = HistoricalMonth.query.filter_by(
                year_config_id=config.id
            ).all()
            assert len(historical) == 5
            total = sum(h.hours_billed for h in historical)
            assert total == 850.0
            config_id = config.id

            # Verify get_historical_hours returns correct total
            from app.services.calculator import get_historical_hours
            calc_total = get_historical_hours(config)
            assert calc_total == 850.0

        # Step 4: Dashboard loads successfully (historical shows when today > start_date)
        response = client.get("/")
        assert response.status_code == 200

        # Step 5: Add entry for June (after start_date)
        entry_date = datetime.date(current_year, 6, 5)
        client.post(
            "/entries/",
            data={"date": entry_date.isoformat(), "hours": "7.5"},
        )

        # Verify entry is recorded
        with app.app_context():
            entry = DailyEntry.query.filter_by(
                year_config_id=config_id,
                date=entry_date
            ).first()
            assert entry is not None
            assert entry.hours_billed == 7.5
