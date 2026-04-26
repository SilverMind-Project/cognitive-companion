"""Tests for shared UTC datetime handling."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import dialect as postgresql_dialect
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base
from backend.core.time import (
    UTCDateTime,
    from_app_timezone,
    normalize_utc_datetime,
    to_app_timezone,
)


class _TimestampRow(Base):
    __tablename__ = "_test_utc_timestamp_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())


class TestNormalizeUtcDatetime:
    def test_normalizes_naive_values_to_utc(self) -> None:
        value = datetime(2026, 4, 11, 13, 30, 0)

        normalized = normalize_utc_datetime(value)

        assert normalized == datetime(2026, 4, 11, 13, 30, 0, tzinfo=UTC)

    def test_normalizes_offset_aware_values_to_utc(self) -> None:
        value = datetime(2026, 4, 11, 9, 30, 0, tzinfo=ZoneInfo("America/New_York"))

        normalized = normalize_utc_datetime(value)

        assert normalized == datetime(2026, 4, 11, 13, 30, 0, tzinfo=UTC)


class TestUTCDateTime:
    def test_sqlite_bind_param_stores_naive_utc(self) -> None:
        value = datetime(2026, 4, 11, 9, 30, 0, tzinfo=ZoneInfo("America/New_York"))

        bound = UTCDateTime().process_bind_param(value, sqlite_dialect())

        assert bound == datetime(2026, 4, 11, 13, 30, 0)
        assert bound.tzinfo is None

    def test_postgres_bind_param_stores_aware_utc(self) -> None:
        value = datetime(2026, 4, 11, 9, 30, 0, tzinfo=ZoneInfo("America/New_York"))

        bound = UTCDateTime().process_bind_param(value, postgresql_dialect())

        assert bound == datetime(2026, 4, 11, 13, 30, 0, tzinfo=UTC)

    def test_rejects_naive_bind_values(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            UTCDateTime().process_bind_param(datetime(2026, 4, 11, 13, 30, 0), sqlite_dialect())

    def test_sqlite_result_values_are_normalized_to_aware_utc(self) -> None:
        value = datetime(2026, 4, 11, 13, 30, 0)

        loaded = UTCDateTime().process_result_value(value, sqlite_dialect())

        assert loaded == datetime(2026, 4, 11, 13, 30, 0, tzinfo=UTC)

    def test_sqlite_round_trip_returns_aware_utc(self, db_session) -> None:
        original = datetime(2026, 4, 11, 9, 30, 0, tzinfo=ZoneInfo("America/New_York"))

        row = _TimestampRow(occurred_at=original)
        db_session.add(row)
        db_session.commit()
        db_session.expire_all()

        loaded = db_session.execute(select(_TimestampRow)).scalar_one()

        assert loaded.occurred_at == datetime(2026, 4, 11, 13, 30, 0, tzinfo=UTC)


class TestTimezoneConversionUtilities:
    """Test timezone conversion utilities for application timezone handling."""

    def test_to_app_timezone_converts_utc_to_configured_timezone(self) -> None:
        """Test conversion from UTC to application timezone."""
        utc_dt = datetime(2026, 4, 11, 13, 30, 0, tzinfo=UTC)

        # Assuming default app timezone is America/New_York (UTC-4 in April)
        app_dt = to_app_timezone(utc_dt)

        assert app_dt.tzinfo is not None
        assert app_dt.tzinfo.key == "America/New_York"
        assert app_dt.hour == 9  # 13:30 UTC = 09:30 EDT

    def test_from_app_timezone_converts_to_utc(self) -> None:
        """Test conversion from application timezone to UTC."""
        app_dt = datetime(2026, 4, 11, 9, 30, 0, tzinfo=ZoneInfo("America/New_York"))

        utc_dt = from_app_timezone(app_dt)

        assert utc_dt.tzinfo == UTC
        assert utc_dt == datetime(2026, 4, 11, 13, 30, 0, tzinfo=UTC)

    def test_round_trip_conversion_preserves_instant(self) -> None:
        """Test that converting UTC -> App -> UTC preserves the instant."""
        original_utc = datetime(2026, 4, 11, 13, 30, 0, tzinfo=UTC)

        app_dt = to_app_timezone(original_utc)
        back_to_utc = from_app_timezone(app_dt)

        assert back_to_utc == original_utc

    def test_to_app_timezone_with_different_timezone(self) -> None:
        """Test conversion with a different source timezone."""
        # Create a datetime in Pacific timezone
        pacific_dt = datetime(2026, 4, 11, 6, 30, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
        utc_dt = pacific_dt.astimezone(UTC)

        # Convert to app timezone (Eastern)
        app_dt = to_app_timezone(utc_dt)

        assert app_dt.hour == 9  # 06:30 PDT = 09:30 EDT


class TestDSTTransitions:
    """Test handling of Daylight Saving Time transitions."""

    def test_spring_forward_transition(self) -> None:
        """Test DST spring forward (2:00 AM -> 3:00 AM) in America/New_York.

        In 2026, DST starts on March 8 at 2:00 AM EST -> 3:00 AM EDT.
        """
        # 1:30 AM EST (before spring forward)
        before_dst = datetime(2026, 3, 8, 1, 30, 0, tzinfo=ZoneInfo("America/New_York"))
        utc_before = before_dst.astimezone(UTC)

        # 3:30 AM EDT (after spring forward, 2:30 doesn't exist)
        after_dst = datetime(2026, 3, 8, 3, 30, 0, tzinfo=ZoneInfo("America/New_York"))
        utc_after = after_dst.astimezone(UTC)

        # The UTC difference should be 1 hour (not 2) due to DST
        time_diff = utc_after - utc_before
        assert time_diff.total_seconds() == 3600  # 1 hour in seconds

    def test_fall_back_transition(self) -> None:
        """Test DST fall back (2:00 AM -> 1:00 AM) in America/New_York.

        In 2026, DST ends on November 1 at 2:00 AM EDT -> 1:00 AM EST.
        """
        # 1:30 AM EDT (before fall back, first occurrence)
        before_dst = datetime(2026, 11, 1, 1, 30, 0, tzinfo=ZoneInfo("America/New_York"), fold=0)
        utc_before = before_dst.astimezone(UTC)

        # 1:30 AM EST (after fall back, second occurrence)
        after_dst = datetime(2026, 11, 1, 1, 30, 0, tzinfo=ZoneInfo("America/New_York"), fold=1)
        utc_after = after_dst.astimezone(UTC)

        # The UTC difference should be 1 hour (same local time, different UTC)
        time_diff = utc_after - utc_before
        assert time_diff.total_seconds() == 3600  # 1 hour in seconds

    def test_utc_datetime_storage_across_dst_boundary(self, db_session) -> None:
        """Test that UTC storage correctly handles DST transitions."""
        # Store timestamps before and after DST transition
        before_dst = datetime(2026, 3, 8, 1, 30, 0, tzinfo=ZoneInfo("America/New_York"))
        after_dst = datetime(2026, 3, 8, 3, 30, 0, tzinfo=ZoneInfo("America/New_York"))

        row1 = _TimestampRow(occurred_at=before_dst)
        row2 = _TimestampRow(occurred_at=after_dst)
        db_session.add_all([row1, row2])
        db_session.commit()
        db_session.expire_all()

        # Retrieve and verify both are in UTC
        loaded_rows = db_session.execute(select(_TimestampRow).order_by(_TimestampRow.id)).scalars().all()

        assert loaded_rows[0].occurred_at.tzinfo == UTC
        assert loaded_rows[1].occurred_at.tzinfo == UTC

        # Verify the time difference is 1 hour (not 2) due to DST
        time_diff = loaded_rows[1].occurred_at - loaded_rows[0].occurred_at
        assert time_diff.total_seconds() == 3600

    def test_normalize_utc_datetime_handles_dst(self) -> None:
        """Test that normalize_utc_datetime correctly handles DST-aware datetimes."""
        # Create a datetime during DST
        summer_dt = datetime(2026, 7, 15, 12, 0, 0, tzinfo=ZoneInfo("America/New_York"))

        # Create a datetime during standard time
        winter_dt = datetime(2026, 1, 15, 12, 0, 0, tzinfo=ZoneInfo("America/New_York"))

        summer_utc = normalize_utc_datetime(summer_dt)
        winter_utc = normalize_utc_datetime(winter_dt)

        # Summer: EDT is UTC-4, so 12:00 EDT = 16:00 UTC
        assert summer_utc.hour == 16

        # Winter: EST is UTC-5, so 12:00 EST = 17:00 UTC
        assert winter_utc.hour == 17

