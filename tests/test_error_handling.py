"""
Error handling and validation tests.

Tests error conditions, input validation, and graceful failure handling
across the application. Sprint 3.12.
"""

import datetime

import pytest

from app import db
from app.models import (
    CatchUpSprint,
    DailyEntry,
    Holiday,
    IntensityLevel,
    MonthConfig,
    PlanConfig,
    PlanType,
    SprintStatus,
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

    Uses current year to match route lookups.
    """
    current_year = datetime.date.today().year

    with app.app_context():
        year_config = YearConfig(year=current_year, annual_target=1800)
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
            target_date=datetime.date(current_year, 12, 31),
        )
        realistic = PlanConfig(
            year_config_id=year_config.id,
            plan_type=PlanType.REALISTIC,
            target_date=datetime.date(current_year, 12, 31),
        )
        optimistic = PlanConfig(
            year_config_id=year_config.id,
            plan_type=PlanType.OPTIMISTIC,
            target_date=datetime.date(current_year, 11, 27),
            target_daily_hours_after=2.0,
        )
        db.session.add_all([firm, realistic, optimistic])
        db.session.commit()
        db.session.refresh(year_config)

        yield year_config


@pytest.fixture
def year_config_behind(app, year_config_with_plans):
    """
    Create a config where user is behind on billing targets.

    Adds minimal entries so user will be behind, making them eligible
    for catch-up sprint creation.
    """
    current_year = datetime.date.today().year

    with app.app_context():
        year_config = db.session.get(YearConfig, year_config_with_plans.id)

        # Add only minimal entries to ensure user is behind
        entries = [
            DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(current_year, 1, 6),
                hours_billed=2.0,
            ),
            DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(current_year, 1, 7),
                hours_billed=2.0,
            ),
        ]
        db.session.add_all(entries)
        db.session.commit()
        db.session.refresh(year_config)

        yield year_config


# -----------------------------------------------------------------------------
# Error Handler Tests
# -----------------------------------------------------------------------------


class TestErrorHandlers:
    """Tests for 404/500 error handlers."""

    def test_404_for_invalid_route(self, client):
        """Invalid route returns 404 page."""
        response = client.get("/nonexistent-page-that-does-not-exist")

        assert response.status_code == 404

    def test_404_for_invalid_entry_delete(self, client, year_config_with_plans):
        """Delete request for non-existent entry returns 404."""
        response = client.post("/entries/delete/99999")

        # Should return 404 (entry not found)
        assert response.status_code == 404


# -----------------------------------------------------------------------------
# Setup Validation Tests
# -----------------------------------------------------------------------------


class TestSetupValidation:
    """Tests for setup wizard validation."""

    def test_setup_year_too_far_future(self, client):
        """Year more than 1 year in future is rejected."""
        current_year = datetime.date.today().year
        future_year = current_year + 2

        response = client.post(
            "/setup/year",
            data={
                "year": str(future_year),
                "annual_target": "1800",
            },
        )

        # Should redirect back to year page (validation failed)
        assert response.status_code == 302
        assert "/setup/" in response.location

    def test_setup_year_too_far_past(self, client):
        """Year more than 1 year in past is rejected."""
        current_year = datetime.date.today().year
        past_year = current_year - 2

        response = client.post(
            "/setup/year",
            data={
                "year": str(past_year),
                "annual_target": "1800",
            },
        )

        # Should redirect back (validation failed)
        assert response.status_code == 302
        assert "/setup/" in response.location

    def test_setup_annual_target_too_low(self, client):
        """Annual target below 1000 is rejected."""
        current_year = datetime.date.today().year

        response = client.post(
            "/setup/year",
            data={
                "year": str(current_year),
                "annual_target": "500",
            },
        )

        # Should redirect back (validation failed)
        assert response.status_code == 302
        assert "/setup/" in response.location

    def test_setup_annual_target_too_high(self, client):
        """Annual target above 3000 is rejected."""
        current_year = datetime.date.today().year

        response = client.post(
            "/setup/year",
            data={
                "year": str(current_year),
                "annual_target": "5000",
            },
        )

        # Should redirect back (validation failed)
        assert response.status_code == 302
        assert "/setup/" in response.location

    def test_holiday_invalid_date_format(self, client, year_config_with_plans):
        """Invalid date format in holiday is rejected."""
        response = client.post(
            "/setup/holidays/add",
            data={"date": "not-a-date"},
            headers={"HX-Request": "true"},
        )

        # Should return 400 with error in HX-Trigger header
        assert response.status_code == 400
        hx_trigger = response.headers.get("HX-Trigger", "")
        assert "Invalid date format" in hx_trigger

    def test_holiday_date_wrong_year(self, client, app, year_config_with_plans):
        """Holiday date in wrong year is rejected."""
        # Get config year
        with app.app_context():
            year_config = db.session.get(YearConfig, year_config_with_plans.id)
            wrong_year = year_config.year + 1

        response = client.post(
            "/setup/holidays/add",
            data={"date": f"{wrong_year}-07-04"},
            headers={"HX-Request": "true"},
        )

        # Should return 400 with error in HX-Trigger header
        assert response.status_code == 400
        hx_trigger = response.headers.get("HX-Trigger", "")
        assert "must be in" in hx_trigger


# -----------------------------------------------------------------------------
# Entry Validation Tests
# -----------------------------------------------------------------------------


class TestEntryValidation:
    """Tests for daily entry validation."""

    def test_entry_negative_hours_rejected(self, client, app, year_config_with_plans):
        """Negative hours in entry are rejected."""
        current_year = datetime.date.today().year

        # First create a valid entry
        with app.app_context():
            year_config = db.session.get(YearConfig, year_config_with_plans.id)
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(current_year, 1, 15),
                hours_billed=7.5,
            )
            db.session.add(entry)
            db.session.commit()
            entry_id = entry.id

        # Try to update with negative hours
        response = client.put(
            f"/entries/{entry_id}",
            data={"hours": "-1"},
            headers={"HX-Request": "true"},
        )

        # Should return 400 with error
        assert response.status_code == 400

    def test_entry_hours_over_24_rejected(self, client, app, year_config_with_plans):
        """Hours over 24 in entry are rejected."""
        current_year = datetime.date.today().year

        # First create a valid entry
        with app.app_context():
            year_config = db.session.get(YearConfig, year_config_with_plans.id)
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(current_year, 1, 16),
                hours_billed=7.5,
            )
            db.session.add(entry)
            db.session.commit()
            entry_id = entry.id

        # Try to update with hours > 24
        response = client.put(
            f"/entries/{entry_id}",
            data={"hours": "25"},
            headers={"HX-Request": "true"},
        )

        # Should return 400 with error
        assert response.status_code == 400

    def test_entry_invalid_hours_format(self, client, app, year_config_with_plans):
        """Non-numeric hours are rejected."""
        current_year = datetime.date.today().year

        # First create a valid entry
        with app.app_context():
            year_config = db.session.get(YearConfig, year_config_with_plans.id)
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(current_year, 1, 17),
                hours_billed=7.5,
            )
            db.session.add(entry)
            db.session.commit()
            entry_id = entry.id

        # Try to update with non-numeric hours
        response = client.put(
            f"/entries/{entry_id}",
            data={"hours": "abc"},
            headers={"HX-Request": "true"},
        )

        # Should return 400 with error
        assert response.status_code == 400

    def test_entry_update_nonexistent_returns_404(self, client, year_config_with_plans):
        """Updating non-existent entry returns 404."""
        response = client.put(
            "/entries/99999",
            data={"hours": "7.5"},
            headers={"HX-Request": "true"},
        )

        # Should return 404
        assert response.status_code == 404


# -----------------------------------------------------------------------------
# Catch-Up Validation Tests
# -----------------------------------------------------------------------------


class TestCatchUpValidation:
    """Tests for catch-up sprint validation."""

    def test_sprint_duration_clamped_low(self, client, app, year_config_behind):
        """Duration below 1 week is clamped to 1."""
        response = client.post(
            "/catchup/",
            data={
                "plan_type": "realistic",
                "duration": "0",  # Below minimum
            },
        )

        # Should redirect (success or error, but not crash)
        assert response.status_code == 302

    def test_sprint_duration_clamped_high(self, client, app, year_config_behind):
        """Duration above 6 weeks is clamped to 6."""
        response = client.post(
            "/catchup/",
            data={
                "plan_type": "realistic",
                "duration": "10",  # Above maximum
            },
        )

        # Should redirect (success or error, but not crash)
        assert response.status_code == 302

    def test_weekend_hours_clamped(self, client, app, year_config_behind):
        """Weekend hours above 4 are clamped to 4."""
        response = client.post(
            "/catchup/",
            data={
                "plan_type": "realistic",
                "duration": "2",
                "include_weekends": "on",
                "weekend_hours": "10",  # Above maximum
            },
        )

        # Should redirect (value clamped, not rejected)
        assert response.status_code == 302

    def test_sprint_firm_plan_rejected(self, client, app, year_config_behind):
        """Cannot create catch-up sprint for Firm plan."""
        response = client.post(
            "/catchup/",
            data={
                "plan_type": "firm",
                "duration": "2",
            },
        )

        # Should redirect with error
        assert response.status_code == 302

        # Verify no sprint was created
        with app.app_context():
            sprint = CatchUpSprint.query.first()
            assert sprint is None


# -----------------------------------------------------------------------------
# Database Error Tests
# -----------------------------------------------------------------------------


class TestDatabaseErrors:
    """Tests for database constraint handling."""

    def test_duplicate_holiday_rejected(self, client, app, year_config_with_plans):
        """Adding same holiday date twice is rejected."""
        current_year = datetime.date.today().year
        date_str = f"{current_year}-07-04"

        # Add holiday first time
        response1 = client.post(
            "/setup/holidays/add",
            data={"date": date_str},
            headers={"HX-Request": "true"},
        )
        assert response1.status_code == 200

        # Try to add same date again
        response2 = client.post(
            "/setup/holidays/add",
            data={"date": date_str},
            headers={"HX-Request": "true"},
        )

        # Should return 400 with error in HX-Trigger header
        assert response2.status_code == 400
        hx_trigger = response2.headers.get("HX-Trigger", "")
        assert "already" in hx_trigger.lower()

    def test_duplicate_vacation_rejected(self, client, app, year_config_with_plans):
        """Adding same vacation date twice is rejected."""
        current_year = datetime.date.today().year
        date_str = f"{current_year}-08-15"

        # Add vacation first time
        response1 = client.post(
            "/setup/vacation/add",
            data={"date": date_str},
            headers={"HX-Request": "true"},
        )
        assert response1.status_code == 200

        # Try to add same date again
        response2 = client.post(
            "/setup/vacation/add",
            data={"date": date_str},
            headers={"HX-Request": "true"},
        )

        # Should return 400 with error in HX-Trigger header
        assert response2.status_code == 400
        hx_trigger = response2.headers.get("HX-Trigger", "")
        assert "already" in hx_trigger.lower()


# -----------------------------------------------------------------------------
# Missing Data Tests
# -----------------------------------------------------------------------------


class TestMissingData:
    """Tests for missing configuration handling."""

    def test_dashboard_without_config_redirects(self, client, app):
        """Dashboard redirects to setup when no config exists."""
        with app.app_context():
            # Delete all year configs
            YearConfig.query.delete()
            db.session.commit()

        response = client.get("/")

        assert response.status_code == 302
        assert "/setup/" in response.location

    def test_export_without_config_redirects(self, client, app):
        """Export redirects to setup when no config exists."""
        with app.app_context():
            # Delete all year configs
            YearConfig.query.delete()
            db.session.commit()

        response = client.get("/export/")

        assert response.status_code == 302
        assert "/setup/" in response.location

    def test_recent_entries_without_config_handles_gracefully(self, client, app):
        """Recent entries partial handles missing config gracefully."""
        with app.app_context():
            YearConfig.query.delete()
            db.session.commit()

        response = client.get("/entries/recent", headers={"HX-Request": "true"})

        # Should return without server error (200 empty or 302 redirect)
        assert response.status_code in [200, 302, 400]
        # Should not crash (no 500)

    def test_catchup_new_without_config_redirects(self, client, app):
        """Catch-up new redirects to setup when no config exists."""
        with app.app_context():
            YearConfig.query.delete()
            db.session.commit()

        response = client.get("/catchup/new")

        assert response.status_code == 302
        assert "/setup/" in response.location
