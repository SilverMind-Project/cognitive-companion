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
from backend.core.time import UTCDateTime, normalize_utc_datetime


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
