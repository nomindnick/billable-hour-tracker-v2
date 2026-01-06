"""
Integration tests for dashboard routes.

Tests the dashboard route handlers in app/routes/dashboard.py,
verifying correct responses for various application states.
"""

import datetime

import pytest

from app import db
from app.models import (
    CatchUpSprint,
    DailyEntry,
    IntensityLevel,
    MonthConfig,
    PlanConfig,
    PlanType,
    SprintStatus,
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
    Add some daily entries to an existing year config.

    Adds 5 days of entries for January 2025.
    """
    with app.app_context():
        year_config = db.session.get(YearConfig, year_config_with_plans.id)

        # Add entries for first week of January 2025
        entries = [
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
        db.session.add_all(entries)
        db.session.commit()
        db.session.refresh(year_config)

        yield year_config


@pytest.fixture
def year_config_with_active_sprint(app, year_config_with_plans):
    """
    Add an active catch-up sprint to an existing year config.
    """
    with app.app_context():
        year_config = db.session.get(YearConfig, year_config_with_plans.id)

        sprint = CatchUpSprint(
            year_config_id=year_config.id,
            target_plan=PlanType.REALISTIC,
            start_date=datetime.date(2025, 1, 6),
            end_date=datetime.date(2025, 1, 17),
            target_hours=80.0,
            status=SprintStatus.ACTIVE,
        )
        db.session.add(sprint)
        db.session.commit()
        db.session.refresh(sprint)

        yield year_config, sprint


# -----------------------------------------------------------------------------
# Dashboard Access Tests
# -----------------------------------------------------------------------------


class TestDashboardAccess:
    """Tests for basic dashboard access and redirects."""

    def test_dashboard_returns_200_with_valid_config(self, client, year_config_with_plans):
        """GET / returns 200 with a valid YearConfig."""
        response = client.get("/")

        assert response.status_code == 200
        assert b"Dashboard" in response.data or b"dashboard" in response.data

    def test_dashboard_redirects_without_config(self, client, app):
        """GET / redirects to /setup/ when no YearConfig exists."""
        with app.app_context():
            # Ensure no configs exist
            YearConfig.query.delete()
            db.session.commit()

        response = client.get("/")

        assert response.status_code == 302
        assert "/setup/" in response.location

    def test_dashboard_handles_no_entries_gracefully(self, client, year_config_with_plans):
        """Dashboard displays correctly when user has no daily entries."""
        response = client.get("/")

        assert response.status_code == 200
        # Should still show the dashboard structure
        assert b"Today" in response.data or b"target" in response.data.lower()


# -----------------------------------------------------------------------------
# Dashboard Content Tests
# -----------------------------------------------------------------------------


class TestDashboardContent:
    """Tests for dashboard content accuracy."""

    def test_dashboard_shows_todays_target(self, client, year_config_with_plans):
        """Dashboard displays today's billing target."""
        response = client.get("/")

        assert response.status_code == 200
        # Dashboard should show a target value (contains "hours" or a number)
        response_text = response.data.decode("utf-8").lower()
        assert "target" in response_text or "hours" in response_text

    def test_dashboard_shows_weekly_progress(self, client, year_config_with_entries):
        """Dashboard displays weekly progress section."""
        response = client.get("/")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8").lower()
        assert "week" in response_text

    def test_dashboard_shows_monthly_progress(self, client, year_config_with_entries):
        """Dashboard displays monthly progress section."""
        response = client.get("/")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8").lower()
        assert "month" in response_text

    def test_dashboard_shows_all_three_plan_status_cards(
        self, client, year_config_with_plans
    ):
        """Dashboard displays status cards for Firm, Realistic, and Optimistic plans."""
        response = client.get("/")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8")

        # Check for each plan type in the response
        assert "Firm" in response_text
        assert "Realistic" in response_text
        assert "Optimistic" in response_text

    def test_dashboard_shows_active_sprint(self, client, year_config_with_active_sprint):
        """Dashboard displays active catch-up sprint when one exists."""
        response = client.get("/")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8").lower()

        # Should show sprint-related content
        assert "sprint" in response_text or "catch" in response_text
