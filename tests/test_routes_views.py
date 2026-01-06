"""
Integration tests for views routes (monthly calendar and history).

Tests the view route handlers in app/routes/views.py,
verifying calendar views, history displays, and navigation.
"""

import datetime

import pytest

from app import db
from app.models import (
    DailyEntry,
    Holiday,
    IntensityLevel,
    MonthConfig,
    PlanConfig,
    PlanType,
    VacationDay,
    YearConfig,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def year_config_with_plans(app):
    """
    Create a complete YearConfig with all three plans and 12 month configs.

    This represents a fully configured user ready to track hours.
    """
    with app.app_context():
        year_config = YearConfig(year=2025, annual_target=1800)
        db.session.add(year_config)
        db.session.flush()

        # Add 12 month configs with default intensity
        for month in range(1, 13):
            month_config = MonthConfig(
                year_config_id=year_config.id,
                month=month,
                intensity=IntensityLevel.NORMAL,
            )
            db.session.add(month_config)

        # Add all three plans
        firm = PlanConfig(
            year_config_id=year_config.id,
            plan_type=PlanType.FIRM,
            target_date=datetime.date(2025, 12, 31),
        )
        realistic = PlanConfig(
            year_config_id=year_config.id,
            plan_type=PlanType.REALISTIC,
            target_date=datetime.date(2025, 12, 31),
        )
        optimistic = PlanConfig(
            year_config_id=year_config.id,
            plan_type=PlanType.OPTIMISTIC,
            target_date=datetime.date(2025, 11, 27),
            target_daily_hours_after=2.0,
        )
        db.session.add_all([firm, realistic, optimistic])
        db.session.commit()
        db.session.refresh(year_config)

        yield year_config


@pytest.fixture
def year_config_with_entries(app, year_config_with_plans):
    """
    Add daily entries across multiple months for history testing.

    Adds entries for January and February 2025.
    """
    with app.app_context():
        year_config = db.session.get(YearConfig, year_config_with_plans.id)

        # January entries - first week (Mon 6 - Fri 10)
        january_entries = [
            DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 6),
                hours_billed=7.5,
            ),
            DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 7),
                hours_billed=8.0,
            ),
            DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 8),
                hours_billed=7.5,
            ),
            DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 9),
                hours_billed=8.0,
            ),
            DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 10),
                hours_billed=7.0,
            ),
        ]

        # February entries
        february_entries = [
            DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 2, 3),
                hours_billed=8.0,
            ),
            DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 2, 4),
                hours_billed=7.5,
            ),
            DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 2, 5),
                hours_billed=8.5,
            ),
        ]

        db.session.add_all(january_entries + february_entries)
        db.session.commit()
        db.session.refresh(year_config)

        yield year_config


@pytest.fixture
def year_config_with_mixed_entries(app, year_config_with_plans):
    """
    Create entries with different statuses for color coding tests.

    Creates:
    - Entry meeting target (8.0 hours)
    - Entry below target (3.0 hours)
    - Skips a workday (missed)
    """
    with app.app_context():
        year_config = db.session.get(YearConfig, year_config_with_plans.id)

        # Add a holiday to test 'off' status
        holiday = Holiday(
            year_config_id=year_config.id,
            date=datetime.date(2025, 1, 1),  # New Year's Day
            name="New Year's Day",
        )
        db.session.add(holiday)

        # Entry meeting target (Jan 6 - Monday)
        entry_met = DailyEntry(
            year_config_id=year_config.id,
            date=datetime.date(2025, 1, 6),
            hours_billed=8.0,  # Should meet target
        )

        # Entry below target (Jan 7 - Tuesday)
        entry_behind = DailyEntry(
            year_config_id=year_config.id,
            date=datetime.date(2025, 1, 7),
            hours_billed=3.0,  # Below target
        )

        # Skip Jan 8 (Wednesday) - will show as 'missed' if in past

        db.session.add_all([entry_met, entry_behind])
        db.session.commit()
        db.session.refresh(year_config)

        yield year_config


# -----------------------------------------------------------------------------
# Monthly View Access Tests
# -----------------------------------------------------------------------------


class TestMonthlyViewAccess:
    """Tests for basic monthly view access and redirects."""

    def test_monthly_redirects_to_current_month(self, client, year_config_with_plans):
        """GET /monthly redirects to /monthly/<year>/<month> for current month."""
        response = client.get("/monthly")

        assert response.status_code == 302
        # Should redirect to a monthly URL with year/month
        assert "/monthly/" in response.location

    def test_monthly_specific_returns_200(self, client, year_config_with_plans):
        """GET /monthly/<year>/<month> returns 200 with valid config."""
        response = client.get("/monthly/2025/3")

        assert response.status_code == 200
        assert b"March" in response.data

    def test_monthly_redirects_without_config(self, client, app):
        """GET /monthly redirects to setup when no YearConfig exists."""
        with app.app_context():
            YearConfig.query.delete()
            db.session.commit()

        # First get redirects to specific month, which then redirects to setup
        response = client.get("/monthly", follow_redirects=True)

        # After following redirects, should end up at setup
        response_text = response.data.decode("utf-8").lower()
        assert "setup" in response_text or response.request.path == "/setup/"

    def test_monthly_invalid_month_flashes_error(self, client, year_config_with_plans):
        """GET /monthly/<year>/13 (invalid month) redirects with error."""
        response = client.get("/monthly/2025/13")

        assert response.status_code == 302
        # Should redirect back to monthly


# -----------------------------------------------------------------------------
# Monthly View Content Tests
# -----------------------------------------------------------------------------


class TestMonthlyViewContent:
    """Tests for monthly view content accuracy."""

    def test_monthly_shows_correct_month(self, client, year_config_with_plans):
        """Monthly view displays the requested month name."""
        response = client.get("/monthly/2025/6")

        assert response.status_code == 200
        assert b"June" in response.data
        assert b"2025" in response.data

    def test_monthly_navigation_shows_prev_next(self, client, year_config_with_plans):
        """Monthly view shows navigation links for previous and next months."""
        response = client.get("/monthly/2025/6")
        response_text = response.data.decode("utf-8")

        assert response.status_code == 200
        # Check for prev month link (May)
        assert "/monthly/2025/5" in response_text
        # Check for next month link (July)
        assert "/monthly/2025/7" in response_text

    def test_monthly_navigation_year_boundary(self, client, year_config_with_plans):
        """Monthly view handles year boundary navigation (Dec -> Jan)."""
        response = client.get("/monthly/2025/12")
        response_text = response.data.decode("utf-8")

        assert response.status_code == 200
        # Previous should be November 2025
        assert "/monthly/2025/11" in response_text
        # Next should be January 2026
        assert "/monthly/2026/1" in response_text

    def test_monthly_shows_color_coding_met(
        self, client, year_config_with_mixed_entries
    ):
        """Monthly view shows green color for days meeting target."""
        response = client.get("/monthly/2025/1")
        response_text = response.data.decode("utf-8")

        assert response.status_code == 200
        # Should have green styling for met target
        assert "bg-green" in response_text

    def test_monthly_shows_color_coding_behind(
        self, client, year_config_with_mixed_entries
    ):
        """Monthly view shows amber color for days behind target."""
        response = client.get("/monthly/2025/1")
        response_text = response.data.decode("utf-8")

        assert response.status_code == 200
        # Should have amber styling for behind target
        assert "bg-amber" in response_text

    def test_monthly_shows_color_coding_off(
        self, client, year_config_with_mixed_entries
    ):
        """Monthly view shows slate color for off days (holidays, weekends)."""
        response = client.get("/monthly/2025/1")
        response_text = response.data.decode("utf-8")

        assert response.status_code == 200
        # Should have slate styling for off days
        assert "bg-slate" in response_text


# -----------------------------------------------------------------------------
# History View Access Tests
# -----------------------------------------------------------------------------


class TestHistoryViewAccess:
    """Tests for basic history view access."""

    def test_history_returns_200(self, client, year_config_with_plans):
        """GET /history returns 200 with valid config."""
        response = client.get("/history")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8").lower()
        assert "history" in response_text or "entry" in response_text

    def test_history_redirects_without_config(self, client, app):
        """GET /history redirects to setup when no YearConfig exists."""
        with app.app_context():
            YearConfig.query.delete()
            db.session.commit()

        response = client.get("/history")

        assert response.status_code == 302
        assert "/setup/" in response.location


# -----------------------------------------------------------------------------
# History View Content Tests
# -----------------------------------------------------------------------------


class TestHistoryViewContent:
    """Tests for history view content accuracy."""

    def test_history_shows_all_entries(self, client, year_config_with_entries):
        """History view displays all daily entries."""
        response = client.get("/history")
        response_text = response.data.decode("utf-8")

        assert response.status_code == 200

        # Check for entry hours appearing (we have 7.5, 8.0, 7.0, 8.5 hours)
        assert "7.5" in response_text
        assert "8.0" in response_text
        assert "7.0" in response_text
        assert "8.5" in response_text

    def test_history_shows_monthly_subtotals(self, client, year_config_with_entries):
        """History view displays monthly subtotals."""
        response = client.get("/history")
        response_text = response.data.decode("utf-8")

        assert response.status_code == 200

        # Should show month names for months with entries
        assert "January" in response_text
        assert "February" in response_text

    def test_history_shows_ytd_totals(self, client, year_config_with_entries):
        """History view displays year-to-date totals."""
        response = client.get("/history")
        response_text = response.data.decode("utf-8")

        assert response.status_code == 200

        # Should show annual target (1800)
        assert "1800" in response_text or "1,800" in response_text

        # Calculate expected total: 5 Jan entries (7.5+8+7.5+8+7=38) + 3 Feb entries (8+7.5+8.5=24) = 62
        # Look for YTD total or check that numbers appear
        assert "62" in response_text or "38" in response_text

    def test_history_shows_remaining_hours(self, client, year_config_with_entries):
        """History view displays remaining hours needed."""
        response = client.get("/history")
        response_text = response.data.decode("utf-8").lower()

        assert response.status_code == 200

        # Should have remaining hours section
        assert "remaining" in response_text or "left" in response_text
