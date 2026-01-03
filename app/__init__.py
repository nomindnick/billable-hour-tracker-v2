"""
Billable Hours Planner - Application Factory

This module contains the Flask application factory that creates and configures
the application instance. Using the factory pattern allows for easy testing
and multiple configurations.
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from config import config


# Initialize SQLAlchemy without binding to a specific app
# This will be initialized with the app in create_app()
db = SQLAlchemy()


def create_app(config_name: str = 'default') -> Flask:
    """
    Create and configure the Flask application.

    This is the application factory function. It creates a new Flask app
    instance, configures it, initializes extensions, and registers blueprints.

    Args:
        config_name: The configuration to use ('development', 'testing', or 'default')

    Returns:
        A configured Flask application instance
    """
    # Create the Flask app instance
    app = Flask(__name__)

    # Load configuration from config.py
    app.config.from_object(config[config_name])

    # Initialize Flask extensions with this app
    db.init_app(app)

    # Register blueprints (route handlers)
    from app.routes.dashboard import dashboard_bp
    from app.routes.setup import setup_bp
    from app.routes.entries import entries_bp
    from app.routes.views import views_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(setup_bp, url_prefix='/setup')
    app.register_blueprint(entries_bp, url_prefix='/entries')
    app.register_blueprint(views_bp)  # No prefix - routes at /monthly, /history

    # Register CLI commands
    register_commands(app)

    return app


def register_commands(app: Flask) -> None:
    """
    Register custom CLI commands with the Flask app.

    Args:
        app: The Flask application instance
    """
    @app.cli.command('init-db')
    def init_db_command():
        """Create all database tables."""
        # Import models so SQLAlchemy knows about them before creating tables
        from app import models  # noqa: F401
        db.create_all()
        print('Database initialized successfully.')
