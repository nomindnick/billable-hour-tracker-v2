"""
Shared pytest fixtures for the Billable Hours Planner test suite.

This module contains fixtures that are used across multiple test files,
eliminating duplication and ensuring consistent test setup.
"""

import pytest

from app import create_app, db


@pytest.fixture
def app():
    """
    Create a Flask application configured for testing.

    Creates a new Flask app instance with TestingConfig (in-memory SQLite),
    creates all database tables, yields the app for testing, then cleans up
    by dropping all tables.

    Yields:
        Flask: A configured Flask application instance for testing
    """
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    """
    Create a Flask test client for route testing.

    Args:
        app: The Flask application fixture

    Returns:
        FlaskClient: A test client for making requests to the app
    """
    return app.test_client()
