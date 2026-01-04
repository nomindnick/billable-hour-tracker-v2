"""
Billable Hours Planner - Application Factory

This module contains the Flask application factory that creates and configures
the application instance. Using the factory pattern allows for easy testing
and multiple configurations.
"""

from flask import Flask, render_template
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
    from app.routes.catchup import catchup_bp
    from app.routes.export import export_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(setup_bp, url_prefix='/setup')
    app.register_blueprint(entries_bp, url_prefix='/entries')
    app.register_blueprint(views_bp)  # No prefix - routes at /monthly, /history
    app.register_blueprint(catchup_bp, url_prefix='/catchup')
    app.register_blueprint(export_bp, url_prefix='/export')

    # Register CLI commands
    register_commands(app)

    # Register error handlers
    register_error_handlers(app)

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


def register_error_handlers(app: Flask) -> None:
    """
    Register custom error handlers for the application.

    These provide friendly error pages when things go wrong, maintaining
    the app's supportive tone even when errors occur.

    Args:
        app: The Flask application instance
    """
    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 Not Found errors with a friendly page."""
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 Internal Server errors with a friendly page."""
        # Roll back any failed database transaction
        db.session.rollback()
        return render_template('500.html'), 500
