"""
Integration tests for setup routes.

Tests the setup wizard route handlers in app/routes/setup.py,
verifying year configuration, holidays, vacation, and plan setup.
"""

import datetime

import pytest

from app import db
from app.models import (
    Holiday,
    HistoricalMonth,
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
def year_config(app):
    """Create a basic YearConfig for testing setup continuation."""
    with app.app_context():
        year_config = YearConfig(year=2025, annual_target=1800)
        db.session.add(year_config)
        db.session.flush()

        # Add 12 month configs
        for month in range(1, 13):
            mc = MonthConfig(
                year_config_id=year_config.id,
                month=month,
                intensity=IntensityLevel.NORMAL,
            )
            db.session.add(mc)

        # Add all three plans
        for plan_type in [PlanType.FIRM, PlanType.REALISTIC, PlanType.OPTIMISTIC]:
            target_date = (
                datetime.date(2025, 11, 27)
                if plan_type == PlanType.OPTIMISTIC
                else datetime.date(2025, 12, 31)
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


# -----------------------------------------------------------------------------
# Year Setup Tests
# -----------------------------------------------------------------------------


class TestYearSetup:
    """Tests for year setup routes."""

    def test_get_setup_returns_form(self, client, app):
        """GET /setup/ returns the setup form."""
        response = client.get("/setup/")

        assert response.status_code == 200
        assert b"year" in response.data.lower() or b"Year" in response.data

    def test_post_year_creates_year_config(self, client, app):
        """POST /setup/year creates a new YearConfig."""
        response = client.post(
            "/setup/year",
            data={"year": "2025", "annual_target": "1800"},
            follow_redirects=False,
        )

        # Should redirect to next step
        assert response.status_code == 302

        with app.app_context():
            config = YearConfig.query.filter_by(year=2025).first()
            assert config is not None
            assert config.annual_target == 1800

    def test_post_year_validates_year_range(self, client, app):
        """POST /setup/year validates that year is within ±1 of current."""
        # Try a year too far in the past
        response = client.post(
            "/setup/year",
            data={"year": "2020", "annual_target": "1800"},
            follow_redirects=True,
        )

        # Should show error or stay on form
        with app.app_context():
            config = YearConfig.query.filter_by(year=2020).first()
            assert config is None  # Should not create invalid year

    def test_post_year_validates_target_range(self, client, app):
        """POST /setup/year validates annual target is 1000-3000."""
        # Try a target below minimum
        response = client.post(
            "/setup/year",
            data={"year": "2025", "annual_target": "500"},
            follow_redirects=True,
        )

        with app.app_context():
            config = YearConfig.query.filter_by(year=2025).first()
            # Either not created or created with clamped value
            if config:
                assert config.annual_target >= 1000


# -----------------------------------------------------------------------------
# Holiday Setup Tests
# -----------------------------------------------------------------------------


class TestHolidaySetup:
    """Tests for holiday setup routes."""

    def test_get_holidays_shows_form(self, client, year_config):
        """GET /setup/holidays shows the holiday form."""
        response = client.get("/setup/holidays")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8").lower()
        assert "holiday" in response_text

    def test_post_holidays_adds_holiday(self, client, app, year_config):
        """POST /setup/holidays/add adds a new holiday."""
        response = client.post(
            "/setup/holidays/add",
            data={
                "name": "New Year",
                "date": "2025-01-01",
            },
        )

        # Should return success (200 or 201 or partial HTML)
        assert response.status_code in [200, 201]

        with app.app_context():
            holiday = Holiday.query.filter_by(name="New Year").first()
            assert holiday is not None
            assert holiday.date == datetime.date(2025, 1, 1)

    def test_post_holidays_prevents_duplicates(self, client, app, year_config):
        """POST /setup/holidays/add prevents duplicate dates."""
        # Add first holiday
        client.post(
            "/setup/holidays/add",
            data={"name": "Holiday 1", "date": "2025-07-04"},
        )

        # Try to add duplicate
        response = client.post(
            "/setup/holidays/add",
            data={"name": "Holiday 2", "date": "2025-07-04"},
        )

        with app.app_context():
            holidays = Holiday.query.filter_by(
                date=datetime.date(2025, 7, 4)
            ).all()
            # Should only have one holiday for this date
            assert len(holidays) == 1

    def test_post_holidays_validates_date_in_year(self, client, app, year_config):
        """POST /setup/holidays/add validates date is in configured year."""
        response = client.post(
            "/setup/holidays/add",
            data={"name": "Wrong Year", "date": "2024-01-01"},
        )

        with app.app_context():
            holiday = Holiday.query.filter_by(name="Wrong Year").first()
            assert holiday is None  # Should not create holiday outside year

    def test_delete_holidays_removes_holiday(self, client, app, year_config):
        """DELETE /setup/holidays/<id> removes a holiday."""
        # First add a holiday
        with app.app_context():
            holiday = Holiday(
                year_config_id=year_config.id,
                date=datetime.date(2025, 12, 25),
                name="Christmas",
            )
            db.session.add(holiday)
            db.session.commit()
            holiday_id = holiday.id

        # Delete it
        response = client.delete(f"/setup/holidays/{holiday_id}")

        with app.app_context():
            deleted = db.session.get(Holiday, holiday_id)
            assert deleted is None


# -----------------------------------------------------------------------------
# Vacation Setup Tests
# -----------------------------------------------------------------------------


class TestVacationSetup:
    """Tests for vacation setup routes."""

    def test_get_vacation_shows_form(self, client, year_config):
        """GET /setup/vacation shows the vacation form."""
        response = client.get("/setup/vacation")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8").lower()
        assert "vacation" in response_text

    def test_post_vacation_adds_day(self, client, app, year_config):
        """POST /setup/vacation/add adds a vacation day."""
        response = client.post(
            "/setup/vacation/add",
            data={"date": "2025-08-15"},
        )

        assert response.status_code in [200, 201]

        with app.app_context():
            vacation = VacationDay.query.filter_by(
                date=datetime.date(2025, 8, 15)
            ).first()
            assert vacation is not None


# -----------------------------------------------------------------------------
# Plans Setup Tests
# -----------------------------------------------------------------------------


class TestPlansSetup:
    """Tests for plan configuration routes."""

    def test_get_plans_shows_configuration(self, client, year_config):
        """GET /setup/plans shows plan configuration."""
        response = client.get("/setup/plans")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8")
        # Should show all three plan types
        assert "Firm" in response_text or "firm" in response_text.lower()

    def test_post_plans_saves_configs(self, client, app, year_config):
        """POST /setup/plans saves plan configurations."""
        response = client.post(
            "/setup/plans",
            data={
                "optimistic_target_date": "2025-11-20",
                "optimistic_maintenance": "3.0",
            },
            follow_redirects=False,
        )

        # Should redirect to complete page
        assert response.status_code == 302

        with app.app_context():
            optimistic = PlanConfig.query.filter_by(
                year_config_id=year_config.id,
                plan_type=PlanType.OPTIMISTIC,
            ).first()
            # Check if target date was updated
            assert optimistic is not None


# -----------------------------------------------------------------------------
# Complete Page Tests
# -----------------------------------------------------------------------------


class TestCompletePage:
    """Tests for setup complete page."""

    def test_get_complete_shows_summary(self, client, year_config):
        """GET /setup/complete shows configuration summary."""
        response = client.get("/setup/complete")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8")
        assert "1800" in response_text or "hours" in response_text.lower()


# -----------------------------------------------------------------------------
# Mid-Year Setup Tests
# -----------------------------------------------------------------------------


class TestMidYearSetup:
    """Tests for mid-year historical hours entry."""

    def test_get_midyear_shows_form(self, client, year_config):
        """GET /setup/midyear shows historical entry form."""
        response = client.get("/setup/midyear")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8").lower()
        assert "historical" in response_text or "hours" in response_text

    def test_post_midyear_saves_historical(self, client, app, year_config):
        """POST /setup/midyear saves historical hours."""
        response = client.post(
            "/setup/midyear",
            data={
                "start_date": "2025-07-01",
                "entry_mode": "lump",
                "hours_pre_start": "600",
            },
            follow_redirects=False,
        )

        # Should redirect to next step
        assert response.status_code == 302

        with app.app_context():
            config = db.session.get(YearConfig, year_config.id)
            assert config.start_date == datetime.date(2025, 7, 1)
            assert config.hours_pre_start == 600.0
