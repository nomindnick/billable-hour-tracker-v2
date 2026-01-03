"""
Unit tests for the catch-up sprint service.

Tests the catch-up sprint calculation and creation logic in app/services/catchup.py.
"""

import datetime
import pytest

from app import create_app, db
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
from app.services.catchup import (
    CHALLENGING_TARGET,
    COMFORTABLE_TARGET,
    MAX_WEEKEND_HOURS,
    SprintPreview,
    calculate_sprint_preview,
    create_catch_up_sprint,
    get_active_sprint,
    get_plan_config_by_type,
    get_plan_statuses,
    get_sprint_message,
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
def year_config_with_plans(app):
    """Create a YearConfig with Realistic and Optimistic plans, normal intensity."""
    with app.app_context():
        year_config = YearConfig(year=2025, annual_target=1800)
        db.session.add(year_config)
        db.session.flush()

        # Add month configs (all normal intensity)
        for month in range(1, 13):
            month_config = MonthConfig(
                year_config_id=year_config.id,
                month=month,
                intensity=IntensityLevel.NORMAL
            )
            db.session.add(month_config)

        # Add plans
        realistic_plan = PlanConfig(
            year_config_id=year_config.id,
            plan_type=PlanType.REALISTIC,
            target_date=datetime.date(2025, 12, 31)
        )
        optimistic_plan = PlanConfig(
            year_config_id=year_config.id,
            plan_type=PlanType.OPTIMISTIC,
            target_date=datetime.date(2025, 11, 27)
        )
        db.session.add(realistic_plan)
        db.session.add(optimistic_plan)

        db.session.commit()
        db.session.refresh(year_config)
        yield year_config


@pytest.fixture
def behind_year_config(app):
    """Create a YearConfig where user is behind on their plan."""
    with app.app_context():
        year_config = YearConfig(year=2025, annual_target=1800)
        db.session.add(year_config)
        db.session.flush()

        # Add month configs (all normal intensity)
        for month in range(1, 13):
            month_config = MonthConfig(
                year_config_id=year_config.id,
                month=month,
                intensity=IntensityLevel.NORMAL
            )
            db.session.add(month_config)

        # Add realistic plan
        realistic_plan = PlanConfig(
            year_config_id=year_config.id,
            plan_type=PlanType.REALISTIC,
            target_date=datetime.date(2025, 12, 31)
        )
        db.session.add(realistic_plan)

        # Add some entries (less than expected)
        # For Jan 2025, expect ~150 hours but only bill 100
        for day in [6, 7, 8, 9, 10, 13, 14, 15]:  # 8 workdays
            entry = DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(2025, 1, day),
                hours_billed=5.0  # Only 5 hours/day
            )
            db.session.add(entry)

        db.session.commit()
        db.session.refresh(year_config)
        yield year_config


# -----------------------------------------------------------------------------
# Test get_sprint_message
# -----------------------------------------------------------------------------

class TestGetSprintMessage:
    """Tests for the get_sprint_message function."""

    def test_comfortable_target_returns_success(self):
        """Targets <= 7.5 hours should return success message."""
        message, msg_type = get_sprint_message(7.0, True, 50.0)
        assert msg_type == "success"
        assert "manageable" in message.lower()

    def test_challenging_target_returns_warning(self):
        """Targets between 7.5 and 9.0 should return warning."""
        message, msg_type = get_sprint_message(8.5, True, 50.0)
        assert msg_type == "warning"
        assert "challenging" in message.lower() or "doable" in message.lower()

    def test_stretch_target_returns_warning(self):
        """Targets between 9.0 and 9.5 should return warning."""
        message, msg_type = get_sprint_message(9.3, True, 50.0)
        assert msg_type == "warning"
        assert "stretch" in message.lower()

    def test_infeasible_returns_error(self):
        """Infeasible sprints should return error message."""
        message, msg_type = get_sprint_message(10.0, False, 50.0)
        assert msg_type == "error"
        assert "feasible" in message.lower() or "longer" in message.lower()


# -----------------------------------------------------------------------------
# Test get_plan_config_by_type
# -----------------------------------------------------------------------------

class TestGetPlanConfigByType:
    """Tests for the get_plan_config_by_type function."""

    def test_finds_realistic_plan(self, app, year_config_with_plans):
        """Should find the Realistic plan."""
        with app.app_context():
            year_config = db.session.get(YearConfig, year_config_with_plans.id)
            plan = get_plan_config_by_type(year_config, PlanType.REALISTIC)
            assert plan is not None
            assert plan.plan_type == PlanType.REALISTIC

    def test_finds_optimistic_plan(self, app, year_config_with_plans):
        """Should find the Optimistic plan."""
        with app.app_context():
            year_config = db.session.get(YearConfig, year_config_with_plans.id)
            plan = get_plan_config_by_type(year_config, PlanType.OPTIMISTIC)
            assert plan is not None
            assert plan.plan_type == PlanType.OPTIMISTIC

    def test_returns_none_for_missing_plan(self, app, year_config_with_plans):
        """Should return None for plan type not in config."""
        with app.app_context():
            year_config = db.session.get(YearConfig, year_config_with_plans.id)
            plan = get_plan_config_by_type(year_config, PlanType.FIRM)
            assert plan is None


# -----------------------------------------------------------------------------
# Test calculate_sprint_preview
# -----------------------------------------------------------------------------

class TestCalculateSprintPreview:
    """Tests for the calculate_sprint_preview function."""

    def test_returns_on_track_when_ahead(self, app, year_config_with_plans):
        """Should indicate no sprint needed when ahead of plan."""
        with app.app_context():
            year_config = db.session.get(YearConfig, year_config_with_plans.id)

            # Add enough entries to be ahead
            for day in range(1, 11):  # First 10 days of January
                entry = DailyEntry(
                    year_config_id=year_config.id,
                    date=datetime.date(2025, 1, day),
                    hours_billed=10.0  # Well above daily target
                )
                db.session.add(entry)
            db.session.commit()

            preview = calculate_sprint_preview(
                year_config,
                PlanType.REALISTIC,
                duration_weeks=2,
                weekend_hours=0,
                as_of_date=datetime.date(2025, 1, 10)
            )
            assert preview.hours_behind == 0
            assert preview.is_feasible
            assert "on track" in preview.message.lower()

    def test_calculates_hours_behind(self, app, behind_year_config):
        """Should correctly calculate hours behind."""
        with app.app_context():
            year_config = db.session.get(YearConfig, behind_year_config.id)
            # After billing only 40 hours (8 days * 5 hours), should be behind
            preview = calculate_sprint_preview(
                year_config,
                PlanType.REALISTIC,
                duration_weeks=2,
                weekend_hours=0,
                as_of_date=datetime.date(2025, 1, 16)  # After entries
            )
            # Should be behind (exact amount depends on monthly target calculation)
            assert preview.hours_behind > 0
            assert preview.target_hours > 0

    def test_weekend_hours_reduce_weekday_target(self, app, behind_year_config):
        """Adding weekend hours should reduce weekday target."""
        with app.app_context():
            year_config = db.session.get(YearConfig, behind_year_config.id)
            as_of_date = datetime.date(2025, 1, 16)

            # Without weekend billing
            preview_no_weekends = calculate_sprint_preview(
                year_config,
                PlanType.REALISTIC,
                duration_weeks=2,
                weekend_hours=0,
                as_of_date=as_of_date
            )

            # With weekend billing
            preview_with_weekends = calculate_sprint_preview(
                year_config,
                PlanType.REALISTIC,
                duration_weeks=2,
                weekend_hours=3.0,
                as_of_date=as_of_date
            )

            # Weekday target should be lower with weekend billing
            if preview_no_weekends.hours_behind > 0:
                assert preview_with_weekends.weekday_target < preview_no_weekends.weekday_target

    def test_longer_duration_reduces_daily_target(self, app, behind_year_config):
        """Longer sprint duration should reduce daily target."""
        with app.app_context():
            year_config = db.session.get(YearConfig, behind_year_config.id)
            as_of_date = datetime.date(2025, 1, 16)

            # 1 week sprint
            preview_1week = calculate_sprint_preview(
                year_config,
                PlanType.REALISTIC,
                duration_weeks=1,
                weekend_hours=0,
                as_of_date=as_of_date
            )

            # 4 week sprint
            preview_4weeks = calculate_sprint_preview(
                year_config,
                PlanType.REALISTIC,
                duration_weeks=4,
                weekend_hours=0,
                as_of_date=as_of_date
            )

            # Longer sprint should have lower daily target
            if preview_1week.hours_behind > 0:
                assert preview_4weeks.weekday_target < preview_1week.weekday_target

    def test_clamps_duration_to_valid_range(self, app, year_config_with_plans):
        """Should clamp duration to 1-6 weeks."""
        with app.app_context():
            year_config = db.session.get(YearConfig, year_config_with_plans.id)

            # Try 0 weeks (should become 1)
            preview = calculate_sprint_preview(
                year_config,
                PlanType.REALISTIC,
                duration_weeks=0,
                as_of_date=datetime.date(2025, 1, 1)
            )
            assert preview.start_date is not None

            # Try 10 weeks (should become 6)
            preview = calculate_sprint_preview(
                year_config,
                PlanType.REALISTIC,
                duration_weeks=10,
                as_of_date=datetime.date(2025, 1, 1)
            )
            assert preview.start_date is not None

    def test_clamps_weekend_hours(self, app, year_config_with_plans):
        """Should clamp weekend hours to 0-4."""
        with app.app_context():
            year_config = db.session.get(YearConfig, year_config_with_plans.id)

            # Try 6 hours (should become 4)
            preview = calculate_sprint_preview(
                year_config,
                PlanType.REALISTIC,
                duration_weeks=2,
                weekend_hours=6.0,
                as_of_date=datetime.date(2025, 1, 1)
            )
            assert preview.weekend_target <= MAX_WEEKEND_HOURS

    def test_returns_error_for_missing_plan(self, app, basic_year_config):
        """Should return error preview when plan not found."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            preview = calculate_sprint_preview(
                year_config,
                PlanType.REALISTIC,  # No plans configured
                duration_weeks=2
            )
            assert not preview.is_feasible
            assert "not found" in preview.message.lower()


# -----------------------------------------------------------------------------
# Test create_catch_up_sprint
# -----------------------------------------------------------------------------

class TestCreateCatchUpSprint:
    """Tests for the create_catch_up_sprint function."""

    def test_raises_for_firm_plan(self, app, year_config_with_plans):
        """Should raise ValueError for Firm plan type."""
        with app.app_context():
            year_config = db.session.get(YearConfig, year_config_with_plans.id)
            with pytest.raises(ValueError, match="Firm plan"):
                create_catch_up_sprint(
                    year_config,
                    PlanType.FIRM,
                    duration_weeks=2
                )

    def test_raises_when_on_track(self, app, year_config_with_plans):
        """Should raise ValueError when not behind."""
        with app.app_context():
            year_config = db.session.get(YearConfig, year_config_with_plans.id)

            # Add enough entries to be ahead
            for day in range(1, 11):  # First 10 days of January
                entry = DailyEntry(
                    year_config_id=year_config.id,
                    date=datetime.date(2025, 1, day),
                    hours_billed=10.0  # Well above daily target
                )
                db.session.add(entry)
            db.session.commit()

            with pytest.raises(ValueError, match="on track"):
                create_catch_up_sprint(
                    year_config,
                    PlanType.REALISTIC,
                    duration_weeks=2,
                    as_of_date=datetime.date(2025, 1, 10)
                )

    def test_creates_sprint_when_behind(self, app, behind_year_config):
        """Should create sprint when user is behind."""
        with app.app_context():
            year_config = db.session.get(YearConfig, behind_year_config.id)
            sprint = create_catch_up_sprint(
                year_config,
                PlanType.REALISTIC,
                duration_weeks=2,
                as_of_date=datetime.date(2025, 1, 16)
            )

            assert sprint is not None
            assert sprint.status == SprintStatus.ACTIVE
            assert sprint.target_plan == PlanType.REALISTIC
            assert sprint.target_hours > 0
            assert sprint.start_date == datetime.date(2025, 1, 16)

    def test_marks_existing_sprint_as_revised(self, app, behind_year_config):
        """Creating new sprint should mark existing as revised."""
        with app.app_context():
            year_config = db.session.get(YearConfig, behind_year_config.id)

            # Create first sprint
            first_sprint = create_catch_up_sprint(
                year_config,
                PlanType.REALISTIC,
                duration_weeks=2,
                as_of_date=datetime.date(2025, 1, 16)
            )
            first_id = first_sprint.id

            # Create second sprint
            second_sprint = create_catch_up_sprint(
                year_config,
                PlanType.REALISTIC,
                duration_weeks=3,
                as_of_date=datetime.date(2025, 1, 20)
            )

            # First sprint should be revised
            first_sprint = db.session.get(CatchUpSprint, first_id)
            assert first_sprint.status == SprintStatus.REVISED
            assert first_sprint.completed_at is not None

            # Second sprint should be active
            assert second_sprint.status == SprintStatus.ACTIVE


# -----------------------------------------------------------------------------
# Test get_active_sprint
# -----------------------------------------------------------------------------

class TestGetActiveSprint:
    """Tests for the get_active_sprint function."""

    def test_returns_none_when_no_sprint(self, app, year_config_with_plans):
        """Should return None when no active sprint."""
        with app.app_context():
            year_config = db.session.get(YearConfig, year_config_with_plans.id)
            active = get_active_sprint(year_config)
            assert active is None

    def test_returns_active_sprint(self, app, behind_year_config):
        """Should return the active sprint."""
        with app.app_context():
            year_config = db.session.get(YearConfig, behind_year_config.id)

            # Create a sprint
            sprint = create_catch_up_sprint(
                year_config,
                PlanType.REALISTIC,
                duration_weeks=2,
                as_of_date=datetime.date(2025, 1, 16)
            )

            # Should find it
            active = get_active_sprint(year_config)
            assert active is not None
            assert active.id == sprint.id


# -----------------------------------------------------------------------------
# Test get_plan_statuses
# -----------------------------------------------------------------------------

class TestGetPlanStatuses:
    """Tests for the get_plan_statuses function."""

    def test_returns_statuses_for_optimistic_and_realistic(self, app, year_config_with_plans):
        """Should return statuses for Optimistic and Realistic plans."""
        with app.app_context():
            year_config = db.session.get(YearConfig, year_config_with_plans.id)
            statuses = get_plan_statuses(year_config, datetime.date(2025, 1, 15))

            assert PlanType.OPTIMISTIC in statuses
            assert PlanType.REALISTIC in statuses
            assert PlanType.FIRM not in statuses

    def test_returns_empty_when_no_plans(self, app, basic_year_config):
        """Should return empty dict when no plans configured."""
        with app.app_context():
            year_config = db.session.get(YearConfig, basic_year_config.id)
            statuses = get_plan_statuses(year_config)
            assert statuses == {}
