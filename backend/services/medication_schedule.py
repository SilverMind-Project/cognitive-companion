"""Caregiver-managed medication schedules.

A change takes effect from a dose's next occurrence. Adding an 8:00 dose at noon starts tomorrow,
so today is not reported as missed, and stopping a dose that was already due today keeps today's
record intact. Entries that have taken effect end rather than change, so past reports stay true.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.exceptions import NotFoundError
from backend.core.time import UTC
from backend.models.medication import MedicationScheduleEntry
from backend.models.person import ActivitySession, ActivitySourceEnum, HouseholdMember
from backend.services.medication_adherence import LoggedDose, ScheduledDose

EVERY_DAY = (0, 1, 2, 3, 4, 5, 6)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def scheduled_doses(
    db: Session, person_id: str, day: date, tz: ZoneInfo
) -> list[ScheduledDose] | None:
    """The doses due on ``day``, or ``None`` when the person had no schedule on that day.

    An empty list means a schedule exists with nothing due that day, such as a weekday-only dose
    on a Sunday.
    """
    entries = db.scalars(
        select(MedicationScheduleEntry).where(
            MedicationScheduleEntry.person_id == person_id,
            MedicationScheduleEntry.starts_on <= day,
            (MedicationScheduleEntry.ends_on.is_(None)) | (MedicationScheduleEntry.ends_on >= day),
        )
    ).all()
    if not entries:
        return None
    return [
        ScheduledDose(
            entry_id=entry.id,
            label=entry.label,
            dose_time=entry.dose_time,
            due_at=datetime.combine(day, entry.dose_time, tzinfo=tz),
        )
        for entry in entries
        if day.weekday() in entry.days_of_week
    ]


def scheduled_doses_around(
    db: Session, person_id: str, day: date, tz: ZoneInfo
) -> list[ScheduledDose]:
    """The doses due on ``day`` and the days either side, for matching across midnight."""
    days = (day - timedelta(days=1), day, day + timedelta(days=1))
    return [dose for d in days for dose in scheduled_doses(db, person_id, d, tz) or []]


def schedule_began_at(db: Session, person_id: str) -> datetime | None:
    """When the person's schedule was first set up, or ``None`` if it never was."""
    return db.scalar(
        select(func.min(MedicationScheduleEntry.created_at)).where(
            MedicationScheduleEntry.person_id == person_id
        )
    )


def logged_doses(db: Session, person_id: str, start: datetime, end: datetime) -> list[LoggedDose]:
    """Medication sessions opened in the window, whether or not they have closed yet.

    A dose has happened once it is seen. Waiting for the session to close would delay an alert
    by its whole timeout. Only a routine completed step by step is confirmed: a camera-inferred
    session supports at most "she was at the cabinet" (DL9).
    """
    sessions = db.scalars(
        select(ActivitySession).where(
            ActivitySession.person_id == person_id,
            ActivitySession.activity_type == "medication",
            ActivitySession.status.in_(("open", "closed")),
            ActivitySession.opened_at >= start,
            ActivitySession.opened_at < end,
        )
    ).all()
    return [
        LoggedDose(
            at=session.opened_at,
            confirmed=session.source == ActivitySourceEnum.guided_companion,
            session_id=session.id,
        )
        for session in sessions
    ]


class MedicationScheduleService:
    """Reads and changes a person's schedule. The one path for the BFF and the MCP tools."""

    def __init__(
        self,
        db_factory: Callable[[], Session],
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._db_factory = db_factory
        self._now = now

    def _local_now(self) -> datetime:
        return self._now().astimezone(ZoneInfo(settings.as_str("app.timezone")))

    def _first_open_day(self, dose_time: time) -> date:
        """The first day a dose at ``dose_time`` can still be taken."""
        local = self._local_now()
        return local.date() if dose_time > local.time() else local.date() + timedelta(days=1)

    @staticmethod
    def _require_person(db: Session, person_id: str) -> None:
        if db.get(HouseholdMember, person_id) is None:
            raise NotFoundError("Household member", person_id)

    @staticmethod
    def _require_entry(db: Session, person_id: str, entry_id: int) -> MedicationScheduleEntry:
        entry = db.get(MedicationScheduleEntry, entry_id)
        if entry is None or entry.person_id != person_id or entry.ends_on is not None:
            raise NotFoundError("Medication schedule entry", entry_id)
        return entry

    def _end(self, db: Session, entry: MedicationScheduleEntry) -> date:
        """End an entry after its last dose, and return the first day free of it."""
        first_open = self._first_open_day(entry.dose_time)
        last_day = first_open - timedelta(days=1)
        if last_day < entry.starts_on:
            db.delete(entry)  # It never took effect, so there is no history to keep.
        else:
            entry.ends_on = last_day
        return first_open

    def list_entries(self, person_id: str) -> list[MedicationScheduleEntry]:
        """The person's current schedule, in time order."""
        with self._db_factory() as db:
            self._require_person(db, person_id)
            return list(
                db.scalars(
                    select(MedicationScheduleEntry)
                    .where(
                        MedicationScheduleEntry.person_id == person_id,
                        MedicationScheduleEntry.ends_on.is_(None),
                    )
                    .order_by(MedicationScheduleEntry.dose_time, MedicationScheduleEntry.id)
                ).all()
            )

    def create_entry(
        self,
        person_id: str,
        *,
        label: str,
        dose_time: time,
        days_of_week: Iterable[int] = EVERY_DAY,
    ) -> MedicationScheduleEntry:
        with self._db_factory() as db:
            self._require_person(db, person_id)
            entry = MedicationScheduleEntry(
                person_id=person_id,
                label=label,
                dose_time=dose_time,
                days_of_week=sorted(set(days_of_week)),
                starts_on=self._first_open_day(dose_time),
            )
            db.add(entry)
            db.commit()
            db.refresh(entry)
            return entry

    def update_entry(
        self,
        person_id: str,
        entry_id: int,
        *,
        label: str | None = None,
        dose_time: time | None = None,
        days_of_week: Iterable[int] | None = None,
    ) -> MedicationScheduleEntry:
        """Change an entry. The result is a new entry when the old one has already taken effect."""
        with self._db_factory() as db:
            entry = self._require_entry(db, person_id, entry_id)
            new_time = dose_time if dose_time is not None else entry.dose_time
            new_days = sorted(set(days_of_week)) if days_of_week is not None else entry.days_of_week
            new_label = label if label is not None else entry.label
            old_end = self._end(db, entry)
            replacement = MedicationScheduleEntry(
                person_id=person_id,
                label=new_label,
                dose_time=new_time,
                days_of_week=new_days,
                # Never both on one day: the old dose and its replacement are the same dose.
                starts_on=max(self._first_open_day(new_time), old_end),
            )
            db.add(replacement)
            db.commit()
            db.refresh(replacement)
            return replacement

    def remove_entry(self, person_id: str, entry_id: int) -> None:
        with self._db_factory() as db:
            self._end(db, self._require_entry(db, person_id, entry_id))
            db.commit()
