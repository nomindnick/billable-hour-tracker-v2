"""
Unit tests for the planning service.

Tests the monthly target distribution algorithm in app/services/planner.py.
"""

import datetime
import pytest

from app import db
from app.models import (
    Holiday,
    IntensityLevel,
    MonthConfig,
    PlanConfig,
    PlanType,
    VacationDay,
    YearConfig,
)
from app.services.planner import (
    INTENSITY_WEIGHTS,
    MAX_DAILY_HOURS,
    MonthlyTarget,
    PlanWarning,
    calculate_monthly_targets,
    calculate_monthly_targets_for_plan,
    extract_holidays_and_vacations,
    get_intensity_weight,
    get_month_intensity,
    get_monthly_breakdown,
    validate_plan_feasibility,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def basic_year_config(app):
    """Create a basic YearConfig for 2025 with 1800 hour target."""
    with app.app_context():
        year_config = YearConfig(year=2025, annual_target=1800)
        db.session.add(year_config)
        db.session.commit()
        # Refresh to ensure we have the ID
        db.session.refresh(year_config)
        yield year_config


@pytest.fixture
def year_config_with_holidays(app):
    """Create a YearConfig with common US holidays."""
    with app.app_context():
        year_config = YearConfig(year=2025, annual_target=1800)
        db.session.add(year_config)
        db.session.flush()

        # Add some holidays
        holidays = [
            Holiday(year_config_id=year_config.id, date=datetime.date(2025, 1, 1), name="New Year's Day"),
            Holiday(year_config_id=year_config.id, date=datetime.date(2025, 7, 4), name="Independence Day"),
            Holiday(year_config_id=year_config.id, date=datetime.date(2025, 11, 27), name="Thanksgiving"),
            Holiday(year_config_id=year_config.id, date=datetime.date(2025, 12, 25), name="Christmas"),
        ]
        db.session.add_all(holidays)
        db.session.commit()
        db.session.refresh(year_config)
        yield year_config


@pytest.fixture
def year_config_with_light_december(app):
    """Create a YearConfig with December set to very_light intensity."""
    with app.app_context():
        year_config = YearConfig(year=2025, annual_target=1800)
        db.session.add(year_config)
        db.session.flush()

        # Set December to very light
        month_config = MonthConfig(
            year_config_id=year_config.id,
            month=12,
            intensity=IntensityLevel.VERY_LIGHT
        )
        db.session.add(month_config)
        db.session.commit()
        db.session.refresh(year_config)
        yield year_config


# -----------------------------------------------------------------------------
# Test: Intensity Weights
# -----------------------------------------------------------------------------

class TestIntensityWeights:
    """Tests for intensity weight constants and helper function."""

    def test_normal_weight_is_1_0(self):
        """Normal intensity should have weight 1.0."""
        assert INTENSITY_WEIGHTS[IntensityLevel.NORMAL] == 1.0
        assert get_intensity_weight(IntensityLevel.NORMAL) == 1.0

    def test_light_weight_is_0_75(self):
        """Light intensity should have weight 0.75."""
        assert INTENSITY_WEIGHTS[IntensityLevel.LIGHT] == 0.75
        assert get_intensity_weight(IntensityLevel.LIGHT) == 0.75

    def test_very_light_weight_is_0_5(self):
        """Very light intensity should have weight 0.5."""
        assert INTENSITY_WEIGHTS[IntensityLevel.VERY_LIGHT] == 0.5
        assert get_intensity_weight(IntensityLevel.VERY_LIGHT) == 0.5


# -----------------------------------------------------------------------------
# Test: Helper Functions
# -----------------------------------------------------------------------------

class TestGetMonthIntensity:
    """Tests for the get_month_intensity helper function."""

    def test_returns_configured_intensity(self, app):
        """Should return the configured intensity for a month."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            month_config = MonthConfig(
                year_config_id=year_config.id,
                month=12,
                intensity=IntensityLevel.LIGHT
            )
            db.session.add(month_config)
            db.session.commit()
            db.session.refresh(year_config)

            intensity = get_month_intensity(year_config, 12)
            assert intensity == IntensityLevel.LIGHT

    def test_defaults_to_normal(self, basic_year_config, app):
        """Should return NORMAL when no MonthConfig exists."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            intensity = get_month_intensity(year_config, 6)
            assert intensity == IntensityLevel.NORMAL


class TestExtractHolidaysAndVacations:
    """Tests for the extract_holidays_and_vacations helper."""

    def test_extracts_holidays(self, year_config_with_holidays, app):
        """Should extract holiday dates as a set."""
        with app.app_context():
            year_config = db.session.get(YearConfig, year_config_with_holidays.id)
            holidays, _ = extract_holidays_and_vacations(year_config)

            assert datetime.date(2025, 1, 1) in holidays
            assert datetime.date(2025, 7, 4) in holidays
            assert datetime.date(2025, 12, 25) in holidays

    def test_extracts_vacations(self, app):
        """Should extract vacation dates as a set."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            vacation = VacationDay(
                year_config_id=year_config.id,
                date=datetime.date(2025, 8, 15),
                note="Summer break"
            )
            db.session.add(vacation)
            db.session.commit()
            db.session.refresh(year_config)

            _, vacations = extract_holidays_and_vacations(year_config)
            assert datetime.date(2025, 8, 15) in vacations

    def test_empty_sets_for_no_holidays(self, basic_year_config, app):
        """Should return empty sets when no holidays/vacations configured."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            holidays, vacations = extract_holidays_and_vacations(year_config)

            assert holidays == set()
            assert vacations == set()


# -----------------------------------------------------------------------------
# Test: calculate_monthly_targets
# -----------------------------------------------------------------------------

class TestCalculateMonthlyTargets:
    """Tests for the core monthly target calculation."""

    def test_returns_all_12_months(self, basic_year_config, app):
        """Should return targets for all 12 months."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            targets = calculate_monthly_targets(year_config)

            assert len(targets) == 12
            assert all(month in targets for month in range(1, 13))

    def test_annual_target_sums_correctly(self, basic_year_config, app):
        """Monthly targets should sum to annual target."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            targets = calculate_monthly_targets(year_config)

            total = sum(targets.values())
            # Allow for floating point rounding
            assert abs(total - 1800) < 0.01

    def test_proportional_to_workdays(self, basic_year_config, app):
        """Months with more workdays should get more hours."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            targets = calculate_monthly_targets(year_config)

            # January 2025 has 23 workdays, February has 20
            # January should have more hours than February
            assert targets[1] > targets[2]

    def test_light_month_gets_fewer_hours(self, year_config_with_light_december, app):
        """Light intensity month should get fewer hours."""
        with app.app_context():
            year_config = db.session.get(YearConfig, year_config_with_light_december.id)
            targets = calculate_monthly_targets(year_config)

            # December is very_light (0.5 weight)
            # November is normal (1.0 weight)
            # Even if both had same workdays, December should have ~half
            # In practice, ratio should be close to 0.5 after accounting for workdays
            dec_hours = targets[12]
            nov_hours = targets[11]

            # December has 23 workdays, November has 20 in 2025
            # But December's weight is 0.5, so effective = 11.5
            # November's effective = 20 * 1.0 = 20
            # December should have significantly fewer hours
            assert dec_hours < nov_hours

    def test_end_month_limits_calculation(self, basic_year_config, app):
        """end_month parameter should limit which months get hours."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            targets = calculate_monthly_targets(year_config, end_month=6)

            # All 12 months are returned, but months 7-12 have 0 hours
            assert len(targets) == 12
            assert all(targets[month] > 0 for month in range(1, 7))
            assert all(targets[month] == 0 for month in range(7, 13))

    def test_target_hours_overrides_annual(self, basic_year_config, app):
        """target_hours parameter should override annual_target."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            targets = calculate_monthly_targets(year_config, target_hours=1200)

            total = sum(targets.values())
            assert abs(total - 1200) < 0.01

    def test_handles_month_with_many_holidays(self, app):
        """Month with many holidays should get proportionally fewer hours."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            # Add 10 holidays to July (normally 23 workdays)
            for day in range(1, 11):
                # Skip weekends
                date = datetime.date(2025, 7, day)
                if date.weekday() < 5:  # Only add weekdays
                    holiday = Holiday(
                        year_config_id=year_config.id,
                        date=date,
                        name=f"Holiday {day}"
                    )
                    db.session.add(holiday)

            db.session.commit()
            db.session.refresh(year_config)

            targets = calculate_monthly_targets(year_config)

            # July should have significantly fewer hours than August
            # (which has similar base workdays but no holidays)
            assert targets[7] < targets[8]


# -----------------------------------------------------------------------------
# Test: calculate_monthly_targets_for_plan
# -----------------------------------------------------------------------------

class TestCalculateMonthlyTargetsForPlan:
    """Tests for plan-specific target calculations."""

    def test_firm_plan_is_fixed_150_per_month(self, basic_year_config, app):
        """Firm plan should return exactly 150 hours per month."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.FIRM,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(plan)

            targets = calculate_monthly_targets_for_plan(year_config, plan)

            assert all(targets[m] == 150.0 for m in range(1, 13))
            assert sum(targets.values()) == 1800.0

    def test_realistic_plan_uses_full_year(self, basic_year_config, app):
        """Realistic plan should distribute across all 12 months."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(plan)

            targets = calculate_monthly_targets_for_plan(year_config, plan)

            assert len(targets) == 12
            assert abs(sum(targets.values()) - 1800) < 0.01

    def test_optimistic_plan_with_early_target(self, basic_year_config, app):
        """Optimistic plan ending in November should compress hours."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)

            # Target to hit 1800 hours by end of November
            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.OPTIMISTIC,
                target_date=datetime.date(2025, 11, 30)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(plan)

            targets = calculate_monthly_targets_for_plan(year_config, plan)

            # All 12 months returned, but December has 0 hours
            assert len(targets) == 12
            assert all(targets[month] > 0 for month in range(1, 12))
            assert targets[12] == 0
            # Total should still be annual target
            assert abs(sum(targets.values()) - 1800) < 0.01

    def test_optimistic_plan_with_maintenance_hours(self, basic_year_config, app):
        """Optimistic plan with maintenance hours after target date."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)

            # Hit target by October, then do 4 hours/day Nov-Dec
            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.OPTIMISTIC,
                target_date=datetime.date(2025, 10, 31),
                target_daily_hours_after=4.0
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(plan)

            targets = calculate_monthly_targets_for_plan(year_config, plan)

            # Should have all 12 months
            assert len(targets) == 12

            # Nov and Dec should have 4 hours/day targets
            # November 2025 has 20 workdays, December has 23
            # Nov target = 20 * 4 = 80, Dec target = 23 * 4 = 92
            assert abs(targets[11] - 80) < 1  # Allow small rounding
            assert abs(targets[12] - 92) < 1

            # Total should still be 1800
            assert abs(sum(targets.values()) - 1800) < 0.01


# -----------------------------------------------------------------------------
# Test: validate_plan_feasibility
# -----------------------------------------------------------------------------

class TestValidatePlanFeasibility:
    """Tests for plan feasibility validation."""

    def test_valid_plan_returns_no_warnings(self, basic_year_config, app):
        """A standard 1800-hour plan should be feasible."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            targets = calculate_monthly_targets(year_config)

            warnings = validate_plan_feasibility(targets, year_config)

            assert warnings == []

    def test_impossible_plan_returns_warnings(self, basic_year_config, app):
        """An overly ambitious plan should generate warnings."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            year_config.annual_target = 3000  # Way too high
            db.session.commit()

            targets = calculate_monthly_targets(year_config)

            warnings = validate_plan_feasibility(targets, year_config)

            # Should have warnings for multiple months
            assert len(warnings) > 0
            assert all(w.required_daily_hours > MAX_DAILY_HOURS for w in warnings)

    def test_warning_includes_month_details(self, basic_year_config, app):
        """Warnings should include helpful details."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            year_config.annual_target = 3000
            db.session.commit()

            targets = calculate_monthly_targets(year_config)

            warnings = validate_plan_feasibility(targets, year_config)

            # Check first warning has all required fields
            if warnings:
                warning = warnings[0]
                assert warning.month >= 1 and warning.month <= 12
                assert warning.required_daily_hours > 0
                assert warning.workdays_in_month > 0
                assert len(warning.message) > 0
                assert "hours/day" in warning.message

    def test_compressed_optimistic_plan_may_warn(self, basic_year_config, app):
        """Compressing 1800 hours into 6 months should trigger warnings."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)

            # Compress all hours into first 6 months
            targets = calculate_monthly_targets(
                year_config,
                end_month=6,
                target_hours=1800
            )

            warnings = validate_plan_feasibility(targets, year_config)

            # Should have some warnings (roughly 12 hours/day needed)
            assert len(warnings) > 0


# -----------------------------------------------------------------------------
# Test: get_monthly_breakdown
# -----------------------------------------------------------------------------

class TestGetMonthlyBreakdown:
    """Tests for the get_monthly_breakdown convenience function."""

    def test_returns_12_monthly_targets(self, basic_year_config, app):
        """Should return a MonthlyTarget for each month."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(plan)

            breakdown = get_monthly_breakdown(year_config, plan)

            assert len(breakdown) == 12
            assert all(isinstance(m, MonthlyTarget) for m in breakdown)
            assert [m.month for m in breakdown] == list(range(1, 13))

    def test_breakdown_includes_daily_target(self, basic_year_config, app):
        """Each MonthlyTarget should have a calculated daily target."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(plan)

            breakdown = get_monthly_breakdown(year_config, plan)

            for month_target in breakdown:
                if month_target.workdays > 0:
                    expected_daily = month_target.target_hours / month_target.workdays
                    assert abs(month_target.daily_target - expected_daily) < 0.1

    def test_breakdown_includes_intensity(self, year_config_with_light_december, app):
        """MonthlyTarget should reflect configured intensity."""
        with app.app_context():
            year_config = db.session.get(YearConfig, year_config_with_light_december.id)

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(plan)

            breakdown = get_monthly_breakdown(year_config, plan)

            december = breakdown[11]  # December is index 11
            assert december.intensity == IntensityLevel.VERY_LIGHT


# -----------------------------------------------------------------------------
# Test: Integration / Edge Cases
# -----------------------------------------------------------------------------

class TestIntegration:
    """Integration tests for the planning algorithm."""

    def test_full_year_setup_scenario(self, app):
        """Test a realistic full-year configuration."""
        with app.app_context():
            # Create year config
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            # Add holidays
            holidays = [
                Holiday(year_config_id=year_config.id, date=datetime.date(2025, 1, 1)),
                Holiday(year_config_id=year_config.id, date=datetime.date(2025, 7, 4)),
                Holiday(year_config_id=year_config.id, date=datetime.date(2025, 11, 27)),
                Holiday(year_config_id=year_config.id, date=datetime.date(2025, 12, 25)),
            ]
            db.session.add_all(holidays)

            # Add vacation (2 weeks in August)
            for day in range(11, 23):
                date = datetime.date(2025, 8, day)
                if date.weekday() < 5:  # Only weekdays
                    vacation = VacationDay(year_config_id=year_config.id, date=date)
                    db.session.add(vacation)

            # Set November and December to light
            month_configs = [
                MonthConfig(year_config_id=year_config.id, month=11, intensity=IntensityLevel.LIGHT),
                MonthConfig(year_config_id=year_config.id, month=12, intensity=IntensityLevel.VERY_LIGHT),
            ]
            db.session.add_all(month_configs)

            db.session.commit()
            db.session.refresh(year_config)

            # Calculate realistic plan
            targets = calculate_monthly_targets(year_config)

            # Verify total hours
            assert abs(sum(targets.values()) - 1800) < 0.01

            # August should have fewer hours due to vacation
            assert targets[8] < targets[7]  # August < July

            # December should have fewer hours due to very_light intensity
            assert targets[12] < targets[1]  # December < January

            # Validate feasibility
            warnings = validate_plan_feasibility(targets, year_config)
            assert warnings == []  # 1800 hours is achievable

    def test_different_annual_targets(self, app):
        """Test with different annual targets."""
        with app.app_context():
            for target in [1750, 1800, 1950, 2000]:
                year_config = YearConfig(year=2025, annual_target=target)
                db.session.add(year_config)
                db.session.commit()
                db.session.refresh(year_config)

                targets = calculate_monthly_targets(year_config)
                assert abs(sum(targets.values()) - target) < 0.01

                db.session.delete(year_config)
                db.session.commit()

    def test_leap_year_february(self, app):
        """Test that leap year February is handled correctly."""
        with app.app_context():
            # 2024 is a leap year
            year_config = YearConfig(year=2024, annual_target=1800)
            db.session.add(year_config)
            db.session.commit()
            db.session.refresh(year_config)

            targets = calculate_monthly_targets(year_config)

            # February 2024 has 21 workdays (Feb 29 is a Thursday)
            # This should work without errors
            assert targets[2] > 0
            assert abs(sum(targets.values()) - 1800) < 0.01


# -----------------------------------------------------------------------------
# Test: Planner Edge Cases (Sprint 3.8)
# -----------------------------------------------------------------------------

class TestPlannerEdgeCases:
    """Edge case tests for planner algorithm - Sprint 3.8."""

    def test_all_very_light_months_distributes_correctly(self, app):
        """All months VERY_LIGHT should distribute proportionally, sum to target."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            # Set all 12 months to VERY_LIGHT
            for month in range(1, 13):
                month_config = MonthConfig(
                    year_config_id=year_config.id,
                    month=month,
                    intensity=IntensityLevel.VERY_LIGHT
                )
                db.session.add(month_config)

            db.session.commit()
            db.session.refresh(year_config)

            targets = calculate_monthly_targets(year_config)

            # Should still sum to annual target
            assert abs(sum(targets.values()) - 1800) < 0.01
            # All months should have hours (weighted proportionally by workdays)
            assert all(targets[m] > 0 for m in range(1, 13))

    def test_single_month_no_workdays_redistributes(self, app):
        """Month with all holidays should get 0 hours, others compensate."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            # Add holidays for all weekdays in February 2025
            # February 2025 has workdays on: 3,4,5,6,7,10,11,12,13,14,17,18,19,20,21,24,25,26,27,28
            feb_weekdays = [
                3, 4, 5, 6, 7, 10, 11, 12, 13, 14,
                17, 18, 19, 20, 21, 24, 25, 26, 27, 28
            ]
            for day in feb_weekdays:
                holiday = Holiday(
                    year_config_id=year_config.id,
                    date=datetime.date(2025, 2, day),
                    name=f"Feb Holiday {day}"
                )
                db.session.add(holiday)

            db.session.commit()
            db.session.refresh(year_config)

            targets = calculate_monthly_targets(year_config)

            # February should have 0 hours
            assert targets[2] == 0.0
            # Total should still be 1800 (other months absorb the hours)
            assert abs(sum(targets.values()) - 1800) < 0.01
            # Other months should have positive hours
            for month in [1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]:
                assert targets[month] > 0

    def test_year_all_holidays_returns_even_distribution(self, app):
        """If every workday is a holiday, should distribute evenly."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            # Add a holiday for every weekday in the year
            # This is the edge case from planner.py lines 233-240
            for month in range(1, 13):
                for day in range(1, 32):
                    try:
                        date = datetime.date(2025, month, day)
                        if date.weekday() < 5:  # Weekday
                            holiday = Holiday(
                                year_config_id=year_config.id,
                                date=date,
                                name=f"Holiday {month}/{day}"
                            )
                            db.session.add(holiday)
                    except ValueError:
                        # Invalid date (e.g., Feb 30)
                        pass

            db.session.commit()
            db.session.refresh(year_config)

            targets = calculate_monthly_targets(year_config)

            # With 0 workdays, algorithm distributes evenly (1800/12 = 150)
            assert abs(sum(targets.values()) - 1800) < 0.01
            for month in range(1, 13):
                assert abs(targets[month] - 150) < 0.01

    def test_leap_year_vs_non_leap_february(self, app):
        """Leap year Feb (29 days) vs non-leap (28 days) should differ."""
        with app.app_context():
            # 2024 is a leap year
            leap_config = YearConfig(year=2024, annual_target=1800)
            db.session.add(leap_config)
            db.session.commit()
            db.session.refresh(leap_config)

            leap_targets = calculate_monthly_targets(leap_config)

            # Clear for next test
            db.session.delete(leap_config)
            db.session.commit()

            # 2025 is not a leap year
            non_leap_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(non_leap_config)
            db.session.commit()
            db.session.refresh(non_leap_config)

            non_leap_targets = calculate_monthly_targets(non_leap_config)

            # February 2024 (leap) has 21 workdays, February 2025 has 20
            # Leap year February should get more hours
            assert leap_targets[2] > non_leap_targets[2]

    def test_optimistic_december_31_target_date(self, basic_year_config, app):
        """Optimistic plan with Dec 31 target should include all 12 months."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.OPTIMISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(plan)

            targets = calculate_monthly_targets_for_plan(year_config, plan)

            # All 12 months should have hours (no compression)
            assert all(targets[m] > 0 for m in range(1, 13))
            assert abs(sum(targets.values()) - 1800) < 0.01

    def test_explicit_january_1_start_date(self, app):
        """Explicit Jan 1 start should include all 12 months."""
        with app.app_context():
            year_config = YearConfig(
                year=2025,
                annual_target=1800,
                start_date=datetime.date(2025, 1, 1)
            )
            db.session.add(year_config)
            db.session.commit()
            db.session.refresh(year_config)

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(plan)

            targets = calculate_monthly_targets_for_plan(year_config, plan)

            # All 12 months should have hours
            assert all(targets[m] > 0 for m in range(1, 13))
            assert abs(sum(targets.values()) - 1800) < 0.01

    def test_mid_month_start_date_excludes_prior_months(self, app):
        """Start date June 15 should exclude Jan-May."""
        with app.app_context():
            year_config = YearConfig(
                year=2025,
                annual_target=1800,
                start_date=datetime.date(2025, 6, 15)
            )
            db.session.add(year_config)
            db.session.commit()
            db.session.refresh(year_config)

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(plan)

            targets = calculate_monthly_targets_for_plan(year_config, plan)

            # Months 1-5 should have 0 hours
            for month in range(1, 6):
                assert targets[month] == 0.0

            # Months 6-12 should have positive hours
            for month in range(6, 13):
                assert targets[month] > 0

            # Total should still be 1800
            assert abs(sum(targets.values()) - 1800) < 0.01

    def test_annual_target_zero_rejected_by_constraint(self, app):
        """Annual target of 0 should be rejected by database constraint."""
        import pytest
        from sqlalchemy.exc import IntegrityError

        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=0)
            db.session.add(year_config)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()

    def test_annual_target_maximum_3000_feasibility(self, app):
        """Annual target 3000 should trigger infeasibility warnings."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=3000)
            db.session.add(year_config)
            db.session.commit()
            db.session.refresh(year_config)

            targets = calculate_monthly_targets(year_config)
            warnings = validate_plan_feasibility(targets, year_config)

            # Should have warnings (most months will exceed 9.5 hours/day)
            assert len(warnings) > 0
            # All warnings should be for exceeding MAX_DAILY_HOURS
            for warning in warnings:
                assert warning.required_daily_hours > MAX_DAILY_HOURS

    def test_annual_target_minimum_1000_feasible(self, app):
        """Annual target 1000 should be easily feasible."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1000)
            db.session.add(year_config)
            db.session.commit()
            db.session.refresh(year_config)

            targets = calculate_monthly_targets(year_config)
            warnings = validate_plan_feasibility(targets, year_config)

            # Should have no warnings (under ~4 hours/day)
            assert warnings == []
            # Sum should still be correct
            assert abs(sum(targets.values()) - 1000) < 0.01

    def test_at_max_daily_hours_threshold_no_warning(self, app):
        """Exactly at 9.5 hours/day threshold should not trigger warning."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            # Add enough holidays to make January require exactly 9.5 hours/day
            # January 2025 has 23 workdays. At 9.5 hrs/day = 218.5 hrs
            # To test threshold, create a custom monthly target dict
            year_config_id = year_config.id
            db.session.commit()
            db.session.refresh(year_config)

            # Create targets where one month is exactly at threshold
            # January 2025 has 23 workdays: 23 * 9.5 = 218.5 hours (exactly at threshold)
            targets = {
                1: 218.5,  # 23 workdays * 9.5 = exactly at threshold
                2: 150.0,
                3: 150.0,
                4: 150.0,
                5: 150.0,
                6: 150.0,
                7: 150.0,
                8: 150.0,
                9: 150.0,
                10: 150.0,
                11: 150.0,
                12: 131.5,  # Remainder
            }

            warnings = validate_plan_feasibility(targets, year_config)

            # January should NOT trigger warning (at threshold, not over)
            january_warnings = [w for w in warnings if w.month == 1]
            assert len(january_warnings) == 0

    def test_just_over_threshold_triggers_warning(self, app):
        """Just over 9.5 hours/day threshold should trigger warning."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.commit()
            db.session.refresh(year_config)

            # Create targets where January is just over threshold
            # January 2025 has 23 workdays: 23 * 9.51 = 218.73 hours
            targets = {
                1: 220.0,  # 23 workdays = 9.57 hrs/day (over threshold)
                2: 150.0,
                3: 150.0,
                4: 150.0,
                5: 150.0,
                6: 150.0,
                7: 150.0,
                8: 150.0,
                9: 150.0,
                10: 150.0,
                11: 150.0,
                12: 130.0,  # Remainder
            }

            warnings = validate_plan_feasibility(targets, year_config)

            # January should trigger warning
            january_warnings = [w for w in warnings if w.month == 1]
            assert len(january_warnings) == 1
            assert january_warnings[0].required_daily_hours > MAX_DAILY_HOURS

    def test_optimistic_target_same_as_start_month(self, app):
        """Optimistic with target month same as start month compresses to one month."""
        with app.app_context():
            # Start mid-July and target end of July
            year_config = YearConfig(
                year=2025,
                annual_target=1800,
                start_date=datetime.date(2025, 7, 15)
            )
            db.session.add(year_config)
            db.session.flush()

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.OPTIMISTIC,
                target_date=datetime.date(2025, 7, 31)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(plan)

            targets = calculate_monthly_targets_for_plan(year_config, plan)

            # Only July should have hours (all 1800 compressed)
            assert targets[7] > 0
            # Months before July should have 0
            for month in range(1, 7):
                assert targets[month] == 0.0
            # Months after July should have 0 (no maintenance hours set)
            for month in range(8, 13):
                assert targets[month] == 0.0

            # July should have all 1800 hours
            assert abs(targets[7] - 1800) < 0.01
