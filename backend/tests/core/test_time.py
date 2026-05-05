"""Tests for shared UTC datetime handling."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import dialect as postgresql_dialect
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

    def test_returns_none_for_none(self) -> None:
        assert normalize_utc_datetime(None) is None


class TestUTCDateTime:
    def test_postgres_bind_param_stores_aware_utc(self) -> None:
        value = datetime(2026, 4, 11, 9, 30, 0, tzinfo=ZoneInfo("America/New_York"))

        bound = UTCDateTime().process_bind_param(value, postgresql_dialect())

        assert bound == datetime(2026, 4, 11, 13, 30, 0, tzinfo=UTC)
        assert bound.tzinfo is UTC

    def test_rejects_naive_bind_values(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            UTCDateTime().process_bind_param(datetime(2026, 4, 11, 13, 30, 0), postgresql_dialect())

    def test_result_value_normalizes_naive_to_utc(self) -> None:
        """Defensive normalisation for server defaults that may return naive values."""
        value = datetime(2026, 4, 11, 13, 30, 0)

        loaded = UTCDateTime().process_result_value(value, postgresql_dialect())

        assert loaded == datetime(2026, 4, 11, 13, 30, 0, tzinfo=UTC)

    def test_postgres_round_trip_returns_aware_utc(self, db_session) -> None:
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
        utc_dt = datetime(2026, 4, 11, 13, 30, 0, tzinfo=UTC)

        app_dt = to_app_timezone(utc_dt)

        assert app_dt.tzinfo is not None
        assert app_dt.tzinfo.key == "America/New_York"
        assert app_dt.hour == 9  # 13:30 UTC = 09:30 EDT

    def test_from_app_timezone_converts_to_utc(self) -> None:
        app_dt = datetime(2026, 4, 11, 9, 30, 0, tzinfo=ZoneInfo("America/New_York"))

        utc_dt = from_app_timezone(app_dt)

        assert utc_dt.tzinfo == UTC
        assert utc_dt == datetime(2026, 4, 11, 13, 30, 0, tzinfo=UTC)

    def test_round_trip_conversion_preserves_instant(self) -> None:
        original_utc = datetime(2026, 4, 11, 13, 30, 0, tzinfo=UTC)

        app_dt = to_app_timezone(original_utc)
        back_to_utc = from_app_timezone(app_dt)

        assert back_to_utc == original_utc

    def test_to_app_timezone_with_different_source_timezone(self) -> None:
        pacific_dt = datetime(2026, 4, 11, 6, 30, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
        utc_dt = pacific_dt.astimezone(UTC)

        app_dt = to_app_timezone(utc_dt)

        assert app_dt.hour == 9  # 06:30 PDT = 09:30 EDT


class TestDSTTransitions:
    """Test handling of Daylight Saving Time transitions."""

    def test_spring_forward_transition(self) -> None:
        """DST spring forward (2:00 AM -> 3:00 AM) in America/New_York, 2026-03-08."""
        before_dst = datetime(2026, 3, 8, 1, 30, 0, tzinfo=ZoneInfo("America/New_York"))
        after_dst = datetime(2026, 3, 8, 3, 30, 0, tzinfo=ZoneInfo("America/New_York"))

        time_diff = after_dst.astimezone(UTC) - before_dst.astimezone(UTC)
        assert time_diff.total_seconds() == 3600  # 1 hour gap due to DST

    def test_fall_back_transition(self) -> None:
        """DST fall back (2:00 AM -> 1:00 AM) in America/New_York, 2026-11-01."""
        before_dst = datetime(2026, 11, 1, 1, 30, 0, tzinfo=ZoneInfo("America/New_York"), fold=0)
        after_dst = datetime(2026, 11, 1, 1, 30, 0, tzinfo=ZoneInfo("America/New_York"), fold=1)

        time_diff = after_dst.astimezone(UTC) - before_dst.astimezone(UTC)
        assert time_diff.total_seconds() == 3600

    def test_utc_storage_across_dst_boundary(self, db_session) -> None:
        """PostgreSQL TIMESTAMPTZ stores UTC; DST boundaries are irrelevant at storage."""
        before_dst = datetime(2026, 3, 8, 1, 30, 0, tzinfo=ZoneInfo("America/New_York"))
        after_dst = datetime(2026, 3, 8, 3, 30, 0, tzinfo=ZoneInfo("America/New_York"))

        db_session.add_all([
            _TimestampRow(occurred_at=before_dst),
            _TimestampRow(occurred_at=after_dst),
        ])
        db_session.commit()
        db_session.expire_all()

        loaded = db_session.execute(select(_TimestampRow).order_by(_TimestampRow.id)).scalars().all()

        assert loaded[0].occurred_at.tzinfo == UTC
        assert loaded[1].occurred_at.tzinfo == UTC
        assert (loaded[1].occurred_at - loaded[0].occurred_at).total_seconds() == 3600

    def test_normalize_handles_dst_aware_datetimes(self) -> None:
        summer_dt = datetime(2026, 7, 15, 12, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        winter_dt = datetime(2026, 1, 15, 12, 0, 0, tzinfo=ZoneInfo("America/New_York"))

        assert normalize_utc_datetime(summer_dt).hour == 16  # EDT = UTC-4
        assert normalize_utc_datetime(winter_dt).hour == 17  # EST = UTC-5
