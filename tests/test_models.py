"""
Tests for database models.

This module verifies:
- Model creation with correct defaults
- Unique constraints at the database level
- Cascade delete behavior
- Enum values match specification
"""

import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import (
    CatchUpSprint,
    DailyEntry,
    HistoricalMonth,
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
# Model Creation Tests
# -----------------------------------------------------------------------------


class TestYearConfigCreation:
    """Tests for YearConfig model creation."""

    def test_year_config_creation_with_defaults(self, app):
        """YearConfig should have default annual_target of 1800."""
        with app.app_context():
            config = YearConfig(year=2025)
            db.session.add(config)
            db.session.commit()

            assert config.id is not None
            assert config.year == 2025
            assert config.annual_target == 1800  # default
            assert config.start_date is None
            assert config.hours_pre_start is None
            assert config.created_at is not None
            assert config.updated_at is not None

    def test_year_config_creation_with_custom_target(self, app):
        """YearConfig can be created with a custom annual_target."""
        with app.app_context():
            config = YearConfig(year=2025, annual_target=2000)
            db.session.add(config)
            db.session.commit()

            assert config.annual_target == 2000


class TestHolidayCreation:
    """Tests for Holiday model creation."""

    def test_holiday_creation_with_year_config(self, app):
        """Holiday should be created with year_config relationship."""
        with app.app_context():
            config = YearConfig(year=2025)
            db.session.add(config)
            db.session.commit()

            holiday = Holiday(
                year_config_id=config.id,
                date=datetime.date(2025, 12, 25),
                name="Christmas"
            )
            db.session.add(holiday)
            db.session.commit()

            assert holiday.id is not None
            assert holiday.year_config_id == config.id
            assert holiday.date == datetime.date(2025, 12, 25)
            assert holiday.name == "Christmas"
            assert holiday.year_config == config
            assert holiday in config.holidays


class TestVacationDayCreation:
    """Tests for VacationDay model creation."""

    def test_vacation_day_creation_with_year_config(self, app):
        """VacationDay should be created with year_config relationship."""
        with app.app_context():
            config = YearConfig(year=2025)
            db.session.add(config)
            db.session.commit()

            vacation = VacationDay(
                year_config_id=config.id,
                date=datetime.date(2025, 7, 4),
                note="Beach trip"
            )
            db.session.add(vacation)
            db.session.commit()

            assert vacation.id is not None
            assert vacation.year_config_id == config.id
            assert vacation.date == datetime.date(2025, 7, 4)
            assert vacation.note == "Beach trip"
            assert vacation.year_config == config
            assert vacation in config.vacation_days


class TestMonthConfigCreation:
    """Tests for MonthConfig model creation."""

    def test_month_config_creation_with_intensity(self, app):
        """MonthConfig should be created with IntensityLevel enum."""
        with app.app_context():
            config = YearConfig(year=2025)
            db.session.add(config)
            db.session.commit()

            month = MonthConfig(
                year_config_id=config.id,
                month=12,
                intensity=IntensityLevel.LIGHT
            )
            db.session.add(month)
            db.session.commit()

            assert month.id is not None
            assert month.month == 12
            assert month.intensity == IntensityLevel.LIGHT
            assert month.year_config == config

    def test_month_config_default_intensity(self, app):
        """MonthConfig should default to NORMAL intensity."""
        with app.app_context():
            config = YearConfig(year=2025)
            db.session.add(config)
            db.session.commit()

            month = MonthConfig(year_config_id=config.id, month=1)
            db.session.add(month)
            db.session.commit()

            assert month.intensity == IntensityLevel.NORMAL


class TestPlanConfigCreation:
    """Tests for PlanConfig model creation."""

    def test_plan_config_creation_with_plan_type(self, app):
        """PlanConfig should be created with PlanType enum."""
        with app.app_context():
            config = YearConfig(year=2025)
            db.session.add(config)
            db.session.commit()

            plan = PlanConfig(
                year_config_id=config.id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()

            assert plan.id is not None
            assert plan.plan_type == PlanType.REALISTIC
            assert plan.target_date == datetime.date(2025, 12, 31)
            assert plan.year_config == config


class TestDailyEntryCreation:
    """Tests for DailyEntry model creation."""

    def test_daily_entry_creation(self, app):
        """DailyEntry should be created with date and hours."""
        with app.app_context():
            config = YearConfig(year=2025)
            db.session.add(config)
            db.session.commit()

            entry = DailyEntry(
                year_config_id=config.id,
                date=datetime.date(2025, 3, 15),
                hours_billed=7.5
            )
            db.session.add(entry)
            db.session.commit()

            assert entry.id is not None
            assert entry.date == datetime.date(2025, 3, 15)
            assert entry.hours_billed == 7.5
            assert entry.created_at is not None
            assert entry.updated_at is not None
            assert entry.year_config == config


class TestCatchUpSprintCreation:
    """Tests for CatchUpSprint model creation."""

    def test_catch_up_sprint_creation_with_status(self, app):
        """CatchUpSprint should be created with SprintStatus enum."""
        with app.app_context():
            config = YearConfig(year=2025)
            db.session.add(config)
            db.session.commit()

            sprint = CatchUpSprint(
                year_config_id=config.id,
                target_plan=PlanType.REALISTIC,
                start_date=datetime.date(2025, 4, 1),
                end_date=datetime.date(2025, 4, 14),
                target_hours=80.0
            )
            db.session.add(sprint)
            db.session.commit()

            assert sprint.id is not None
            assert sprint.status == SprintStatus.ACTIVE  # default
            assert sprint.target_plan == PlanType.REALISTIC
            assert sprint.target_hours == 80.0
            assert sprint.year_config == config


class TestHistoricalMonthCreation:
    """Tests for HistoricalMonth model creation."""

    def test_historical_month_creation(self, app):
        """HistoricalMonth should be created for mid-year starts."""
        with app.app_context():
            config = YearConfig(year=2025)
            db.session.add(config)
            db.session.commit()

            historical = HistoricalMonth(
                year_config_id=config.id,
                month=1,
                hours_billed=150.0,
                notes="From firm system"
            )
            db.session.add(historical)
            db.session.commit()

            assert historical.id is not None
            assert historical.month == 1
            assert historical.hours_billed == 150.0
            assert historical.notes == "From firm system"
            assert historical.year_config == config


# -----------------------------------------------------------------------------
# Unique Constraint Tests
# -----------------------------------------------------------------------------


class TestUniqueConstraints:
    """Tests for unique constraints at the database level."""

    def test_year_config_unique_year(self, app):
        """Cannot create two YearConfigs for the same year."""
        with app.app_context():
            config1 = YearConfig(year=2025)
            db.session.add(config1)
            db.session.commit()

            config2 = YearConfig(year=2025)
            db.session.add(config2)

            with pytest.raises(IntegrityError):
                db.session.commit()

    def test_holiday_unique_year_date(self, app):
        """Cannot create duplicate holiday dates for same year config."""
        with app.app_context():
            config = YearConfig(year=2025)
            db.session.add(config)
            db.session.commit()

            holiday1 = Holiday(
                year_config_id=config.id,
                date=datetime.date(2025, 12, 25)
            )
            db.session.add(holiday1)
            db.session.commit()

            holiday2 = Holiday(
                year_config_id=config.id,
                date=datetime.date(2025, 12, 25)
            )
            db.session.add(holiday2)

            with pytest.raises(IntegrityError):
                db.session.commit()

    def test_vacation_day_unique_year_date(self, app):
        """Cannot create duplicate vacation dates for same year config."""
        with app.app_context():
            config = YearConfig(year=2025)
            db.session.add(config)
            db.session.commit()

            vacation1 = VacationDay(
                year_config_id=config.id,
                date=datetime.date(2025, 7, 4)
            )
            db.session.add(vacation1)
            db.session.commit()

            vacation2 = VacationDay(
                year_config_id=config.id,
                date=datetime.date(2025, 7, 4)
            )
            db.session.add(vacation2)

            with pytest.raises(IntegrityError):
                db.session.commit()

    def test_month_config_unique_year_month(self, app):
        """Cannot create duplicate month config for same year."""
        with app.app_context():
            config = YearConfig(year=2025)
            db.session.add(config)
            db.session.commit()

            month1 = MonthConfig(year_config_id=config.id, month=12)
            db.session.add(month1)
            db.session.commit()

            month2 = MonthConfig(year_config_id=config.id, month=12)
            db.session.add(month2)

            with pytest.raises(IntegrityError):
                db.session.commit()

    def test_plan_config_unique_year_type(self, app):
        """Cannot create duplicate plan type for same year."""
        with app.app_context():
            config = YearConfig(year=2025)
            db.session.add(config)
            db.session.commit()

            plan1 = PlanConfig(
                year_config_id=config.id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan1)
            db.session.commit()

            plan2 = PlanConfig(
                year_config_id=config.id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan2)

            with pytest.raises(IntegrityError):
                db.session.commit()

    def test_daily_entry_unique_year_date(self, app):
        """Cannot create duplicate entries for same date."""
        with app.app_context():
            config = YearConfig(year=2025)
            db.session.add(config)
            db.session.commit()

            entry1 = DailyEntry(
                year_config_id=config.id,
                date=datetime.date(2025, 3, 15),
                hours_billed=7.5
            )
            db.session.add(entry1)
            db.session.commit()

            entry2 = DailyEntry(
                year_config_id=config.id,
                date=datetime.date(2025, 3, 15),
                hours_billed=8.0
            )
            db.session.add(entry2)

            with pytest.raises(IntegrityError):
                db.session.commit()

    def test_historical_month_unique_year_month(self, app):
        """Cannot create duplicate historical months for same year."""
        with app.app_context():
            config = YearConfig(year=2025)
            db.session.add(config)
            db.session.commit()

            hist1 = HistoricalMonth(
                year_config_id=config.id,
                month=1,
                hours_billed=150.0
            )
            db.session.add(hist1)
            db.session.commit()

            hist2 = HistoricalMonth(
                year_config_id=config.id,
                month=1,
                hours_billed=160.0
            )
            db.session.add(hist2)

            with pytest.raises(IntegrityError):
                db.session.commit()


# -----------------------------------------------------------------------------
# Cascade Delete Test
# -----------------------------------------------------------------------------


class TestCascadeDelete:
    """Tests for cascade delete behavior."""

    def test_year_config_cascade_delete(self, app):
        """Deleting YearConfig should delete all related records."""
        with app.app_context():
            # Create YearConfig with all child types
            config = YearConfig(year=2025)
            db.session.add(config)
            db.session.commit()
            config_id = config.id

            # Add child records
            holiday = Holiday(
                year_config_id=config_id,
                date=datetime.date(2025, 12, 25)
            )
            vacation = VacationDay(
                year_config_id=config_id,
                date=datetime.date(2025, 7, 4)
            )
            month = MonthConfig(year_config_id=config_id, month=1)
            plan = PlanConfig(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            entry = DailyEntry(
                year_config_id=config_id,
                date=datetime.date(2025, 3, 15),
                hours_billed=7.5
            )
            sprint = CatchUpSprint(
                year_config_id=config_id,
                target_plan=PlanType.REALISTIC,
                start_date=datetime.date(2025, 4, 1),
                end_date=datetime.date(2025, 4, 14),
                target_hours=80.0
            )
            historical = HistoricalMonth(
                year_config_id=config_id,
                month=1,
                hours_billed=150.0
            )

            db.session.add_all([
                holiday, vacation, month, plan, entry, sprint, historical
            ])
            db.session.commit()

            # Verify records exist
            assert Holiday.query.count() == 1
            assert VacationDay.query.count() == 1
            assert MonthConfig.query.count() == 1
            assert PlanConfig.query.count() == 1
            assert DailyEntry.query.count() == 1
            assert CatchUpSprint.query.count() == 1
            assert HistoricalMonth.query.count() == 1

            # Delete YearConfig
            db.session.delete(config)
            db.session.commit()

            # Verify all child records are deleted
            assert YearConfig.query.count() == 0
            assert Holiday.query.count() == 0
            assert VacationDay.query.count() == 0
            assert MonthConfig.query.count() == 0
            assert PlanConfig.query.count() == 0
            assert DailyEntry.query.count() == 0
            assert CatchUpSprint.query.count() == 0
            assert HistoricalMonth.query.count() == 0


# -----------------------------------------------------------------------------
# Enum Value Tests
# -----------------------------------------------------------------------------


class TestEnumValues:
    """Tests to verify enum values match specification."""

    def test_intensity_level_enum_values(self):
        """IntensityLevel should have NORMAL, LIGHT, VERY_LIGHT."""
        assert IntensityLevel.NORMAL.value == "normal"
        assert IntensityLevel.LIGHT.value == "light"
        assert IntensityLevel.VERY_LIGHT.value == "very_light"

        # Verify no unexpected values
        values = [e.value for e in IntensityLevel]
        assert len(values) == 3
        assert set(values) == {"normal", "light", "very_light"}

    def test_plan_type_enum_values(self):
        """PlanType should have FIRM, OPTIMISTIC, REALISTIC."""
        assert PlanType.FIRM.value == "firm"
        assert PlanType.OPTIMISTIC.value == "optimistic"
        assert PlanType.REALISTIC.value == "realistic"

        # Verify no unexpected values
        values = [e.value for e in PlanType]
        assert len(values) == 3
        assert set(values) == {"firm", "optimistic", "realistic"}

    def test_sprint_status_enum_values(self):
        """SprintStatus should have ACTIVE, COMPLETED, REVISED, DISMISSED."""
        assert SprintStatus.ACTIVE.value == "active"
        assert SprintStatus.COMPLETED.value == "completed"
        assert SprintStatus.REVISED.value == "revised"
        assert SprintStatus.DISMISSED.value == "dismissed"

        # Verify no unexpected values
        values = [e.value for e in SprintStatus]
        assert len(values) == 4
        assert set(values) == {"active", "completed", "revised", "dismissed"}
