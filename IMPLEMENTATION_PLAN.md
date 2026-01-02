# Implementation Plan: Billable Hours Planner

> **Reference:** See [SPEC.md](./SPEC.md) for full project context, architecture decisions, and feature details.

## Overview

This implementation follows a progressive approach: establish the foundation, build the core planning algorithm, implement daily tracking, add the catch-up sprint feature, and finish with export and polish. Each sprint builds on the previous, with the most complex logic (planning algorithm) tackled early so the rest of the app can use it.

**Estimated Total Time:** 14-18 hours across 10 sprints

---

## Phase 1: Foundation & Project Setup

**Goal:** A running Flask application with database models and basic project structure. By the end of this phase, you can start the server and see a placeholder page.

### Sprint 1.1: Project Scaffolding
**Estimated Time:** 1-1.5 hours

**Objective:** Set up the project structure, dependencies, and basic Flask application.

**Tasks:**
- [x] Create project directory structure:
  ```
  billable-hours/
  ├── app/
  │   ├── __init__.py          # Application factory
  │   ├── models.py            # SQLAlchemy models
  │   ├── routes/
  │   │   ├── __init__.py
  │   │   ├── dashboard.py
  │   │   ├── setup.py
  │   │   └── entries.py
  │   ├── services/
  │   │   ├── __init__.py
  │   │   ├── planner.py       # Planning algorithm
  │   │   └── calculator.py    # Daily calculations
  │   ├── templates/
  │   │   ├── base.html
  │   │   ├── dashboard.html
  │   │   └── setup/
  │   └── static/
  │       └── css/
  ├── tests/
  ├── config.py
  ├── requirements.txt
  └── run.py
  ```
- [x] Create `requirements.txt` with initial dependencies:
  - Flask
  - SQLAlchemy
  - Flask-SQLAlchemy
  - python-dateutil
- [x] Set up `config.py` with development configuration
- [x] Create application factory in `app/__init__.py`
- [x] Create `run.py` entry point
- [x] Verify app starts with `flask run` and shows a test page

**Acceptance Criteria:**
- Running `python run.py` starts a Flask development server
- Visiting `http://localhost:5000` shows a placeholder page
- Project structure matches the layout above

**Sprint Update:**
> **Completed.** Project structure created with Flask application factory pattern. All blueprints registered (dashboard, setup, entries). Configuration supports development and testing environments. Virtual environment set up with all dependencies installed.

---

### Sprint 1.2: Database Models
**Estimated Time:** 1-1.5 hours

**Objective:** Define all SQLAlchemy models and set up database initialization.

**Tasks:**
- [x] Implement `YearConfig` model with fields: id, year, annual_target, created_at, updated_at
- [x] Implement `Holiday` model with fields: id, year_config_id (FK), date, name
- [x] Implement `VacationDay` model with fields: id, year_config_id (FK), date, note
- [x] Implement `MonthConfig` model with fields: id, year_config_id (FK), month, intensity (enum)
- [x] Implement `PlanConfig` model with fields: id, year_config_id (FK), plan_type (enum), target_date, target_daily_hours_after
- [x] Implement `DailyEntry` model with fields: id, year_config_id (FK), date, hours_billed, created_at, updated_at
- [x] Implement `CatchUpSprint` model with fields per SPEC
- [x] Create database initialization command (`flask init-db`)
- [x] Add proper indexes (date fields, foreign keys)
- [x] Test that models can be created and queried

**Acceptance Criteria:**
- All models defined with proper relationships
- `flask init-db` creates the SQLite database file
- Can create and query records in Python shell

**Sprint Update:**
> **Completed 2026-01-02.** All 7 models implemented using SQLAlchemy 2.0 style with `Mapped` type hints and `mapped_column()`. Three enum types created: `IntensityLevel`, `PlanType`, `SprintStatus`. All models have bidirectional relationships with cascade delete. Indexes added for date lookups and frequently queried columns. Unique constraints on (year_config_id, date) for entries and (year_config_id, month) for month configs. Fixed the `init-db` command to import models before calling `db.create_all()`. All tests pass: models can be created, queried, and cascade delete works correctly.

---

## Phase 2: Planning Algorithm

**Goal:** The core algorithm that distributes annual hours across months and calculates daily targets. This is the brain of the application.

### Sprint 2.1: Workday Calculator
**Estimated Time:** 1.5 hours

**Objective:** Build utilities for calculating workdays, accounting for weekends, holidays, and vacation.

**Tasks:**
- [x] Create `services/calendar_utils.py`
- [x] Implement `get_workdays_in_month(year, month, holidays, vacation_days)` → list of dates
- [x] Implement `get_workdays_in_range(start_date, end_date, holidays, vacation_days)` → list of dates
- [x] Implement `is_workday(date, holidays, vacation_days)` → boolean
- [x] Implement `get_remaining_workdays_in_month(from_date, holidays, vacation_days)` → list of dates
- [x] Handle edge cases: month boundaries, year boundaries
- [x] Write unit tests for all calendar functions

**Acceptance Criteria:**
- Functions correctly identify weekends as non-workdays
- Functions correctly exclude holidays and vacation days
- All unit tests pass
- Edge cases (empty months, all holidays) handled gracefully

**Sprint Update:**
> **Completed 2026-01-02.** Created `app/services/calendar_utils.py` with 4 functions: `is_workday()`, `get_workdays_in_month()`, `get_workdays_in_range()`, and `get_remaining_workdays_in_month()`. All functions use `set[datetime.date]` for O(1) holiday/vacation lookup. Functions use Python's `calendar.monthrange()` for month boundary handling. Created `tests/test_calendar_utils.py` with 40 comprehensive unit tests covering weekends, holidays, vacation days, month/year boundaries, leap years, and edge cases. All tests pass.

---

### Sprint 2.2: Monthly Distribution Algorithm
**Estimated Time:** 2 hours

**Objective:** Implement the algorithm that distributes annual target hours across months based on workdays and intensity settings.

**Tasks:**
- [x] Create `services/planner.py`
- [x] Define intensity weights: normal=1.0, light=0.75, very_light=0.5
- [x] Implement `calculate_monthly_targets(year_config)`:
  - Get workdays per month
  - Apply intensity weights to get "weighted workdays"
  - Distribute annual target proportionally
  - Return dict of {month: target_hours}
- [x] Implement `calculate_monthly_targets_for_plan(year_config, plan_config)`:
  - Handle Optimistic plan's earlier end date
  - Handle Realistic plan's standard distribution
  - Handle Firm plan's fixed 150/month baseline
- [x] Implement validation: check if any month requires >9.5 hours/day average
- [x] Write comprehensive unit tests with various scenarios:
  - Normal year with standard settings
  - Year with many holidays in one month
  - Aggressive optimistic plan
  - Very light December

**Acceptance Criteria:**
- Monthly targets sum to annual target (within rounding tolerance)
- Intensity weights correctly reduce targets for light months
- Optimistic plan correctly compresses timeline
- Validation catches impossible plans
- All unit tests pass

**Sprint Update:**
> **Completed 2026-01-02.** Implemented the full monthly distribution algorithm in `app/services/planner.py`. Key functions: `calculate_monthly_targets()` distributes hours proportionally based on weighted workdays (intensity × workday count), `calculate_monthly_targets_for_plan()` handles plan-specific logic (Firm=fixed 150/month, Realistic=full year weighted, Optimistic=compressed timeline with optional maintenance hours), `validate_plan_feasibility()` checks no month requires >9.5 hours/day. Added `PlanWarning` and `MonthlyTarget` dataclasses for structured return values. Created comprehensive test suite in `tests/test_planner.py` with 29 tests covering intensity weights, helper functions, core algorithm, plan-specific logic, validation, and integration scenarios. All 69 tests pass (40 calendar_utils + 29 planner).

---

### Sprint 2.3: Daily Target Calculator
**Estimated Time:** 1.5 hours

**Objective:** Implement the dynamic daily target calculation that adjusts based on actual hours billed.

**Tasks:**
- [x] Create `services/calculator.py`
- [x] Implement `calculate_daily_target(year_config, plan_config, date)`:
  - Get monthly target for the month
  - Get hours already billed this month
  - Get remaining workdays in month
  - Calculate: (monthly_target - hours_billed) / remaining_days
  - Cap at 9.5 hours
  - Return target and a flag if catch-up is recommended
- [x] Implement `calculate_plan_status(year_config, plan_config)`:
  - Calculate expected hours to date based on plan
  - Compare to actual hours billed
  - Return: hours_ahead_or_behind, status_label ("On track", "Slightly behind", etc.)
- [x] Implement `calculate_hours_banked(year_config, plan_config)`:
  - Sum of (actual - target) for days where actual > target
- [x] Write unit tests for daily calculations

**Acceptance Criteria:**
- Daily targets correctly recalculate based on hours billed
- Shortfalls are distributed across remaining days
- Targets never exceed 9.5 hours
- Banked hours calculated correctly
- Catch-up flag triggers when daily target would exceed 9.5

**Sprint Update:**
> **Completed 2026-01-02.** Implemented the full calculator service in `app/services/calculator.py` with 3 core functions (`calculate_daily_target()`, `calculate_plan_status()`, `calculate_hours_banked()`) and 3 helper functions (`get_hours_billed_in_month()`, `get_hours_billed_to_date()`, `get_expected_hours_to_date()`). Two dataclasses created: `DailyTargetResult` and `PlanStatus`. Status thresholds configured per spec: 5 hours for "slightly behind", 15 hours for "catch-up recommended". Daily targets capped at 9.5 hours with catch-up flag. Created `tests/test_calculator.py` with 33 unit tests covering all functions, edge cases, and integration scenarios. All 102 tests pass (40 calendar_utils + 29 planner + 33 calculator).

---

## Phase 3: Setup Flow

**Goal:** Users can configure their billing year through a multi-step setup wizard.

### Sprint 3.1: Setup UI - Year and Target
**Estimated Time:** 1.5 hours

**Objective:** Build the first step of setup: selecting year and annual target.

**Tasks:**
- [x] Create base template (`templates/base.html`) with:
  - Tailwind CSS via CDN
  - HTMX via CDN
  - Basic layout structure
  - Navigation placeholder
- [x] Create `templates/setup/year.html`:
  - Year selector (default to current year)
  - Annual target input (default 1800)
  - "Next" button
- [x] Implement routes in `routes/setup.py`:
  - GET `/setup` - show year selection
  - POST `/setup/year` - save and proceed
- [x] Create or update YearConfig on submission
- [x] Style with Tailwind for clean, modern look

**Acceptance Criteria:**
- User can select year and set annual target
- Form submits and creates/updates YearConfig
- Redirects to next step (holidays)
- Looks clean and professional

**Sprint Update:**
> **Completed 2026-01-02.** Implemented the first setup wizard step with year selection and annual target input. Base template already existed from Sprint 1.1 with Tailwind CSS v4 and HTMX v1.9.10 via CDN. Created `app/templates/setup/year.html` with a clean card-based form, 4-step progress indicator, year dropdown (current ±1 year), annual target input with validation (1000-3000 range), and quick reference info. Implemented routes in `app/routes/setup.py`: GET `/setup/` displays the form, POST `/setup/year` validates input and creates/updates YearConfig. On new config creation, also creates 12 default MonthConfig records (all NORMAL intensity) and 3 default PlanConfig records (Firm=Dec 31, Realistic=Dec 31, Optimistic=Nov 27). Added flash message support to base template and Setup nav link. Holidays route temporarily redirects to dashboard pending Sprint 3.2.

---

### Sprint 3.2: Setup UI - Holidays and Vacation
**Estimated Time:** 1.5 hours

**Objective:** Build the interface for adding holidays and vacation days.

**Tasks:**
- [x] Create `templates/setup/holidays.html`:
  - Date picker for adding holidays
  - Optional name field
  - List of added holidays with delete option
  - "Add common holidays" helper (optional but nice)
- [x] Create `templates/setup/vacation.html`:
  - Date picker or date range for vacation
  - Optional note field
  - List of vacation days with delete option
- [x] Implement HTMX interactions for add/remove without full page reload
- [x] Implement routes:
  - GET/POST `/setup/holidays`
  - GET/POST `/setup/vacation`
  - DELETE endpoints for removing dates
- [x] Validate dates are within selected year

**Acceptance Criteria:**
- User can add/remove holidays
- User can add/remove vacation days
- Changes persist to database
- UI updates dynamically (HTMX)
- Clear visual feedback on actions

**Sprint Update:**
> **Completed 2026-01-02.** Implemented holidays and vacation setup pages with full HTMX interactivity. Created templates: `holidays.html`, `vacation.html`, and partials `holiday_item.html`, `vacation_item.html` for dynamic list updates. Routes implemented: GET/POST/DELETE for both holidays and vacation days, plus "Add Common US Holidays" feature that adds 11 standard US holidays (New Year's Day, MLK Day, Presidents Day, Memorial Day, Independence Day, Labor Day, Thanksgiving, Day After Thanksgiving, Christmas Eve, Christmas Day, New Year's Eve). Progress indicator shows completed steps with green checkmarks. All dates validated to be within the configured year. Duplicate dates are prevented. Plans step added as placeholder (redirects to dashboard with info message).

---

### Sprint 3.3: Setup UI - Plans Configuration
**Estimated Time:** 1.5 hours

**Objective:** Build the interface for configuring the three plans and monthly intensity.

**Tasks:**
- [ ] Create `templates/setup/plans.html`:
  - Firm Plan: Display only (fixed 150/month)
  - Optimistic Plan: Date picker for target completion date OR "X hours/day after date" option
  - Realistic Plan: Toggle for "lighter December" preset or custom intensity
- [ ] Create `templates/setup/intensity.html`:
  - 12-month grid showing each month
  - Dropdown or toggle for each month's intensity (normal/light/very_light)
  - Presets: "Standard", "Light December", "Light Nov-Dec"
- [ ] Implement routes for saving plan configurations
- [ ] Run validation after setup complete:
  - Call planning algorithm
  - Check for impossible configurations
  - Show warnings if any month requires >9.5 hours/day
- [ ] Create `templates/setup/complete.html` - summary and "Go to Dashboard" button

**Acceptance Criteria:**
- User can configure all three plans
- Monthly intensity is adjustable
- Validation runs and shows warnings for impossible plans
- Setup completion redirects to dashboard
- Plan configs saved to database

**Sprint Update:**
> _[To be completed by Claude Code]_

---

## Phase 4: Dashboard & Daily Entry

**Goal:** The main interface users interact with daily—viewing status and logging hours.

### Sprint 4.1: Dashboard - Status Display
**Estimated Time:** 2 hours

**Objective:** Build the main dashboard showing current status across all plans.

**Tasks:**
- [ ] Create `templates/dashboard.html` with sections:
  - **Today's Focus**: Current date, today's target (Realistic plan emphasized), quick entry form
  - **Weekly Progress**: Hours billed this week vs. target
  - **Monthly Progress**: Visual progress bar for current month
  - **Plan Status Cards**: Three cards showing each plan's status
- [ ] Implement `routes/dashboard.py`:
  - GET `/` or `/dashboard` - main dashboard view
  - Fetch all calculated data from services
- [ ] Create status card component showing:
  - Plan name
  - Hours ahead/behind
  - Status label with color coding (green=ahead, yellow=slightly behind, red=needs catch-up)
  - Today's target for this plan
- [ ] Add Chart.js for monthly progress visualization
- [ ] Handle edge case: no year configured → redirect to setup

**Acceptance Criteria:**
- Dashboard loads with all plan statuses
- Visual progress indicators work
- Today's target clearly displayed
- Color coding correctly reflects status
- Clean, uncluttered UI that's easy to scan

**Sprint Update:**
> _[To be completed by Claude Code]_

---

### Sprint 4.2: Daily Hours Entry
**Estimated Time:** 1 hour

**Objective:** Implement the quick hours entry form with immediate feedback.

**Tasks:**
- [ ] Add hours entry form to dashboard:
  - Single number input for hours billed
  - Date selector (defaults to today, can select recent past dates)
  - Submit button
- [ ] Implement HTMX submission:
  - POST `/entries` - save hours
  - Return updated dashboard section (partial HTML)
  - Dashboard updates without full page reload
- [ ] Implement entry editing:
  - Click on recent entries to edit
  - PUT `/entries/<id>` - update hours
- [ ] Show recent entries list (last 5-7 days)
- [ ] Add positive feedback when entry results in being ahead

**Acceptance Criteria:**
- Can enter hours in under 10 seconds
- Dashboard updates immediately after entry
- Can edit recent entries
- Positive feedback for good performance ("Nice! You're 2 hours ahead this month")

**Sprint Update:**
> _[To be completed by Claude Code]_

---

### Sprint 4.3: Monthly and Historical Views
**Estimated Time:** 1.5 hours

**Objective:** Add views for seeing the full month and historical data.

**Tasks:**
- [ ] Create `templates/monthly.html`:
  - Calendar view of current month
  - Each day shows: target, actual (if entered), difference
  - Color coding for ahead/behind/not-yet days
  - Navigate between months
- [ ] Create `templates/history.html`:
  - Table view of all entries
  - Sortable by date
  - Monthly subtotals
  - YTD total
- [ ] Implement routes:
  - GET `/monthly` and `/monthly/<year>/<month>`
  - GET `/history`
- [ ] Add navigation between dashboard, monthly, and history views

**Acceptance Criteria:**
- Monthly calendar view shows clear daily breakdown
- Can navigate to any month in the configured year
- History shows complete entry log
- Easy navigation between views

**Sprint Update:**
> _[To be completed by Claude Code]_

---

## Phase 5: Catch-Up Sprints

**Goal:** Implement the catch-up sprint feature for recovery planning.

### Sprint 5.1: Catch-Up Sprint Creation
**Estimated Time:** 1.5 hours

**Objective:** Build the interface for creating a catch-up sprint.

**Tasks:**
- [ ] Create `templates/catchup/create.html`:
  - Target plan selector (Optimistic or Realistic)
  - Duration selector (1-6 weeks)
  - Show calculated daily target based on selection
  - Option to include weekend days (2-4 hours)
  - Adjustable parameters before accepting
  - Preview of the sprint plan
- [ ] Implement sprint calculation in `services/catchup.py`:
  - Calculate hours needed to catch up
  - Distribute across sprint duration
  - Respect 9.5 hour max
  - Include optional weekend hours
- [ ] Implement routes:
  - GET `/catchup/new` - show creation form
  - POST `/catchup` - create sprint
- [ ] Save CatchUpSprint to database

**Acceptance Criteria:**
- User can create catch-up sprint with clear preview
- Parameters are adjustable before committing
- Sprint respects 9.5 hour daily maximum
- Weekend billing is optional and capped at 4 hours

**Sprint Update:**
> _[To be completed by Claude Code]_

---

### Sprint 5.2: Catch-Up Sprint Tracking
**Estimated Time:** 1.5 hours

**Objective:** Integrate active catch-up sprint into the dashboard and daily flow.

**Tasks:**
- [ ] Add sprint status to dashboard:
  - Show as fourth "plan" card when active
  - Display sprint progress (hours billed vs. target)
  - Days remaining in sprint
  - Daily target for sprint
- [ ] Implement sprint monitoring:
  - Check if user is falling behind sprint (>3 hours behind)
  - Show proactive alert: "You're behind your catch-up plan. Want to revise?"
- [ ] Implement sprint completion:
  - Auto-detect when sprint target is hit
  - Show success message with positive feedback
  - Mark sprint as completed
- [ ] Implement sprint revision:
  - "Revise Sprint" button
  - Pre-fill form with current sprint parameters
  - Create new sprint, mark old as "revised"
- [ ] Implement sprint dismissal:
  - "Dismiss Sprint" option
  - Confirmation dialog
  - Mark sprint as dismissed

**Acceptance Criteria:**
- Active sprint visible on dashboard
- Proactive alerts for falling behind
- Success celebration on completion
- Revision feels natural, not punishing
- Can dismiss sprint if circumstances change

**Sprint Update:**
> _[To be completed by Claude Code]_

---

## Phase 6: Export & Polish

**Goal:** Add the export feature and polish the overall experience.

### Sprint 6.1: Export Functionality
**Estimated Time:** 1.5 hours

**Objective:** Generate downloadable charts showing plans vs. actual.

**Tasks:**
- [ ] Install Matplotlib or Plotly for chart generation
- [ ] Create `services/export.py`:
  - Generate line chart with all three plans' trajectories
  - Overlay actual hours billed as a fourth line
  - Monthly breakdown on x-axis
  - Clear legend and labels
- [ ] Implement export route:
  - GET `/export` - show export options
  - GET `/export/chart.png` - generate and return PNG
  - GET `/export/chart.pdf` - generate and return PDF
- [ ] Style chart professionally:
  - Clean colors (not garish)
  - Clear fonts
  - Include title with year and date generated
  - Include summary stats below chart

**Acceptance Criteria:**
- Can download PNG and PDF versions
- Chart clearly shows all three plans plus actual
- Professional appearance suitable for firm meetings
- Summary statistics included

**Sprint Update:**
> _[To be completed by Claude Code]_

---

### Sprint 6.2: Mid-Year Start Support
**Estimated Time:** 1 hour

**Objective:** Allow users who start mid-year to enter historical hours.

**Tasks:**
- [ ] Add to setup flow: "Starting mid-year?" option
- [ ] Create `templates/setup/catchup_entry.html`:
  - Option to enter lump sum (total hours YTD)
  - Option to enter by month
  - Calculate and display what plans look like from here
- [ ] Implement routes for historical entry
- [ ] Ensure planning algorithm handles partial-year correctly
- [ ] Test with various mid-year scenarios

**Acceptance Criteria:**
- User can start app in any month
- Can enter historical hours easily
- Plans calculate correctly from current date forward
- No errors or edge cases with partial-year data

**Sprint Update:**
> _[To be completed by Claude Code]_

---

### Sprint 6.3: UX Polish and Error Handling
**Estimated Time:** 1.5 hours

**Objective:** Refine the user experience and add proper error handling.

**Tasks:**
- [ ] Review all user-facing messages for supportive tone:
  - Change any negative framing to constructive
  - Add encouraging messages for positive performance
  - Ensure "behind" messaging suggests solutions, not just problems
- [ ] Add proper error handling:
  - Database errors
  - Invalid inputs
  - Edge cases (no data yet, etc.)
- [ ] Add loading states for HTMX interactions
- [ ] Add keyboard shortcuts:
  - Quick entry from dashboard (press 'e' to focus entry field)
  - Navigation shortcuts
- [ ] Test responsive design for different screen sizes
- [ ] Add favicon and polish base template
- [ ] Review and improve color scheme and typography

**Acceptance Criteria:**
- All messaging is supportive and constructive
- Errors are handled gracefully with user-friendly messages
- UI feels polished and professional
- Works well on laptop screens (primary use case)

**Sprint Update:**
> _[To be completed by Claude Code]_

---

### Sprint 6.4: Documentation and Cleanup
**Estimated Time:** 1 hour

**Objective:** Final documentation and code cleanup.

**Tasks:**
- [ ] Write comprehensive README.md:
  - Project overview
  - Installation instructions
  - How to run locally
  - Brief user guide
- [ ] Review all code for:
  - Consistent style
  - Adequate comments
  - Type hints throughout
  - Removal of debug code
- [ ] Ensure all tests pass
- [ ] Create sample data script for demo/testing
- [ ] Document any configuration options

**Acceptance Criteria:**
- README allows someone to get started quickly
- Code is clean and well-documented
- All tests pass
- Sample data script works

**Sprint Update:**
> _[To be completed by Claude Code]_

---

## Implementation Notes

### Dependencies Between Sprints

- Phase 2 (Algorithm) must complete before Phase 4 (Dashboard) can show real data
- Sprint 1.2 (Models) must complete before any data-dependent work
- Sprint 4.1 (Dashboard) should complete before Sprint 5 (Catch-Up) since catch-up displays on dashboard
- Export (6.1) can technically happen anytime after Phase 4, but sequenced here for logical flow

### Testing Strategy

- **Unit tests:** Focus on planning algorithm (Phase 2) - this is the most complex and critical logic
- **Integration tests:** Key user flows (setup → dashboard → entry → status update)
- **Manual testing:** UI polish, responsive design, user experience feel

### Definition of Done

A sprint is complete when:
1. All tasks are checked off
2. Acceptance criteria are met
3. Code runs without errors
4. Relevant tests pass
5. Sprint Update is filled in with key decisions and notes for future sprints

### Key Technical Decisions to Make During Implementation

1. **Intensity weights:** Starting with normal=1.0, light=0.75, very_light=0.5 but may need tuning based on how the math works out
2. **"Behind" thresholds:** When does "slightly behind" become "needs catch-up"? Suggest: >5 hours behind = slightly behind, >15 hours behind = catch-up recommended
3. **Chart library choice:** Matplotlib is simpler, Plotly is more interactive - either works, decide based on ease of implementation
4. **HTMX partial templates:** May want a `partials/` subdirectory for small HTML fragments returned by HTMX endpoints
