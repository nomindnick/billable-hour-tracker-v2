"""
Tests for mid-year start functionality.

These tests verify that users who start using the app mid-year can
enter historical hours and have plans calculate correctly.
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
from app.services.calculator import (
    get_historical_hours,
    get_hours_billed_to_date,
    get_expected_hours_to_date,
    calculate_plan_status,
)
from app.services.planner import calculate_monthly_targets_for_plan


# -----------------------------------------------------------------------------
# Tests: get_historical_hours
# -----------------------------------------------------------------------------

class TestGetHistoricalHours:
    """Tests for the get_historical_hours helper function."""

    def test_lump_sum_only(self, app):
        """Lump sum hours should be returned."""
        with app.app_context():
            year_config = YearConfig(
                year=2025,
                annual_target=1800,
                start_date=datetime.date(2025, 7, 1),
                hours_pre_start=600.0
            )
            db.session.add(year_config)
            db.session.commit()
            db.session.refresh(year_config)

            result = get_historical_hours(year_config)
            assert result == 600.0

    def test_monthly_breakdown_only(self, app):
        """Monthly breakdown hours should sum correctly."""
        with app.app_context():
            year_config = YearConfig(
                year=2025,
                annual_target=1800,
                start_date=datetime.date(2025, 9, 1),
                hours_pre_start=0.0
            )
            db.session.add(year_config)
            db.session.flush()

            # Add historical months (Jan-Aug): 100+110+120+130+140+150+160+170 = 1080
            monthly_hours = [100, 110, 120, 130, 140, 150, 160, 170]
            for month, hours in enumerate(monthly_hours, start=1):
                hist = HistoricalMonth(
                    year_config_id=year_config.id,
                    month=month,
                    hours_billed=hours
                )
                db.session.add(hist)

            db.session.commit()
            db.session.refresh(year_config)

            result = get_historical_hours(year_config)
            assert result == 1080.0

    def test_combined_lump_and_monthly(self, app):
        """Both lump sum and monthly should combine."""
        with app.app_context():
            year_config = YearConfig(
                year=2025,
                annual_target=1800,
                start_date=datetime.date(2025, 6, 1),
                hours_pre_start=200.0
            )
            db.session.add(year_config)
            db.session.flush()

            # Add some monthly hours (5 months * 50 = 250)
            for month in range(1, 6):
                hist = HistoricalMonth(
                    year_config_id=year_config.id,
                    month=month,
                    hours_billed=50.0
                )
                db.session.add(hist)

            db.session.commit()
            db.session.refresh(year_config)

            result = get_historical_hours(year_config)
            # 200 lump + (5 months * 50) = 450
            assert result == 450.0

    def test_no_historical_hours(self, app):
        """Year config with no historical data should return 0."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.commit()
            db.session.refresh(year_config)

            result = get_historical_hours(year_config)
            assert result == 0.0


# -----------------------------------------------------------------------------
# Tests: get_hours_billed_to_date (with historical)
# -----------------------------------------------------------------------------

class TestGetHoursBilledToDateWithHistorical:
    """Tests that get_hours_billed_to_date includes historical hours."""

    def test_includes_historical_hours(self, app):
        """Historical hours should be included in total."""
        with app.app_context():
            year_config = YearConfig(
                year=2025,
                annual_target=1800,
                start_date=datetime.date(2025, 7, 1),
                hours_pre_start=600.0
            )
            db.session.add(year_config)
            db.session.flush()

            # Add some daily entries after start date
            for day in range(1, 11):
                entry = DailyEntry(
                    year_config_id=year_config.id,
                    date=datetime.date(2025, 7, day),
                    hours_billed=8.0
                )
                db.session.add(entry)

            db.session.commit()
            db.session.refresh(year_config)

            result = get_hours_billed_to_date(
                year_config,
                datetime.date(2025, 7, 15)
            )
            # 600 historical + (10 days * 8 hours) = 680
            assert result == 680.0

    def test_before_start_date_no_historical(self, app):
        """Querying before start date should not include historical."""
        with app.app_context():
            year_config = YearConfig(
                year=2025,
                annual_target=1800,
                start_date=datetime.date(2025, 7, 1),
                hours_pre_start=600.0
            )
            db.session.add(year_config)
            db.session.commit()
            db.session.refresh(year_config)

            result = get_hours_billed_to_date(
                year_config,
                datetime.date(2025, 6, 30)  # Day before start
            )
            # No entries exist before start date
            assert result == 0.0


# -----------------------------------------------------------------------------
# Tests: get_expected_hours_to_date (with start_date)
# -----------------------------------------------------------------------------

class TestGetExpectedHoursToDateWithStartDate:
    """Tests that expected hours respect start_date."""

    def test_before_start_date_returns_zero(self, app):
        """Expected hours before start date should be 0."""
        with app.app_context():
            year_config = YearConfig(
                year=2025,
                annual_target=1800,
                start_date=datetime.date(2025, 7, 1),
                hours_pre_start=600.0
            )
            db.session.add(year_config)
            db.session.flush()

            # Add month configs
            for month in range(1, 13):
                mc = MonthConfig(
                    year_config_id=year_config.id,
                    month=month,
                    intensity=IntensityLevel.NORMAL
                )
                db.session.add(mc)

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            result = get_expected_hours_to_date(
                year_config,
                plan,
                datetime.date(2025, 6, 15)
            )
            assert result == 0.0

    def test_after_start_date_calculates_from_start(self, app):
        """Expected hours after start date should only count from start."""
        with app.app_context():
            year_config = YearConfig(
                year=2025,
                annual_target=1800,
                start_date=datetime.date(2025, 7, 1),
                hours_pre_start=600.0
            )
            db.session.add(year_config)
            db.session.flush()

            # Add month configs
            for month in range(1, 13):
                mc = MonthConfig(
                    year_config_id=year_config.id,
                    month=month,
                    intensity=IntensityLevel.NORMAL
                )
                db.session.add(mc)

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            result = get_expected_hours_to_date(
                year_config,
                plan,
                datetime.date(2025, 12, 31)
            )
            # Should be based on remaining hours (1800 - 600 = 1200)
            # distributed across Jul-Dec
            assert result > 0
            # Since all 6 months are complete, should equal remaining target
            assert abs(result - 1200) < 10  # Allow some rounding


# -----------------------------------------------------------------------------
# Tests: calculate_monthly_targets_for_plan (with mid-year start)
# -----------------------------------------------------------------------------

class TestMonthlyTargetsWithMidYearStart:
    """Tests for monthly target calculation with mid-year starts."""

    def test_months_before_start_have_zero_target(self, app):
        """Months before start date should have 0 target."""
        with app.app_context():
            year_config = YearConfig(
                year=2025,
                annual_target=1800,
                start_date=datetime.date(2025, 7, 1),
                hours_pre_start=600.0
            )
            db.session.add(year_config)
            db.session.flush()

            # Add month configs
            for month in range(1, 13):
                mc = MonthConfig(
                    year_config_id=year_config.id,
                    month=month,
                    intensity=IntensityLevel.NORMAL
                )
                db.session.add(mc)

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            targets = calculate_monthly_targets_for_plan(year_config, plan)

            # Jan-Jun should be 0
            for month in range(1, 7):
                assert targets[month] == 0.0

            # Jul-Dec should be > 0
            for month in range(7, 13):
                assert targets[month] > 0

    def test_remaining_hours_distributed_correctly(self, app):
        """Remaining hours should sum to annual_target - historical."""
        with app.app_context():
            year_config = YearConfig(
                year=2025,
                annual_target=1800,
                start_date=datetime.date(2025, 7, 1),
                hours_pre_start=600.0
            )
            db.session.add(year_config)
            db.session.flush()

            # Add month configs
            for month in range(1, 13):
                mc = MonthConfig(
                    year_config_id=year_config.id,
                    month=month,
                    intensity=IntensityLevel.NORMAL
                )
                db.session.add(mc)

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            targets = calculate_monthly_targets_for_plan(year_config, plan)
            total = sum(targets.values())

            # Should equal remaining: 1800 - 600 = 1200
            assert abs(total - 1200) < 0.01

    def test_firm_plan_midyear_gets_150_per_active_month(self, app):
        """Firm plan should have 150/month for months from start date."""
        with app.app_context():
            year_config = YearConfig(
                year=2025,
                annual_target=1800,
                start_date=datetime.date(2025, 7, 1),
                hours_pre_start=600.0
            )
            db.session.add(year_config)
            db.session.flush()

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.FIRM,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            targets = calculate_monthly_targets_for_plan(year_config, plan)

            # Jan-Jun should be 0 (before start)
            for month in range(1, 7):
                assert targets[month] == 0.0

            # Jul-Dec should be 150
            for month in range(7, 13):
                assert targets[month] == 150.0


# -----------------------------------------------------------------------------
# Tests: calculate_plan_status (with mid-year start)
# -----------------------------------------------------------------------------

class TestPlanStatusWithMidYearStart:
    """Tests for plan status calculation with mid-year starts."""

    def test_status_includes_historical_in_actual(self, app):
        """Plan status should include historical hours in actual."""
        with app.app_context():
            year_config = YearConfig(
                year=2025,
                annual_target=1800,
                start_date=datetime.date(2025, 7, 1),
                hours_pre_start=600.0
            )
            db.session.add(year_config)
            db.session.flush()

            # Add month configs
            for month in range(1, 13):
                mc = MonthConfig(
                    year_config_id=year_config.id,
                    month=month,
                    intensity=IntensityLevel.NORMAL
                )
                db.session.add(mc)

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)

            # Add some hours in July
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 7, 15),
                hours_billed=100.0
            )
            db.session.add(entry)

            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            status = calculate_plan_status(
                year_config,
                plan,
                datetime.date(2025, 7, 15)
            )

            # Actual should include 600 historical + 100 daily
            assert status.actual_hours_to_date == 700.0

    def test_on_track_with_historical_catch_up(self, app):
        """User who caught up with historical should be on track."""
        with app.app_context():
            year_config = YearConfig(
                year=2025,
                annual_target=1800,
                start_date=datetime.date(2025, 7, 1),
                hours_pre_start=600.0
            )
            db.session.add(year_config)
            db.session.flush()

            # Add month configs
            for month in range(1, 13):
                mc = MonthConfig(
                    year_config_id=year_config.id,
                    month=month,
                    intensity=IntensityLevel.NORMAL
                )
                db.session.add(mc)

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            # 600 historical hours should put us ahead of expected
            # since expected starts from July 1
            status = calculate_plan_status(
                year_config,
                plan,
                datetime.date(2025, 7, 1)
            )

            # On start date, expected is ~0 but we have 600 historical
            assert status.hours_ahead_or_behind >= 0
