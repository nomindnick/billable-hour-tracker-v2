#!/usr/bin/env python3
"""
Create sample data for demonstration and testing.

This script creates a complete year configuration with:
- 2026 year config with 1,800 hour target
- Common US holidays
- A week of vacation in July
- Monthly intensity settings (light November-December)
- Sample daily entries showing varied billing patterns
- An active catch-up sprint

Usage:
    python create_sample_data.py

The script will initialize the database if needed and create fresh sample data.
Existing data for year 2026 will be deleted first.
"""

import datetime
import random
from app import create_app, db
from app.models import (
    YearConfig,
    Holiday,
    VacationDay,
    MonthConfig,
    PlanConfig,
    DailyEntry,
    CatchUpSprint,
    IntensityLevel,
    PlanType,
    SprintStatus
)


def create_sample_data() -> None:
    """Create sample data for the 2026 billing year."""

    app = create_app('development')

    with app.app_context():
        # Create tables if they don't exist
        db.create_all()

        # Delete existing 2026 data
        existing = YearConfig.query.filter_by(year=2026).first()
        if existing:
            print("Deleting existing 2026 data...")
            db.session.delete(existing)
            db.session.commit()

        # Create year configuration
        print("Creating year configuration...")
        year_config = YearConfig(
            year=2026,
            annual_target=1800
        )
        db.session.add(year_config)
        db.session.flush()  # Get the ID

        # Add common US holidays
        print("Adding holidays...")
        holidays = [
            (datetime.date(2026, 1, 1), "New Year's Day"),
            (datetime.date(2026, 1, 19), "Martin Luther King Jr. Day"),
            (datetime.date(2026, 2, 16), "Presidents Day"),
            (datetime.date(2026, 5, 25), "Memorial Day"),
            (datetime.date(2026, 7, 3), "Independence Day (Observed)"),
            (datetime.date(2026, 9, 7), "Labor Day"),
            (datetime.date(2026, 11, 26), "Thanksgiving"),
            (datetime.date(2026, 11, 27), "Day After Thanksgiving"),
            (datetime.date(2026, 12, 24), "Christmas Eve"),
            (datetime.date(2026, 12, 25), "Christmas Day"),
            (datetime.date(2026, 12, 31), "New Year's Eve"),
        ]
        for date, name in holidays:
            holiday = Holiday(
                year_config_id=year_config.id,
                date=date,
                name=name
            )
            db.session.add(holiday)

        # Add vacation days (a week in July)
        print("Adding vacation days...")
        vacation_dates = [
            datetime.date(2026, 7, 6),
            datetime.date(2026, 7, 7),
            datetime.date(2026, 7, 8),
            datetime.date(2026, 7, 9),
            datetime.date(2026, 7, 10),
        ]
        for date in vacation_dates:
            vacation = VacationDay(
                year_config_id=year_config.id,
                date=date,
                note="Summer vacation"
            )
            db.session.add(vacation)

        # Create monthly intensity settings (light Nov-Dec)
        print("Setting monthly intensities...")
        for month in range(1, 13):
            if month == 12:
                intensity = IntensityLevel.VERY_LIGHT
            elif month == 11:
                intensity = IntensityLevel.LIGHT
            else:
                intensity = IntensityLevel.NORMAL

            month_config = MonthConfig(
                year_config_id=year_config.id,
                month=month,
                intensity=intensity
            )
            db.session.add(month_config)

        # Create plan configurations
        print("Creating plan configurations...")
        plans = [
            (PlanType.FIRM, datetime.date(2026, 12, 31), None),
            (PlanType.REALISTIC, datetime.date(2026, 12, 31), None),
            (PlanType.OPTIMISTIC, datetime.date(2026, 11, 25), 4.0),  # Target Thanksgiving
        ]
        for plan_type, target_date, maintenance_hours in plans:
            plan = PlanConfig(
                year_config_id=year_config.id,
                plan_type=plan_type,
                target_date=target_date,
                target_daily_hours_after=maintenance_hours
            )
            db.session.add(plan)

        # Create sample daily entries
        # Generate entries through Q3 2026 for a good demo experience
        print("Creating daily entries...")
        end_date = datetime.date(2026, 9, 30)  # Through end of Q3

        holiday_dates = {h.date for h in year_config.holidays}
        vacation_dates_set = {v.date for v in year_config.vacation_days}

        # Generate realistic billing pattern
        current_date = datetime.date(2026, 1, 2)  # Start Jan 2 (Jan 1 is holiday)
        total_hours = 0
        entry_count = 0

        while current_date <= end_date:
            # Skip weekends, holidays, and vacation
            if (current_date.weekday() < 5 and
                current_date not in holiday_dates and
                current_date not in vacation_dates_set):

                # Generate realistic hours (mostly 7-8, sometimes more or less)
                base_hours = 7.5
                variation = random.gauss(0, 1.5)  # Normal distribution
                hours = max(0, min(12, base_hours + variation))
                hours = round(hours * 2) / 2  # Round to nearest 0.5

                # Occasionally have very light or very heavy days
                if random.random() < 0.05:  # 5% chance of light day
                    hours = random.choice([3.0, 4.0, 4.5, 5.0])
                elif random.random() < 0.03:  # 3% chance of very heavy day
                    hours = random.choice([10.0, 10.5, 11.0])

                if hours > 0:
                    entry = DailyEntry(
                        year_config_id=year_config.id,
                        date=current_date,
                        hours_billed=hours
                    )
                    db.session.add(entry)
                    total_hours += hours
                    entry_count += 1

            current_date += datetime.timedelta(days=1)

        # Create an active catch-up sprint (if user is behind)
        print("Creating catch-up sprint...")
        sprint_start = end_date + datetime.timedelta(days=1)
        sprint_end = sprint_start + datetime.timedelta(weeks=2)

        sprint = CatchUpSprint(
            year_config_id=year_config.id,
            target_plan=PlanType.REALISTIC,
            start_date=sprint_start,
            end_date=sprint_end,
            target_hours=75.0,  # About 7.5 hours/day for 2 weeks
            status=SprintStatus.ACTIVE
        )
        db.session.add(sprint)

        db.session.commit()

        print(f"\nSample data created successfully!")
        print(f"  Year: 2026")
        print(f"  Annual target: 1,800 hours")
        print(f"  Holidays: {len(holidays)}")
        print(f"  Vacation days: {len(vacation_dates)}")
        print(f"  Daily entries: {entry_count}")
        print(f"  Total hours billed: {total_hours:.1f}")
        print(f"  Active catch-up sprint: {sprint_start} to {sprint_end}")
        print(f"\nRun 'python run.py' to start the application and view the data.")


if __name__ == "__main__":
    create_sample_data()
