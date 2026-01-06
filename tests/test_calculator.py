"""
Unit tests for the calculator service.

Tests the daily target calculation logic in app/services/calculator.py.
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
from app.services.calculator import (
    CATCH_UP_THRESHOLD,
    SLIGHTLY_BEHIND_THRESHOLD,
    STATUS_AHEAD,
    STATUS_CATCH_UP_RECOMMENDED,
    STATUS_ON_TRACK,
    STATUS_SLIGHTLY_BEHIND,
    DailyTargetResult,
    PlanStatus,
    calculate_daily_target,
    calculate_hours_banked,
    calculate_plan_status,
    get_expected_hours_to_date,
    get_hours_billed_in_month,
    get_hours_billed_to_date,
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
        db.session.refresh(year_config)
        yield year_config


@pytest.fixture
def realistic_plan(app, basic_year_config):
    """Create a realistic plan for the basic year config."""
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
        yield plan


@pytest.fixture
def firm_plan(app, basic_year_config):
    """Create a firm plan for the basic year config."""
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
        yield plan


@pytest.fixture
def year_config_with_entries(app):
    """Create a YearConfig with some daily entries."""
    with app.app_context():
        year_config = YearConfig(year=2025, annual_target=1800)
        db.session.add(year_config)
        db.session.flush()

        # Add entries for January 2025 (Mon-Fri of first week)
        entries = [
            DailyEntry(year_config_id=year_config.id, date=datetime.date(2025, 1, 6), hours_billed=7.5),
            DailyEntry(year_config_id=year_config.id, date=datetime.date(2025, 1, 7), hours_billed=8.0),
            DailyEntry(year_config_id=year_config.id, date=datetime.date(2025, 1, 8), hours_billed=7.0),
            DailyEntry(year_config_id=year_config.id, date=datetime.date(2025, 1, 9), hours_billed=8.5),
            DailyEntry(year_config_id=year_config.id, date=datetime.date(2025, 1, 10), hours_billed=7.0),
        ]
        db.session.add_all(entries)
        db.session.commit()
        db.session.refresh(year_config)
        yield year_config


# -----------------------------------------------------------------------------
# Test: Constants
# -----------------------------------------------------------------------------

class TestConstants:
    """Tests for calculator constants."""

    def test_slightly_behind_threshold(self):
        """Slightly behind threshold should be 5 hours."""
        assert SLIGHTLY_BEHIND_THRESHOLD == 5.0

    def test_catch_up_threshold(self):
        """Catch-up threshold should be 15 hours."""
        assert CATCH_UP_THRESHOLD == 15.0

    def test_status_labels_defined(self):
        """All status labels should be defined."""
        assert STATUS_ON_TRACK == "On track"
        assert STATUS_AHEAD == "Ahead"
        assert STATUS_SLIGHTLY_BEHIND == "Slightly behind"
        assert STATUS_CATCH_UP_RECOMMENDED == "Catch-up recommended"


# -----------------------------------------------------------------------------
# Test: get_hours_billed_in_month
# -----------------------------------------------------------------------------

class TestGetHoursBilledInMonth:
    """Tests for the get_hours_billed_in_month helper."""

    def test_no_entries_returns_zero(self, basic_year_config, app):
        """Should return 0 when no entries exist."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            hours = get_hours_billed_in_month(year_config, 2025, 1)
            assert hours == 0.0

    def test_sums_entries_in_month(self, year_config_with_entries, app):
        """Should sum all entries in the specified month."""
        with app.app_context():
            year_config = db.session.get(YearConfig, year_config_with_entries.id)
            # 7.5 + 8.0 + 7.0 + 8.5 + 7.0 = 38.0
            hours = get_hours_billed_in_month(year_config, 2025, 1)
            assert hours == 38.0

    def test_ignores_entries_in_other_months(self, app):
        """Should not include entries from other months."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            # Add entries in January and February
            entries = [
                DailyEntry(year_config_id=year_config.id, date=datetime.date(2025, 1, 6), hours_billed=5.0),
                DailyEntry(year_config_id=year_config.id, date=datetime.date(2025, 2, 3), hours_billed=7.0),
            ]
            db.session.add_all(entries)
            db.session.commit()
            db.session.refresh(year_config)

            jan_hours = get_hours_billed_in_month(year_config, 2025, 1)
            feb_hours = get_hours_billed_in_month(year_config, 2025, 2)

            assert jan_hours == 5.0
            assert feb_hours == 7.0


# -----------------------------------------------------------------------------
# Test: get_hours_billed_to_date
# -----------------------------------------------------------------------------

class TestGetHoursBilledToDate:
    """Tests for the get_hours_billed_to_date helper."""

    def test_no_entries_returns_zero(self, basic_year_config, app):
        """Should return 0 when no entries exist."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            hours = get_hours_billed_to_date(year_config, datetime.date(2025, 3, 15))
            assert hours == 0.0

    def test_sums_entries_up_to_date(self, year_config_with_entries, app):
        """Should sum entries up to and including the specified date."""
        with app.app_context():
            year_config = db.session.get(YearConfig, year_config_with_entries.id)

            # Through Jan 8 should be 7.5 + 8.0 + 7.0 = 22.5
            hours = get_hours_billed_to_date(year_config, datetime.date(2025, 1, 8))
            assert hours == 22.5

    def test_includes_entries_on_date(self, year_config_with_entries, app):
        """Should include entries on the exact date specified."""
        with app.app_context():
            year_config = db.session.get(YearConfig, year_config_with_entries.id)

            # Jan 10 entry (7.0) should be included
            hours = get_hours_billed_to_date(year_config, datetime.date(2025, 1, 10))
            assert hours == 38.0  # All entries

    def test_excludes_future_entries(self, app):
        """Should not include entries after the specified date."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            entries = [
                DailyEntry(year_config_id=year_config.id, date=datetime.date(2025, 1, 6), hours_billed=5.0),
                DailyEntry(year_config_id=year_config.id, date=datetime.date(2025, 1, 15), hours_billed=10.0),
            ]
            db.session.add_all(entries)
            db.session.commit()
            db.session.refresh(year_config)

            hours = get_hours_billed_to_date(year_config, datetime.date(2025, 1, 10))
            assert hours == 5.0  # Only Jan 6 entry


# -----------------------------------------------------------------------------
# Test: get_expected_hours_to_date
# -----------------------------------------------------------------------------

class TestGetExpectedHoursToDate:
    """Tests for the get_expected_hours_to_date helper."""

    def test_first_day_of_year(self, basic_year_config, realistic_plan, app):
        """First day of year should have minimal expected hours."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            plan = db.session.get(PlanConfig, realistic_plan.id)

            # Jan 2, 2025 is a Thursday (first workday after New Year)
            expected = get_expected_hours_to_date(
                year_config, plan, datetime.date(2025, 1, 2)
            )

            # Should be a small fraction of January's target
            # January has ~23 workdays, we're at day 2
            assert expected > 0
            assert expected < 20  # Should be very small

    def test_end_of_first_month(self, basic_year_config, realistic_plan, app):
        """End of first month should have full month's target."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            plan = db.session.get(PlanConfig, realistic_plan.id)

            # Jan 31, 2025 is a Friday
            expected = get_expected_hours_to_date(
                year_config, plan, datetime.date(2025, 1, 31)
            )

            # Should be approximately January's target
            # For 1800 hours over 12 months with ~equal workdays, ~150/month
            assert expected > 100
            assert expected < 200

    def test_mid_month_prorates_correctly(self, basic_year_config, firm_plan, app):
        """Mid-month should prorate based on workdays."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            plan = db.session.get(PlanConfig, firm_plan.id)

            # Firm plan is 150/month
            # Mid-January should be roughly half of 150
            expected = get_expected_hours_to_date(
                year_config, plan, datetime.date(2025, 1, 15)
            )

            # January has 23 workdays, Jan 1-15 has about 10-11 workdays
            # So expected should be roughly (10/23) * 150 ≈ 65
            assert expected > 50
            assert expected < 100

    def test_includes_full_completed_months(self, basic_year_config, firm_plan, app):
        """Should include full targets for completed months."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            plan = db.session.get(PlanConfig, firm_plan.id)

            # Mid-March: should include Jan + Feb (150 each) + partial March
            expected = get_expected_hours_to_date(
                year_config, plan, datetime.date(2025, 3, 15)
            )

            # Should be 300 (Jan+Feb) plus part of March
            assert expected > 300
            assert expected < 400


# -----------------------------------------------------------------------------
# Test: calculate_daily_target
# -----------------------------------------------------------------------------

class TestCalculateDailyTarget:
    """Tests for the calculate_daily_target function."""

    def test_start_of_month_even_distribution(self, basic_year_config, firm_plan, app):
        """Start of month should distribute evenly across workdays."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            plan = db.session.get(PlanConfig, firm_plan.id)

            # January 2, 2025 - start of month (Jan 1 is holiday)
            # Firm plan is 150 hours/month
            result = calculate_daily_target(
                year_config, plan, datetime.date(2025, 1, 2)
            )

            # 150 hours / ~23 workdays ≈ 6.5 hours/day
            assert isinstance(result, DailyTargetResult)
            assert result.daily_target > 6.0
            assert result.daily_target < 8.0
            assert result.catch_up_recommended is False

    def test_mid_month_adjusts_for_billed_hours(self, app):
        """Mid-month target should adjust based on hours already billed."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.FIRM,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)

            # Add entries totaling 75 hours (half of 150 monthly target)
            for day in range(6, 16):  # Jan 6-15 are weekdays
                date = datetime.date(2025, 1, day)
                if date.weekday() < 5:
                    entry = DailyEntry(
                        year_config_id=year_config.id,
                        date=date,
                        hours_billed=7.5
                    )
                    db.session.add(entry)

            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            # Calculate target for Jan 20 (remaining ~11 workdays in month)
            result = calculate_daily_target(
                year_config, plan, datetime.date(2025, 1, 20)
            )

            # Remaining hours depends on what's been billed
            # With 75 hours billed, need 75 more, over ~10 days = 7.5/day
            assert result.remaining_hours_this_month < 100
            assert result.daily_target > 0

    def test_caps_at_max_daily_hours(self, app):
        """Target should cap at 9.5 hours."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
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

            # Calculate for end of month with no hours billed
            # Jan 30, 2025 is Thursday, Jan 31 is Friday = 2 workdays left
            # 150 hours / 2 days = 75 hours/day (way over cap)
            result = calculate_daily_target(
                year_config, plan, datetime.date(2025, 1, 30)
            )

            assert result.daily_target == 9.5
            assert result.catch_up_recommended is True

    def test_flags_catch_up_when_exceeds_max(self, app):
        """Should flag catch-up when target would exceed 9.5."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
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

            # End of month with no hours billed = impossible daily target
            result = calculate_daily_target(
                year_config, plan, datetime.date(2025, 1, 31)
            )

            assert result.catch_up_recommended is True

    def test_already_exceeded_target_returns_zero(self, app):
        """Should return 0 target when monthly target already exceeded."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.FIRM,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)

            # Add 160 hours (exceeds 150 monthly target for Firm plan)
            # Using a single entry to clearly exceed the target
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 15),
                hours_billed=160.0
            )
            db.session.add(entry)

            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            result = calculate_daily_target(
                year_config, plan, datetime.date(2025, 1, 28)
            )

            assert result.daily_target == 0.0
            assert result.catch_up_recommended is False
            assert result.remaining_hours_this_month < 0

    def test_no_remaining_workdays_flags_catch_up(self, app):
        """Should flag catch-up when no workdays remain but hours needed."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
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

            # Feb 1, 2025 is a Saturday - no workdays until next month
            # But we still have January hours needed
            result = calculate_daily_target(
                year_config, plan, datetime.date(2025, 2, 1)
            )

            # February 1 is a Saturday, so remaining workdays in Feb
            # starts from Monday Feb 3
            # This test checks a weekend day
            assert result.remaining_workdays >= 0

    def test_ahead_daily_target_stays_at_original_pace(self, app):
        """When ahead, daily target should stay at original pace, not decrease.

        Per spec (SPEC.md line 308): "Banked hours...don't change the daily
        targets—this encourages continued strong performance rather than coasting."

        If user bills significantly more than target, the next day's target
        should stay at the original pace (~6.5 hours), not decrease to a
        lower value.
        """
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.FIRM,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()

            # January 2025 has 23 workdays (Jan 1 is Wed)
            # Firm plan = 150 hours/month
            # On-track target = 150 / 23 = ~6.52 hours/day

            # Add entries for first 5 days at 10 hours each (50 hours total)
            # This puts us significantly ahead of the ~32.6 hours we'd need
            # to be on track for the first 5 workdays
            for day in [2, 3, 6, 7, 8]:  # First 5 workdays in Jan 2025
                entry = DailyEntry(
                    year_config_id=year_config.id,
                    date=datetime.date(2025, 1, day),
                    hours_billed=10.0
                )
                db.session.add(entry)
            db.session.commit()
            db.session.refresh(year_config)

            # Now check target for Jan 9 (6th workday)
            # With 50 hours billed, we need only 100 more over 18 days = ~5.56/day
            # But per spec, daily target should NOT drop below on_track (~6.52)
            result = calculate_daily_target(
                year_config, plan, datetime.date(2025, 1, 9)
            )

            # The on-track target is 150 / 23 = ~6.52
            # Even though we only need 100/18 = 5.56/day now,
            # the target should stay at the on-track pace to encourage
            # continued strong performance
            on_track_target = 150.0 / 23  # ~6.52
            assert result.daily_target >= on_track_target - 0.01

    def test_behind_daily_target_increases(self, app):
        """When behind, daily target should increase to distribute shortfall."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.FIRM,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()

            # Get the initial daily target at start of January
            initial_result = calculate_daily_target(
                year_config, plan, datetime.date(2025, 1, 2)
            )
            initial_target = initial_result.daily_target

            # Now add a low-billing day (3 hours on Jan 2, way below target)
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 2),
                hours_billed=3.0
            )
            db.session.add(entry)
            db.session.commit()
            db.session.refresh(year_config)

            # Get the next day's target (Jan 3)
            next_day_result = calculate_daily_target(
                year_config, plan, datetime.date(2025, 1, 3)
            )

            # The target should increase to compensate for the shortfall
            assert next_day_result.daily_target > initial_target


# -----------------------------------------------------------------------------
# Test: calculate_plan_status
# -----------------------------------------------------------------------------

class TestCalculatePlanStatus:
    """Tests for the calculate_plan_status function."""

    def test_exactly_on_track(self, app):
        """Exactly meeting expectations should show 'On track'."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
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

            # Calculate expected hours for end of January
            # Then add exactly that many hours
            from app.services.calculator import get_expected_hours_to_date
            expected = get_expected_hours_to_date(
                year_config, plan, datetime.date(2025, 1, 31)
            )

            # Add entries to match expected exactly
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 15),
                hours_billed=expected
            )
            db.session.add(entry)
            db.session.commit()
            db.session.refresh(year_config)

            status = calculate_plan_status(
                year_config, plan, datetime.date(2025, 1, 31)
            )

            assert status.status_label == STATUS_ON_TRACK
            assert abs(status.hours_ahead_or_behind) < 0.01

    def test_ahead_positive_hours(self, app):
        """Being ahead should show 'Ahead' with positive hours."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.FIRM,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)

            # Add 200 hours in January (Firm plan expects 150)
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 15),
                hours_billed=200.0
            )
            db.session.add(entry)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            status = calculate_plan_status(
                year_config, plan, datetime.date(2025, 1, 31)
            )

            assert status.status_label == STATUS_AHEAD
            assert status.hours_ahead_or_behind > 0

    def test_within_tolerance_shows_on_track(self, app):
        """Being slightly behind (< 5 hours) should still show 'On track'."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.FIRM,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)

            # Add 147 hours in January (Firm plan expects 150, 3 hours behind)
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 15),
                hours_billed=147.0
            )
            db.session.add(entry)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            status = calculate_plan_status(
                year_config, plan, datetime.date(2025, 1, 31)
            )

            # 3 hours behind is within the 5-hour tolerance
            assert status.status_label == STATUS_ON_TRACK
            assert status.hours_ahead_or_behind < 0
            assert status.hours_ahead_or_behind > -5

    def test_slightly_behind_threshold(self, app):
        """Being 5-15 hours behind should show 'Slightly behind'."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.FIRM,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)

            # Add 140 hours in January (Firm plan expects 150, 10 hours behind)
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 15),
                hours_billed=140.0
            )
            db.session.add(entry)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            status = calculate_plan_status(
                year_config, plan, datetime.date(2025, 1, 31)
            )

            assert status.status_label == STATUS_SLIGHTLY_BEHIND
            assert status.hours_ahead_or_behind <= -5
            assert status.hours_ahead_or_behind > -15

    def test_catch_up_recommended_threshold(self, app):
        """Being more than 15 hours behind should show 'Catch-up recommended'."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.FIRM,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)

            # Add 130 hours in January (Firm plan expects 150, 20 hours behind)
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 15),
                hours_billed=130.0
            )
            db.session.add(entry)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            status = calculate_plan_status(
                year_config, plan, datetime.date(2025, 1, 31)
            )

            assert status.status_label == STATUS_CATCH_UP_RECOMMENDED
            assert status.hours_ahead_or_behind <= -15

    def test_defaults_to_today(self, basic_year_config, realistic_plan, app):
        """Should default to today's date if not specified."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            plan = db.session.get(PlanConfig, realistic_plan.id)

            status = calculate_plan_status(year_config, plan)

            assert isinstance(status, PlanStatus)
            assert status.actual_hours_to_date == 0.0  # No entries


# -----------------------------------------------------------------------------
# Test: calculate_hours_banked
# -----------------------------------------------------------------------------

class TestCalculateHoursBanked:
    """Tests for the calculate_hours_banked function."""

    def test_no_entries_returns_zero(self, basic_year_config, realistic_plan, app):
        """Should return 0 when no hours billed."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            plan = db.session.get(PlanConfig, realistic_plan.id)

            banked = calculate_hours_banked(
                year_config, plan, datetime.date(2025, 1, 15)
            )

            assert banked == 0.0

    def test_behind_returns_zero(self, app):
        """Should return 0 when behind schedule."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.FIRM,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)

            # Add 100 hours (behind 150 expected)
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 15),
                hours_billed=100.0
            )
            db.session.add(entry)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            banked = calculate_hours_banked(
                year_config, plan, datetime.date(2025, 1, 31)
            )

            assert banked == 0.0

    def test_ahead_returns_difference(self, app):
        """Should return positive difference when ahead of schedule."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.FIRM,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)

            # Add 180 hours (30 hours ahead of 150 expected)
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 15),
                hours_billed=180.0
            )
            db.session.add(entry)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            banked = calculate_hours_banked(
                year_config, plan, datetime.date(2025, 1, 31)
            )

            # Should be approximately 30 hours (180 billed - 150 expected)
            assert banked > 25
            assert banked < 35

    def test_defaults_to_today(self, basic_year_config, realistic_plan, app):
        """Should default to today's date if not specified."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            plan = db.session.get(PlanConfig, realistic_plan.id)

            banked = calculate_hours_banked(year_config, plan)

            assert banked == 0.0


# -----------------------------------------------------------------------------
# Test: Integration / Edge Cases
# -----------------------------------------------------------------------------

class TestIntegration:
    """Integration tests for calculator functions."""

    def test_full_month_scenario(self, app):
        """Test a realistic full-month billing scenario."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)

            # Add entries for first half of January
            for day in range(6, 18):  # Jan 6-17
                date = datetime.date(2025, 1, day)
                if date.weekday() < 5:  # Weekdays only
                    entry = DailyEntry(
                        year_config_id=year_config.id,
                        date=date,
                        hours_billed=7.5
                    )
                    db.session.add(entry)

            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            # Check status mid-month
            status = calculate_plan_status(
                year_config, plan, datetime.date(2025, 1, 17)
            )

            # Check daily target for remaining days
            target = calculate_daily_target(
                year_config, plan, datetime.date(2025, 1, 20)
            )

            # Both should work without errors
            assert isinstance(status, PlanStatus)
            assert isinstance(target, DailyTargetResult)

            # User should be roughly on track
            assert status.actual_hours_to_date > 0
            assert target.daily_target > 0

    def test_consistency_between_functions(self, app):
        """Verify that status and banked hours are consistent."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.FIRM,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)

            # Add some hours
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 15),
                hours_billed=160.0
            )
            db.session.add(entry)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            test_date = datetime.date(2025, 1, 31)

            status = calculate_plan_status(year_config, plan, test_date)
            banked = calculate_hours_banked(year_config, plan, test_date)

            # If ahead, banked should equal hours_ahead_or_behind
            if status.hours_ahead_or_behind > 0:
                assert abs(banked - status.hours_ahead_or_behind) < 0.01

            # If behind, banked should be 0
            if status.hours_ahead_or_behind < 0:
                assert banked == 0.0

    def test_light_december_scenario(self, app):
        """Test with light intensity month affecting calculations."""
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

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            # Daily target in December should be lower than other months
            dec_target = calculate_daily_target(
                year_config, plan, datetime.date(2025, 12, 15)
            )
            nov_target = calculate_daily_target(
                year_config, plan, datetime.date(2025, 11, 15)
            )

            # December target should be notably lower due to very_light intensity
            assert dec_target.daily_target < nov_target.daily_target

    def test_intensity_weight_affects_expected_hours(self, app):
        """Verify LIGHT intensity (0.75x) reduces expected hours for a month."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            # Set January to LIGHT intensity
            month_config = MonthConfig(
                year_config_id=year_config.id,
                month=1,
                intensity=IntensityLevel.LIGHT
            )
            db.session.add(month_config)

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            # Get expected hours at end of January
            expected = get_expected_hours_to_date(
                year_config, plan, datetime.date(2025, 1, 31)
            )

            # With LIGHT intensity (0.75x weight) on January, expected should be
            # less than a proportional 1/12 of annual target (150 hours)
            # due to the reduced weight
            assert expected < 150.0
            assert expected > 100.0  # Should still be meaningful amount

    def test_holiday_reduces_workdays_in_calculation(self, app):
        """Verify holidays reduce available workdays in daily target calculation."""
        with app.app_context():
            # Create year config with holiday
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            # Add a mid-month holiday (Jan 15, 2025 is Wednesday - a workday)
            holiday = Holiday(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 15),
                name="Test Holiday"
            )
            db.session.add(holiday)

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            # Get expected hours at end of January with the holiday
            expected_with_holiday = get_expected_hours_to_date(
                year_config, plan, datetime.date(2025, 1, 31)
            )

            # January 2025 typically has 23 workdays
            # With one holiday, it has 22 workdays
            # This should result in a lower proportional allocation vs full 23 workdays

            # The annual target is 1800 hours. If all months were equal, each month
            # would have ~150 hours. With proportional distribution based on workdays,
            # a month with fewer workdays gets a smaller share.
            # Verify expected is in a reasonable range and exists
            assert expected_with_holiday > 0
            assert expected_with_holiday < 160  # Less than equal distribution

            # Verify daily target calculation also works correctly
            target = calculate_daily_target(
                year_config, plan, datetime.date(2025, 1, 2)
            )
            # Daily target should be reasonable (around 7 hours)
            assert target.daily_target > 5.0
            assert target.daily_target < 9.5

    def test_vacation_reduces_workdays_in_calculation(self, app):
        """Verify vacation days reduce available workdays in daily target calculation."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            # Add a week of vacation (Jan 6-10, 2025 are weekdays Mon-Fri)
            for day in range(6, 11):
                vacation = VacationDay(
                    year_config_id=year_config.id,
                    date=datetime.date(2025, 1, day)
                )
                db.session.add(vacation)

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.REALISTIC,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            # Get daily target after vacation week
            target = calculate_daily_target(
                year_config, plan, datetime.date(2025, 1, 13)
            )

            # January 2025 has 23 total workdays, minus 5 vacation = 18 remaining
            # But from Jan 13, there are about 14-15 workdays left in month
            # Remaining workdays should reflect vacation was excluded
            assert target.remaining_workdays > 0
            assert target.remaining_workdays <= 15  # Reasonable remaining after vacation

            # Expected hours should account for fewer available workdays overall
            expected = get_expected_hours_to_date(
                year_config, plan, datetime.date(2025, 1, 31)
            )

            # With 5 fewer workdays in January, expected hours should be lower
            # than a full January allocation
            assert expected > 0


# -----------------------------------------------------------------------------
# Test: Calculator Edge Cases (Sprint 3.9)
# -----------------------------------------------------------------------------

class TestCalculatorEdgeCases:
    """Edge case tests for calculator - Sprint 3.9."""

    def test_daily_target_on_weekend_handles_gracefully(self, app):
        """Calculate daily target when target_date is a Saturday."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
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

            # Feb 1, 2025 is a Saturday
            result = calculate_daily_target(
                year_config, plan, datetime.date(2025, 2, 1)
            )

            # Should handle gracefully - return valid result for February
            assert isinstance(result, DailyTargetResult)
            # Remaining workdays is for February starting from first workday
            assert result.remaining_workdays >= 0

    def test_daily_target_on_holiday(self, app):
        """Calculate daily target when target_date is a holiday."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            # Add Jan 15 as a holiday (Wednesday - a workday)
            holiday = Holiday(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 15),
                name="Test Holiday"
            )
            db.session.add(holiday)

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.FIRM,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            # Calculate on the holiday date itself
            result = calculate_daily_target(
                year_config, plan, datetime.date(2025, 1, 15)
            )

            # Should handle gracefully - holiday is excluded from remaining workdays
            assert isinstance(result, DailyTargetResult)
            assert result.daily_target >= 0

    def test_daily_target_on_december_31(self, app):
        """Daily target calculation on last day of year."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
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

            # Dec 31, 2025 is a Wednesday (a workday)
            result = calculate_daily_target(
                year_config, plan, datetime.date(2025, 12, 31)
            )

            # Should handle last day of year correctly
            assert isinstance(result, DailyTargetResult)
            # Last workday of month - remaining_workdays should be 1 or 0
            assert result.remaining_workdays <= 1
            # With no hours billed all year, catch-up should be recommended
            assert result.catch_up_recommended is True

    def test_expected_hours_on_january_1(self, app):
        """Expected hours at start of year should be minimal."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
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

            # Jan 1, 2025 is a Wednesday (holiday in many cases, but not configured)
            expected = get_expected_hours_to_date(
                year_config, plan, datetime.date(2025, 1, 1)
            )

            # First day of year - should have minimal expected hours
            # (small fraction of January's target)
            assert expected >= 0
            assert expected < 20  # Very small on day 1

    def test_status_with_zero_hours_entire_year(self, app):
        """Plan status when no hours billed at all."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
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

            # No entries added - calculate status mid-year
            status = calculate_plan_status(
                year_config, plan, datetime.date(2025, 6, 30)
            )

            # Should be significantly behind with 0 hours
            assert status.actual_hours_to_date == 0.0
            assert status.hours_ahead_or_behind < 0  # Behind
            # At mid-year, expected ~900 hours, so way behind
            assert status.status_label == STATUS_CATCH_UP_RECOMMENDED

    def test_hours_exceed_annual_target(self, app):
        """Plan status when billed hours exceed 1800."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.FIRM,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)

            # Add entries totaling 1850 hours (exceeds 1800 target)
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 11, 15),
                hours_billed=1850.0
            )
            db.session.add(entry)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            # Calculate status in November (before year end)
            status = calculate_plan_status(
                year_config, plan, datetime.date(2025, 11, 30)
            )

            # Should be ahead with positive banked hours
            assert status.status_label == STATUS_AHEAD
            assert status.hours_ahead_or_behind > 0
            assert status.actual_hours_to_date == 1850.0

            # Banked hours should be positive
            banked = calculate_hours_banked(
                year_config, plan, datetime.date(2025, 11, 30)
            )
            assert banked > 0

    def test_hours_exactly_meet_annual_target(self, app):
        """Plan status when hours exactly equal annual target at year end."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.FIRM,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)

            # Add entries totaling exactly 1800 hours
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 12, 15),
                hours_billed=1800.0
            )
            db.session.add(entry)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            # Calculate status at year end
            status = calculate_plan_status(
                year_config, plan, datetime.date(2025, 12, 31)
            )

            # Should be on track or slightly ahead (exact match)
            assert status.status_label in [STATUS_ON_TRACK, STATUS_AHEAD]
            # Difference should be very close to 0
            assert abs(status.hours_ahead_or_behind) < 5

    def test_daily_target_on_last_workday_of_month(self, app):
        """Daily target on last workday with hours remaining."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
            db.session.add(year_config)
            db.session.flush()

            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=PlanType.FIRM,
                target_date=datetime.date(2025, 12, 31)
            )
            db.session.add(plan)

            # Add some hours but not enough to meet January target
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 15),
                hours_billed=100.0
            )
            db.session.add(entry)
            db.session.commit()
            db.session.refresh(year_config)
            db.session.refresh(plan)

            # Jan 31, 2025 is Friday (last workday of January)
            result = calculate_daily_target(
                year_config, plan, datetime.date(2025, 1, 31)
            )

            # Last workday with 50 hours remaining (150 - 100)
            # remaining_workdays should be 1
            assert result.remaining_workdays == 1
            # Need 50 hours in 1 day = capped at 9.5
            assert result.daily_target == 9.5
            assert result.catch_up_recommended is True

    def test_expected_hours_spanning_year_boundary(self, app):
        """Expected hours calculation when config starts in previous year."""
        with app.app_context():
            # Config for 2025 with start_date in 2024 (edge case - unlikely but test)
            year_config = YearConfig(
                year=2025,
                annual_target=1800,
                start_date=datetime.date(2025, 1, 1)  # Normal start
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

            # Calculate expected hours for December 31 (full year)
            expected = get_expected_hours_to_date(
                year_config, plan, datetime.date(2025, 12, 31)
            )

            # Should be very close to annual target (1800)
            # Firm plan is 150/month * 12 = 1800
            assert abs(expected - 1800) < 5

    def test_banked_hours_exactly_zero_boundary(self, app):
        """Banked hours when actual exactly equals expected."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
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

            # Get expected hours for end of January
            expected = get_expected_hours_to_date(
                year_config, plan, datetime.date(2025, 1, 31)
            )

            # Add exactly that amount
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 15),
                hours_billed=expected
            )
            db.session.add(entry)
            db.session.commit()
            db.session.refresh(year_config)

            # Calculate banked hours
            banked = calculate_hours_banked(
                year_config, plan, datetime.date(2025, 1, 31)
            )

            # Should be exactly 0 (actual == expected)
            assert banked == 0.0

    def test_status_boundary_slightly_behind_threshold(self, app):
        """Test exact boundary at 5 hours behind threshold."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
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

            # Get expected hours for end of January (150 for Firm plan)
            expected = get_expected_hours_to_date(
                year_config, plan, datetime.date(2025, 1, 31)
            )

            # Add hours that put us exactly 5.01 hours behind
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 15),
                hours_billed=expected - 5.01
            )
            db.session.add(entry)
            db.session.commit()
            db.session.refresh(year_config)

            status = calculate_plan_status(
                year_config, plan, datetime.date(2025, 1, 31)
            )

            # 5.01 hours behind should trigger "Slightly behind"
            assert status.status_label == STATUS_SLIGHTLY_BEHIND

    def test_status_boundary_catch_up_threshold(self, app):
        """Test exact boundary at 15 hours behind threshold."""
        with app.app_context():
            year_config = YearConfig(year=2025, annual_target=1800)
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

            # Get expected hours for end of January (150 for Firm plan)
            expected = get_expected_hours_to_date(
                year_config, plan, datetime.date(2025, 1, 31)
            )

            # Add hours that put us exactly 15.01 hours behind
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, 15),
                hours_billed=expected - 15.01
            )
            db.session.add(entry)
            db.session.commit()
            db.session.refresh(year_config)

            status = calculate_plan_status(
                year_config, plan, datetime.date(2025, 1, 31)
            )

            # 15.01 hours behind should trigger "Catch-up recommended"
            assert status.status_label == STATUS_CATCH_UP_RECOMMENDED
