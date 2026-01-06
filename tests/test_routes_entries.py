"""
Integration tests for entry routes.

Tests the daily hours entry route handlers in app/routes/entries.py,
verifying entry creation, editing, deletion, and validation.
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
def year_config_with_plans(app):
    """Create a complete YearConfig with all three plans."""
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


@pytest.fixture
def existing_entry(app, year_config_with_plans):
    """Create an existing daily entry for testing edits."""
    with app.app_context():
        entry = DailyEntry(
            year_config_id=year_config_with_plans.id,
            date=datetime.date(2025, 1, 10),
            hours_billed=7.5,
        )
        db.session.add(entry)
        db.session.commit()
        db.session.refresh(entry)
        yield entry


# -----------------------------------------------------------------------------
# Entry Creation Tests
# -----------------------------------------------------------------------------


class TestEntryCreation:
    """Tests for entry creation routes."""

    def test_post_entries_creates_new_entry(self, client, app, year_config_with_plans):
        """POST /entries/ creates a new entry."""
        response = client.post(
            "/entries/",
            data={
                "date": "2025-01-15",
                "hours": "8.0",
            },
        )

        # Should succeed (200 or redirect)
        assert response.status_code in [200, 302]

        with app.app_context():
            entry = DailyEntry.query.filter_by(
                date=datetime.date(2025, 1, 15)
            ).first()
            assert entry is not None
            assert entry.hours_billed == 8.0

    def test_post_entries_updates_existing_for_same_date(
        self, client, app, year_config_with_plans
    ):
        """POST /entries/ updates existing entry when same date submitted."""
        # Create first entry
        client.post(
            "/entries/",
            data={"date": "2025-01-20", "hours": "7.0"},
        )

        # Submit again for same date with different hours
        client.post(
            "/entries/",
            data={"date": "2025-01-20", "hours": "8.5"},
        )

        with app.app_context():
            entries = DailyEntry.query.filter_by(
                date=datetime.date(2025, 1, 20)
            ).all()
            # Should only have one entry for this date
            assert len(entries) == 1
            assert entries[0].hours_billed == 8.5

    def test_post_entries_validates_non_negative_hours(
        self, client, app, year_config_with_plans
    ):
        """POST /entries/ validates that hours are non-negative."""
        response = client.post(
            "/entries/",
            data={"date": "2025-01-25", "hours": "-5.0"},
        )

        with app.app_context():
            entry = DailyEntry.query.filter_by(
                date=datetime.date(2025, 1, 25)
            ).first()
            # Should either not create, or clamp to 0
            if entry:
                assert entry.hours_billed >= 0

    def test_post_entries_accepts_any_date(self, client, app, year_config_with_plans):
        """POST /entries/ accepts entries for any date (no year restriction)."""
        response = client.post(
            "/entries/",
            data={"date": "2025-03-15", "hours": "8.0"},
        )

        with app.app_context():
            entry = DailyEntry.query.filter_by(
                date=datetime.date(2025, 3, 15)
            ).first()
            # Entry should be created
            assert entry is not None
            assert entry.hours_billed == 8.0


# -----------------------------------------------------------------------------
# Entry Editing Tests
# -----------------------------------------------------------------------------


class TestEntryEditing:
    """Tests for entry editing routes."""

    def test_get_edit_returns_form(self, client, existing_entry):
        """GET /entries/<id>/edit returns edit form."""
        response = client.get(f"/entries/{existing_entry.id}/edit")

        # Should return 200 with form
        assert response.status_code == 200
        response_text = response.data.decode("utf-8")
        assert "7.5" in response_text or "hours" in response_text.lower()

    def test_post_edit_updates_entry(self, client, app, existing_entry):
        """POST /entries/<id> updates the entry."""
        response = client.post(
            f"/entries/{existing_entry.id}",
            data={"hours": "9.0"},
        )

        with app.app_context():
            entry = db.session.get(DailyEntry, existing_entry.id)
            assert entry.hours_billed == 9.0


# -----------------------------------------------------------------------------
# Entry Update/Replace Tests
# -----------------------------------------------------------------------------


class TestEntryUpdate:
    """Tests for entry update functionality."""

    def test_update_entry_replaces_hours(self, client, app, existing_entry):
        """PUT /entries/<id> replaces the entry hours."""
        entry_id = existing_entry.id

        response = client.put(
            f"/entries/{entry_id}",
            data={"hours": "10.0"},
        )

        with app.app_context():
            entry = db.session.get(DailyEntry, entry_id)
            assert entry.hours_billed == 10.0

    def test_zero_hours_effectively_clears_entry(self, client, app, existing_entry):
        """Setting hours to 0 effectively clears the entry value."""
        entry_id = existing_entry.id

        response = client.put(
            f"/entries/{entry_id}",
            data={"hours": "0"},
        )

        with app.app_context():
            entry = db.session.get(DailyEntry, entry_id)
            assert entry.hours_billed == 0.0


# -----------------------------------------------------------------------------
# HTMX Response Tests
# -----------------------------------------------------------------------------


class TestHTMXResponses:
    """Tests for HTMX-specific responses."""

    def test_htmx_request_returns_partial(self, client, year_config_with_plans):
        """HTMX requests return partial HTML, not full page."""
        response = client.post(
            "/entries/",
            data={"date": "2025-02-01", "hours": "7.5"},
            headers={"HX-Request": "true"},
        )

        # Should return 200 with partial content or refresh header
        assert response.status_code == 200
        # Check for HX-Refresh header (full page refresh) or partial HTML
        has_refresh = response.headers.get("HX-Refresh") == "true"
        has_partial = b"<" in response.data  # Contains HTML
        assert has_refresh or has_partial

    def test_positive_feedback_displayed(self, client, app, year_config_with_plans):
        """Entry submission shows positive feedback message."""
        response = client.post(
            "/entries/",
            data={"date": "2025-02-05", "hours": "8.0"},
            headers={"HX-Request": "true"},
        )

        # Response should contain encouraging feedback
        response_text = response.data.decode("utf-8").lower()
        # Look for any positive words
        positive_words = ["great", "excellent", "good", "nice", "logged", "saved"]
        has_positive = any(word in response_text for word in positive_words)
        # Either has positive feedback or triggers refresh (which shows flash)
        has_refresh = response.headers.get("HX-Refresh") == "true"
        assert has_positive or has_refresh
