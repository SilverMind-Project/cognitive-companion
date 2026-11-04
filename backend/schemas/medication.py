"""HTTP schemas for medication schedules."""

from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


def _check_days(days: list[int] | None) -> list[int] | None:
    if days is not None and (not days or not set(days) <= set(range(7))):
        raise ValueError("days_of_week needs at least one day, 0 for Monday through 6 for Sunday")
    return days


def _check_time(value: time | None) -> time | None:
    if value is not None and value.tzinfo is not None:
        raise ValueError("dose_time is a wall-clock time in app.timezone, without an offset")
    return value


class MedicationEntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=128)
    dose_time: time
    days_of_week: list[int] = Field(default_factory=lambda: list(range(7)))

    _days = field_validator("days_of_week")(_check_days)
    _time = field_validator("dose_time")(_check_time)


class MedicationEntryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=128)
    dose_time: time | None = None
    days_of_week: list[int] | None = None

    _days = field_validator("days_of_week")(_check_days)
    _time = field_validator("dose_time")(_check_time)


class MedicationEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    person_id: str
    label: str
    dose_time: time
    days_of_week: list[int]
    starts_on: date

    @field_serializer("dose_time")
    def _hours_and_minutes(self, value: time) -> str:
        return value.strftime("%H:%M")


class MedicationScheduleOut(BaseModel):
    items: list[MedicationEntryOut]
    total: int
