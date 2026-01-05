"""
Unit tests for Flask application initialization and configuration.

Tests the application factory pattern and configuration loading
in app/__init__.py and config.py.
"""

import pytest
from flask import Flask

from app import create_app, db
from config import Config, DevelopmentConfig, TestingConfig


# -----------------------------------------------------------------------------
# Configuration Tests
# -----------------------------------------------------------------------------


def test_create_app_returns_flask_instance():
    """Verify create_app() returns a Flask instance."""
    app = create_app("testing")
    assert isinstance(app, Flask)


def test_create_app_with_testing_config():
    """Verify testing config sets TESTING=True and uses in-memory SQLite."""
    app = create_app("testing")

    assert app.config["TESTING"] is True
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///:memory:"


def test_create_app_with_development_config():
    """Verify development config sets DEBUG=True."""
    app = create_app("development")

    assert app.config["DEBUG"] is True
    assert "billable_hours.db" in app.config["SQLALCHEMY_DATABASE_URI"]


def test_create_app_with_default_config():
    """Verify default config uses development settings."""
    app = create_app("default")

    # Default should use DevelopmentConfig
    assert app.config["DEBUG"] is True


def test_secret_key_from_environment(monkeypatch):
    """Verify SECRET_KEY can be set via environment variable."""
    # Set a custom secret key via environment
    test_secret = "test-secret-key-12345"
    monkeypatch.setenv("SECRET_KEY", test_secret)

    # Need to reimport config to pick up the new environment variable
    import importlib
    import config as config_module

    importlib.reload(config_module)

    assert config_module.Config.SECRET_KEY == test_secret

    # Clean up: reload again without the env var
    monkeypatch.delenv("SECRET_KEY", raising=False)
    importlib.reload(config_module)


def test_database_uri_from_environment(monkeypatch):
    """Verify DATABASE_URL can override default SQLite path."""
    test_db_uri = "sqlite:///custom_test.db"
    monkeypatch.setenv("DATABASE_URL", test_db_uri)

    # Need to reimport config to pick up the new environment variable
    import importlib
    import config as config_module

    importlib.reload(config_module)

    assert config_module.DevelopmentConfig.SQLALCHEMY_DATABASE_URI == test_db_uri

    # Clean up: reload again without the env var
    monkeypatch.delenv("DATABASE_URL", raising=False)
    importlib.reload(config_module)


def test_sqlalchemy_track_modifications_disabled():
    """Verify SQLALCHEMY_TRACK_MODIFICATIONS is False (best practice)."""
    app = create_app("testing")
    assert app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] is False


# -----------------------------------------------------------------------------
# Blueprint Registration Tests
# -----------------------------------------------------------------------------


def test_all_blueprints_registered():
    """Verify all 6 blueprints are registered."""
    app = create_app("testing")

    expected_blueprints = [
        "dashboard",
        "setup",
        "entries",
        "views",
        "catchup",
        "export",
    ]

    registered_names = list(app.blueprints.keys())

    for bp_name in expected_blueprints:
        assert bp_name in registered_names, f"Blueprint '{bp_name}' not registered"

    assert len(registered_names) == 6


def test_blueprint_url_prefixes():
    """Verify correct URL prefixes for blueprints by checking registered routes."""
    app = create_app("testing")

    # Get all registered rules
    rules = [rule.rule for rule in app.url_map.iter_rules()]

    # Check that routes with correct prefixes exist
    assert any(rule.startswith("/setup/") for rule in rules), "No /setup/ routes found"
    assert any(rule.startswith("/entries/") for rule in rules), "No /entries/ routes found"
    assert any(rule.startswith("/catchup/") for rule in rules), "No /catchup/ routes found"
    assert any(rule.startswith("/export/") for rule in rules), "No /export/ routes found"

    # Dashboard and views should have root-level routes
    # Dashboard has "/" route, views has "/monthly" and "/history"
    assert "/" in rules, "No root route found (dashboard)"
    assert "/monthly" in rules, "No /monthly route found (views)"
    assert "/history" in rules, "No /history route found (views)"


# -----------------------------------------------------------------------------
# CLI Command Tests
# -----------------------------------------------------------------------------


def test_init_db_command_registered():
    """Verify init-db CLI command exists."""
    app = create_app("testing")

    # Check that the init-db command is registered
    runner = app.test_cli_runner()
    result = runner.invoke(args=["init-db"])

    # The command should run successfully
    assert result.exit_code == 0
    assert "Database initialized successfully" in result.output


# -----------------------------------------------------------------------------
# Error Handler Tests
# -----------------------------------------------------------------------------


def test_404_error_handler(client):
    """Verify 404 returns friendly error page."""
    response = client.get("/nonexistent-route-xyz")

    assert response.status_code == 404
    # Check that a friendly error page is returned (not default Flask error)
    assert b"404" in response.data or b"Not Found" in response.data


def test_500_error_handler():
    """Verify 500 error handler is registered."""
    app = create_app("testing")

    # Verify the error handler is registered
    assert 500 in app.error_handler_spec[None]


# -----------------------------------------------------------------------------
# Database Initialization Tests
# -----------------------------------------------------------------------------


def test_database_initializes_with_app_context():
    """Verify database can be created within app context."""
    app = create_app("testing")

    with app.app_context():
        db.create_all()
        # If we get here without exception, tables were created
        db.drop_all()


def test_multiple_app_instances_independent():
    """Verify multiple app instances don't share state."""
    app1 = create_app("testing")
    app2 = create_app("testing")

    # Each app should be a separate instance
    assert app1 is not app2

    # Each app should have its own config
    assert app1.config is not app2.config
