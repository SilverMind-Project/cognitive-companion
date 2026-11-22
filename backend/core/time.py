"""Shared datetime helpers and SQLAlchemy types for UTC handling."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.sql.type_api import TypeEngine
from sqlalchemy.types import TypeDecorator

from backend.core.config import settings

__all__ = [
    "UTCDateTime",
    "app_day_bounds_utc",
    "from_app_timezone",
    "normalize_utc_datetime",
    "to_app_timezone",
]


def normalize_utc_datetime(value: datetime | None) -> datetime | None:
    """Return *value* as a UTC-aware datetime.

    PostgreSQL ``TIMESTAMPTZ`` columns always carry UTC offset information, so
    loaded values are already timezone-aware in the normal case.  This function
    acts as a safety net for server-default values (e.g. ``now()``) that
    SQLAlchemy may surface as naive datetimes before the ORM type processor
    runs, and for any non-ORM code paths that bypass the type decorator.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """SQLAlchemy column type that always round-trips UTC-aware datetimes.

    Maps to ``TIMESTAMPTZ`` in PostgreSQL, which stores all values as UTC
    internally and returns them with timezone offset information.

    Contract:
    - Bind values must be timezone-aware; they are normalised to UTC before
      being handed to the driver.
    - Loaded values are always returned as UTC-aware ``datetime`` objects via
      ``process_result_value``.

    This gives application code a single invariant: every ``datetime`` object
    obtained from the ORM is UTC-aware, regardless of how it was inserted.
    """

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[datetime]:
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UTCDateTime only accepts timezone-aware datetimes")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return normalize_utc_datetime(value)


def to_app_timezone(utc_dt: datetime) -> datetime:
    """Convert a UTC-aware datetime to the application timezone.

    Args:
        utc_dt: A timezone-aware datetime (UTC).

    Returns:
        The same instant expressed in the timezone configured under
        ``app.timezone`` in ``settings.yaml``.
    """
    app_tz_name = settings.as_str("app.timezone")
    app_tz = ZoneInfo(app_tz_name)
    return utc_dt.astimezone(app_tz)


def from_app_timezone(app_dt: datetime) -> datetime:
    """Convert an application-timezone datetime to UTC.

    Args:
        app_dt: A timezone-aware datetime in the application timezone.

    Returns:
        The same instant expressed as UTC.
    """
    return app_dt.astimezone(UTC)


def app_day_bounds_utc(
    date_from: date | None, date_to: date | None
) -> tuple[datetime | None, datetime | None]:
    """UTC ``[start, end)`` bounds for an inclusive range of household calendar days.

    A caregiver's "from" and "to" dates are wall-clock days in ``app.timezone``, not UTC days:
    an evening event belongs to the local day it happened on. ``end`` is the local midnight
    after ``date_to``, so callers filter with ``>= start`` and ``< end`` and lose no instant.
    Either bound is ``None`` when its date is.
    """
    app_tz = ZoneInfo(settings.as_str("app.timezone"))
    start = (
        datetime.combine(date_from, time.min, tzinfo=app_tz).astimezone(UTC)
        if date_from is not None
        else None
    )
    end = (
        datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=app_tz).astimezone(UTC)
        if date_to is not None
        else None
    )
    return start, end
