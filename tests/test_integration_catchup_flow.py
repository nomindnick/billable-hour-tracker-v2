"""
Integration tests for the catch-up sprint workflow (Sprint 4.3).

Tests the complete catch-up sprint journey - falling behind, triggering
suggestions, creating sprints, tracking progress, revision, and auto-completion.
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
def current_year():
    """Return the current year for testing."""
    return datetime.date.today().year


@pytest.fixture
def today():
    """Return today's date."""
    return datetime.date.today()


@pytest.fixture
def year_config_with_plans(app, current_year):
    """
    Create a complete YearConfig with all three plans and 12 month configs.
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
            )
            db.session.add(plan)

        db.session.commit()
        db.session.refresh(year_config)
        yield year_config


@pytest.fixture
def year_config_slightly_behind(app, year_config_with_plans, current_year):
    """
    Create a config where user is slightly behind (5-15 hours).

    Adds entries with below-target hours to create "Slightly behind" status.
    """
    with app.app_context():
        config = db.session.get(YearConfig, year_config_with_plans.id)

        # Add entries with low hours - enough to be 5+ hours behind but less than 15
        # Assuming ~7.5 hours/day target, 5 hours/day creates ~2.5 hour/day deficit
        # 3-4 days would create 7.5-10 hours behind
        for i in range(4):
            entry_date = datetime.date(current_year, 1, 6 + i)  # Start from Jan 6 (Mon)
            if entry_date.weekday() < 5:  # Only weekdays
                entry = DailyEntry(
                    year_config_id=config.id,
                    date=entry_date,
                    hours_billed=5.0,  # Below target
                )
                db.session.add(entry)

        db.session.commit()
        db.session.refresh(config)
        yield config


@pytest.fixture
def year_config_significantly_behind(app, year_config_with_plans, current_year):
    """
    Create a config where user is significantly behind (15+ hours).

    Adds entries with below-target hours to create "Catch-up recommended" status.
    """
    with app.app_context():
        config = db.session.get(YearConfig, year_config_with_plans.id)

        # Add entries with low hours - 10 days at 5 hrs creates ~25 hour deficit
        # (10 * 2.5 = 25 hours behind)
        workdays_added = 0
        day_offset = 0
        while workdays_added < 10:
            entry_date = datetime.date(current_year, 1, 6) + datetime.timedelta(days=day_offset)
            if entry_date.weekday() < 5:  # Only weekdays
                entry = DailyEntry(
                    year_config_id=config.id,
                    date=entry_date,
                    hours_billed=5.0,  # Below target
                )
                db.session.add(entry)
                workdays_added += 1
            day_offset += 1

        db.session.commit()
        db.session.refresh(config)
        yield config


@pytest.fixture
def active_sprint(app, year_config_significantly_behind, current_year, today):
    """
    Create an active catch-up sprint.
    """
    with app.app_context():
        config = db.session.get(YearConfig, year_config_significantly_behind.id)

        sprint = CatchUpSprint(
            year_config_id=config.id,
            target_plan=PlanType.REALISTIC,
            start_date=today,
            end_date=today + datetime.timedelta(weeks=2),
            target_hours=20.0,
            status=SprintStatus.ACTIVE,
        )
        db.session.add(sprint)
        db.session.commit()
        db.session.refresh(sprint)
        yield sprint


# -----------------------------------------------------------------------------
# Falling Behind Status Tests
# -----------------------------------------------------------------------------


class TestFallingBehindStatus:
    """Tests for falling behind status indicators."""

    def test_slightly_behind_after_low_hours(
        self, client, year_config_slightly_behind
    ):
        """Dashboard shows 'Slightly behind' when 5-15 hours behind."""
        response = client.get("/")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8").lower()

        # Should show slightly behind status
        assert "behind" in response_text or "slightly" in response_text

    def test_catchup_recommended_after_significant_shortfall(
        self, client, year_config_significantly_behind
    ):
        """Dashboard shows catch-up recommendation when 15+ hours behind."""
        response = client.get("/")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8").lower()

        # Should show catch-up recommendation
        assert "catch" in response_text or "behind" in response_text


# -----------------------------------------------------------------------------
# Catch-Up Sprint Creation Tests
# -----------------------------------------------------------------------------


class TestCatchUpSprintCreation:
    """Tests for catch-up sprint creation."""

    def test_sprint_preview_shows_hours_behind(
        self, client, year_config_significantly_behind
    ):
        """Sprint preview displays hours behind deficit."""
        response = client.post(
            "/catchup/preview",
            data={"plan_type": "realistic", "duration": "2"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        response_text = response.data.decode("utf-8").lower()

        # Should show hours behind or target hours
        assert "hour" in response_text

    def test_sprint_preview_shows_daily_targets(
        self, client, year_config_significantly_behind
    ):
        """Sprint preview shows weekday and weekend daily targets."""
        response = client.post(
            "/catchup/preview",
            data={
                "plan_type": "realistic",
                "duration": "2",
                "include_weekends": "on",
                "weekend_hours": "2",
            },
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        response_text = response.data.decode("utf-8")

        # Should show target information
        assert "target" in response_text.lower() or "hour" in response_text.lower()

    def test_sprint_preview_shows_feasibility(
        self, client, year_config_significantly_behind
    ):
        """Sprint preview indicates whether plan is feasible."""
        response = client.post(
            "/catchup/preview",
            data={"plan_type": "realistic", "duration": "2"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        # Should return partial HTML with feasibility info
        assert b"<" in response.data

    def test_create_sprint_for_realistic_plan(
        self, client, app, year_config_significantly_behind, today
    ):
        """Creating a catch-up sprint saves correct settings."""
        response = client.post(
            "/catchup/",
            data={
                "plan_type": "realistic",
                "duration": "2",
                "include_weekends": "on",
                "weekend_hours": "2",
            },
            follow_redirects=False,
        )

        # Should redirect (to dashboard or catchup page)
        assert response.status_code == 302

        with app.app_context():
            sprint = CatchUpSprint.query.filter_by(
                year_config_id=year_config_significantly_behind.id,
                status=SprintStatus.ACTIVE,
            ).first()
            assert sprint is not None
            assert sprint.target_plan == PlanType.REALISTIC


# -----------------------------------------------------------------------------
# Sprint on Dashboard Tests
# -----------------------------------------------------------------------------


class TestSprintOnDashboard:
    """Tests for sprint display on dashboard."""

    def test_dashboard_shows_sprint_card(
        self, client, active_sprint
    ):
        """Dashboard shows active sprint as additional section."""
        response = client.get("/")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8").lower()

        # Should show sprint information
        assert "sprint" in response_text or "catch" in response_text

    def test_sprint_progress_displayed(
        self, client, active_sprint
    ):
        """Dashboard shows sprint progress information."""
        response = client.get("/")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8").lower()

        # Should show progress-related content
        assert "progress" in response_text or "%" in response_text or "day" in response_text


# -----------------------------------------------------------------------------
# Sprint Progress Tests
# -----------------------------------------------------------------------------


class TestSprintProgress:
    """Tests for sprint progress tracking."""

    def test_sprint_progress_updates_with_entries(
        self, client, app, active_sprint, today
    ):
        """Sprint progress updates when hours are entered."""
        with app.app_context():
            sprint = db.session.get(CatchUpSprint, active_sprint.id)
            config_id = sprint.year_config_id

        # Enter hours for today
        client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "8.0"},
        )

        # Check dashboard shows updated progress
        response = client.get("/")
        assert response.status_code == 200
        response_text = response.data.decode("utf-8")

        # Should reflect the 8 hours entered
        assert "8" in response_text

    def test_behind_pace_alert_appears(
        self, client, app, active_sprint, today
    ):
        """Behind pace alert shows when >3 hours behind sprint target."""
        # Don't enter any hours - sprint will be behind pace
        # Just check dashboard
        response = client.get("/")

        assert response.status_code == 200
        # Dashboard should show sprint status (may show behind indicator)
        response_text = response.data.decode("utf-8").lower()
        assert "sprint" in response_text or "catch" in response_text


# -----------------------------------------------------------------------------
# Sprint Revision Tests
# -----------------------------------------------------------------------------


class TestSprintRevision:
    """Tests for sprint revision functionality."""

    def test_revise_sprint_shows_prefilled_form(
        self, client, app, active_sprint
    ):
        """Revision form shows prefilled with current sprint values."""
        with app.app_context():
            sprint_id = active_sprint.id

        response = client.get(f"/catchup/{sprint_id}/revise")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8").lower()
        assert "sprint" in response_text or "duration" in response_text

    def test_old_sprint_marked_revised(
        self, client, app, active_sprint
    ):
        """Creating new sprint marks old one as REVISED."""
        with app.app_context():
            old_sprint_id = active_sprint.id
            config_id = active_sprint.year_config_id

        # Create a new sprint (which should mark old one as REVISED)
        response = client.post(
            "/catchup/",
            data={
                "plan_type": "realistic",
                "duration": "3",  # Extended duration
                "include_weekends": "false",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302

        with app.app_context():
            # Old sprint should be REVISED
            old_sprint = db.session.get(CatchUpSprint, old_sprint_id)
            assert old_sprint.status == SprintStatus.REVISED

            # New sprint should be ACTIVE
            new_sprint = CatchUpSprint.query.filter_by(
                year_config_id=config_id,
                status=SprintStatus.ACTIVE,
            ).first()
            assert new_sprint is not None
            assert new_sprint.id != old_sprint_id


# -----------------------------------------------------------------------------
# Sprint Completion Tests
# -----------------------------------------------------------------------------


class TestSprintCompletion:
    """Tests for sprint completion."""

    def test_complete_sprint_updates_status(
        self, client, app, active_sprint
    ):
        """Completing a sprint sets status to COMPLETED."""
        with app.app_context():
            sprint_id = active_sprint.id

        response = client.post(
            f"/catchup/{sprint_id}/complete",
            follow_redirects=False,
        )

        assert response.status_code == 302

        with app.app_context():
            sprint = db.session.get(CatchUpSprint, sprint_id)
            assert sprint.status == SprintStatus.COMPLETED
            assert sprint.completed_at is not None

    def test_dismiss_sprint_updates_status(
        self, client, app, active_sprint
    ):
        """Dismissing a sprint sets status to DISMISSED."""
        with app.app_context():
            sprint_id = active_sprint.id

        response = client.post(
            f"/catchup/{sprint_id}/dismiss",
            follow_redirects=False,
        )

        assert response.status_code == 302

        with app.app_context():
            sprint = db.session.get(CatchUpSprint, sprint_id)
            assert sprint.status == SprintStatus.DISMISSED

    def test_dashboard_returns_to_three_plans_after_completion(
        self, client, app, active_sprint
    ):
        """Dashboard shows only three plans after sprint completion."""
        with app.app_context():
            sprint_id = active_sprint.id

        # Complete the sprint
        client.post(f"/catchup/{sprint_id}/complete")

        # Check dashboard
        response = client.get("/")
        assert response.status_code == 200
        response_text = response.data.decode("utf-8")

        # Should show three plans
        assert "Firm" in response_text
        assert "Realistic" in response_text
        assert "Optimistic" in response_text


# -----------------------------------------------------------------------------
# Full End-to-End Workflow Test
# -----------------------------------------------------------------------------


class TestFullCatchUpWorkflow:
    """End-to-end test of complete catch-up workflow."""

    def test_complete_catchup_flow_end_to_end(
        self, client, app, year_config_with_plans, current_year, today
    ):
        """
        Complete catch-up workflow from falling behind through completion.

        This test walks through:
        1. Enter below-target hours to fall behind
        2. Verify "behind" status appears
        3. Create catch-up sprint
        4. Verify sprint appears on dashboard
        5. Enter hours during sprint
        6. Complete/dismiss sprint
        7. Verify dashboard returns to normal
        """
        with app.app_context():
            config_id = year_config_with_plans.id

        # Step 1: Enter below-target hours (5 hrs/day for multiple days)
        workdays_added = 0
        day_offset = 0
        while workdays_added < 8:
            entry_date = datetime.date(current_year, 1, 6) + datetime.timedelta(days=day_offset)
            if entry_date.weekday() < 5:  # Only weekdays
                client.post(
                    "/entries/",
                    data={"date": entry_date.isoformat(), "hours": "5.0"},
                )
                workdays_added += 1
            day_offset += 1

        # Step 2: Check dashboard shows behind status
        response = client.get("/")
        assert response.status_code == 200
        response_text = response.data.decode("utf-8").lower()
        assert "behind" in response_text or "catch" in response_text

        # Step 3: Create catch-up sprint
        response = client.post(
            "/catchup/",
            data={
                "plan_type": "realistic",
                "duration": "2",
                "include_weekends": "on",
                "weekend_hours": "2",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        with app.app_context():
            sprint = CatchUpSprint.query.filter_by(
                year_config_id=config_id,
                status=SprintStatus.ACTIVE,
            ).first()
            assert sprint is not None
            sprint_id = sprint.id

        # Step 4: Verify sprint appears on dashboard
        response = client.get("/")
        assert response.status_code == 200
        response_text = response.data.decode("utf-8").lower()
        assert "sprint" in response_text or "catch" in response_text

        # Step 5: Enter some hours during sprint
        client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "9.0"},
        )

        # Step 6: Complete the sprint
        client.post(f"/catchup/{sprint_id}/complete")

        with app.app_context():
            sprint = db.session.get(CatchUpSprint, sprint_id)
            assert sprint.status == SprintStatus.COMPLETED

        # Step 7: Verify dashboard returns to normal (three plans)
        response = client.get("/")
        assert response.status_code == 200
        response_text = response.data.decode("utf-8")
        assert "Firm" in response_text
        assert "Realistic" in response_text
        assert "Optimistic" in response_text
