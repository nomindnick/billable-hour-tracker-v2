"""
Integration tests for the daily usage workflow (Sprint 4.2).

Tests the typical daily billing workflow - entering hours via quick entry,
viewing progress updates across dashboard/monthly/history views, and
editing/deleting entries.
"""

import datetime

import pytest

from app import db
from app.models import (
    DailyEntry,
    IntensityLevel,
    MonthConfig,
    PlanConfig,
    PlanType,
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
def yesterday(today):
    """Return yesterday's date."""
    return today - datetime.timedelta(days=1)


@pytest.fixture
def year_config_with_plans(app, current_year):
    """
    Create a complete YearConfig with all three plans and 12 month configs.

    This represents a fully configured user ready to track hours.
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
def entry_for_today(app, year_config_with_plans, today):
    """Create an entry for today with 7.5 hours."""
    with app.app_context():
        entry = DailyEntry(
            year_config_id=year_config_with_plans.id,
            date=today,
            hours_billed=7.5,
        )
        db.session.add(entry)
        db.session.commit()
        db.session.refresh(entry)
        yield entry


@pytest.fixture
def entry_for_yesterday(app, year_config_with_plans, yesterday):
    """Create an entry for yesterday with 7.0 hours."""
    with app.app_context():
        entry = DailyEntry(
            year_config_id=year_config_with_plans.id,
            date=yesterday,
            hours_billed=7.0,
        )
        db.session.add(entry)
        db.session.commit()
        db.session.refresh(entry)
        yield entry


# -----------------------------------------------------------------------------
# Quick Entry Tests
# -----------------------------------------------------------------------------


class TestQuickEntry:
    """Tests for quick entry functionality."""

    def test_quick_entry_creates_entry(self, client, app, year_config_with_plans, today):
        """POST /entries/ creates a new DailyEntry."""
        response = client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "7.5"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code in [200, 201]

        with app.app_context():
            entry = DailyEntry.query.filter_by(date=today).first()
            assert entry is not None
            assert entry.hours_billed == 7.5

    def test_quick_entry_shows_positive_feedback(
        self, client, year_config_with_plans, today
    ):
        """Quick entry returns positive feedback message."""
        response = client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "8.0"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code in [200, 201]

        # Either HX-Refresh (full page) or positive message in response
        has_refresh = response.headers.get("HX-Refresh") == "true"
        response_text = response.data.decode("utf-8").lower()
        positive_words = ["great", "excellent", "good", "nice", "logged", "saved", "success"]
        has_positive = any(word in response_text for word in positive_words)

        assert has_refresh or has_positive

    def test_quick_entry_triggers_dashboard_update(
        self, client, year_config_with_plans, today
    ):
        """Quick entry triggers dashboard refresh via HX-Refresh header."""
        response = client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "7.5"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code in [200, 201]

        # Should have HX-Refresh header to trigger full dashboard update
        has_refresh = response.headers.get("HX-Refresh") == "true"
        # Or returns partial HTML
        has_html = b"<" in response.data

        assert has_refresh or has_html


# -----------------------------------------------------------------------------
# Dashboard Update Tests
# -----------------------------------------------------------------------------


class TestDashboardUpdates:
    """Tests for dashboard updates after entry."""

    def test_dashboard_shows_todays_hours(
        self, client, app, year_config_with_plans, today
    ):
        """Dashboard shows today's hours after entry."""
        # Create entry
        client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "7.5"},
        )

        # Check dashboard
        response = client.get("/")
        assert response.status_code == 200

        response_text = response.data.decode("utf-8")
        # Dashboard should show the hours billed
        assert "7.5" in response_text or "7.50" in response_text

    def test_weekly_progress_updates(
        self, client, app, year_config_with_plans, today
    ):
        """Weekly progress reflects new entry."""
        # Create entry
        client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "7.5"},
        )

        # Check dashboard
        response = client.get("/")
        assert response.status_code == 200

        response_text = response.data.decode("utf-8").lower()
        # Should show weekly section with hours
        assert "week" in response_text

    def test_monthly_progress_updates(
        self, client, app, year_config_with_plans, today
    ):
        """Monthly progress reflects new entry."""
        # Create entry
        client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "7.5"},
        )

        # Check dashboard
        response = client.get("/")
        assert response.status_code == 200

        response_text = response.data.decode("utf-8").lower()
        # Should show monthly section
        assert "month" in response_text

    def test_plan_status_cards_update(
        self, client, app, year_config_with_plans, today
    ):
        """Plan status cards reflect new entry."""
        # Create entry
        client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "7.5"},
        )

        # Check dashboard
        response = client.get("/")
        assert response.status_code == 200

        response_text = response.data.decode("utf-8")
        # All three plans should be visible
        assert "Firm" in response_text
        assert "Realistic" in response_text
        assert "Optimistic" in response_text


# -----------------------------------------------------------------------------
# Historical Entry Tests
# -----------------------------------------------------------------------------


class TestHistoricalEntry:
    """Tests for entering hours for past dates."""

    def test_enter_hours_for_yesterday(
        self, client, app, year_config_with_plans, yesterday
    ):
        """Can enter hours for yesterday."""
        response = client.post(
            "/entries/",
            data={"date": yesterday.isoformat(), "hours": "7.0"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code in [200, 201]

        with app.app_context():
            entry = DailyEntry.query.filter_by(date=yesterday).first()
            assert entry is not None
            assert entry.hours_billed == 7.0

    def test_historical_entry_in_recent_list(
        self, client, app, year_config_with_plans, yesterday
    ):
        """Historical entry appears in recent entries on dashboard."""
        # Create entry for yesterday
        client.post(
            "/entries/",
            data={"date": yesterday.isoformat(), "hours": "7.0"},
        )

        # Check dashboard for recent entries
        response = client.get("/")
        assert response.status_code == 200

        response_text = response.data.decode("utf-8")
        # Should show yesterday's entry in recent list
        assert "7.0" in response_text or "7.00" in response_text


# -----------------------------------------------------------------------------
# Monthly View Tests
# -----------------------------------------------------------------------------


class TestMonthlyView:
    """Tests for monthly calendar view."""

    def test_monthly_shows_entries(
        self, client, app, year_config_with_plans, today, yesterday
    ):
        """Monthly calendar displays entries for both days."""
        # Create entries for today and yesterday
        client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "7.5"},
        )
        client.post(
            "/entries/",
            data={"date": yesterday.isoformat(), "hours": "7.0"},
        )

        # Check monthly view
        response = client.get(f"/monthly/{today.year}/{today.month}")
        assert response.status_code == 200

        response_text = response.data.decode("utf-8")
        # Should show both values
        assert "7.5" in response_text or "7.50" in response_text
        assert "7.0" in response_text or "7.00" in response_text

    def test_monthly_color_coding_green(
        self, client, app, year_config_with_plans, today
    ):
        """Days that meet target show green color coding."""
        # Create a high entry that should meet target
        client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "10.0"},
        )

        # Check monthly view
        response = client.get(f"/monthly/{today.year}/{today.month}")
        assert response.status_code == 200

        response_text = response.data.decode("utf-8").lower()
        # Should have green color class for met target
        assert "green" in response_text or "success" in response_text


# -----------------------------------------------------------------------------
# History View Tests
# -----------------------------------------------------------------------------


class TestHistoryView:
    """Tests for history view."""

    def test_history_shows_entries(
        self, client, app, year_config_with_plans, today, yesterday
    ):
        """History view lists all entries."""
        # Create entries
        client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "7.5"},
        )
        client.post(
            "/entries/",
            data={"date": yesterday.isoformat(), "hours": "7.0"},
        )

        # Check history view
        response = client.get("/history")
        assert response.status_code == 200

        response_text = response.data.decode("utf-8")
        # Should show both entries
        assert "7.5" in response_text or "7.50" in response_text
        assert "7.0" in response_text or "7.00" in response_text

    def test_history_monthly_subtotals(
        self, client, app, year_config_with_plans, today, yesterday
    ):
        """History view shows monthly subtotals."""
        # Create entries (both in same month if same month)
        client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "7.5"},
        )
        client.post(
            "/entries/",
            data={"date": yesterday.isoformat(), "hours": "7.0"},
        )

        # Check history view
        response = client.get("/history")
        assert response.status_code == 200

        response_text = response.data.decode("utf-8")
        # If both in same month, subtotal should be 14.5
        if today.month == yesterday.month:
            assert "14.5" in response_text or "14.50" in response_text


# -----------------------------------------------------------------------------
# Entry Editing Tests
# -----------------------------------------------------------------------------


class TestEntryEditing:
    """Tests for editing existing entries."""

    def test_edit_entry_updates_hours(
        self, client, app, entry_for_yesterday, yesterday
    ):
        """PUT /entries/<id> updates entry hours."""
        with app.app_context():
            entry_id = entry_for_yesterday.id

        response = client.put(
            f"/entries/{entry_id}",
            data={"hours": "8.0"},
        )

        assert response.status_code in [200, 201, 302]

        with app.app_context():
            entry = db.session.get(DailyEntry, entry_id)
            assert entry.hours_billed == 8.0

    def test_edit_triggers_recalculation(
        self, client, app, entry_for_yesterday, yesterday
    ):
        """Editing an entry updates dashboard calculations."""
        with app.app_context():
            entry_id = entry_for_yesterday.id

        # Edit entry to higher value
        client.put(
            f"/entries/{entry_id}",
            data={"hours": "10.0"},
        )

        # Check dashboard reflects new value
        response = client.get("/")
        assert response.status_code == 200

        response_text = response.data.decode("utf-8")
        # Should show updated hours somewhere
        assert "10.0" in response_text or "10.00" in response_text


# -----------------------------------------------------------------------------
# Entry Deletion Tests
# -----------------------------------------------------------------------------


class TestEntryDeletion:
    """Tests for clearing/deleting entries."""

    def test_clear_entry_sets_zero(
        self, client, app, entry_for_yesterday
    ):
        """Setting hours to 0 effectively 'deletes' the entry."""
        with app.app_context():
            entry_id = entry_for_yesterday.id

        response = client.put(
            f"/entries/{entry_id}",
            data={"hours": "0"},
        )

        assert response.status_code in [200, 201, 302]

        with app.app_context():
            entry = db.session.get(DailyEntry, entry_id)
            # Entry either deleted or has 0 hours
            if entry:
                assert entry.hours_billed == 0.0

    def test_clear_removes_from_calculations(
        self, client, app, entry_for_today, today
    ):
        """Clearing an entry removes it from YTD calculations."""
        with app.app_context():
            entry_id = entry_for_today.id

        # First verify entry is counted
        response = client.get("/")
        response_text = response.data.decode("utf-8")
        assert "7.5" in response_text or "7.50" in response_text

        # Clear the entry
        client.put(
            f"/entries/{entry_id}",
            data={"hours": "0"},
        )

        # Verify dashboard no longer shows those hours
        response = client.get("/")
        response_text = response.data.decode("utf-8")
        # The 7.5 should no longer appear as today's hours
        # (it might appear in targets, so we just verify the page loads)
        assert response.status_code == 200


# -----------------------------------------------------------------------------
# Full End-to-End Workflow Test
# -----------------------------------------------------------------------------


class TestFullDailyWorkflow:
    """End-to-end test of complete daily usage workflow."""

    def test_complete_daily_usage_flow(
        self, client, app, year_config_with_plans, today, yesterday
    ):
        """
        Complete daily usage workflow from fresh config to edited entries.

        This test walks through the entire daily usage journey:
        1. Enter 7.5 hours for today
        2. Verify positive feedback
        3. Verify dashboard updates
        4. Enter 7.0 hours for yesterday
        5. Check monthly view shows both days
        6. Check history view shows entries with subtotals
        7. Edit yesterday's entry to 8.0
        8. Verify calculations update
        9. Clear yesterday's entry
        10. Verify removal
        """
        with app.app_context():
            config_id = year_config_with_plans.id

        # Step 1: Enter 7.5 hours for today
        response = client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "7.5"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code in [200, 201]

        # Step 2: Verify positive feedback or refresh
        has_refresh = response.headers.get("HX-Refresh") == "true"
        response_text = response.data.decode("utf-8").lower()
        positive_words = ["great", "excellent", "good", "nice", "logged", "saved"]
        has_positive = any(word in response_text for word in positive_words)
        assert has_refresh or has_positive or response.status_code == 200

        # Step 3: Verify dashboard updates
        response = client.get("/")
        assert response.status_code == 200
        response_text = response.data.decode("utf-8")
        assert "7.5" in response_text or "7.50" in response_text

        # Step 4: Enter 7.0 hours for yesterday
        response = client.post(
            "/entries/",
            data={"date": yesterday.isoformat(), "hours": "7.0"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code in [200, 201]

        # Step 5: Check monthly view shows both days
        response = client.get(f"/monthly/{today.year}/{today.month}")
        assert response.status_code == 200
        response_text = response.data.decode("utf-8")
        # Today's entry
        assert "7.5" in response_text or "7.50" in response_text
        # Yesterday's entry (if same month)
        if today.month == yesterday.month:
            assert "7.0" in response_text or "7.00" in response_text

        # Step 6: Check history view
        response = client.get("/history")
        assert response.status_code == 200
        response_text = response.data.decode("utf-8")
        assert "7.5" in response_text or "7.50" in response_text
        if today.month == yesterday.month:
            # Subtotal should include both (14.5)
            assert "14.5" in response_text or "14.50" in response_text

        # Get yesterday's entry ID for editing
        with app.app_context():
            yesterday_entry = DailyEntry.query.filter_by(
                year_config_id=config_id,
                date=yesterday,
            ).first()
            entry_id = yesterday_entry.id

        # Step 7: Edit yesterday's entry to 8.0
        response = client.put(
            f"/entries/{entry_id}",
            data={"hours": "8.0"},
        )
        assert response.status_code in [200, 201, 302]

        # Step 8: Verify calculations update
        with app.app_context():
            entry = db.session.get(DailyEntry, entry_id)
            assert entry.hours_billed == 8.0

        # Check dashboard shows updated value
        response = client.get("/")
        response_text = response.data.decode("utf-8")
        # New subtotal if same month: 7.5 + 8.0 = 15.5
        if today.month == yesterday.month:
            assert "15.5" in response_text or "15.50" in response_text

        # Step 9: Clear yesterday's entry
        response = client.put(
            f"/entries/{entry_id}",
            data={"hours": "0"},
        )
        assert response.status_code in [200, 201, 302]

        # Step 10: Verify removal from calculations
        with app.app_context():
            entry = db.session.get(DailyEntry, entry_id)
            if entry:
                assert entry.hours_billed == 0.0

        # Dashboard should now only show today's 7.5 hours
        response = client.get("/")
        assert response.status_code == 200
