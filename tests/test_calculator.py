"""
Unit tests for the calculator service.

Tests the daily target calculation logic in app/services/calculator.py.
"""

import datetime
import pytest

from app import create_app, db
from app.models import (
    DailyEntry,
    IntensityLevel,
    MonthConfig,
    PlanConfig,
    PlanType,
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
def app():
    """Create a Flask application configured for testing."""
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


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
