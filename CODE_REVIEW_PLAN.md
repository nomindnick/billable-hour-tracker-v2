# CODE_REVIEW_PLAN.md

## Billable Hour Tracker v2 - Production Readiness Review

**Goal:** Ensure 100% production readiness through systematic verification of all features, requirements, and code quality.

**Total Sprints:** 52
**Estimated Total Effort:** Comprehensive, methodical review

---

## Phase 1: Spec Traceability Review (10 Sprints)

Verify every requirement in SPEC.md exists and works as specified.

---

### Sprint 1.1: Year Setup & Configuration

**Objective:** Verify all year setup requirements from SPEC.md are implemented correctly

**Scope:**
- `app/routes/setup.py`
- `app/templates/setup/year.html`
- `app/models.py` (YearConfig model)

**Review Checklist:**
- [x] Annual target is adjustable (default 1,800 hours)
- [x] Year selection allows calendar year input
- [x] Year range is reasonable (±1 year from current as per implementation)
- [x] Annual target has valid range (1000-3000 as implemented)
- [x] YearConfig model stores all required fields
- [x] Setup wizard creates YearConfig correctly
- [x] Redirects to next step (midyear/historical) after year selection

**Acceptance Criteria:**
- All year setup requirements from spec are verified working
- No deviations from spec without documented justification

**Sprint Findings:**
- Issues Found: 3 (missing server-side year validation, progress indicator mismatch across 4 templates, button text mismatch)
- Fixes Applied: Server-side year range validation added to setup.py; progress indicators updated to 5 steps (Year → Historical → Holidays → Vacation → Plans) in year.html, holidays.html, vacation.html, plans.html; button text in year.html changed to "Next: Historical Hours"
- Remaining Concerns: None
- Tests Added: None (manual verification sufficient for UI fixes; validation logic straightforward)

---

### Sprint 1.2: Holidays and Vacation Configuration

**Objective:** Verify holiday and vacation management matches spec

**Scope:**
- `app/routes/setup.py` (holidays and vacation endpoints)
- `app/templates/setup/holidays.html`
- `app/templates/setup/vacation.html`
- `app/models.py` (Holiday, VacationDay models)

**Review Checklist:**
- [x] Holidays can be manually entered
- [x] Holidays are firm-recognized non-billing days
- [x] Vacation days can be entered separately
- [x] "Add Common US Holidays" helper works correctly
- [x] All 11 standard US holidays are included
- [x] Dates are validated to be within configured year
- [x] Duplicate date prevention works
- [x] HTMX-powered add/remove without full page reload
- [x] Can remove holidays after adding
- [x] Can remove vacation days after adding

**Acceptance Criteria:**
- All holiday/vacation features work as specified
- Date validation prevents invalid entries

**Sprint Findings:**
- Issues Found: 1 (missing database unique constraints on Holiday and VacationDay models)
- Fixes Applied: Added UniqueConstraint to both models' __table_args__ for (year_config_id, date) in models.py
- Remaining Concerns: None
- Tests Added: None (existing app-level duplicate checks already test this behavior; DB constraint is defense-in-depth)

---

### Sprint 1.3: Three-Plan System

**Objective:** Verify all three billing plans exist and have correct characteristics

**Scope:**
- `app/models.py` (PlanConfig, PlanType enum)
- `app/services/planner.py`
- `app/templates/setup/plans.html`

**Review Checklist:**
- [x] **Firm Requirements Plan:** Fixed linear distribution (150 hours/month)
- [x] Firm Plan: Non-dynamically adjusted reference point
- [x] Firm Plan: Shows 450 hours/quarter
- [x] **Optimistic Plan:** User-defined aggressive goal
- [x] Optimistic Plan: Configurable target date (e.g., Thanksgiving)
- [x] Optimistic Plan: Creates maximum holiday flexibility
- [x] Optimistic Plan: Supports maintenance hours after target
- [x] **Realistic Plan:** Hits annual target by Dec 31
- [x] Realistic Plan: Accounts for billing intensity preferences
- [x] Realistic Plan: Allows lighter December
- [x] Realistic Plan: Intended as primary plan (emphasized in UI)
- [x] All three plans created during setup

**Acceptance Criteria:**
- Each plan type has distinct, correct behavior
- Plan characteristics match spec exactly

**Sprint Findings:**
- Issues Found: 0 - All three plans correctly implemented
- Fixes Applied: None needed
- Remaining Concerns: None
- Tests Added: None (existing coverage adequate)
- Verification Notes:
  - FIRM: Fixed 150/month in planner.py:293-299, read-only display in plans.html:72-93 with "450 hours/quarter"
  - OPTIMISTIC: Configurable target date (default Nov 27) and maintenance hours in plans.html:95-143, calculation logic in planner.py:320-369
  - REALISTIC: Full-year weighted distribution in planner.py:311-318, marked as primary with green color + "Primary" badge in dashboard.html:267-274, is_primary flag set in dashboard.py:307
  - All three plans created during setup in setup.py:107-134

---

### Sprint 1.4: Monthly Target Distribution Algorithm

**Objective:** Verify the core distribution algorithm works per spec

**Scope:**
- `app/services/planner.py` (calculate_monthly_targets, validate_plan_feasibility)
- `app/services/calendar_utils.py`
- `app/models.py` (MonthConfig, IntensityLevel)

**Review Checklist:**
- [x] Distributes annual target across months
- [x] Considers available workdays (excludes weekends)
- [x] Excludes holidays from workday count
- [x] Excludes vacation days from workday count
- [x] Applies billing intensity settings correctly
- [x] **Intensity weights:** normal=1.0, light=0.75, very_light=0.5
- [x] Plan-specific timeline handling (Optimistic ends early)
- [x] **Daily targets stay near 7.5 hours**
- [x] **Daily targets NEVER exceed 9.5 hours**
- [x] Surfaces impossible configurations during setup
- [x] Returns PlanWarning when plan is infeasible
- [x] Warning includes month, required hours, and message

**Acceptance Criteria:**
- Algorithm produces correct monthly targets for all scenarios
- 9.5-hour limit is strictly enforced
- Impossible configurations are detected and surfaced

**Sprint Findings:**
- Issues Found: 0 - Algorithm correctly implemented
- Fixes Applied: None needed
- Remaining Concerns: None
- Tests Added: None (existing coverage in test_planner.py adequate)
- Verification Notes:
  - Distribution: planner.py:194-244 uses proportional weighted distribution (workdays × intensity)
  - Workdays: calendar_utils.py:21-57 excludes weekends (weekday() >= 5), holidays, vacation
  - Intensity weights: planner.py:35-39 defines INTENSITY_WEIGHTS dict with exact values (1.0, 0.75, 0.5)
  - 9.5 hour cap: planner.py:42 MAX_DAILY_HOURS = 9.5, enforced in validate_plan_feasibility()
  - PlanWarning: planner.py:49-63 dataclass with month, required_daily_hours, workdays_in_month, message
  - UI surfacing: setup.py:865-872 passes warnings to validation_warnings.html partial
  - 7.5 hour reference: catchup.py:38 COMFORTABLE_TARGET = 7.5 used for color coding

---

### Sprint 1.5: Dynamic Daily Targets

**Objective:** Verify daily target recalculation works per spec

**Scope:**
- `app/services/calculator.py`
- `app/routes/dashboard.py`

**Review Checklist:**
- [x] Start of month: daily target = monthly target ÷ remaining workdays
- [x] Recalculates after each day entry
- [x] Shortfalls distribute across remaining days
- [x] Excess hours banked as "ahead"
- [x] Banked hours don't reset daily targets (spec requirement)
- [x] **Hard cap at 9.5 hours/day**
- [x] Suggests catch-up sprint when cap exceeded
- [x] Remaining workdays calculation is accurate
- [x] Weekend days excluded from remaining workdays
- [x] Holidays excluded from remaining workdays

**Acceptance Criteria:**
- Daily targets recalculate correctly in real-time
- 9.5-hour cap is enforced with appropriate suggestions

**Sprint Findings:**
- Issues Found: 2
  1. **BUG (High):** Missing `db` import in dashboard.py:342 - would cause crash on auto-complete error path
  2. **SPEC DEVIATION (Medium):** Daily targets decreased when ahead, but spec says they should stay at original pace to "encourage continued strong performance rather than coasting"
- Fixes Applied:
  1. Added `from app import db` import to dashboard.py (line 13)
  2. Updated `calculate_daily_target()` in calculator.py (lines 312-428) to use "on-track" target when ahead, "current" target when behind
- Remaining Concerns: None
- Tests Added: 2 new tests in test_calculator.py
  1. `test_ahead_daily_target_stays_at_original_pace` - verifies daily target doesn't drop when ahead
  2. `test_behind_daily_target_increases` - verifies daily target increases to distribute shortfall

---

### Sprint 1.6: Dashboard Interface

**Objective:** Verify dashboard shows all required information per spec

**Scope:**
- `app/routes/dashboard.py`
- `app/templates/dashboard.html`
- `app/templates/dashboard/partials/*.html`

**Review Checklist:**
- [ ] **Today's target** displayed (emphasizes Realistic plan)
- [ ] Hours billed today shown (if entered)
- [ ] **Weekly progress:** Hours billed vs. target
- [ ] **Monthly progress:** Visual indicator (progress bar)
- [ ] **Plan status cards** for each plan
- [ ] Status shows ahead/behind with labels
- [ ] Status labels: "On track", "Slightly behind", "Catch-up recommended"
- [ ] **Threshold:** >5 hours behind = "Slightly behind"
- [ ] **Threshold:** >15 hours behind = "Catch-up recommended"
- [ ] Current catch-up sprint status shown when active
- [ ] Redirects to setup if no YearConfig exists
- [ ] Dashboard updates immediately after entry

**Acceptance Criteria:**
- All dashboard sections from spec are present and accurate
- Status thresholds match spec exactly

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 1.7: Daily Hours Entry

**Objective:** Verify daily entry system works per spec

**Scope:**
- `app/routes/entries.py`
- `app/templates/dashboard/partials/quick_entry_form.html`
- `app/models.py` (DailyEntry)

**Review Checklist:**
- [ ] Single number input for total billable hours
- [ ] Can edit previous days' entries
- [ ] Dashboard immediately updates all calculations after entry
- [ ] Entry form is accessible from dashboard
- [ ] Date selector defaults to today
- [ ] Positive feedback messages shown ("Excellent!", "Great work!", etc.)
- [ ] HTMX submission without full page reload
- [ ] Recent entries list visible
- [ ] Keyboard shortcut 'e' focuses entry field

**Acceptance Criteria:**
- Entry flow is smooth and matches spec
- All calculations update immediately

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 1.8: Catch-Up Sprints

**Objective:** Verify catch-up sprint system works per spec

**Scope:**
- `app/services/catchup.py`
- `app/routes/catchup.py`
- `app/templates/catchup/*.html`
- `app/models.py` (CatchUpSprint, SprintStatus)

**Review Checklist:**
- [ ] **Setup:** Select target plan (Realistic/Optimistic only, not Firm)
- [ ] **Setup:** Select timeframe (1-6 weeks)
- [ ] **Setup:** App suggests daily targets
- [ ] **Setup:** Optional 2-4 hour weekend billing
- [ ] **During sprint:** Shows as fourth plan on dashboard
- [ ] **During sprint:** Proactive alerts if falling behind
- [ ] **Behind threshold:** >3 hours behind triggers alert
- [ ] **Endings:** Auto-dismiss on success (target achieved)
- [ ] **Endings:** Can revise parameters
- [ ] **Endings:** Can manually dismiss
- [ ] Revision flow is smooth, not punishing
- [ ] Sprint preview shows feasibility before creation
- [ ] Infeasible sprints show clear error message
- [ ] Existing active sprint marked REVISED when new one created

**Acceptance Criteria:**
- Full sprint lifecycle works as specified
- UX is encouraging, not punishing

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 1.9: Plan Adjustment & Export Function

**Objective:** Verify mid-year adjustment and export features work per spec

**Scope:**
- `app/routes/setup.py` (adjustment endpoints)
- `app/services/export.py`
- `app/routes/export.py`
- `app/templates/export.html`

**Review Checklist:**
**Plan Adjustment:**
- [ ] Can adjust Optimistic plan's goal mid-year
- [ ] Can add/remove holidays mid-year
- [ ] Can add/remove vacation days mid-year
- [ ] Can change billing intensity for upcoming months
- [ ] Can adjust annual target
- [ ] Changes affect future calculations only
- [ ] Historical data remains intact

**Export Function:**
- [ ] Line chart shows all three plans' expected trajectory
- [ ] Actual hours billed overlaid on chart
- [ ] Chart shows cumulative hours by month
- [ ] Summary statistics: YTD total
- [ ] Summary statistics: Current pace
- [ ] Summary statistics: Projected year-end
- [ ] PDF download option works
- [ ] PNG download option works
- [ ] Files named correctly: billable_hours_{year}_{date}.png/pdf

**Acceptance Criteria:**
- Mid-year adjustments work without affecting history
- Export produces accurate, professional charts

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 1.10: Mid-Year Start Support

**Objective:** Verify mid-year start functionality works per spec

**Scope:**
- `app/routes/setup.py` (midyear endpoint)
- `app/templates/setup/midyear.html`
- `app/models.py` (YearConfig.start_date, hours_pre_start, HistoricalMonth)
- `app/services/calculator.py` (historical hours handling)

**Review Checklist:**
- [ ] Can enter hours already billed (lump sum)
- [ ] Can enter hours by month (detailed breakdown)
- [ ] App calculates plans forward from current date
- [ ] Months before start_date get 0 hours allocation
- [ ] Historical hours included in YTD totals
- [ ] Historical hours included in plan status calculations
- [ ] All features work normally from start date forward
- [ ] Dashboard reflects correct totals with historical data
- [ ] Export includes historical data correctly

**Acceptance Criteria:**
- Mid-year start produces correct calculations
- User can start using app at any point in the year

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

## Phase 2: Implementation Plan Reconciliation (17 Sprints)

Verify each implementation sprint's acceptance criteria are met and identify test gaps.

---

### Sprint 2.1: Project Scaffolding (Sprint 1.1)

**Objective:** Verify foundation is correctly implemented

**Scope:**
- Project directory structure
- `requirements.txt`
- `app/__init__.py`
- `run.py`
- `config.py`

**Review Checklist:**
- [ ] Directory structure matches blueprint pattern
- [ ] requirements.txt includes Flask, SQLAlchemy, python-dateutil, pytest, matplotlib
- [ ] Application factory pattern implemented in app/__init__.py
- [ ] create_app(config_name) function works correctly
- [ ] run.py entry point starts development server
- [ ] Config classes exist: Config, DevelopmentConfig, TestingConfig
- [ ] SECRET_KEY is configurable via environment
- [ ] Database URI is configurable per environment

**Test Gap Analysis:**
- [ ] Document any missing tests for app initialization
- [ ] Document any missing tests for config loading

**Acceptance Criteria:**
- Foundation code matches implementation plan
- Test gaps documented

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 2.2: Database Models (Sprint 1.2)

**Objective:** Verify all 7 models are correctly implemented

**Scope:**
- `app/models.py`

**Review Checklist:**
- [ ] YearConfig model with all fields
- [ ] Holiday model with year_config relationship
- [ ] VacationDay model with year_config relationship
- [ ] MonthConfig model with intensity enum
- [ ] PlanConfig model with plan_type enum
- [ ] DailyEntry model with date uniqueness
- [ ] CatchUpSprint model with status enum
- [ ] HistoricalMonth model for mid-year
- [ ] IntensityLevel enum: NORMAL, LIGHT, VERY_LIGHT
- [ ] PlanType enum: FIRM, OPTIMISTIC, REALISTIC
- [ ] SprintStatus enum: ACTIVE, COMPLETED, REVISED, DISMISSED
- [ ] Cascade delete configured on all relationships
- [ ] Unique constraints on appropriate fields
- [ ] Indexes on frequently queried fields
- [ ] init-db command creates all tables

**Test Gap Analysis:**
- [ ] No model validation tests exist - document gap
- [ ] No cascade delete tests exist - document gap
- [ ] No unique constraint tests exist - document gap

**Acceptance Criteria:**
- All models match implementation plan
- Relationships and constraints verified

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 2.3: Workday Calculator (Sprint 2.1)

**Objective:** Verify workday calculation functions

**Scope:**
- `app/services/calendar_utils.py`
- `tests/test_calendar_utils.py`

**Review Checklist:**
- [ ] is_workday() correctly identifies workdays
- [ ] get_workdays_in_month() returns accurate counts
- [ ] get_workdays_in_range() handles date ranges correctly
- [ ] get_remaining_workdays_in_month() works correctly
- [ ] get_weekend_days_in_range() for sprint calculations
- [ ] Weekends (Sat/Sun) correctly excluded
- [ ] Holidays correctly excluded
- [ ] Vacation days correctly excluded
- [ ] Edge cases: month boundaries, year boundaries, leap years

**Test Coverage Review:**
- [ ] Review all 58 tests in test_calendar_utils.py
- [ ] Verify edge cases are covered
- [ ] Document any missing test scenarios

**Acceptance Criteria:**
- All 4+ functions work correctly
- 40+ tests passing (implementation plan says 40)
- Edge cases covered

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 2.4: Monthly Distribution Algorithm (Sprint 2.2)

**Objective:** Verify monthly target distribution

**Scope:**
- `app/services/planner.py`
- `tests/test_planner.py`

**Review Checklist:**
- [ ] calculate_monthly_targets() distributes proportionally
- [ ] calculate_monthly_targets_for_plan() handles plan-specific logic
- [ ] FIRM plan returns fixed 150/month
- [ ] REALISTIC plan distributes across full year
- [ ] OPTIMISTIC plan compresses to target date
- [ ] validate_plan_feasibility() detects impossible plans
- [ ] PlanWarning dataclass has all required fields
- [ ] MonthlyTarget dataclass has all required fields
- [ ] Intensity weights applied correctly
- [ ] 9.5-hour daily limit enforced

**Test Coverage Review:**
- [ ] Review all tests in test_planner.py
- [ ] Verify plan-specific tests exist
- [ ] Document any missing test scenarios

**Acceptance Criteria:**
- Algorithm produces correct results
- 29+ tests passing (implementation plan says 29)

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 2.5: Daily Target Calculator (Sprint 2.3)

**Objective:** Verify daily target calculations

**Scope:**
- `app/services/calculator.py`
- `tests/test_calculator.py`

**Review Checklist:**
- [ ] calculate_daily_target() returns correct target
- [ ] Daily target capped at 9.5 hours
- [ ] catch_up_recommended flag set when >9.5 needed
- [ ] calculate_plan_status() returns correct status
- [ ] Status thresholds: 5 hours (slightly behind), 15 hours (catch-up)
- [ ] calculate_hours_banked() returns positive values only
- [ ] get_hours_billed_to_date() sums correctly
- [ ] get_expected_hours_to_date() calculates correctly
- [ ] DailyTargetResult dataclass complete
- [ ] PlanStatus dataclass complete

**Test Coverage Review:**
- [ ] Review all tests in test_calculator.py
- [ ] Verify threshold tests exist
- [ ] Document any missing test scenarios

**Acceptance Criteria:**
- Calculator functions work correctly
- 33+ tests passing (implementation plan says 33)

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 2.6: Setup UI - Year and Target (Sprint 3.1)

**Objective:** Verify year setup UI

**Scope:**
- `app/routes/setup.py`
- `app/templates/setup/year.html`

**Review Checklist:**
- [ ] Year selector shows ±1 year from current
- [ ] Annual target input accepts 1000-3000 range
- [ ] Form creates YearConfig on submit
- [ ] Creates 12 MonthConfigs with default intensity
- [ ] Creates 3 PlanConfigs (one per plan type)
- [ ] Redirects to holidays step
- [ ] Validation errors displayed appropriately

**Test Gap Analysis:**
- [ ] No route tests exist - document gap
- [ ] No form validation tests exist - document gap

**Acceptance Criteria:**
- Year setup flow works correctly
- Test gaps documented

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 2.7: Setup UI - Holidays and Vacation (Sprint 3.2)

**Objective:** Verify holiday/vacation setup UI

**Scope:**
- `app/routes/setup.py`
- `app/templates/setup/holidays.html`
- `app/templates/setup/vacation.html`

**Review Checklist:**
- [ ] Date pickers work correctly
- [ ] HTMX add without page reload
- [ ] HTMX remove without page reload
- [ ] "Add Common US Holidays" adds 11 holidays
- [ ] Date validation for configured year
- [ ] Duplicate date prevention
- [ ] Navigation to next/previous steps works

**Test Gap Analysis:**
- [ ] No HTMX interaction tests - document gap
- [ ] No holiday validation tests - document gap

**Acceptance Criteria:**
- Holiday/vacation management works correctly
- Test gaps documented

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 2.8: Setup UI - Plans Configuration (Sprint 3.3)

**Objective:** Verify plan configuration UI

**Scope:**
- `app/routes/setup.py`
- `app/templates/setup/plans.html`
- `app/templates/setup/complete.html`

**Review Checklist:**
- [ ] Firm Plan displayed as read-only (150/month)
- [ ] Optimistic Plan target date configurable
- [ ] Optimistic Plan maintenance hours configurable
- [ ] Realistic Plan uses intensity preferences
- [ ] Monthly intensity grid with 12 dropdowns
- [ ] Preset buttons: Standard, Light December, Light Nov-Dec
- [ ] Validation warnings display inline
- [ ] Complete.html shows configuration summary
- [ ] Can go back and modify settings

**Test Gap Analysis:**
- [ ] No plan configuration tests - document gap
- [ ] No preset button tests - document gap

**Acceptance Criteria:**
- Plan configuration works correctly
- Test gaps documented

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 2.9: Dashboard - Status Display (Sprint 4.1)

**Objective:** Verify dashboard implementation

**Scope:**
- `app/routes/dashboard.py`
- `app/templates/dashboard.html`

**Review Checklist:**
- [ ] Today's Focus section: date, target, quick entry
- [ ] Weekly Progress: hours vs target with progress bar
- [ ] Monthly Progress: progress bar, percentage, day X of Y
- [ ] Plan Status Cards: three cards with badges
- [ ] Monthly Chart: Chart.js bar chart
- [ ] YTD Summary: total, target, remaining, percentage
- [ ] Active Sprint Alert: purple banner when active
- [ ] Redirects to setup if no YearConfig
- [ ] Realistic plan emphasized as primary

**Test Gap Analysis:**
- [ ] No dashboard route tests - document gap
- [ ] No template rendering tests - document gap

**Acceptance Criteria:**
- Dashboard displays all required information
- Test gaps documented

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 2.10: Daily Hours Entry (Sprint 4.2)

**Objective:** Verify entry system implementation

**Scope:**
- `app/routes/entries.py`
- `app/templates/dashboard/partials/*.html`

**Review Checklist:**
- [ ] Single number input for hours
- [ ] Date selector defaults to today
- [ ] HTMX submission works
- [ ] Dashboard updates immediately
- [ ] Entry editing with inline forms
- [ ] Recent entries list (last 7 days)
- [ ] Positive feedback messages displayed
- [ ] Keyboard shortcut 'e' works

**Test Gap Analysis:**
- [ ] No entry route tests - document gap
- [ ] No HTMX response tests - document gap

**Acceptance Criteria:**
- Entry system works correctly
- Test gaps documented

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 2.11: Monthly and Historical Views (Sprint 4.3)

**Objective:** Verify calendar and history views

**Scope:**
- `app/routes/views.py`
- `app/templates/monthly.html`
- `app/templates/history.html`

**Review Checklist:**
- [ ] Calendar view shows daily targets and actuals
- [ ] Color coding: green (met), amber (behind), gray (missed), slate (off)
- [ ] Month navigation (prev/next) works
- [ ] History view shows all entries
- [ ] Monthly subtotals displayed
- [ ] YTD running total displayed
- [ ] Navigation between views in header

**Test Gap Analysis:**
- [ ] No view route tests - document gap
- [ ] No color logic tests - document gap

**Acceptance Criteria:**
- Calendar and history views work correctly
- Test gaps documented

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 2.12: Catch-Up Sprint Creation (Sprint 5.1)

**Objective:** Verify sprint creation

**Scope:**
- `app/services/catchup.py`
- `app/routes/catchup.py`
- `app/templates/catchup/create.html`

**Review Checklist:**
- [ ] Create form: plan selector, duration, weekend hours
- [ ] SprintPreview dataclass complete
- [ ] calculate_sprint_preview() works correctly
- [ ] create_catch_up_sprint() saves to database
- [ ] Existing active sprint marked as REVISED
- [ ] Catch-Up link in navigation
- [ ] Dashboard shows suggestion banner when behind

**Test Coverage Review:**
- [ ] Review sprint creation tests in test_catchup.py
- [ ] Verify preview calculation tests exist
- [ ] Document any gaps

**Acceptance Criteria:**
- Sprint creation works correctly
- Tests cover creation flow

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 2.13: Catch-Up Sprint Tracking (Sprint 5.2)

**Objective:** Verify sprint tracking

**Scope:**
- `app/services/catchup.py`
- `app/routes/catchup.py`

**Review Checklist:**
- [ ] SprintProgress dataclass with 12 fields
- [ ] calculate_sprint_progress() works correctly
- [ ] Auto-complete when target achieved
- [ ] Behind-pace alert at >3 hours behind
- [ ] Revision flow with pre-filled form
- [ ] Dismiss capability with confirmation
- [ ] Dashboard shows sprint as fourth "plan"
- [ ] Progress messages are encouraging

**Test Coverage Review:**
- [ ] Review sprint tracking tests in test_catchup.py
- [ ] Verify progress calculation tests exist
- [ ] Document any gaps

**Acceptance Criteria:**
- Sprint tracking works correctly
- 151 tests passing (implementation plan total at this point)

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 2.14: Export Functionality (Sprint 6.1)

**Objective:** Verify export system

**Scope:**
- `app/services/export.py`
- `app/routes/export.py`
- `app/templates/export.html`

**Review Checklist:**
- [ ] Matplotlib chart generation works
- [ ] 4 lines: Firm (gray dashed), Optimistic (blue), Realistic (green), Actual (purple bold)
- [ ] PNG download works
- [ ] PDF download works
- [ ] get_export_data() gathers cumulative targets
- [ ] generate_chart() creates matplotlib chart
- [ ] get_chart_as_base64() for HTML embedding
- [ ] Summary statistics displayed
- [ ] File naming: billable_hours_{year}_{date}.ext

**Test Coverage Review:**
- [ ] Review tests in test_export.py
- [ ] Verify chart format tests exist
- [ ] Document any gaps

**Acceptance Criteria:**
- Export system works correctly
- Tests cover export functionality

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 2.15: Mid-Year Start Support (Sprint 6.2)

**Objective:** Verify mid-year start

**Scope:**
- `app/models.py` (YearConfig.start_date, hours_pre_start, HistoricalMonth)
- `app/services/calculator.py`
- `app/templates/setup/midyear.html`

**Review Checklist:**
- [ ] start_date field on YearConfig
- [ ] hours_pre_start field on YearConfig
- [ ] HistoricalMonth model for monthly breakdown
- [ ] get_historical_hours() helper function
- [ ] get_hours_billed_to_date() includes historical
- [ ] get_expected_hours_to_date() adjusts for start date
- [ ] HTMX monthly grid in template
- [ ] Mid-year tests passing

**Test Coverage Review:**
- [ ] Review all 13 tests in test_midyear.py
- [ ] Verify edge cases covered
- [ ] Document any gaps

**Acceptance Criteria:**
- Mid-year start works correctly
- 13 tests passing for mid-year

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 2.16: UX Polish and Error Handling (Sprint 6.3)

**Objective:** Verify polish and error handling

**Scope:**
- `app/__init__.py` (error handlers)
- `app/templates/404.html`
- `app/templates/500.html`
- All route files (error handling)

**Review Checklist:**
- [ ] Global 404 error handler works
- [ ] Global 500 error handler works
- [ ] Friendly error templates exist
- [ ] All db.session.commit() wrapped in try/except
- [ ] Rollback on error
- [ ] HTMX loading states with spinner
- [ ] Messaging is supportive ("Consider" vs "Recommended")
- [ ] Favicon exists
- [ ] Active nav state highlighting
- [ ] Mobile responsive calendar

**Test Gap Analysis:**
- [ ] No error handler tests - document gap
- [ ] No rollback tests - document gap

**Acceptance Criteria:**
- Error handling is comprehensive
- UX is polished

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 2.17: Documentation and Cleanup (Sprint 6.4)

**Objective:** Verify documentation and final cleanup

**Scope:**
- `README.md`
- `CLAUDE.md`
- All code files (docstrings, type hints)

**Review Checklist:**
- [ ] README.md has project overview
- [ ] README.md has setup instructions
- [ ] README.md has usage guide
- [ ] README.md has configuration info
- [ ] CLAUDE.md has accurate commands
- [ ] No datetime.utcnow() deprecation warnings
- [ ] create_sample_data.py exists and works
- [ ] All 177 tests passing with no warnings
- [ ] All functions have docstrings
- [ ] All functions have type hints

**Acceptance Criteria:**
- Documentation is complete and accurate
- All tests pass with no warnings

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

## Phase 3: Test Expansion (12 Sprints)

Create comprehensive tests for identified gaps.

---

### Sprint 3.1: Route Tests - Dashboard

**Objective:** Add integration tests for dashboard routes

**Scope:**
- `app/routes/dashboard.py`
- New file: `tests/test_routes_dashboard.py`

**Tests to Create:**
- [ ] GET / returns 200 with valid YearConfig
- [ ] GET / redirects to /setup/ without YearConfig
- [ ] Dashboard shows correct today's target
- [ ] Dashboard shows correct weekly progress
- [ ] Dashboard shows correct monthly progress
- [ ] Dashboard shows all three plan status cards
- [ ] Dashboard shows active sprint when exists
- [ ] Dashboard handles no entries gracefully

**Acceptance Criteria:**
- All dashboard routes have test coverage
- Tests pass

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 3.2: Route Tests - Setup

**Objective:** Add integration tests for setup routes

**Scope:**
- `app/routes/setup.py`
- New file: `tests/test_routes_setup.py`

**Tests to Create:**
- [ ] GET /setup/ returns setup form
- [ ] POST /setup/year creates YearConfig
- [ ] POST /setup/year validates year range
- [ ] POST /setup/year validates target range
- [ ] GET /setup/holidays shows holiday form
- [ ] POST /setup/holidays adds holiday
- [ ] POST /setup/holidays prevents duplicates
- [ ] POST /setup/holidays validates date in year
- [ ] DELETE /setup/holidays removes holiday
- [ ] GET /setup/vacation shows vacation form
- [ ] POST /setup/vacation adds vacation day
- [ ] GET /setup/plans shows plan configuration
- [ ] POST /setup/plans saves plan configs
- [ ] GET /setup/complete shows summary
- [ ] GET /setup/midyear shows historical entry form
- [ ] POST /setup/midyear saves historical hours

**Acceptance Criteria:**
- All setup routes have test coverage
- Tests pass

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 3.3: Route Tests - Entries

**Objective:** Add integration tests for entry routes

**Scope:**
- `app/routes/entries.py`
- New file: `tests/test_routes_entries.py`

**Tests to Create:**
- [ ] GET /entries/ returns entry form
- [ ] POST /entries/add creates new entry
- [ ] POST /entries/add updates existing entry for same date
- [ ] POST /entries/add validates hours (non-negative)
- [ ] POST /entries/add validates date
- [ ] GET /entries/<id>/edit returns edit form
- [ ] POST /entries/<id>/edit updates entry
- [ ] POST /entries/<id>/delete removes entry
- [ ] HTMX responses return correct partials
- [ ] Positive feedback messages displayed

**Acceptance Criteria:**
- All entry routes have test coverage
- Tests pass

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 3.4: Route Tests - Views

**Objective:** Add integration tests for view routes

**Scope:**
- `app/routes/views.py`
- New file: `tests/test_routes_views.py`

**Tests to Create:**
- [ ] GET /monthly returns calendar view
- [ ] GET /monthly?month=X&year=Y shows correct month
- [ ] GET /monthly navigation works (prev/next)
- [ ] Monthly view shows correct color coding
- [ ] GET /history returns history view
- [ ] History shows all entries
- [ ] History shows monthly subtotals
- [ ] History shows YTD totals

**Acceptance Criteria:**
- All view routes have test coverage
- Tests pass

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 3.5: Route Tests - Catch-Up

**Objective:** Add integration tests for catch-up routes

**Scope:**
- `app/routes/catchup.py`
- New file: `tests/test_routes_catchup.py`

**Tests to Create:**
- [ ] GET /catchup/create shows creation form
- [ ] GET /catchup/create redirects if no YearConfig
- [ ] POST /catchup/create creates sprint
- [ ] POST /catchup/create validates duration (1-6)
- [ ] POST /catchup/create validates weekend hours (0-4)
- [ ] POST /catchup/create prevents FIRM plan selection
- [ ] POST /catchup/dismiss dismisses active sprint
- [ ] POST /catchup/complete completes active sprint
- [ ] HTMX preview updates correctly
- [ ] Sprint revision flow works

**Acceptance Criteria:**
- All catch-up routes have test coverage
- Tests pass

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 3.6: Route Tests - Export

**Objective:** Add integration tests for export routes

**Scope:**
- `app/routes/export.py`
- New file: `tests/test_routes_export.py`

**Tests to Create:**
- [ ] GET /export/ shows export page
- [ ] GET /export/ displays summary statistics
- [ ] GET /export/chart?format=png returns PNG
- [ ] GET /export/chart?format=pdf returns PDF
- [ ] Chart contains correct data points
- [ ] File download has correct filename
- [ ] Export handles no data gracefully

**Acceptance Criteria:**
- All export routes have test coverage
- Tests pass

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 3.7: Model Tests

**Objective:** Add tests for database models

**Scope:**
- `app/models.py`
- New file: `tests/test_models.py`

**Tests to Create:**
- [ ] YearConfig creation with defaults
- [ ] YearConfig unique constraint on year
- [ ] Holiday creation with year_config relationship
- [ ] Holiday unique constraint (year_config_id, date)
- [ ] VacationDay creation and constraints
- [ ] MonthConfig creation with intensity enum
- [ ] MonthConfig unique constraint (year_config_id, month)
- [ ] PlanConfig creation with plan_type enum
- [ ] PlanConfig unique constraint (year_config_id, plan_type)
- [ ] DailyEntry creation with date uniqueness
- [ ] CatchUpSprint creation with status enum
- [ ] HistoricalMonth creation and constraints
- [ ] Cascade delete: deleting YearConfig removes children
- [ ] Enum values are correct

**Acceptance Criteria:**
- All models have test coverage
- Tests pass

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 3.8: Algorithm Edge Cases - Planner

**Objective:** Add edge case tests for planner algorithm

**Scope:**
- `app/services/planner.py`
- `tests/test_planner.py`

**Tests to Create:**
- [ ] All months with VERY_LIGHT intensity
- [ ] Single month with all holidays (no workdays)
- [ ] Year with maximum holidays (every workday)
- [ ] Leap year February handling
- [ ] December 31 target date (edge of year)
- [ ] January 1 start date (beginning of year)
- [ ] Mid-month start date
- [ ] Annual target of exactly 0
- [ ] Annual target at maximum (3000)
- [ ] Annual target at minimum (1000)
- [ ] All months at 9.5 hours/day threshold
- [ ] Optimistic target date same as start date

**Acceptance Criteria:**
- Edge cases don't crash or produce incorrect results
- Tests pass

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 3.9: Algorithm Edge Cases - Calculator

**Objective:** Add edge case tests for calculator

**Scope:**
- `app/services/calculator.py`
- `tests/test_calculator.py`

**Tests to Create:**
- [ ] Calculate target on weekend (should handle gracefully)
- [ ] Calculate target on holiday
- [ ] Calculate target with no remaining workdays in month
- [ ] Calculate status at year end (Dec 31)
- [ ] Calculate status at year start (Jan 1)
- [ ] Zero hours billed for entire year
- [ ] Hours billed exceed annual target
- [ ] Hours billed exactly meet annual target
- [ ] Daily target calculation on last workday of month
- [ ] Expected hours calculation spanning year boundary
- [ ] Banked hours with exactly expected value (edge of 0)

**Acceptance Criteria:**
- Edge cases handled correctly
- Tests pass

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 3.10: Algorithm Edge Cases - Catch-Up

**Objective:** Add edge case tests for catch-up sprints

**Scope:**
- `app/services/catchup.py`
- `tests/test_catchup.py`

**Tests to Create:**
- [ ] Sprint spanning year boundary (Dec-Jan)
- [ ] Sprint with all weekend days (no workdays)
- [ ] Sprint with maximum weekend hours (4/day)
- [ ] Sprint exactly at 9.5 hour threshold
- [ ] Sprint slightly over 9.5 hour threshold
- [ ] Sprint with 1 day duration
- [ ] Sprint with 6 week duration (maximum)
- [ ] Sprint when exactly on track (0 hours behind)
- [ ] Sprint when 1 hour behind (just under threshold)
- [ ] Sprint progress at 100% exactly
- [ ] Sprint progress over 100%
- [ ] Multiple sprints revised in sequence
- [ ] Sprint dismissed immediately after creation

**Acceptance Criteria:**
- Edge cases handled correctly
- Tests pass

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 3.11: Date Handling Edge Cases

**Objective:** Test date boundary conditions

**Scope:**
- `app/services/calendar_utils.py`
- `tests/test_calendar_utils.py`

**Tests to Create:**
- [ ] February 29 in leap year (2024, 2028)
- [ ] February 28 in non-leap year
- [ ] December 31 to January 1 transition
- [ ] Month with 31 days (Jan, Mar, May, Jul, Aug, Oct, Dec)
- [ ] Month with 30 days (Apr, Jun, Sep, Nov)
- [ ] First day of year (Jan 1)
- [ ] Last day of year (Dec 31)
- [ ] Holiday on weekend (shouldn't double-count)
- [ ] Vacation on holiday (shouldn't double-count)
- [ ] Date range spanning multiple months
- [ ] Date range spanning multiple years
- [ ] Single day range (start = end)
- [ ] Empty range (start > end)

**Acceptance Criteria:**
- All date edge cases handled correctly
- Tests pass

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 3.12: Error Handling Tests

**Objective:** Test error conditions and validation

**Scope:**
- All route files
- All service files
- New file: `tests/test_error_handling.py`

**Tests to Create:**
- [ ] 404 error for invalid routes
- [ ] 500 error triggers rollback
- [ ] Invalid year in setup (out of range)
- [ ] Invalid annual target (out of range)
- [ ] Invalid date format in forms
- [ ] Negative hours in entry
- [ ] Hours over 24 in entry
- [ ] Invalid sprint duration
- [ ] Invalid weekend hours
- [ ] Missing required form fields
- [ ] Database constraint violations
- [ ] Concurrent modification handling

**Acceptance Criteria:**
- Error conditions handled gracefully
- User-friendly error messages displayed
- Tests pass

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

## Phase 4: Integration & Real-World Testing (8 Sprints)

Test complete user workflows with realistic scenarios.

---

### Sprint 4.1: Fresh Year Setup Flow

**Objective:** Test complete setup from scratch

**Scenario:** Configure 2025/2026, add holidays, set intensity, verify plans

**Test Steps:**
- [ ] Navigate to /setup/
- [ ] Select year (current or next year)
- [ ] Enter annual target (1800)
- [ ] Submit and verify redirect to holidays
- [ ] Add 5 custom holidays manually
- [ ] Click "Add Common US Holidays"
- [ ] Verify 11 US holidays added (no duplicates)
- [ ] Navigate to vacation setup
- [ ] Add 10 vacation days
- [ ] Navigate to plan configuration
- [ ] Verify Firm plan shows 150/month (read-only)
- [ ] Set Optimistic target date (Thanksgiving)
- [ ] Set maintenance hours (2/day after target)
- [ ] Use "Light December" preset
- [ ] Verify intensity grid shows December as light
- [ ] Submit and verify redirect to complete
- [ ] Review summary on complete page
- [ ] Navigate to dashboard
- [ ] Verify all three plans display correctly
- [ ] Verify daily targets are reasonable (~7.5 hours)
- [ ] Verify no plan exceeds 9.5 hours/day

**Expected Results:**
- Setup completes without errors
- All three plans calculate correctly
- Dashboard displays accurate information

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 4.2: Daily Usage Flow

**Objective:** Test typical daily billing workflow

**Scenario:** Enter hours for multiple days, verify updates

**Test Steps:**
- [ ] Open dashboard with configured year
- [ ] Note today's target for Realistic plan
- [ ] Enter 7.5 hours using quick entry
- [ ] Verify positive feedback message appears
- [ ] Verify dashboard updates immediately
- [ ] Verify weekly progress updates
- [ ] Verify monthly progress updates
- [ ] Verify plan status cards update
- [ ] Enter hours for yesterday (7.0)
- [ ] Verify historical entry appears in recent entries
- [ ] Navigate to monthly view
- [ ] Verify both days show in calendar
- [ ] Verify color coding (green if met target)
- [ ] Navigate to history view
- [ ] Verify both entries listed
- [ ] Verify monthly subtotal correct
- [ ] Edit yesterday's entry to 8.0
- [ ] Verify all calculations update
- [ ] Delete yesterday's entry
- [ ] Verify entry removed and calculations update

**Expected Results:**
- All entries recorded correctly
- Calculations update in real-time
- Edit and delete work correctly

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 4.3: Falling Behind Scenario

**Objective:** Test catch-up sprint workflow

**Scenario:** Enter below-target hours, trigger catch-up suggestion

**Test Steps:**
- [ ] Start with clean year configuration
- [ ] Enter 5 hours/day for 5 consecutive workdays (25 total)
- [ ] Verify dashboard shows "Slightly behind" for Realistic
- [ ] Continue entering 5 hours/day for 2 more weeks
- [ ] Verify dashboard shows "Consider a catch-up sprint"
- [ ] Note hours behind value
- [ ] Click to create catch-up sprint
- [ ] Select Realistic plan as target
- [ ] Select 2-week duration
- [ ] Enable weekend billing (2 hours/day)
- [ ] Verify preview shows:
  - [ ] Total hours to catch up
  - [ ] Weekday daily target
  - [ ] Weekend target
  - [ ] Feasibility assessment
- [ ] Create sprint
- [ ] Verify dashboard shows sprint as fourth "plan"
- [ ] Enter 8 hours for first day
- [ ] Verify sprint progress updates
- [ ] Enter below-pace hours for several days
- [ ] Verify "behind pace" alert appears
- [ ] Revise sprint (extend to 3 weeks)
- [ ] Verify old sprint marked REVISED
- [ ] Continue entering hours until sprint complete
- [ ] Verify auto-completion works
- [ ] Verify success message displayed
- [ ] Verify dashboard returns to three plans

**Expected Results:**
- Catch-up flow is intuitive and encouraging
- Sprint tracking is accurate
- Revision and completion work correctly

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 4.4: Mid-Year Start Scenario

**Objective:** Test starting app mid-year with historical data

**Scenario:** Start in June with 900 hours already billed

**Test Steps:**
- [ ] Navigate to /setup/
- [ ] Select current year (assume it's mid-year)
- [ ] Enter annual target (1800)
- [ ] Complete holiday setup
- [ ] Complete vacation setup
- [ ] Navigate to mid-year setup
- [ ] Enter start date (June 1)
- [ ] Option A: Enter 900 hours as lump sum
- [ ] Option B: Enter hours by month (150/month Jan-May)
- [ ] Complete setup
- [ ] Navigate to dashboard
- [ ] Verify YTD shows 900 hours
- [ ] Verify remaining target is 900 hours
- [ ] Verify plans calculate forward from June
- [ ] Verify daily targets are reasonable for remaining months
- [ ] Enter hours for June 1
- [ ] Verify calculations include historical + new entry
- [ ] Check monthly view for June
- [ ] Verify months before June not editable/displayed as past
- [ ] Check export
- [ ] Verify chart shows historical data correctly
- [ ] Verify projection uses historical baseline

**Expected Results:**
- Mid-year start calculates correctly
- Historical data integrated properly
- Forward calculations are accurate

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 4.5: Edge Cases in UI

**Objective:** Test UI boundary conditions

**Scenario:** Various edge cases and invalid inputs

**Test Steps:**
**Empty States:**
- [ ] Dashboard with no entries (first day)
- [ ] Monthly view with no entries
- [ ] History view with no entries
- [ ] Export with no entries

**Invalid Inputs:**
- [ ] Enter negative hours (-5)
- [ ] Enter excessive hours (25)
- [ ] Enter non-numeric hours ("abc")
- [ ] Enter hours with many decimal places (7.123456)
- [ ] Select date outside configured year
- [ ] Enter duplicate holiday
- [ ] Enter vacation on existing holiday

**Rapid Interactions:**
- [ ] Submit entry form multiple times quickly
- [ ] Navigate rapidly between views
- [ ] Create and dismiss sprint rapidly
- [ ] Edit entry while dashboard updating

**Browser Edge Cases:**
- [ ] Refresh during form submission
- [ ] Back button after submission
- [ ] Open multiple tabs
- [ ] Mobile browser testing

**Expected Results:**
- All edge cases handled gracefully
- No crashes or data corruption
- User-friendly error messages

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 4.6: Export Functionality Testing

**Objective:** Test export at various states

**Scenario:** Generate exports and verify accuracy

**Test Steps:**
**Early Year Export:**
- [ ] Configure year and add entries for January only
- [ ] Generate PNG export
- [ ] Verify chart shows all three plan lines
- [ ] Verify actual line shows January data only
- [ ] Verify summary statistics accurate
- [ ] Generate PDF export
- [ ] Verify PDF opens correctly

**Mid-Year Export:**
- [ ] Add entries through June
- [ ] Generate exports
- [ ] Verify cumulative actual line accurate
- [ ] Verify projection calculation correct
- [ ] Verify all months displayed

**End-of-Year Export:**
- [ ] Add entries for full year
- [ ] Generate exports
- [ ] Verify final totals correct
- [ ] Verify comparison to plans accurate

**Edge Cases:**
- [ ] Export with exactly target met
- [ ] Export with significantly over target
- [ ] Export with significantly under target
- [ ] Export with mid-year start
- [ ] Export during active catch-up sprint

**File Verification:**
- [ ] PNG file opens in image viewer
- [ ] PNG has correct dimensions
- [ ] PDF file opens in PDF reader
- [ ] Filenames follow convention

**Expected Results:**
- Exports accurate at all stages
- Files download and open correctly
- Summary statistics match dashboard

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 4.7: Plan Adjustment Scenarios

**Objective:** Test mid-year plan modifications

**Scenario:** Modify plans and verify calculations update

**Test Steps:**
**Adjust Annual Target:**
- [ ] Start with 1800 hour target, entries through March
- [ ] Increase target to 2000 hours
- [ ] Verify daily targets increase appropriately
- [ ] Verify past entries unchanged
- [ ] Decrease target to 1600 hours
- [ ] Verify daily targets decrease

**Adjust Holidays:**
- [ ] Add new holiday for upcoming month
- [ ] Verify that month's target adjusts
- [ ] Remove existing holiday
- [ ] Verify target adjusts back

**Adjust Vacation:**
- [ ] Add vacation week in upcoming month
- [ ] Verify targets redistribute
- [ ] Remove vacation days
- [ ] Verify redistribution

**Adjust Intensity:**
- [ ] Change upcoming month to LIGHT
- [ ] Verify target decreases, others increase
- [ ] Change to VERY_LIGHT
- [ ] Verify further reduction
- [ ] Revert to NORMAL
- [ ] Verify targets normalize

**Adjust Optimistic Plan:**
- [ ] Change target date earlier
- [ ] Verify daily targets increase
- [ ] Change target date later
- [ ] Verify daily targets decrease
- [ ] Modify maintenance hours
- [ ] Verify post-target calculations update

**Expected Results:**
- All adjustments work correctly
- Historical data preserved
- Future calculations update properly

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 4.8: Stress Testing

**Objective:** Test application with large data volumes

**Scenario:** Create many entries and verify performance

**Test Steps:**
**Data Volume:**
- [ ] Create year config with all 11 US holidays
- [ ] Add 20 vacation days
- [ ] Add entries for 200+ workdays
- [ ] Verify dashboard loads quickly (<2 seconds)
- [ ] Verify monthly view loads quickly
- [ ] Verify history view handles 200+ entries
- [ ] Verify export generates in reasonable time

**Multiple Years:**
- [ ] Create configs for 3 consecutive years
- [ ] Verify year switching works
- [ ] Verify data isolation (years don't mix)

**Database Integrity:**
- [ ] Verify no orphaned records after deletions
- [ ] Verify cascade delete works for year config
- [ ] Verify unique constraints enforced

**Expected Results:**
- Application performs well with realistic data
- No performance degradation
- Data integrity maintained

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

## Phase 5: Code Quality Review (13 Sprints)

Review every file for quality, security, and maintainability.

---

### Sprint 5.1: Models Code Review

**Objective:** Review database models for quality and correctness

**Scope:** `app/models.py` (441 lines)

**Review Checklist:**
**Structure & Organization:**
- [ ] Models are well-organized and logically grouped
- [ ] Enums defined before models that use them
- [ ] Relationships defined consistently

**Naming:**
- [ ] Model names are clear and descriptive
- [ ] Column names follow conventions
- [ ] Relationship names make sense

**Type Hints:**
- [ ] All columns have proper type hints
- [ ] Relationships have correct Mapped types
- [ ] Optional fields correctly annotated

**Relationships:**
- [ ] All foreign keys have corresponding relationships
- [ ] back_populates used consistently
- [ ] Cascade delete configured where appropriate

**Constraints:**
- [ ] Primary keys defined
- [ ] Unique constraints where needed
- [ ] Indexes on frequently queried columns
- [ ] Not null constraints where appropriate

**Default Values:**
- [ ] Reasonable defaults for all optional fields
- [ ] Timestamps use correct UTC functions

**Docstrings:**
- [ ] Each model has docstring explaining purpose
- [ ] Complex fields documented

**Security:**
- [ ] No sensitive data stored in plaintext
- [ ] No SQL injection vulnerabilities

**Acceptance Criteria:**
- All issues identified and fixed
- Models are clean and well-documented

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 5.2: Planner Service Code Review

**Objective:** Review monthly distribution algorithm

**Scope:** `app/services/planner.py` (493 lines)

**Review Checklist:**
**Function Design:**
- [ ] Each function does one thing well
- [ ] Functions are appropriately sized
- [ ] Parameters are well-named and typed
- [ ] Return types are clear

**Algorithm Correctness:**
- [ ] Intensity weights applied correctly
- [ ] Workday calculations accurate
- [ ] Proportional distribution mathematically correct
- [ ] Edge cases handled (no workdays, all light, etc.)

**Constants:**
- [ ] Magic numbers extracted to named constants
- [ ] Constants documented with purpose
- [ ] INTENSITY_WEIGHTS values correct
- [ ] MAX_DAILY_HOURS = 9.5

**Error Handling:**
- [ ] Edge cases don't cause crashes
- [ ] Invalid inputs handled gracefully
- [ ] Warnings generated for infeasible plans

**Type Hints:**
- [ ] All functions have complete type hints
- [ ] Return types accurate
- [ ] Generic types used where appropriate

**Docstrings:**
- [ ] All functions have docstrings
- [ ] Parameters documented
- [ ] Return values documented
- [ ] Examples provided where helpful

**Performance:**
- [ ] No unnecessary iterations
- [ ] Sets used for O(1) lookups
- [ ] No N+1 query patterns

**Acceptance Criteria:**
- Algorithm is correct and well-documented
- All issues fixed

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 5.3: Calculator Service Code Review

**Objective:** Review daily target calculation logic

**Scope:** `app/services/calculator.py` (499 lines)

**Review Checklist:**
**Function Design:**
- [ ] Functions are focused and single-purpose
- [ ] Long functions broken into helpers
- [ ] Parameters minimize coupling

**Algorithm Correctness:**
- [ ] Daily target = remaining / remaining workdays
- [ ] 9.5 hour cap enforced correctly
- [ ] Status thresholds correct (5, 15 hours)
- [ ] Hours banked calculation correct
- [ ] Expected hours calculation correct

**Mid-Year Handling:**
- [ ] start_date respected in all calculations
- [ ] Historical hours included correctly
- [ ] Months before start excluded

**Constants:**
- [ ] SLIGHTLY_BEHIND_THRESHOLD = 5.0
- [ ] CATCH_UP_THRESHOLD = 15.0
- [ ] STATUS_LABELS are accurate

**Error Handling:**
- [ ] Division by zero prevented
- [ ] Missing data handled gracefully
- [ ] Future dates handled correctly

**Type Hints:**
- [ ] Complete and accurate
- [ ] Dataclasses properly typed

**Docstrings:**
- [ ] All functions documented
- [ ] Complex logic explained

**Acceptance Criteria:**
- Calculator is correct and maintainable
- All issues fixed

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 5.4: Calendar Utils Code Review

**Objective:** Review workday calculation utilities

**Scope:** `app/services/calendar_utils.py` (216 lines)

**Review Checklist:**
**Function Design:**
- [ ] Each function is pure (no side effects)
- [ ] Functions are composable
- [ ] Parameter types are appropriate (dates, sets)

**Correctness:**
- [ ] Weekend detection correct (Sat=5, Sun=6)
- [ ] Holiday exclusion works
- [ ] Vacation exclusion works
- [ ] Range calculations inclusive/exclusive as documented

**Edge Cases:**
- [ ] Empty holiday/vacation sets
- [ ] Single day ranges
- [ ] Reversed date ranges
- [ ] Month/year boundaries
- [ ] Leap year February

**Performance:**
- [ ] Set operations O(1)
- [ ] No unnecessary iterations
- [ ] Date generation efficient

**Type Hints:**
- [ ] All parameters and returns typed
- [ ] List[date] vs set[date] used appropriately

**Docstrings:**
- [ ] All functions documented
- [ ] Edge case behavior documented

**Acceptance Criteria:**
- Utilities are correct and efficient
- All issues fixed

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 5.5: Catch-Up Service Code Review

**Objective:** Review catch-up sprint logic

**Scope:** `app/services/catchup.py` (682 lines)

**Review Checklist:**
**Function Design:**
- [ ] Preview vs. creation separated
- [ ] Progress tracking isolated
- [ ] State transitions clear

**Algorithm Correctness:**
- [ ] Hours behind calculated correctly
- [ ] Weekday/weekend targets correct
- [ ] Feasibility check at 9.5 hours
- [ ] Progress percentage accurate
- [ ] Auto-completion logic correct

**Constants:**
- [ ] MAX_WEEKEND_HOURS = 4.0
- [ ] COMFORTABLE_TARGET = 7.5
- [ ] CHALLENGING_TARGET = 9.0
- [ ] BEHIND_THRESHOLD = 3.0

**State Management:**
- [ ] Sprint status transitions valid
- [ ] REVISED status set correctly
- [ ] COMPLETED on success
- [ ] DISMISSED on cancel

**Messaging:**
- [ ] Messages are encouraging
- [ ] Difficulty levels communicated
- [ ] Progress messages motivating

**Error Handling:**
- [ ] Invalid plan type rejected
- [ ] Invalid duration rejected
- [ ] On-track users handled

**Type Hints & Docstrings:**
- [ ] Complete and accurate

**Acceptance Criteria:**
- Catch-up logic is correct and user-friendly
- All issues fixed

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 5.6: Export Service Code Review

**Objective:** Review chart generation logic

**Scope:** `app/services/export.py`

**Review Checklist:**
**Function Design:**
- [ ] Data gathering separated from rendering
- [ ] Chart generation isolated
- [ ] Export formats abstracted

**Correctness:**
- [ ] Cumulative data calculated correctly
- [ ] All three plans included
- [ ] Actual data accurate
- [ ] Projection formula correct

**Chart Quality:**
- [ ] Labels readable
- [ ] Colors distinguishable
- [ ] Legend clear
- [ ] Axis scales appropriate

**File Generation:**
- [ ] PNG format correct
- [ ] PDF format correct
- [ ] Base64 encoding correct
- [ ] File naming convention followed

**Performance:**
- [ ] Matplotlib figures closed properly
- [ ] Memory not leaked

**Error Handling:**
- [ ] Missing data handled
- [ ] Empty charts handled

**Acceptance Criteria:**
- Export produces accurate, professional output
- All issues fixed

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 5.7: Dashboard Routes Code Review

**Objective:** Review main dashboard route handler

**Scope:** `app/routes/dashboard.py`

**Review Checklist:**
**Route Design:**
- [ ] Routes follow REST conventions
- [ ] HTTP methods appropriate
- [ ] URL patterns consistent

**Data Gathering:**
- [ ] Efficient database queries
- [ ] No N+1 queries
- [ ] Required data fetched in minimal queries

**Template Context:**
- [ ] All template variables documented
- [ ] No unnecessary data passed
- [ ] Calculations done in service layer

**Error Handling:**
- [ ] Missing YearConfig redirects to setup
- [ ] Database errors handled
- [ ] User-friendly error messages

**Security:**
- [ ] No SQL injection possible
- [ ] No XSS vulnerabilities
- [ ] CSRF protection active

**Code Quality:**
- [ ] Functions focused
- [ ] No duplicate code
- [ ] Comments where needed

**Acceptance Criteria:**
- Dashboard routes are clean and secure
- All issues fixed

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 5.8: Setup Routes Code Review

**Objective:** Review setup wizard route handlers

**Scope:** `app/routes/setup.py`

**Review Checklist:**
**Route Design:**
- [ ] Wizard flow is logical
- [ ] Steps can be revisited
- [ ] Progress is tracked

**Form Handling:**
- [ ] All inputs validated
- [ ] Invalid data rejected with helpful messages
- [ ] Valid data saved correctly

**Database Operations:**
- [ ] Transactions used appropriately
- [ ] Rollback on errors
- [ ] Related records created atomically

**HTMX Integration:**
- [ ] Partial responses correct
- [ ] Full page fallbacks work
- [ ] Loading states handled

**Security:**
- [ ] Input sanitized
- [ ] Date validation prevents injection
- [ ] Integer validation on targets

**Acceptance Criteria:**
- Setup routes are robust and user-friendly
- All issues fixed

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 5.9: Entry Routes Code Review

**Objective:** Review daily entry route handlers

**Scope:** `app/routes/entries.py`

**Review Checklist:**
**Route Design:**
- [ ] CRUD operations complete
- [ ] HTTP methods correct
- [ ] Idempotency considered

**Form Handling:**
- [ ] Hours validated (non-negative, reasonable max)
- [ ] Date validated (within year)
- [ ] Duplicate entries handled (update vs. error)

**HTMX Integration:**
- [ ] Inline editing works
- [ ] Partial updates efficient
- [ ] Feedback messages displayed

**Database Operations:**
- [ ] Efficient queries
- [ ] Proper error handling

**User Experience:**
- [ ] Positive feedback on success
- [ ] Clear error messages
- [ ] Keyboard navigation works

**Acceptance Criteria:**
- Entry routes are efficient and user-friendly
- All issues fixed

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 5.10: Remaining Routes Code Review

**Objective:** Review views, catchup, and export routes

**Scope:**
- `app/routes/views.py`
- `app/routes/catchup.py`
- `app/routes/export.py`

**Review Checklist:**
**Views Routes:**
- [ ] Monthly calendar data correct
- [ ] History pagination if needed
- [ ] Navigation works

**Catch-Up Routes:**
- [ ] Preview calculation efficient
- [ ] Creation validates inputs
- [ ] State transitions handled

**Export Routes:**
- [ ] File download headers correct
- [ ] Content types appropriate
- [ ] File sizes reasonable

**Common Issues:**
- [ ] Error handling consistent
- [ ] Database session management
- [ ] Template variables complete

**Acceptance Criteria:**
- All remaining routes reviewed and fixed
- Consistency across routes

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 5.11: Application Factory Code Review

**Objective:** Review Flask application initialization

**Scope:** `app/__init__.py` (103 lines)

**Review Checklist:**
**Factory Pattern:**
- [ ] create_app() is idempotent
- [ ] Config loading correct
- [ ] Extensions initialized properly

**Blueprint Registration:**
- [ ] All blueprints registered
- [ ] URL prefixes correct
- [ ] No naming conflicts

**Error Handlers:**
- [ ] 404 handler works
- [ ] 500 handler with rollback
- [ ] Error templates exist

**CLI Commands:**
- [ ] init-db command works
- [ ] Commands registered correctly

**Security:**
- [ ] Secret key handled securely
- [ ] Debug mode off in production
- [ ] Sensitive configs from environment

**Acceptance Criteria:**
- App factory is production-ready
- All issues fixed

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 5.12: Templates Code Review

**Objective:** Review all HTML templates

**Scope:** `app/templates/` (26 files)

**Review Checklist:**
**Base Template:**
- [ ] Navigation complete
- [ ] Active state highlighting works
- [ ] Mobile responsive
- [ ] HTMX configured

**Dashboard Templates:**
- [ ] All sections present
- [ ] Data binding correct
- [ ] Loading states work

**Setup Templates:**
- [ ] Form validation displays
- [ ] Navigation between steps
- [ ] Help text clear

**Partial Templates:**
- [ ] HTMX targets correct
- [ ] IDs unique
- [ ] Swap behaviors appropriate

**Accessibility:**
- [ ] Form labels present
- [ ] ARIA attributes where needed
- [ ] Keyboard navigation

**Security:**
- [ ] All user data escaped
- [ ] No XSS vulnerabilities
- [ ] CSRF tokens in forms

**Acceptance Criteria:**
- Templates are accessible and secure
- All issues fixed

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

### Sprint 5.13: Configuration and Documentation Review

**Objective:** Final review of config and docs

**Scope:**
- `config.py`
- `run.py`
- `requirements.txt`
- `README.md`
- `CLAUDE.md`

**Review Checklist:**
**Configuration:**
- [ ] All environments defined
- [ ] Secrets configurable via env
- [ ] Defaults are safe
- [ ] Testing config isolated

**Dependencies:**
- [ ] All deps in requirements.txt
- [ ] Versions pinned appropriately
- [ ] No unused dependencies
- [ ] Security vulnerabilities checked

**Documentation:**
- [ ] README has setup instructions
- [ ] README has usage guide
- [ ] CLAUDE.md accurate for development
- [ ] Code comments accurate

**Entry Point:**
- [ ] run.py works for development
- [ ] Environment detection works

**Acceptance Criteria:**
- Project is well-documented and configurable
- Ready for production use

**Sprint Findings:** *(fill in after completing sprint)*
- Issues Found:
- Fixes Applied:
- Remaining Concerns:
- Tests Added:

---

## Summary Checklist

Before considering the review complete, verify:

**Phase 1 Complete:**
- [ ] All 10 spec sections verified
- [ ] All deviations documented
- [ ] All issues fixed

**Phase 2 Complete:**
- [ ] All 17 implementation sprints reconciled
- [ ] All acceptance criteria verified
- [ ] All test gaps documented

**Phase 3 Complete:**
- [ ] Route tests added
- [ ] Model tests added
- [ ] Edge case tests added
- [ ] Error handling tests added
- [ ] All new tests passing

**Phase 4 Complete:**
- [ ] All 8 scenarios tested end-to-end
- [ ] All bugs found are fixed
- [ ] UX issues documented

**Phase 5 Complete:**
- [ ] All 13 code modules reviewed
- [ ] All issues fixed
- [ ] Code quality verified

**Final Verification:**
- [ ] All tests pass (target: 200+)
- [ ] No warnings in test output
- [ ] Application runs without errors
- [ ] All features work as specified

---

## Instructions for Claude Code

1. **Execute sprints sequentially** within each phase
2. **Fix issues immediately** when found - don't just document
3. **Fill in Sprint Findings** after completing each sprint
4. **Cross-reference fixes** when an issue affects multiple areas
5. **Run tests frequently** - after any code change
6. **Commit working states** - don't let fixes pile up
7. **Ask for clarification** if requirements are ambiguous
8. **Be thorough** - this is production deployment quality

The goal is **zero bugs** when the review is complete.
