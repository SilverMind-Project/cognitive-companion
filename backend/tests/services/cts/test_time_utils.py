"""Tests for shared CTS time utilities in backend.services.cts._time."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from backend.services.cts._time import ensure_aware, ns_to_iso, parse_ts


class TestNsToIso:
    def test_positive_ns_converts_to_iso(self):
        ts_ns = int(datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC).timestamp() * 1e9)
        result = ns_to_iso(ts_ns)
        assert result.startswith("2026-05-13T12:00:00")

    def test_zero_ns_returns_now(self):
        now = datetime.now(UTC)
        result = ns_to_iso(0)
        parsed = datetime.fromisoformat(result)
        assert abs((parsed - now).total_seconds()) < 5

    def test_negative_ns_returns_now(self):
        now = datetime.now(UTC)
        result = ns_to_iso(-1)
        parsed = datetime.fromisoformat(result)
        assert abs((parsed - now).total_seconds()) < 5


class TestParseTs:
    def test_none_returns_now(self):
        now = datetime.now(UTC)
        result = parse_ts(None)
        assert abs((result - now).total_seconds()) < 5

    def test_aware_datetime_returns_unchanged(self):
        dt = datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC)
        assert parse_ts(dt) == dt

    def test_naive_datetime_becomes_utc_aware(self):
        dt = datetime(2026, 5, 13, 12, 0, 0)
        result = parse_ts(dt)
        assert result.tzinfo is not None
        assert result.tzinfo.utcoffset(result) == timedelta(0)

    def test_iso_string_parsed_and_made_aware(self):
        result = parse_ts("2026-05-13T12:00:00")
        assert result.tzinfo is not None
        assert result.hour == 12

    def test_iso_string_with_z(self):
        result = parse_ts("2026-05-13T12:00:00Z")
        assert result.hour == 12
        assert result.tzinfo is not None

    def test_iso_string_with_offset(self):
        result = parse_ts("2026-05-13T12:00:00+00:00")
        assert result.hour == 12

    def test_malformed_string_returns_now(self):
        now = datetime.now(UTC)
        result = parse_ts("not-a-date-2024")
        assert abs((result - now).total_seconds()) < 5

    def test_aware_datetime_with_offset_preserved(self):
        offset = timezone(timedelta(hours=-8))
        dt = datetime(2026, 5, 13, 12, 0, 0, tzinfo=offset)
        result = parse_ts(dt)
        assert result is dt  # already aware, returned unchanged


class TestEnsureAware:
    def test_aware_returns_unchanged(self):
        dt = datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC)
        assert ensure_aware(dt) is dt

    def test_naive_becomes_utc(self):
        dt = datetime(2026, 5, 13, 12, 0, 0)
        result = ensure_aware(dt)
        assert result.tzinfo is not None
        assert result.hour == 12
