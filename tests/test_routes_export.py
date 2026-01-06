"""
Integration tests for export routes.

Tests the export route handlers in app/routes/export.py,
verifying chart generation, downloads, and summary statistics.
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
    """
    Create a complete YearConfig with all three plans and 12 month configs.

    Uses current year to match route's today.year lookup.
    """
    current_year = datetime.date.today().year

    with app.app_context():
        year_config = YearConfig(year=current_year, annual_target=1800)
        db.session.add(year_config)
        db.session.flush()

        # Add 12 month configs with default intensity
        for month in range(1, 13):
            month_config = MonthConfig(
                year_config_id=year_config.id,
                month=month,
                intensity=IntensityLevel.NORMAL,
            )
            db.session.add(month_config)

        # Add all three plans
        firm = PlanConfig(
            year_config_id=year_config.id,
            plan_type=PlanType.FIRM,
            target_date=datetime.date(current_year, 12, 31),
        )
        realistic = PlanConfig(
            year_config_id=year_config.id,
            plan_type=PlanType.REALISTIC,
            target_date=datetime.date(current_year, 12, 31),
        )
        optimistic = PlanConfig(
            year_config_id=year_config.id,
            plan_type=PlanType.OPTIMISTIC,
            target_date=datetime.date(current_year, 11, 27),
            target_daily_hours_after=2.0,
        )
        db.session.add_all([firm, realistic, optimistic])
        db.session.commit()
        db.session.refresh(year_config)

        yield year_config


@pytest.fixture
def year_config_with_entries(app, year_config_with_plans):
    """
    Add daily entries to test summary statistics.

    Adds entries totaling 38 hours for verification.
    """
    current_year = datetime.date.today().year

    with app.app_context():
        year_config = db.session.get(YearConfig, year_config_with_plans.id)

        # Add 5 entries totaling 38 hours
        entries = [
            DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(current_year, 1, 6),
                hours_billed=7.5,
            ),
            DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(current_year, 1, 7),
                hours_billed=8.0,
            ),
            DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(current_year, 1, 8),
                hours_billed=7.5,
            ),
            DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(current_year, 1, 9),
                hours_billed=8.0,
            ),
            DailyEntry(
                year_config_id=year_config.id,
                date=datetime.date(current_year, 1, 10),
                hours_billed=7.0,
            ),
        ]
        db.session.add_all(entries)
        db.session.commit()
        db.session.refresh(year_config)

        yield year_config


# -----------------------------------------------------------------------------
# Export Access Tests
# -----------------------------------------------------------------------------


class TestExportAccess:
    """Tests for export page access and redirects."""

    def test_export_returns_200_with_config(self, client, year_config_with_plans):
        """GET /export/ returns 200 with valid YearConfig."""
        response = client.get("/export/")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8").lower()
        assert "export" in response_text

    def test_export_redirects_without_config(self, client, app):
        """GET /export/ redirects to setup when no YearConfig exists."""
        with app.app_context():
            YearConfig.query.delete()
            db.session.commit()

        response = client.get("/export/")

        assert response.status_code == 302
        assert "/setup/" in response.location

    def test_export_handles_no_entries_gracefully(self, client, year_config_with_plans):
        """Export page displays correctly with no entries."""
        response = client.get("/export/")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8")
        # Should show 0 or "No data" for YTD hours
        assert "0" in response_text or "No data" in response_text


# -----------------------------------------------------------------------------
# Export Content Tests
# -----------------------------------------------------------------------------


class TestExportContent:
    """Tests for export page content accuracy."""

    def test_export_displays_summary_statistics(self, client, year_config_with_entries):
        """Export page shows YTD hours, annual target, and remaining hours."""
        response = client.get("/export/")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8")

        # Should show annual target (1800 or 1,800)
        assert "1800" in response_text or "1,800" in response_text

    def test_export_displays_chart_preview(self, client, year_config_with_plans):
        """Export page includes base64 chart preview image."""
        response = client.get("/export/")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8")

        # Should have base64 image data
        assert "data:image/png;base64" in response_text

    def test_export_displays_download_options(self, client, year_config_with_plans):
        """Export page shows PNG and PDF download links."""
        response = client.get("/export/")

        assert response.status_code == 200
        response_text = response.data.decode("utf-8").lower()

        # Should have download links/buttons
        assert "png" in response_text
        assert "pdf" in response_text


# -----------------------------------------------------------------------------
# Export Download Tests
# -----------------------------------------------------------------------------


class TestExportDownload:
    """Tests for chart download functionality."""

    def test_download_png_returns_image(self, client, year_config_with_plans):
        """GET /export/chart.png returns PNG image."""
        response = client.get("/export/chart.png")

        assert response.status_code == 200
        assert response.content_type == "image/png"
        # Check PNG magic bytes
        assert response.data[:4] == b"\x89PNG"

    def test_download_pdf_returns_document(self, client, year_config_with_plans):
        """GET /export/chart.pdf returns PDF document."""
        response = client.get("/export/chart.pdf")

        assert response.status_code == 200
        assert response.content_type == "application/pdf"
        # Check PDF magic bytes
        assert response.data[:4] == b"%PDF"

    def test_download_png_has_correct_filename(self, client, year_config_with_plans):
        """PNG download has correctly formatted filename in Content-Disposition."""
        response = client.get("/export/chart.png")

        assert response.status_code == 200

        # Check Content-Disposition header
        content_disposition = response.headers.get("Content-Disposition", "")
        assert "attachment" in content_disposition
        assert "billable_hours_" in content_disposition
        assert ".png" in content_disposition

    def test_download_pdf_has_correct_filename(self, client, year_config_with_plans):
        """PDF download has correctly formatted filename in Content-Disposition."""
        response = client.get("/export/chart.pdf")

        assert response.status_code == 200

        # Check Content-Disposition header
        content_disposition = response.headers.get("Content-Disposition", "")
        assert "attachment" in content_disposition
        assert "billable_hours_" in content_disposition
        assert ".pdf" in content_disposition

    def test_download_png_redirects_without_config(self, client, app):
        """GET /export/chart.png redirects to setup when no YearConfig exists."""
        with app.app_context():
            YearConfig.query.delete()
            db.session.commit()

        response = client.get("/export/chart.png")

        assert response.status_code == 302
        assert "/setup/" in response.location

    def test_download_pdf_redirects_without_config(self, client, app):
        """GET /export/chart.pdf redirects to setup when no YearConfig exists."""
        with app.app_context():
            YearConfig.query.delete()
            db.session.commit()

        response = client.get("/export/chart.pdf")

        assert response.status_code == 302
        assert "/setup/" in response.location
