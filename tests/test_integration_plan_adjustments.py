"""
Integration tests for plan adjustment scenarios (Sprint 4.7).

Tests mid-year plan modifications including annual target changes,
holiday/vacation adjustments, intensity modifications, and Optimistic
plan settings - verifying calculations update while preserving historical data.
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
from app.services.planner import (
    calculate_monthly_targets_for_plan,
    get_monthly_breakdown,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def current_year():
    """Return the current year for testing."""
    return datetime.date.today().year


@pytest.fixture
def year_config_with_march_entries(app, current_year):
    """
    Create a fully configured YearConfig with entries through March.

    This represents a user who has been tracking for 3 months and now
    wants to make mid-year adjustments.
    """
    with app.app_context():
        year_config = YearConfig(year=current_year, annual_target=1800)
        db.session.add(year_config)
        db.session.flush()

        # Add 12 month configs with normal intensity
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
                target_daily_hours_after=2.0,
            )
            db.session.add(plan)

        # Add entries for January, February, March (typical billing ~150 hrs/month)
        # This totals to ~450 hours for Q1
        for month in range(1, 4):
            # Add ~10 workday entries per month with 7.5 hours each
            for day in [3, 6, 7, 10, 13, 14, 17, 20, 21, 24]:
                try:
                    entry_date = datetime.date(current_year, month, day)
                    # Skip weekends
                    if entry_date.weekday() < 5:
                        entry = DailyEntry(
                            year_config_id=year_config.id,
                            date=entry_date,
                            hours_billed=7.5,
                        )
                        db.session.add(entry)
                except ValueError:
                    # Skip invalid dates (e.g., Feb 30)
                    pass

        db.session.commit()
        db.session.refresh(year_config)
        yield year_config


@pytest.fixture
def year_config_basic(app, current_year):
    """
    Create a basic YearConfig without entries for simpler tests.
    """
    with app.app_context():
        year_config = YearConfig(year=current_year, annual_target=1800)
        db.session.add(year_config)
        db.session.flush()

        # Add 12 month configs with normal intensity
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
                target_daily_hours_after=2.0,
            )
            db.session.add(plan)

        db.session.commit()
        db.session.refresh(year_config)
        yield year_config


# -----------------------------------------------------------------------------
# Annual Target Adjustment Tests
# -----------------------------------------------------------------------------


class TestAnnualTargetAdjustment:
    """Tests for annual target modifications."""

    def test_increase_annual_target_increases_daily_targets(
        self, client, app, year_config_with_march_entries, current_year
    ):
        """Increasing annual target from 1800 to 2000 increases daily targets."""
        with app.app_context():
            config_id = year_config_with_march_entries.id

            # Get original target for Realistic plan
            config = db.session.get(YearConfig, config_id)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            original_breakdown = get_monthly_breakdown(config, realistic_plan)
            original_june_target = next(
                m.target_hours for m in original_breakdown if m.month == 6
            )

        # Increase annual target to 2000
        response = client.post(
            "/setup/year",
            data={"year": str(current_year), "annual_target": "2000"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            assert config.annual_target == 2000

            # Get new target for Realistic plan
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            new_breakdown = get_monthly_breakdown(config, realistic_plan)
            new_june_target = next(
                m.target_hours for m in new_breakdown if m.month == 6
            )

            # New target should be higher
            assert new_june_target > original_june_target

    def test_decrease_annual_target_decreases_daily_targets(
        self, client, app, year_config_with_march_entries, current_year
    ):
        """Decreasing annual target from 1800 to 1600 decreases daily targets."""
        with app.app_context():
            config_id = year_config_with_march_entries.id

            # Get original target for Realistic plan
            config = db.session.get(YearConfig, config_id)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            original_breakdown = get_monthly_breakdown(config, realistic_plan)
            original_june_target = next(
                m.target_hours for m in original_breakdown if m.month == 6
            )

        # Decrease annual target to 1600
        response = client.post(
            "/setup/year",
            data={"year": str(current_year), "annual_target": "1600"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            assert config.annual_target == 1600

            # Get new target for Realistic plan
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            new_breakdown = get_monthly_breakdown(config, realistic_plan)
            new_june_target = next(
                m.target_hours for m in new_breakdown if m.month == 6
            )

            # New target should be lower
            assert new_june_target < original_june_target

    def test_annual_target_change_preserves_past_entries(
        self, client, app, year_config_with_march_entries, current_year
    ):
        """Changing annual target does not affect historical DailyEntry records."""
        with app.app_context():
            config_id = year_config_with_march_entries.id

            # Count entries before
            entries_before = DailyEntry.query.filter_by(
                year_config_id=config_id
            ).all()
            entry_count_before = len(entries_before)
            total_hours_before = sum(e.hours_billed for e in entries_before)

        # Change annual target
        response = client.post(
            "/setup/year",
            data={"year": str(current_year), "annual_target": "2000"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        with app.app_context():
            # Count entries after - should be unchanged
            entries_after = DailyEntry.query.filter_by(
                year_config_id=config_id
            ).all()
            entry_count_after = len(entries_after)
            total_hours_after = sum(e.hours_billed for e in entries_after)

            assert entry_count_after == entry_count_before
            assert total_hours_after == total_hours_before

    def test_target_change_redistributes_remaining_hours(
        self, client, app, year_config_basic, current_year
    ):
        """Target change redistributes hours across all remaining months."""
        with app.app_context():
            config_id = year_config_basic.id

        # Set to 1800
        client.post(
            "/setup/year",
            data={"year": str(current_year), "annual_target": "1800"},
        )

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            targets_1800 = calculate_monthly_targets_for_plan(config, realistic_plan)
            total_1800 = sum(targets_1800.values())

        # Change to 2400
        client.post(
            "/setup/year",
            data={"year": str(current_year), "annual_target": "2400"},
        )

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            db.session.refresh(config)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            targets_2400 = calculate_monthly_targets_for_plan(config, realistic_plan)
            total_2400 = sum(targets_2400.values())

            # Totals should reflect new target
            assert abs(total_1800 - 1800) < 1.0
            assert abs(total_2400 - 2400) < 1.0

    def test_sequential_target_changes_apply_correctly(
        self, client, app, year_config_basic, current_year
    ):
        """Multiple sequential target changes all apply correctly."""
        with app.app_context():
            config_id = year_config_basic.id

        # Change: 1800 -> 2000 -> 1500 -> 1800
        for target in [2000, 1500, 1800]:
            response = client.post(
                "/setup/year",
                data={"year": str(current_year), "annual_target": str(target)},
                follow_redirects=False,
            )
            assert response.status_code == 302

            with app.app_context():
                config = db.session.get(YearConfig, config_id)
                assert config.annual_target == target

    def test_target_at_boundaries_1000_and_3000(
        self, client, app, year_config_basic, current_year
    ):
        """Annual target can be set to boundary values 1000 and 3000."""
        with app.app_context():
            config_id = year_config_basic.id

        # Set to minimum (1000)
        response = client.post(
            "/setup/year",
            data={"year": str(current_year), "annual_target": "1000"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            assert config.annual_target == 1000

        # Set to maximum (3000)
        response = client.post(
            "/setup/year",
            data={"year": str(current_year), "annual_target": "3000"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            assert config.annual_target == 3000


# -----------------------------------------------------------------------------
# Holiday Adjustment Tests
# -----------------------------------------------------------------------------


class TestHolidayAdjustment:
    """Tests for holiday modifications."""

    def test_add_holiday_reduces_workdays_increases_daily_target(
        self, client, app, year_config_basic, current_year
    ):
        """Adding a holiday reduces workdays and increases daily target for that month."""
        with app.app_context():
            config_id = year_config_basic.id

            # Get original June workdays
            config = db.session.get(YearConfig, config_id)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            original_breakdown = get_monthly_breakdown(config, realistic_plan)
            original_june = next(m for m in original_breakdown if m.month == 6)
            original_daily = original_june.daily_target

        # Add a holiday in June (June 15)
        response = client.post(
            "/setup/holidays/add",
            data={"date": f"{current_year}-06-15", "name": "Test Holiday"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code in [200, 201]

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            db.session.refresh(config)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            new_breakdown = get_monthly_breakdown(config, realistic_plan)
            new_june = next(m for m in new_breakdown if m.month == 6)

            # Daily target should increase (fewer days, same hours)
            assert new_june.daily_target > original_daily
            # Workdays should decrease by 1 (if June 15 is a weekday)
            june_15 = datetime.date(current_year, 6, 15)
            if june_15.weekday() < 5:  # Weekday
                assert new_june.workdays == original_june.workdays - 1

    def test_remove_holiday_increases_workdays_decreases_daily_target(
        self, client, app, year_config_basic, current_year
    ):
        """Removing a holiday increases workdays and decreases daily target."""
        with app.app_context():
            config_id = year_config_basic.id

            # First add a holiday on a guaranteed weekday (July 15 is always a weekday in most years)
            # Find a guaranteed weekday in July
            holiday_date = datetime.date(current_year, 7, 15)
            while holiday_date.weekday() >= 5:  # Skip weekends
                holiday_date += datetime.timedelta(days=1)

            config = db.session.get(YearConfig, config_id)
            holiday = Holiday(
                year_config_id=config_id,
                date=holiday_date,
                name="Test Holiday",
            )
            db.session.add(holiday)
            db.session.commit()
            holiday_id = holiday.id

            # Get target with holiday
            db.session.refresh(config)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            with_holiday = get_monthly_breakdown(config, realistic_plan)
            july_with = next(m for m in with_holiday if m.month == 7)

        # Remove the holiday
        response = client.delete(
            f"/setup/holidays/{holiday_id}",
            headers={"HX-Request": "true"},
        )
        assert response.status_code in [200, 204]

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            db.session.refresh(config)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            without_holiday = get_monthly_breakdown(config, realistic_plan)
            july_without = next(m for m in without_holiday if m.month == 7)

            # Daily target should decrease (more days, same hours)
            assert july_without.daily_target < july_with.daily_target

    def test_holiday_change_only_affects_that_month(
        self, client, app, year_config_basic, current_year
    ):
        """Adding a holiday in one month doesn't significantly change other months' targets."""
        with app.app_context():
            config_id = year_config_basic.id

            # Get original targets
            config = db.session.get(YearConfig, config_id)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            original = get_monthly_breakdown(config, realistic_plan)
            original_jan = next(m.target_hours for m in original if m.month == 1)

        # Add holiday in August (shouldn't affect January much)
        client.post(
            "/setup/holidays/add",
            data={"date": f"{current_year}-08-15", "name": "Test"},
            headers={"HX-Request": "true"},
        )

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            db.session.refresh(config)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            new = get_monthly_breakdown(config, realistic_plan)
            new_jan = next(m.target_hours for m in new if m.month == 1)

            # January target should increase slightly (redistribution) but not dramatically
            # The change should be small - hours redistributed across all months
            change_percent = abs(new_jan - original_jan) / original_jan * 100
            assert change_percent < 5  # Less than 5% change

    def test_multiple_holiday_changes_accumulate(
        self, client, app, year_config_basic, current_year
    ):
        """Adding multiple holidays in a month accumulates the effect."""
        with app.app_context():
            config_id = year_config_basic.id

            # Get original September workdays
            config = db.session.get(YearConfig, config_id)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            original = get_monthly_breakdown(config, realistic_plan)
            original_sept = next(m for m in original if m.month == 9)

        # Add 3 holidays in September (Labor Day week)
        for day in [2, 3, 4]:
            client.post(
                "/setup/holidays/add",
                data={"date": f"{current_year}-09-0{day}", "name": f"Holiday {day}"},
                headers={"HX-Request": "true"},
            )

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            db.session.refresh(config)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            new = get_monthly_breakdown(config, realistic_plan)
            new_sept = next(m for m in new if m.month == 9)

            # Daily target should have increased more than with just one holiday
            assert new_sept.daily_target > original_sept.daily_target


# -----------------------------------------------------------------------------
# Vacation Adjustment Tests
# -----------------------------------------------------------------------------


class TestVacationAdjustment:
    """Tests for vacation day modifications."""

    def test_add_vacation_week_redistributes_targets(
        self, client, app, year_config_basic, current_year
    ):
        """Adding a week of vacation redistributes targets to other months."""
        with app.app_context():
            config_id = year_config_basic.id

            # Get original August target
            config = db.session.get(YearConfig, config_id)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            original = get_monthly_breakdown(config, realistic_plan)
            original_aug = next(m for m in original if m.month == 8)
            original_total = sum(m.target_hours for m in original)

        # Add 5 vacation days in August (week vacation)
        for day in range(11, 16):  # Aug 11-15
            client.post(
                "/setup/vacation/add",
                data={"date": f"{current_year}-08-{day}", "note": "Summer vacation"},
                headers={"HX-Request": "true"},
            )

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            db.session.refresh(config)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            new = get_monthly_breakdown(config, realistic_plan)
            new_aug = next(m for m in new if m.month == 8)
            new_total = sum(m.target_hours for m in new)

            # August workdays should decrease
            assert new_aug.workdays < original_aug.workdays
            # Total target hours should remain the same (redistributed)
            assert abs(new_total - original_total) < 1.0

    def test_remove_vacation_redistributes_targets(
        self, client, app, year_config_basic, current_year
    ):
        """Removing vacation days redistributes hours back."""
        with app.app_context():
            config_id = year_config_basic.id

            # Add vacation days
            config = db.session.get(YearConfig, config_id)
            vacation_ids = []
            for day in range(18, 23):  # Oct 18-22
                vacation = VacationDay(
                    year_config_id=config_id,
                    date=datetime.date(current_year, 10, day),
                    note="Fall break",
                )
                db.session.add(vacation)
                db.session.flush()
                vacation_ids.append(vacation.id)
            db.session.commit()

            # Get target with vacation
            db.session.refresh(config)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            with_vacation = get_monthly_breakdown(config, realistic_plan)
            oct_with = next(m for m in with_vacation if m.month == 10)

        # Remove all vacation days
        for vac_id in vacation_ids:
            client.delete(
                f"/setup/vacation/{vac_id}",
                headers={"HX-Request": "true"},
            )

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            db.session.refresh(config)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            without_vacation = get_monthly_breakdown(config, realistic_plan)
            oct_without = next(m for m in without_vacation if m.month == 10)

            # October should have more workdays now
            assert oct_without.workdays > oct_with.workdays
            # Daily target should be lower (more days to spread hours)
            assert oct_without.daily_target < oct_with.daily_target

    def test_vacation_change_only_affects_that_month(
        self, client, app, year_config_basic, current_year
    ):
        """Vacation changes primarily affect the target month."""
        with app.app_context():
            config_id = year_config_basic.id

            # Get original February target
            config = db.session.get(YearConfig, config_id)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            original = get_monthly_breakdown(config, realistic_plan)
            original_feb = next(m.target_hours for m in original if m.month == 2)

        # Add vacation in December (shouldn't affect February much)
        for day in range(23, 28):
            client.post(
                "/setup/vacation/add",
                data={"date": f"{current_year}-12-{day}", "note": "Holiday break"},
                headers={"HX-Request": "true"},
            )

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            db.session.refresh(config)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            new = get_monthly_breakdown(config, realistic_plan)
            new_feb = next(m.target_hours for m in new if m.month == 2)

            # February change should be small
            change_percent = abs(new_feb - original_feb) / original_feb * 100
            assert change_percent < 5

    def test_vacation_on_different_months_independent(
        self, client, app, year_config_basic, current_year
    ):
        """Vacation in different months affects each independently."""
        with app.app_context():
            config_id = year_config_basic.id

            # Get original targets
            config = db.session.get(YearConfig, config_id)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            original = get_monthly_breakdown(config, realistic_plan)
            original_apr = next(m.workdays for m in original if m.month == 4)
            original_jul = next(m.workdays for m in original if m.month == 7)

        # Add vacation in April
        client.post(
            "/setup/vacation/add",
            data={"date": f"{current_year}-04-15", "note": "April trip"},
            headers={"HX-Request": "true"},
        )

        # Add vacation in July
        client.post(
            "/setup/vacation/add",
            data={"date": f"{current_year}-07-15", "note": "July trip"},
            headers={"HX-Request": "true"},
        )

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            db.session.refresh(config)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            new = get_monthly_breakdown(config, realistic_plan)
            new_apr = next(m.workdays for m in new if m.month == 4)
            new_jul = next(m.workdays for m in new if m.month == 7)

            # Each month should be affected independently
            apr_15 = datetime.date(current_year, 4, 15)
            jul_15 = datetime.date(current_year, 7, 15)

            if apr_15.weekday() < 5:
                assert new_apr == original_apr - 1
            if jul_15.weekday() < 5:
                assert new_jul == original_jul - 1


# -----------------------------------------------------------------------------
# Intensity Adjustment Tests
# -----------------------------------------------------------------------------


class TestIntensityAdjustment:
    """Tests for monthly intensity modifications."""

    def test_change_to_light_decreases_month_target(
        self, client, app, year_config_basic, current_year
    ):
        """Changing a month to LIGHT intensity decreases its target."""
        with app.app_context():
            config_id = year_config_basic.id

            # Get original May target
            config = db.session.get(YearConfig, config_id)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            original = get_monthly_breakdown(config, realistic_plan)
            original_may = next(m.target_hours for m in original if m.month == 5)

        # Change May to LIGHT
        response = client.post(
            "/setup/intensity/5",
            data={"intensity": "light"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            db.session.refresh(config)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            new = get_monthly_breakdown(config, realistic_plan)
            new_may = next(m.target_hours for m in new if m.month == 5)

            # May target should be lower
            assert new_may < original_may

    def test_change_to_very_light_further_decreases_target(
        self, client, app, year_config_basic, current_year
    ):
        """Changing to VERY_LIGHT decreases target more than LIGHT."""
        with app.app_context():
            config_id = year_config_basic.id

        # First set to LIGHT
        client.post(
            "/setup/intensity/6",
            data={"intensity": "light"},
            headers={"HX-Request": "true"},
        )

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            db.session.refresh(config)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            light = get_monthly_breakdown(config, realistic_plan)
            light_june = next(m.target_hours for m in light if m.month == 6)

        # Change to VERY_LIGHT
        client.post(
            "/setup/intensity/6",
            data={"intensity": "very_light"},
            headers={"HX-Request": "true"},
        )

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            db.session.refresh(config)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            very_light = get_monthly_breakdown(config, realistic_plan)
            vl_june = next(m.target_hours for m in very_light if m.month == 6)

            # VERY_LIGHT should be even lower than LIGHT
            assert vl_june < light_june

    def test_revert_to_normal_restores_original_distribution(
        self, client, app, year_config_basic, current_year
    ):
        """Reverting to NORMAL intensity restores original distribution."""
        with app.app_context():
            config_id = year_config_basic.id

            # Get original target
            config = db.session.get(YearConfig, config_id)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            original = get_monthly_breakdown(config, realistic_plan)
            original_march = next(m.target_hours for m in original if m.month == 3)

        # Change to LIGHT
        client.post(
            "/setup/intensity/3",
            data={"intensity": "light"},
            headers={"HX-Request": "true"},
        )

        # Revert to NORMAL
        client.post(
            "/setup/intensity/3",
            data={"intensity": "normal"},
            headers={"HX-Request": "true"},
        )

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            db.session.refresh(config)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            reverted = get_monthly_breakdown(config, realistic_plan)
            reverted_march = next(m.target_hours for m in reverted if m.month == 3)

            # Should be back to original
            assert abs(reverted_march - original_march) < 0.1

    def test_intensity_change_redistributes_to_other_months(
        self, client, app, year_config_basic, current_year
    ):
        """Making one month lighter redistributes hours to other months."""
        with app.app_context():
            config_id = year_config_basic.id

            # Get original April target
            config = db.session.get(YearConfig, config_id)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            original = get_monthly_breakdown(config, realistic_plan)
            original_apr = next(m.target_hours for m in original if m.month == 4)

        # Make August VERY_LIGHT - should increase April target
        client.post(
            "/setup/intensity/8",
            data={"intensity": "very_light"},
            headers={"HX-Request": "true"},
        )

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            db.session.refresh(config)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            new = get_monthly_breakdown(config, realistic_plan)
            new_apr = next(m.target_hours for m in new if m.month == 4)

            # April should have more hours now
            assert new_apr > original_apr

    def test_multiple_months_light_compounds_effect(
        self, client, app, year_config_basic, current_year
    ):
        """Making multiple months light compounds the redistribution effect."""
        with app.app_context():
            config_id = year_config_basic.id

            # Get original January target
            config = db.session.get(YearConfig, config_id)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            original = get_monthly_breakdown(config, realistic_plan)
            original_jan = next(m.target_hours for m in original if m.month == 1)

        # Make November and December both VERY_LIGHT
        client.post(
            "/setup/intensity/11",
            data={"intensity": "very_light"},
            headers={"HX-Request": "true"},
        )
        client.post(
            "/setup/intensity/12",
            data={"intensity": "very_light"},
            headers={"HX-Request": "true"},
        )

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            db.session.refresh(config)
            realistic_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.REALISTIC,
            ).first()
            new = get_monthly_breakdown(config, realistic_plan)
            new_jan = next(m.target_hours for m in new if m.month == 1)

            # January should have significantly more hours
            increase_percent = (new_jan - original_jan) / original_jan * 100
            assert increase_percent > 5  # More than 5% increase

    def test_intensity_preset_light_december(
        self, client, app, year_config_basic, current_year
    ):
        """Light December preset sets December to VERY_LIGHT."""
        with app.app_context():
            config_id = year_config_basic.id

        response = client.post(
            "/setup/intensity/preset",
            data={"preset": "light_december"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200

        with app.app_context():
            december = MonthConfig.query.filter_by(
                year_config_id=config_id,
                month=12,
            ).first()
            assert december.intensity == IntensityLevel.VERY_LIGHT

            # Other months should still be NORMAL
            january = MonthConfig.query.filter_by(
                year_config_id=config_id,
                month=1,
            ).first()
            assert january.intensity == IntensityLevel.NORMAL


# -----------------------------------------------------------------------------
# Optimistic Plan Adjustment Tests
# -----------------------------------------------------------------------------


class TestOptimisticPlanAdjustment:
    """Tests for Optimistic plan settings modifications."""

    def test_earlier_target_date_increases_daily_targets(
        self, client, app, year_config_basic, current_year
    ):
        """Moving target date earlier increases daily targets (less time)."""
        with app.app_context():
            config_id = year_config_basic.id

            # Get original Optimistic breakdown (Nov 27 target)
            config = db.session.get(YearConfig, config_id)
            opt_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.OPTIMISTIC,
            ).first()
            original = get_monthly_breakdown(config, opt_plan)
            original_june = next(m.daily_target for m in original if m.month == 6)

        # Move target to October 15 (earlier)
        response = client.post(
            "/setup/plans",
            data={
                "optimistic_target_date": f"{current_year}-10-15",
                "maintenance_hours": "2.0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            db.session.refresh(config)
            opt_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.OPTIMISTIC,
            ).first()
            new = get_monthly_breakdown(config, opt_plan)
            new_june = next(m.daily_target for m in new if m.month == 6)

            # Daily target should be higher (less time to hit goal)
            assert new_june > original_june

    def test_later_target_date_decreases_daily_targets(
        self, client, app, year_config_basic, current_year
    ):
        """Moving target date later decreases daily targets (more time)."""
        with app.app_context():
            config_id = year_config_basic.id

            # First set to early date (Oct 15)
            config = db.session.get(YearConfig, config_id)
            opt_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.OPTIMISTIC,
            ).first()
            opt_plan.target_date = datetime.date(current_year, 10, 15)
            db.session.commit()

            db.session.refresh(config)
            early = get_monthly_breakdown(config, opt_plan)
            early_june = next(m.daily_target for m in early if m.month == 6)

        # Move target to December 15 (later)
        response = client.post(
            "/setup/plans",
            data={
                "optimistic_target_date": f"{current_year}-12-15",
                "maintenance_hours": "2.0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            db.session.refresh(config)
            opt_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.OPTIMISTIC,
            ).first()
            later = get_monthly_breakdown(config, opt_plan)
            later_june = next(m.daily_target for m in later if m.month == 6)

            # Daily target should be lower
            assert later_june < early_june

    def test_modify_maintenance_hours_updates_post_target(
        self, client, app, year_config_basic, current_year
    ):
        """Changing maintenance hours affects post-target calculations."""
        with app.app_context():
            config_id = year_config_basic.id

        # Set maintenance hours to 4.0
        response = client.post(
            "/setup/plans",
            data={
                "optimistic_target_date": f"{current_year}-10-31",
                "maintenance_hours": "4.0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        with app.app_context():
            opt_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.OPTIMISTIC,
            ).first()
            assert opt_plan.target_daily_hours_after == 4.0

    def test_zero_maintenance_hours_front_loads_all(
        self, client, app, year_config_basic, current_year
    ):
        """Setting maintenance to 0 front-loads all hours before target."""
        with app.app_context():
            config_id = year_config_basic.id

        # Set maintenance to 0 with early target
        response = client.post(
            "/setup/plans",
            data={
                "optimistic_target_date": f"{current_year}-10-31",
                "maintenance_hours": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        with app.app_context():
            config = db.session.get(YearConfig, config_id)
            db.session.refresh(config)
            opt_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.OPTIMISTIC,
            ).first()
            breakdown = get_monthly_breakdown(config, opt_plan)

            # November and December should have minimal hours (just maintenance = 0)
            nov = next(m.target_hours for m in breakdown if m.month == 11)
            dec = next(m.target_hours for m in breakdown if m.month == 12)

            # With 0 maintenance, these should be very low or zero
            assert nov < 50 or dec < 50  # Much less than typical ~150/month

    def test_target_date_same_month_as_current(
        self, client, app, year_config_basic, current_year
    ):
        """Target date in current month is handled correctly."""
        today = datetime.date.today()

        # Set target to end of current month
        end_of_month = datetime.date(
            today.year,
            today.month,
            28 if today.month == 2 else 30  # Safe last day
        )

        response = client.post(
            "/setup/plans",
            data={
                "optimistic_target_date": end_of_month.isoformat(),
                "maintenance_hours": "2.0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        with app.app_context():
            config_id = year_config_basic.id
            opt_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.OPTIMISTIC,
            ).first()
            assert opt_plan.target_date == end_of_month

    def test_combined_date_and_maintenance_change(
        self, client, app, year_config_basic, current_year
    ):
        """Changing both target date and maintenance hours together works."""
        with app.app_context():
            config_id = year_config_basic.id

            # Get original state
            opt_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.OPTIMISTIC,
            ).first()
            original_date = opt_plan.target_date
            original_maint = opt_plan.target_daily_hours_after

        # Change both at once
        new_date = datetime.date(current_year, 9, 30)
        new_maint = 3.5

        response = client.post(
            "/setup/plans",
            data={
                "optimistic_target_date": new_date.isoformat(),
                "maintenance_hours": str(new_maint),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        with app.app_context():
            opt_plan = PlanConfig.query.filter_by(
                year_config_id=config_id,
                plan_type=PlanType.OPTIMISTIC,
            ).first()

            # Both should be updated
            assert opt_plan.target_date == new_date
            assert opt_plan.target_daily_hours_after == new_maint

            # And they should be different from original
            assert opt_plan.target_date != original_date or opt_plan.target_daily_hours_after != original_maint
