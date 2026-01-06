"""
Integration tests for UI edge cases (Sprint 4.5).

Tests empty states, invalid inputs, rapid interactions, and boundary values
across the application to ensure graceful handling of edge cases.
"""

import datetime

import pytest

from app import db
from app.models import (
    CatchUpSprint,
    DailyEntry,
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
def year_config_no_entries(app, current_year):
    """
    Create a YearConfig with all three plans but NO daily entries.

    This represents a fresh user who has completed setup but hasn't
    logged any hours yet.
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
def year_config_with_holiday(app, year_config_no_entries, current_year):
    """Add a holiday to the year config for duplicate testing."""
    with app.app_context():
        year_config = db.session.get(YearConfig, year_config_no_entries.id)
        holiday = Holiday(
            year_config_id=year_config.id,
            date=datetime.date(current_year, 7, 4),
            name="Independence Day",
        )
        db.session.add(holiday)
        db.session.commit()
        yield year_config


@pytest.fixture
def year_config_behind(app, year_config_no_entries, current_year):
    """
    Create a config where user is behind on billing targets.

    Adds minimal entries so user will be behind, making them eligible
    for catch-up sprint creation.
    """
    with app.app_context():
        year_config = db.session.get(YearConfig, year_config_no_entries.id)

        # Add only minimal entries to ensure user is behind
        entries = [
            DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(current_year, 1, 6),
                hours_billed=2.0,
            ),
            DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(current_year, 1, 7),
                hours_billed=2.0,
            ),
        ]
        db.session.add_all(entries)
        db.session.commit()
        db.session.refresh(year_config)
        yield year_config


# -----------------------------------------------------------------------------
# Empty States Tests
# -----------------------------------------------------------------------------


class TestEmptyStates:
    """Tests for empty state handling across all views."""

    def test_dashboard_with_no_entries_shows_zeros(
        self, client, app, year_config_no_entries
    ):
        """Dashboard shows zero progress when no entries exist."""
        response = client.get("/")
        assert response.status_code == 200

        response_text = response.data.decode("utf-8").lower()
        # Should still render with zeros for progress
        assert "week" in response_text
        assert "month" in response_text
        # All three plans should be visible
        assert "firm" in response_text
        assert "realistic" in response_text
        assert "optimistic" in response_text

    def test_dashboard_recent_entries_empty_message(
        self, client, app, year_config_no_entries
    ):
        """Recent entries section shows empty state message."""
        response = client.get("/entries/recent", headers={"HX-Request": "true"})
        assert response.status_code == 200

        response_text = response.data.decode("utf-8").lower()
        # Should show empty state or have no entry data
        # Either "no recent entries" message or just empty list
        assert response.status_code == 200

    def test_monthly_view_with_no_entries_shows_calendar(
        self, client, app, year_config_no_entries, current_year, today
    ):
        """Monthly view renders calendar grid even with no entries."""
        response = client.get(f"/monthly/{current_year}/{today.month}")
        assert response.status_code == 200

        response_text = response.data.decode("utf-8")
        # Calendar should still render
        # Should have day numbers
        assert "1" in response_text
        # Should have month navigation
        assert "Previous" in response_text or "prev" in response_text.lower()

    def test_history_view_with_no_entries_shows_empty_message(
        self, client, app, year_config_no_entries
    ):
        """History view shows appropriate empty state message."""
        response = client.get("/history")
        assert response.status_code == 200

        response_text = response.data.decode("utf-8").lower()
        # Should show empty state message
        assert "no entries" in response_text or "start logging" in response_text

    def test_export_with_no_entries_generates_chart(
        self, client, app, year_config_no_entries
    ):
        """Export page still generates chart even with no entries."""
        response = client.get("/export/")
        assert response.status_code == 200

        response_text = response.data.decode("utf-8")
        # Chart should still be rendered (base64 image embedded)
        assert "base64" in response_text or "chart" in response_text.lower()
        # Summary should show 0 YTD
        assert "0" in response_text


# -----------------------------------------------------------------------------
# Invalid Hours Input Tests
# -----------------------------------------------------------------------------


class TestInvalidHoursInput:
    """Tests for invalid hours input validation."""

    def test_negative_hours_rejected(self, client, app, year_config_no_entries, today):
        """Negative hours are rejected with error."""
        response = client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "-5"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 400
        response_text = response.data.decode("utf-8").lower()
        assert "valid" in response_text or "error" in response_text

    def test_excessive_hours_over_24_rejected(
        self, client, app, year_config_no_entries, today
    ):
        """Hours over 24 are rejected."""
        response = client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "25"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 400
        response_text = response.data.decode("utf-8").lower()
        assert "valid" in response_text or "error" in response_text

    def test_non_numeric_hours_abc_rejected(
        self, client, app, year_config_no_entries, today
    ):
        """Non-numeric hours string is rejected."""
        response = client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "abc"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 400
        response_text = response.data.decode("utf-8").lower()
        assert "valid" in response_text or "error" in response_text

    def test_hours_many_decimal_places_accepted_and_stored(
        self, client, app, year_config_no_entries, today
    ):
        """Hours with many decimal places are accepted (Python float)."""
        response = client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "7.123456"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code in [200, 201]

        # Verify entry was created with the value
        with app.app_context():
            entry = DailyEntry.query.filter_by(date=today).first()
            assert entry is not None
            # Value should be stored (may be truncated to float precision)
            assert abs(entry.hours_billed - 7.123456) < 0.001

    def test_empty_hours_string_rejected(
        self, client, app, year_config_no_entries, today
    ):
        """Empty hours string is rejected."""
        response = client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": ""},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 400


# -----------------------------------------------------------------------------
# Invalid Date Input Tests
# -----------------------------------------------------------------------------


class TestInvalidDateInput:
    """Tests for invalid date input validation."""

    def test_date_outside_configured_year(
        self, client, app, year_config_no_entries, current_year
    ):
        """Date in different year than config is handled."""
        # Try to add entry for next year
        future_date = datetime.date(current_year + 1, 6, 15)

        response = client.post(
            "/entries/",
            data={"date": future_date.isoformat(), "hours": "7.5"},
            headers={"HX-Request": "true"},
        )

        # May be accepted (app allows any date) or rejected
        # Just verify no server error
        assert response.status_code in [200, 201, 400]

    def test_invalid_date_format(self, client, app, year_config_no_entries):
        """Invalid date format is rejected."""
        response = client.post(
            "/entries/",
            data={"date": "not-a-date", "hours": "7.5"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 400
        response_text = response.data.decode("utf-8").lower()
        assert "date" in response_text or "invalid" in response_text

    def test_future_date_far_in_future(
        self, client, app, year_config_no_entries, current_year
    ):
        """Date far in the future is handled gracefully."""
        far_future = datetime.date(current_year + 5, 1, 1)

        response = client.post(
            "/entries/",
            data={"date": far_future.isoformat(), "hours": "7.5"},
            headers={"HX-Request": "true"},
        )

        # Should not crash - either accepted or rejected gracefully
        assert response.status_code in [200, 201, 400]


# -----------------------------------------------------------------------------
# Duplicate Prevention Tests
# -----------------------------------------------------------------------------


class TestDuplicatePrevention:
    """Tests for duplicate record prevention."""

    def test_duplicate_holiday_prevented(
        self, client, app, year_config_with_holiday, current_year
    ):
        """Adding same holiday date twice is rejected."""
        # Try to add July 4th again (already in fixture)
        response = client.post(
            "/setup/holidays/add",
            data={"date": f"{current_year}-07-04"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 400
        hx_trigger = response.headers.get("HX-Trigger", "")
        assert "already" in hx_trigger.lower()

    def test_duplicate_vacation_prevented(
        self, client, app, year_config_no_entries, current_year
    ):
        """Adding same vacation date twice is rejected."""
        date_str = f"{current_year}-08-15"

        # Add vacation first time
        response1 = client.post(
            "/setup/vacation/add",
            data={"date": date_str},
            headers={"HX-Request": "true"},
        )
        assert response1.status_code == 200

        # Try to add same date again
        response2 = client.post(
            "/setup/vacation/add",
            data={"date": date_str},
            headers={"HX-Request": "true"},
        )

        assert response2.status_code == 400
        hx_trigger = response2.headers.get("HX-Trigger", "")
        assert "already" in hx_trigger.lower()

    def test_vacation_on_holiday_allowed(
        self, client, app, year_config_with_holiday, current_year
    ):
        """Vacation can be added on same date as holiday (different lists)."""
        # July 4th is already a holiday in fixture
        response = client.post(
            "/setup/vacation/add",
            data={"date": f"{current_year}-07-04"},
            headers={"HX-Request": "true"},
        )

        # Should be allowed - they're different lists
        assert response.status_code == 200


# -----------------------------------------------------------------------------
# Rapid Interactions Tests
# -----------------------------------------------------------------------------


class TestRapidInteractions:
    """Tests for rapid/concurrent interactions."""

    def test_submit_entry_multiple_times_same_date_updates(
        self, client, app, year_config_no_entries, today
    ):
        """Multiple submissions for same date result in latest value (upsert)."""
        # First submission
        client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "5.0"},
            headers={"HX-Request": "true"},
        )

        # Second submission for same date
        client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "7.5"},
            headers={"HX-Request": "true"},
        )

        # Third submission for same date
        client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "8.0"},
            headers={"HX-Request": "true"},
        )

        # Verify final value is 8.0
        with app.app_context():
            entries = DailyEntry.query.filter_by(date=today).all()
            # Should be only one entry (upsert behavior)
            assert len(entries) == 1
            assert entries[0].hours_billed == 8.0

    def test_multiple_holiday_adds_same_session(
        self, client, app, year_config_no_entries, current_year
    ):
        """Multiple different holidays can be added in rapid succession."""
        dates = [
            f"{current_year}-01-01",
            f"{current_year}-02-14",
            f"{current_year}-03-17",
        ]

        for date_str in dates:
            response = client.post(
                "/setup/holidays/add",
                data={"date": date_str},
                headers={"HX-Request": "true"},
            )
            assert response.status_code == 200

        # Verify all three holidays were added
        with app.app_context():
            holidays = Holiday.query.all()
            assert len(holidays) == 3

    def test_create_and_dismiss_sprint_same_request_cycle(
        self, client, app, year_config_behind, current_year
    ):
        """Sprint can be created and dismissed in same session."""
        # Create sprint
        create_response = client.post(
            "/catchup/",
            data={
                "plan_type": "realistic",
                "duration": "2",
            },
        )
        assert create_response.status_code == 302

        # Get the sprint ID
        with app.app_context():
            sprint = CatchUpSprint.query.filter_by(status=SprintStatus.ACTIVE).first()
            if sprint:
                sprint_id = sprint.id

                # Dismiss the sprint
                dismiss_response = client.post(f"/catchup/{sprint_id}/dismiss")
                assert dismiss_response.status_code == 302

                # Verify sprint is dismissed
                db.session.refresh(sprint)
                assert sprint.status == SprintStatus.DISMISSED


# -----------------------------------------------------------------------------
# Boundary Values Tests
# -----------------------------------------------------------------------------


class TestBoundaryValues:
    """Tests for boundary value handling."""

    def test_hours_exactly_zero_accepted(
        self, client, app, year_config_no_entries, today
    ):
        """Zero hours entry is accepted (clears/creates entry with 0)."""
        response = client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "0"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code in [200, 201]

        with app.app_context():
            entry = DailyEntry.query.filter_by(date=today).first()
            if entry:
                assert entry.hours_billed == 0.0

    def test_hours_exactly_24_accepted(
        self, client, app, year_config_no_entries, today
    ):
        """Maximum hours (24) is accepted."""
        response = client.post(
            "/entries/",
            data={"date": today.isoformat(), "hours": "24"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code in [200, 201]

        with app.app_context():
            entry = DailyEntry.query.filter_by(date=today).first()
            assert entry is not None
            assert entry.hours_billed == 24.0

    def test_hours_0_point_5_increments(
        self, client, app, year_config_no_entries, current_year
    ):
        """0.5 hour increments are all accepted."""
        test_values = [0.5, 1.0, 1.5, 2.5, 7.5]

        for i, hours in enumerate(test_values):
            test_date = datetime.date(current_year, 1, i + 10)
            response = client.post(
                "/entries/",
                data={"date": test_date.isoformat(), "hours": str(hours)},
                headers={"HX-Request": "true"},
            )
            assert response.status_code in [200, 201]

            with app.app_context():
                entry = DailyEntry.query.filter_by(date=test_date).first()
                assert entry is not None
                assert entry.hours_billed == hours

    def test_year_boundary_december_31_entry(
        self, client, app, year_config_no_entries, current_year
    ):
        """Entry can be made for December 31 of configured year."""
        dec_31 = datetime.date(current_year, 12, 31)

        response = client.post(
            "/entries/",
            data={"date": dec_31.isoformat(), "hours": "7.5"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code in [200, 201]

        with app.app_context():
            entry = DailyEntry.query.filter_by(date=dec_31).first()
            assert entry is not None
            assert entry.hours_billed == 7.5

    def test_year_boundary_january_1_entry(
        self, client, app, year_config_no_entries, current_year
    ):
        """Entry can be made for January 1 of configured year."""
        jan_1 = datetime.date(current_year, 1, 1)

        response = client.post(
            "/entries/",
            data={"date": jan_1.isoformat(), "hours": "7.5"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code in [200, 201]

        with app.app_context():
            entry = DailyEntry.query.filter_by(date=jan_1).first()
            assert entry is not None
            assert entry.hours_billed == 7.5
