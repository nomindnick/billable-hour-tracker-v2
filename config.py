"""
Configuration settings for the Billable Hours Planner application.

This module contains configuration classes for different environments.
Currently only development configuration is implemented since this is
a local-only application.
"""

import os
from pathlib import Path


# Base directory of the application
BASE_DIR = Path(__file__).resolve().parent


class Config:
    """Base configuration class with settings common to all environments."""

    # Secret key for session management and CSRF protection
    # In production, this should be set via environment variable
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # SQLAlchemy settings
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(Config):
    """Development configuration with debug mode enabled."""

    DEBUG = True

    # SQLite database stored in the project directory
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f'sqlite:///{BASE_DIR / "billable_hours.db"}'


class TestingConfig(Config):
    """Testing configuration with in-memory database."""

    TESTING = True

    # Use in-memory SQLite for tests
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


# Configuration dictionary for easy selection
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
