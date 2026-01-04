"""
Database models for the Billable Hours Planner.

This module defines the SQLAlchemy models for storing:
- Year configuration (annual target, year)
- Holidays and vacation days
- Monthly intensity settings
- Plan configurations
- Daily hour entries
- Catch-up sprints

Each model uses SQLAlchemy 2.0 style with type hints for clarity.
"""

import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import Enum, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app import db


# -----------------------------------------------------------------------------
# Enum Types
# -----------------------------------------------------------------------------

class IntensityLevel(PyEnum):
    """
    Billing intensity levels for months.

    Affects how many hours are allocated to each month:
    - normal: Full allocation (weight = 1.0)
    - light: Reduced allocation (weight = 0.75)
    - very_light: Minimal allocation (weight = 0.5)
    """
    NORMAL = "normal"
    LIGHT = "light"
    VERY_LIGHT = "very_light"


class PlanType(PyEnum):
    """
    Types of billing plans tracked by the application.

    - firm: Fixed 150 hours/month, 450/quarter - the baseline requirement
    - optimistic: Front-loaded plan to hit target early
    - realistic: Balanced plan to hit target by year-end
    """
    FIRM = "firm"
    OPTIMISTIC = "optimistic"
    REALISTIC = "realistic"


class SprintStatus(PyEnum):
    """
    Status of a catch-up sprint.

    - active: Sprint is currently in progress
    - completed: Sprint target was achieved
    - revised: Sprint was adjusted and replaced with a new one
    - dismissed: Sprint was cancelled (circumstances changed)
    """
    ACTIVE = "active"
    COMPLETED = "completed"
    REVISED = "revised"
    DISMISSED = "dismissed"


# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------

class YearConfig(db.Model):
    """
    Configuration for a billing year.

    This is the parent record that all other data relates to.
    Each year has its own configuration, holidays, plans, and entries.

    Attributes:
        id: Primary key
        year: The calendar year (e.g., 2025)
        annual_target: Total billable hours target for the year (default: 1800)
        start_date: Date user started tracking (for mid-year starts), defaults to Jan 1
        hours_pre_start: Lump sum of hours billed before start_date (optional)
        created_at: When this configuration was created
        updated_at: When this configuration was last modified
    """
    __tablename__ = "year_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(nullable=False)
    annual_target: Mapped[int] = mapped_column(default=1800)
    start_date: Mapped[Optional[datetime.date]] = mapped_column(nullable=True)
    hours_pre_start: Mapped[Optional[float]] = mapped_column(nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        default=lambda: datetime.datetime.now(datetime.UTC)
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        default=lambda: datetime.datetime.now(datetime.UTC),
        onupdate=lambda: datetime.datetime.now(datetime.UTC)
    )

    # Relationships to child tables (cascade delete when year is deleted)
    holidays: Mapped[list["Holiday"]] = relationship(
        back_populates="year_config",
        cascade="all, delete-orphan"
    )
    vacation_days: Mapped[list["VacationDay"]] = relationship(
        back_populates="year_config",
        cascade="all, delete-orphan"
    )
    month_configs: Mapped[list["MonthConfig"]] = relationship(
        back_populates="year_config",
        cascade="all, delete-orphan"
    )
    plan_configs: Mapped[list["PlanConfig"]] = relationship(
        back_populates="year_config",
        cascade="all, delete-orphan"
    )
    daily_entries: Mapped[list["DailyEntry"]] = relationship(
        back_populates="year_config",
        cascade="all, delete-orphan"
    )
    catch_up_sprints: Mapped[list["CatchUpSprint"]] = relationship(
        back_populates="year_config",
        cascade="all, delete-orphan"
    )
    historical_months: Mapped[list["HistoricalMonth"]] = relationship(
        back_populates="year_config",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<YearConfig {self.year}: {self.annual_target} hours>"


class Holiday(db.Model):
    """
    A firm-recognized holiday when no billing is expected.

    Holidays are excluded from workday calculations.

    Attributes:
        id: Primary key
        year_config_id: Foreign key to the year configuration
        date: The date of the holiday
        name: Optional name (e.g., "Thanksgiving", "Christmas")
    """
    __tablename__ = "holiday"

    id: Mapped[int] = mapped_column(primary_key=True)
    year_config_id: Mapped[int] = mapped_column(
        ForeignKey("year_config.id"),
        nullable=False
    )
    date: Mapped[datetime.date] = mapped_column(nullable=False)
    name: Mapped[Optional[str]] = mapped_column(db.String(100), nullable=True)

    # Relationship back to parent
    year_config: Mapped["YearConfig"] = relationship(back_populates="holidays")

    # Index for efficient date lookups within a year
    __table_args__ = (
        Index("ix_holiday_year_date", "year_config_id", "date"),
    )

    def __repr__(self) -> str:
        name_str = f" ({self.name})" if self.name else ""
        return f"<Holiday {self.date}{name_str}>"


class VacationDay(db.Model):
    """
    A planned vacation day when no billing is expected.

    Vacation days are excluded from workday calculations.

    Attributes:
        id: Primary key
        year_config_id: Foreign key to the year configuration
        date: The date of the vacation day
        note: Optional note (e.g., "Hawaii trip", "Kids' spring break")
    """
    __tablename__ = "vacation_day"

    id: Mapped[int] = mapped_column(primary_key=True)
    year_config_id: Mapped[int] = mapped_column(
        ForeignKey("year_config.id"),
        nullable=False
    )
    date: Mapped[datetime.date] = mapped_column(nullable=False)
    note: Mapped[Optional[str]] = mapped_column(db.String(200), nullable=True)

    # Relationship back to parent
    year_config: Mapped["YearConfig"] = relationship(back_populates="vacation_days")

    # Index for efficient date lookups within a year
    __table_args__ = (
        Index("ix_vacation_day_year_date", "year_config_id", "date"),
    )

    def __repr__(self) -> str:
        note_str = f" ({self.note})" if self.note else ""
        return f"<VacationDay {self.date}{note_str}>"


class HistoricalMonth(db.Model):
    """
    Historical hours billed for a month before the user started tracking.

    For mid-year starts, users can optionally break down their historical
    hours by month (instead of just entering a lump sum). This provides
    better visibility in reports and charts.

    Attributes:
        id: Primary key
        year_config_id: Foreign key to the year configuration
        month: Month number (1-12)
        hours_billed: Total hours billed in this historical month
        notes: Optional note (e.g., "Estimated from firm reports")
    """
    __tablename__ = "historical_month"

    id: Mapped[int] = mapped_column(primary_key=True)
    year_config_id: Mapped[int] = mapped_column(
        ForeignKey("year_config.id"),
        nullable=False
    )
    month: Mapped[int] = mapped_column(nullable=False)
    hours_billed: Mapped[float] = mapped_column(nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(db.String(200), nullable=True)

    # Relationship back to parent
    year_config: Mapped["YearConfig"] = relationship(back_populates="historical_months")

    # Each month can only have one historical entry per year
    __table_args__ = (
        UniqueConstraint(
            "year_config_id",
            "month",
            name="uq_historical_month_year_month"
        ),
        Index("ix_historical_month_year", "year_config_id"),
    )

    def __repr__(self) -> str:
        return f"<HistoricalMonth month={self.month}: {self.hours_billed} hours>"


class MonthConfig(db.Model):
    """
    Billing intensity configuration for a specific month.

    Controls how many hours are allocated to each month based on
    the intensity level (normal, light, or very_light).

    Attributes:
        id: Primary key
        year_config_id: Foreign key to the year configuration
        month: Month number (1-12)
        intensity: How heavily to load this month with hours
    """
    __tablename__ = "month_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    year_config_id: Mapped[int] = mapped_column(
        ForeignKey("year_config.id"),
        nullable=False
    )
    month: Mapped[int] = mapped_column(nullable=False)
    intensity: Mapped[IntensityLevel] = mapped_column(
        Enum(IntensityLevel),
        default=IntensityLevel.NORMAL
    )

    # Relationship back to parent
    year_config: Mapped["YearConfig"] = relationship(back_populates="month_configs")

    # Each month can only have one config per year
    __table_args__ = (
        UniqueConstraint("year_config_id", "month", name="uq_month_config_year_month"),
    )

    def __repr__(self) -> str:
        return f"<MonthConfig month={self.month} intensity={self.intensity.value}>"


class PlanConfig(db.Model):
    """
    Configuration for one of the three billing plans.

    Each year has three plans:
    - Firm: Fixed 150/month baseline (target_date = Dec 31)
    - Optimistic: Front-loaded to finish early
    - Realistic: Balanced approach considering intensity preferences

    Attributes:
        id: Primary key
        year_config_id: Foreign key to the year configuration
        plan_type: Which plan this configures (firm, optimistic, realistic)
        target_date: Date by which to hit the annual target
        target_daily_hours_after: For optimistic plan - hours/day after target date
    """
    __tablename__ = "plan_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    year_config_id: Mapped[int] = mapped_column(
        ForeignKey("year_config.id"),
        nullable=False
    )
    plan_type: Mapped[PlanType] = mapped_column(
        Enum(PlanType),
        nullable=False
    )
    target_date: Mapped[datetime.date] = mapped_column(nullable=False)
    target_daily_hours_after: Mapped[Optional[float]] = mapped_column(nullable=True)

    # Relationship back to parent
    year_config: Mapped["YearConfig"] = relationship(back_populates="plan_configs")

    # Each plan type can only have one config per year
    __table_args__ = (
        UniqueConstraint(
            "year_config_id",
            "plan_type",
            name="uq_plan_config_year_type"
        ),
    )

    def __repr__(self) -> str:
        return f"<PlanConfig {self.plan_type.value} target={self.target_date}>"


class DailyEntry(db.Model):
    """
    Record of hours billed for a specific day.

    This is the core data users enter daily.

    Attributes:
        id: Primary key
        year_config_id: Foreign key to the year configuration
        date: The date these hours were billed
        hours_billed: Number of hours billed (can be decimal, e.g., 7.5)
        created_at: When this entry was first created
        updated_at: When this entry was last modified
    """
    __tablename__ = "daily_entry"

    id: Mapped[int] = mapped_column(primary_key=True)
    year_config_id: Mapped[int] = mapped_column(
        ForeignKey("year_config.id"),
        nullable=False
    )
    date: Mapped[datetime.date] = mapped_column(nullable=False)
    hours_billed: Mapped[float] = mapped_column(nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        default=lambda: datetime.datetime.now(datetime.UTC)
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        default=lambda: datetime.datetime.now(datetime.UTC),
        onupdate=lambda: datetime.datetime.now(datetime.UTC)
    )

    # Relationship back to parent
    year_config: Mapped["YearConfig"] = relationship(back_populates="daily_entries")

    # Each date can only have one entry per year; also index date for queries
    __table_args__ = (
        UniqueConstraint(
            "year_config_id",
            "date",
            name="uq_daily_entry_year_date"
        ),
        Index("ix_daily_entry_date", "date"),
    )

    def __repr__(self) -> str:
        return f"<DailyEntry {self.date}: {self.hours_billed} hours>"


class CatchUpSprint(db.Model):
    """
    A time-limited intensive billing period to recover from being behind.

    Catch-up sprints help users get back on track with their plans
    through focused effort over 1-6 weeks.

    Attributes:
        id: Primary key
        year_config_id: Foreign key to the year configuration
        target_plan: Which plan to catch up to (optimistic or realistic)
        start_date: When the sprint begins
        end_date: When the sprint ends
        target_hours: Total hours to bill during the sprint
        status: Current state of the sprint
        created_at: When this sprint was created
        completed_at: When sprint was completed (if applicable)
    """
    __tablename__ = "catch_up_sprint"

    id: Mapped[int] = mapped_column(primary_key=True)
    year_config_id: Mapped[int] = mapped_column(
        ForeignKey("year_config.id"),
        nullable=False
    )
    # Note: Using PlanType but only "optimistic" and "realistic" are valid
    # The firm plan is fixed and doesn't support catch-up sprints
    target_plan: Mapped[PlanType] = mapped_column(
        Enum(PlanType),
        nullable=False
    )
    start_date: Mapped[datetime.date] = mapped_column(nullable=False)
    end_date: Mapped[datetime.date] = mapped_column(nullable=False)
    target_hours: Mapped[float] = mapped_column(nullable=False)
    status: Mapped[SprintStatus] = mapped_column(
        Enum(SprintStatus),
        default=SprintStatus.ACTIVE
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        default=lambda: datetime.datetime.now(datetime.UTC)
    )
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(nullable=True)

    # Relationship back to parent
    year_config: Mapped["YearConfig"] = relationship(back_populates="catch_up_sprints")

    # Index for finding active sprints quickly
    __table_args__ = (
        Index("ix_catch_up_sprint_year_status", "year_config_id", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<CatchUpSprint {self.start_date} to {self.end_date}: "
            f"{self.target_hours} hours ({self.status.value})>"
        )
