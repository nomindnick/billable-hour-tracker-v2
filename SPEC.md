# Billable Hours Planner

## Overview

A personal billable hours planning and tracking application for attorneys with annual billing requirements. The app helps users create realistic billing plans, track daily progress, and recover from shortfalls without creating a demoralizing experience. Designed to run locally as a web application.

## Problem Statement

Attorneys with annual billable hour requirements (typically 1,800 hours) need to plan and track their billing throughout the year. Spreadsheets are functional but lack dynamic recalculation, multiple plan comparison, and intelligent recovery suggestions. When attorneys fall behind, they need supportive tools that help them catch up rather than tools that make them feel worse and ultimately abandon tracking entirely.

The user is a partner at a California law firm with an 1,800-hour annual requirement, quarterly bonus targets (450 hours/quarter), and a desire to balance aggressive professional goals with quality of life—particularly lighter billing during the holiday season.

## Goals & Success Criteria

- **Goal 1:** User can set up an annual billing plan in under 10 minutes, including holidays and vacation days
- **Goal 2:** Daily interaction takes under 30 seconds—open app, see today's target, enter hours billed, done
- **Goal 3:** User always knows where they stand relative to firm requirements and personal goals
- **Goal 4:** When behind, user receives actionable recovery options rather than just bad news
- **Goal 5:** User can export a professional-looking summary for meetings with firm leadership

## Target Users

Solo user application for the developer (an attorney learning Python). The primary user is a law firm partner with:
- 1,800 annual billable hour requirement
- Quarterly bonus targets (450 hours)
- Desire to front-load billing to have lighter December
- Occasional need to take extended vacation or handle slow periods
- Meetings with firm leadership where billing progress needs to be presented

Technical level: The user is a Python beginner, so the codebase should be clean, well-commented, and follow straightforward patterns.

## Core Features

### 1. Year Setup & Configuration

Users configure their billing year with:
- **Annual target:** Default 1,800, adjustable (e.g., 1,750 for a recovery year, 1,950 for bonus targeting)
- **Year selection:** Which calendar year to plan
- **Holidays:** Manual entry of firm-recognized holidays (dates when the user won't bill)
- **Vacation days:** Planned time off
- **Billing intensity by month:** Users can flag months as "normal," "light," or "very light" to account for expected slow periods or desired lighter schedules (e.g., December = "very light")

The app automatically identifies weekends as non-billing days.

### 2. Three-Plan System

The app maintains three concurrent plans, each with the same annual target but different pacing:

**Firm Requirements Plan**
- Straight linear distribution: 150 hours/month, 450 hours/quarter
- Serves as the benchmark for firm expectations and bonus eligibility
- Not dynamically adjusted—this is the fixed reference point

**Optimistic Plan**
- User-defined aggressive goal (e.g., "hit target by Thanksgiving" or "only need 5-hour days after Thanksgiving")
- Front-loads billing to create maximum holiday flexibility
- Can be adjusted mid-year if the original goal becomes unrealistic

**Realistic Plan**
- Designed to hit the annual target by December 31
- Accounts for billing intensity preferences (lighter December)
- The primary plan most users will actually follow
- Balances sustainability with goal achievement

### 3. Monthly Target Distribution

This is the core planning algorithm. The annual target gets distributed across months based on:
- Available workdays (excluding weekends, holidays, vacation)
- Billing intensity settings for each month
- The specific plan's timeline (Optimistic ends earlier, Realistic uses full year)

**Key constraint:** Daily targets should stay close to 7.5 hours and never require more than 9.5 hours. If a plan would require impossible daily targets, the app should surface this during setup.

### 4. Dynamic Daily Targets

Within each month, daily targets recalculate based on actual performance:
- **Start of month:** Daily targets set based on monthly target ÷ remaining workdays
- **After each day:** If hours billed < target, shortfall distributes across remaining days
- **Exceeding target:** Excess hours are banked as "ahead," daily targets stay the same
- **Constraint:** Recalculated daily targets cannot exceed 9.5 hours

If the math doesn't work (recovery would require 10+ hour days), the app suggests a catch-up sprint rather than showing impossible targets.

### 5. Dashboard

The primary daily interface showing:
- **Today's target** (for each plan, with Realistic emphasized)
- **Hours billed today** (if already entered)
- **This week's progress:** Hours billed vs. weekly target
- **Monthly progress:** Visual indicator of where you are in the current month's target
- **Plan status cards:** For each plan, show hours ahead/behind and what that means ("On track," "Slightly behind," "Catch-up recommended")
- **Current catch-up sprint status** (if active)

### 6. Daily Hours Entry

Simple, fast interaction:
- Single number input: total billable hours for the day
- Can edit previous days if needed (forgot to log, correction)
- After entry, dashboard immediately updates all calculations

### 7. Catch-Up Sprints

When a user falls behind (or wants to build a buffer proactively), they can create a catch-up sprint:

**Setup:**
- Select target: "Get back on track with [Realistic/Optimistic] Plan"
- Select timeframe: 1-6 weeks
- App suggests daily targets (may include modest weekend billing of 2-4 hours)
- User can adjust before accepting

**During sprint:**
- Sprint appears as a fourth plan on dashboard
- Proactive alerts if falling behind the sprint itself (e.g., "You're 3 hours behind your catch-up plan—want to revise?")

**Endings:**
- **Success:** Hit the target, sprint auto-dismisses with positive feedback
- **Revised:** User adjusts the sprint parameters to recalibrate
- **Dismissed:** User manually ends the sprint (circumstances changed)

The UX should make revision feel like a natural part of the workflow, not failure.

### 8. Plan Adjustment

Users can modify plans mid-year:
- Adjust the Optimistic plan's goal if it becomes unrealistic
- Add/remove holidays or vacation days
- Change billing intensity for upcoming months
- Adjust annual target (rare, but possible)

Changes only affect future calculations—historical data remains intact.

### 9. Export Function

Generate a downloadable visualization showing:
- All three plans' expected trajectory (line chart by month)
- Actual hours billed (overlaid on the chart)
- Summary statistics (YTD hours, current pace, projected year-end)

Output format: PDF or PNG suitable for printing or sharing in meetings.

### 10. Mid-Year Start Support

If a user starts the app mid-year:
- Enter hours already billed (either as a lump sum or by month)
- App calculates plans forward from current date
- All features work normally from that point

## Technical Architecture

### System Overview

A lightweight local web application with:
- **Backend:** Python web server handling business logic and data persistence
- **Frontend:** Server-rendered HTML with minimal JavaScript for interactivity
- **Database:** SQLite file for storing configuration and daily entries
- **Export:** Server-side chart generation for PDF/PNG export

### Technology Stack

- **Language/Runtime:** Python 3.11+
- **Framework:** Flask (simple, well-documented, beginner-friendly)
- **Database:** SQLite via SQLAlchemy ORM
- **Frontend:** Jinja2 templates + HTMX for dynamic updates without complex JavaScript
- **CSS:** Tailwind CSS via CDN for clean, modern styling without build steps
- **Charts:** Matplotlib or Plotly for export generation; Chart.js for dashboard visualizations
- **PDF Export:** WeasyPrint or similar for PDF generation

### Data Model

**YearConfig**
- `id`: Primary key
- `year`: Integer (e.g., 2025)
- `annual_target`: Integer (default 1800)
- `created_at`: Timestamp
- `updated_at`: Timestamp

**Holiday**
- `id`: Primary key
- `year_config_id`: Foreign key
- `date`: Date
- `name`: String (optional, e.g., "Thanksgiving")

**VacationDay**
- `id`: Primary key
- `year_config_id`: Foreign key
- `date`: Date
- `note`: String (optional)

**MonthConfig**
- `id`: Primary key
- `year_config_id`: Foreign key
- `month`: Integer (1-12)
- `intensity`: Enum ("normal", "light", "very_light")

**PlanConfig**
- `id`: Primary key
- `year_config_id`: Foreign key
- `plan_type`: Enum ("firm", "optimistic", "realistic")
- `target_date`: Date (when to hit annual target; Dec 31 for firm/realistic, earlier for optimistic)
- `target_daily_hours_after`: Float (optional, for optimistic plan "only X hours/day after target_date" mode)

**DailyEntry**
- `id`: Primary key
- `year_config_id`: Foreign key
- `date`: Date (unique per year_config)
- `hours_billed`: Float
- `created_at`: Timestamp
- `updated_at`: Timestamp

**CatchUpSprint**
- `id`: Primary key
- `year_config_id`: Foreign key
- `target_plan`: Enum ("optimistic", "realistic")
- `start_date`: Date
- `end_date`: Date
- `target_hours`: Float (total hours to bill during sprint)
- `status`: Enum ("active", "completed", "revised", "dismissed")
- `created_at`: Timestamp
- `completed_at`: Timestamp (nullable)

### Key Design Decisions

1. **Flask over FastAPI:** FastAPI is excellent but adds complexity (async, Pydantic) that isn't needed for a simple local app. Flask's synchronous model and extensive documentation make it more beginner-friendly.

2. **HTMX over React/Vue:** Keeps the frontend simple—no build step, no JavaScript framework to learn. HTMX provides the dynamic updates needed (refresh dashboard after entry) with minimal code.

3. **SQLite over PostgreSQL:** Perfect for single-user local apps. No server to run, database is just a file, easy to back up.

4. **Server-side chart generation for export:** Ensures consistent, high-quality output regardless of browser. Dashboard charts can use Chart.js for interactivity, but exports use Matplotlib/Plotly for precise control.

5. **Monthly targets as primary unit:** The algorithm distributes annual targets to months first, then calculates daily targets within months. This matches how the user thinks about billing and makes the recalculation logic cleaner.

## Constraints & Considerations

### Known Challenges

**Planning algorithm complexity:** Distributing hours across months while respecting intensity preferences and daily limits requires careful math. Edge cases include: months with many holidays, very aggressive optimistic plans, mid-year starts with large hour deficits.

**Catch-up sprint UX:** Making "revise" feel natural rather than like failure requires thoughtful copy and visual design. The app should never make the user feel bad about adjusting plans.

**Date handling:** Weekends, holidays, and the year boundary all require careful handling. Using Python's `datetime` and possibly `python-dateutil` for robust date arithmetic.

### Out of Scope

- Multi-user support or authentication
- Cloud hosting or sync (local-only for v1)
- Client/matter-level time tracking (this is about total hours only)
- Integration with firm billing systems
- Mobile-native app (web works on mobile browsers if needed)

### Security Considerations

Minimal for a local-only app. SQLite file contains only billing numbers, not client information. No authentication needed since it runs locally.

### Future Considerations

- **Cloud sync:** Could add later with a simple backend (user mentioned possible future hosting)
- **Multiple years:** Archive previous years, compare year-over-year
- **Colleague sharing:** If others want to use it, could add multi-user support
- **Notifications:** Browser notifications or daily email reminders

---

## Notes for Claude Code

### Implementation Preferences

- Write clean, well-commented code suitable for a Python beginner to learn from
- Use type hints throughout for clarity
- Follow Flask best practices (blueprints for organization, application factory pattern)
- Keep functions small and single-purpose
- Prefer explicit over clever—readability matters more than brevity

### Testing Expectations

- Unit tests for the planning algorithm (this is the most complex logic)
- Basic integration tests for key user flows
- Manual testing is fine for UI polish

### Documentation

- README with setup instructions
- Docstrings for all functions
- Comments explaining non-obvious logic, especially in the planning algorithm

### UI/UX Priorities

- **Speed:** Dashboard should load instantly, entry should be frictionless
- **Clarity:** Always obvious where you stand and what to do next
- **Encouragement:** Language should be supportive, never punishing
- **Simplicity:** Resist feature creep—every element should earn its place

### Algorithm Notes

The monthly distribution algorithm should:
1. Calculate total available workdays per month (excluding weekends, holidays, vacation)
2. Apply intensity weights (normal = 1.0, light = 0.75, very_light = 0.5 as starting points, may need tuning)
3. Distribute annual target proportionally based on weighted workdays
4. Validate that no month requires daily averages above 9.5 hours
5. If validation fails, surface to user during setup rather than silently creating impossible plans

The daily recalculation algorithm should:
1. Calculate remaining hours needed for monthly target
2. Calculate remaining workdays in month
3. If (remaining hours / remaining days) ≤ 9.5, set that as the new daily target
4. If it exceeds 9.5, cap daily target at 9.5 and flag for catch-up sprint suggestion

Banked hours (from exceeding daily targets) accumulate as "ahead" status but don't change the daily targets—this encourages continued strong performance rather than coasting.
