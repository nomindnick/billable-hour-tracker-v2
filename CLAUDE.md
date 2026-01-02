# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Billable Hours Planner - a local web app for attorneys to plan and track annual billable hour requirements (typically 1,800 hours). Features three concurrent billing plans (Firm Requirements, Optimistic, Realistic), dynamic daily targets, and catch-up sprints.

## Commands

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run development server
python run.py

# Initialize database
flask init-db

# Run tests
pytest tests/
```

## Architecture

**Stack:** Flask + SQLAlchemy + SQLite + HTMX + Tailwind CSS (CDN)

**Application Factory:** `app/__init__.py` - creates Flask app with `create_app(config_name)`

**Blueprints:**
- `routes/dashboard.py` - Main daily interface (`/`)
- `routes/setup.py` - Year configuration wizard (`/setup/*`)
- `routes/entries.py` - Daily hour logging (`/entries/*`)

**Services (business logic):**
- `services/planner.py` - Monthly target distribution algorithm
- `services/calculator.py` - Dynamic daily target calculations

**Key Algorithm Constraints:**
- Daily targets should stay near 7.5 hours, never exceed 9.5 hours
- Intensity weights: normal=1.0, light=0.75, very_light=0.5
- "Behind" thresholds: >5 hours = slightly behind, >15 hours = catch-up recommended

## Implementation Status

See `IMPLEMENTATION_PLAN.md` for sprint-by-sprint tasks. Check sprint checkboxes and "Sprint Update" sections for current progress.

## Code Style

- Type hints throughout
- Docstrings for all functions
- Clean, well-commented code (target audience: Python beginner learning the codebase)
- Flask best practices: blueprints, application factory pattern
- HTMX for dynamic updates without complex JavaScript
