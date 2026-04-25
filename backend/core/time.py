"""Shared datetime helpers and SQLAlchemy types for UTC handling."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.sql.type_api import TypeEngine
from sqlalchemy.types import TypeDecorator

from backend.core.config import settings

__all__ = ["UTCDateTime", "from_app_timezone", "normalize_utc_datetime", "to_app_timezone"]


def normalize_utc_datetime(value: datetime | None) -> datetime | None:
    """Return *value* as a UTC-aware datetime.

    SQLite commonly round-trips ``DateTime(timezone=True)`` columns as naive
    datetimes. Throughout this codebase, those naive values are treated as UTC
    by convention.
    """

    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """SQLAlchemy column type that always round-trips aware UTC datetimes.

    SQLite does not have a native timezone-aware timestamp type, so SQLAlchemy
    round-trips ``DateTime(timezone=True)`` values as naive ``datetime``
    objects there. This type centralizes the compatibility behavior:

    - bind values must be timezone-aware
    - values are normalized to UTC before persistence
    - SQLite stores naive UTC values for lexical ordering compatibility
    - loaded values are always returned as UTC-aware datetimes

    That gives application code one invariant regardless of database backend.
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

        normalized = value.astimezone(UTC)
        if dialect.name == "sqlite":
            return normalized.replace(tzinfo=None)
        return normalized

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return normalize_utc_datetime(value)


def to_app_timezone(utc_dt: datetime) -> datetime:
    """Convert UTC datetime to application timezone.
    
    Args:
        utc_dt: A timezone-aware datetime in UTC
        
    Returns:
        The datetime converted to the application timezone configured in settings
    """
    app_tz_name = settings.get("app.timezone", "America/New_York")
    app_tz = ZoneInfo(app_tz_name)
    return utc_dt.astimezone(app_tz)


def from_app_timezone(app_dt: datetime) -> datetime:
    """Convert application timezone datetime to UTC.
    
    Args:
        app_dt: A timezone-aware datetime in the application timezone
        
    Returns:
        The datetime converted to UTC
    """
    return app_dt.astimezone(UTC)
