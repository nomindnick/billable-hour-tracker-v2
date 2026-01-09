#!/usr/bin/env python3
"""
Entry point for the Billable Hours Planner application.

Run this file to start the Flask development server:
    python run.py

The server will start on http://localhost:5000 by default.

To use a different configuration, set the FLASK_CONFIG environment variable:
    FLASK_CONFIG=testing python run.py
"""

import os

from app import create_app


# Create the application instance using the factory
# Defaults to 'development' if FLASK_CONFIG not set
config_name = os.environ.get('FLASK_CONFIG', 'development')
app = create_app(config_name)


if __name__ == '__main__':
    # Run the development server
    # Debug mode is set in the configuration
    app.run(host='127.0.0.1', port=5000)
