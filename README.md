# Billable Hours Planner

A local web application for attorneys to plan and track annual billable hour requirements. Designed to help you create realistic billing plans, track daily progress, and recover from shortfalls without creating a demoralizing experience.

## Features

- **Three-Plan System**: Track against Firm Requirements (fixed 150/month), Optimistic (front-loaded for lighter holidays), and Realistic (balanced with intensity preferences) plans simultaneously
- **Dynamic Daily Targets**: Targets automatically recalculate based on actual performance, distributing shortfalls across remaining workdays
- **Smart Workday Calculation**: Automatically excludes weekends, holidays, and vacation days from calculations
- **Catch-Up Sprints**: When you fall behind, create focused sprints with achievable daily targets (including optional weekend hours)
- **Monthly Intensity Settings**: Flag months as "normal," "light," or "very light" to match your expected billing patterns
- **Professional Exports**: Generate PDF or PNG charts suitable for meetings with firm leadership
- **Mid-Year Start**: Start tracking any time during the year by entering historical hours

## Quick Start

### Prerequisites

- Python 3.11 or higher
- pip (Python package manager)

### Installation

```bash
# Clone or download the project
cd billable-hour-tracker-v2

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Initialize the database
flask init-db

# Run the development server
python run.py
```

The application will be available at `http://localhost:5000`.

## Usage Guide

### Initial Setup

1. **Year Configuration**: Select your billing year and annual target (default: 1,800 hours)
2. **Mid-Year Entry** (optional): If starting after January, enter hours already billed
3. **Holidays**: Add firm-recognized holidays (use "Add Common US Holidays" for quick setup)
4. **Vacation Days**: Add planned time off
5. **Plans & Intensity**: Configure your Optimistic plan's target date and set monthly intensity preferences

### Daily Use

1. Open the dashboard at `http://localhost:5000`
2. See today's target for each plan (Realistic plan is emphasized)
3. Enter your hours billed for the day
4. View your weekly and monthly progress

**Keyboard Shortcut**: Press `e` to quickly focus the hours entry field.

### Catch-Up Sprints

When you fall behind:
1. Click "Start a Catch-Up Sprint" on the dashboard
2. Choose which plan to catch up to (Realistic or Optimistic)
3. Select a timeframe (1-6 weeks)
4. Optionally include weekend billing (2-4 hours)
5. Preview and accept the sprint

During a sprint:
- Sprint progress appears on the dashboard
- If you fall behind the sprint, you'll see suggestions to revise
- Complete, revise, or dismiss the sprint as circumstances change

### Export

Generate professional charts showing all three plans' trajectories plus your actual hours:
1. Navigate to Export in the menu
2. Review the summary statistics
3. Download as PNG or PDF

## Configuration

Configuration is managed in `config.py`. Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `SECRET_KEY` | Random | Session security key (set via `SECRET_KEY` env var in production) |
| `SQLALCHEMY_DATABASE_URI` | `sqlite:///billable_hours.db` | Database location |

### Algorithm Constants

These are set in the services and match the spec:

- **Daily target cap**: 9.5 hours (plans won't exceed this)
- **Ideal daily target**: ~7.5 hours
- **Intensity weights**: Normal=1.0, Light=0.75, Very Light=0.5
- **"Behind" thresholds**: >5 hours = slightly behind, >15 hours = catch-up recommended

## Project Structure

```
billable-hour-tracker-v2/
├── app/
│   ├── __init__.py          # Application factory
│   ├── models.py             # SQLAlchemy models (YearConfig, Holiday, etc.)
│   ├── routes/
│   │   ├── dashboard.py      # Main daily interface
│   │   ├── setup.py          # Year configuration wizard
│   │   ├── entries.py        # Daily hour logging
│   │   ├── views.py          # Monthly/history views
│   │   ├── catchup.py        # Catch-up sprint management
│   │   └── export.py         # Chart generation
│   ├── services/
│   │   ├── planner.py        # Monthly target distribution algorithm
│   │   ├── calculator.py     # Dynamic daily calculations
│   │   ├── calendar_utils.py # Workday calculations
│   │   ├── catchup.py        # Sprint logic
│   │   └── export.py         # Chart generation
│   ├── templates/            # Jinja2 HTML templates
│   └── static/               # CSS, favicon
├── tests/                    # pytest test suite
├── config.py                 # Flask configuration
├── run.py                    # Entry point
└── requirements.txt          # Python dependencies
```

## Development

### Running Tests

```bash
# Activate virtual environment
source venv/bin/activate

# Run all tests
pytest tests/

# Run with verbose output
pytest tests/ -v

# Run specific test file
pytest tests/test_planner.py
```

### Creating Sample Data

For demo or testing purposes:

```bash
python create_sample_data.py
```

This creates a year configuration with holidays, sample entries, and an active catch-up sprint.

## Technical Stack

- **Backend**: Flask + SQLAlchemy + SQLite
- **Frontend**: Jinja2 templates + HTMX + Tailwind CSS (via CDN)
- **Charts**: Chart.js (dashboard) + Matplotlib (exports)

## License

Personal project - all rights reserved.
