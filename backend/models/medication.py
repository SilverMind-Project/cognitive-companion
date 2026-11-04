"""A person's medication schedule: when doses are due, as caregivers set it."""

from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, Time, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base
from backend.core.time import UTCDateTime


class MedicationScheduleEntry(Base):
    """One scheduled dose time, valid between two calendar days.

    ``dose_time`` is a wall-clock time in ``app.timezone``, so it stays at 8:00 across daylight
    saving. Reports regenerate on every read, so an entry is never edited once it has taken effect:
    it ends and a new entry starts (``MedicationScheduleService``). That keeps past adherence true
    to the schedule of the day.
    """

    __tablename__ = "medication_schedule_entries"
    __table_args__ = (
        CheckConstraint(
            "ends_on IS NULL OR ends_on >= starts_on", name="ck_medication_entry_window"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("household_members.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    dose_time: Mapped[time] = mapped_column(Time(), nullable=False)
    days_of_week: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    """Python weekdays, 0 for Monday through 6 for Sunday."""
    starts_on: Mapped[date] = mapped_column(Date(), nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date(), nullable=True)
    """The last day the entry applies, inclusive. ``None`` while it is current."""
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now(), onupdate=func.now()
    )
