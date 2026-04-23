"""Unit tests for :class:`~backend.services.cts.signal_store.SignalStore`.

Uses the in-memory SQLite fixture from conftest so no mocking is needed.
"""

from __future__ import annotations

import pytest

import backend.models  # noqa: F401 — registers DementiaSignal with Base
from backend.services.cts.signal_store import SignalStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_SIGNAL: dict = {
    "person_id": "grandma",
    "signal_type": "pacing",
    "severity": "warning",
    "window_start": "2026-04-23T10:00:00+00:00",
    "window_end": "2026-04-23T10:30:00+00:00",
    "value": 7.0,
}


@pytest.fixture
def store(db_factory) -> SignalStore:
    return SignalStore(db_factory=db_factory)


# ---------------------------------------------------------------------------
# insert
# ---------------------------------------------------------------------------


class TestInsert:
    @pytest.mark.asyncio
    async def test_returns_integer_id(self, store: SignalStore):
        sid = await store.insert(_BASE_SIGNAL)
        assert isinstance(sid, int)
        assert sid > 0

    @pytest.mark.asyncio
    async def test_two_inserts_get_different_ids(self, store: SignalStore):
        id1 = await store.insert(_BASE_SIGNAL)
        id2 = await store.insert({**_BASE_SIGNAL, "signal_type": "sundowning"})
        assert id1 != id2

    @pytest.mark.asyncio
    async def test_optional_fields_accepted(self, store: SignalStore):
        sid = await store.insert(
            {**_BASE_SIGNAL, "baseline": 3.0, "z_score": 1.5, "context_json": {"room": "kitchen"}}
        )
        assert sid > 0

    @pytest.mark.asyncio
    async def test_naive_datetime_accepted(self, store: SignalStore):
        """window_start/end without timezone info should be accepted."""
        sid = await store.insert(
            {**_BASE_SIGNAL, "window_start": "2026-04-23T10:00:00", "window_end": "2026-04-23T10:30:00"}
        )
        assert sid > 0


# ---------------------------------------------------------------------------
# list_recent
# ---------------------------------------------------------------------------


class TestListRecent:
    @pytest.mark.asyncio
    async def test_returns_inserted_signal(self, store: SignalStore):
        await store.insert(_BASE_SIGNAL)
        results = await store.list_recent(window_hours=24)
        assert len(results) == 1
        assert results[0]["person_id"] == "grandma"
        assert results[0]["signal_type"] == "pacing"

    @pytest.mark.asyncio
    async def test_filter_by_person_id(self, store: SignalStore):
        await store.insert(_BASE_SIGNAL)
        await store.insert({**_BASE_SIGNAL, "person_id": "dad"})
        results = await store.list_recent(person_id="grandma")
        assert all(r["person_id"] == "grandma" for r in results)

    @pytest.mark.asyncio
    async def test_filter_by_signal_type(self, store: SignalStore):
        await store.insert(_BASE_SIGNAL)
        await store.insert({**_BASE_SIGNAL, "signal_type": "sundowning"})
        results = await store.list_recent(signal_type="pacing")
        assert all(r["signal_type"] == "pacing" for r in results)

    @pytest.mark.asyncio
    async def test_filter_by_severity(self, store: SignalStore):
        await store.insert(_BASE_SIGNAL)
        await store.insert({**_BASE_SIGNAL, "severity": "emergency"})
        results = await store.list_recent(severity="emergency")
        assert all(r["severity"] == "emergency" for r in results)

    @pytest.mark.asyncio
    async def test_empty_when_no_signals(self, store: SignalStore):
        results = await store.list_recent()
        assert results == []


# ---------------------------------------------------------------------------
# acknowledge
# ---------------------------------------------------------------------------


class TestAcknowledge:
    @pytest.mark.asyncio
    async def test_acknowledge_existing_signal(self, store: SignalStore):
        sid = await store.insert(_BASE_SIGNAL)
        ok = await store.acknowledge(sid)
        assert ok is True

    @pytest.mark.asyncio
    async def test_acknowledge_nonexistent_returns_false(self, store: SignalStore):
        ok = await store.acknowledge(99999)
        assert ok is False

    @pytest.mark.asyncio
    async def test_acknowledged_signal_has_timestamp(self, store: SignalStore):
        sid = await store.insert(_BASE_SIGNAL)
        await store.acknowledge(sid)
        results = await store.list_recent()
        assert results[0]["acknowledged_at"] is not None


# ---------------------------------------------------------------------------
# get_unacknowledged
# ---------------------------------------------------------------------------


class TestGetUnacknowledged:
    @pytest.mark.asyncio
    async def test_returns_unacknowledged(self, store: SignalStore):
        await store.insert(_BASE_SIGNAL)
        results = await store.get_unacknowledged()
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_excludes_acknowledged(self, store: SignalStore):
        sid = await store.insert(_BASE_SIGNAL)
        await store.acknowledge(sid)
        results = await store.get_unacknowledged()
        assert results == []


# ---------------------------------------------------------------------------
# get_24h_summary
# ---------------------------------------------------------------------------


class TestGet24hSummary:
    @pytest.mark.asyncio
    async def test_summary_counts_by_type(self, store: SignalStore):
        await store.insert(_BASE_SIGNAL)
        await store.insert({**_BASE_SIGNAL, "signal_type": "sundowning", "severity": "emergency"})
        summary = await store.get_24h_summary()
        assert summary["total_signals"] == 2
        assert "pacing" in summary["by_type"]
        assert "sundowning" in summary["by_type"]
        assert summary["by_type"]["sundowning"]["max_severity"] == "emergency"

    @pytest.mark.asyncio
    async def test_summary_empty_when_no_signals(self, store: SignalStore):
        summary = await store.get_24h_summary()
        assert summary["total_signals"] == 0
        assert summary["by_type"] == {}

    @pytest.mark.asyncio
    async def test_summary_filtered_by_person(self, store: SignalStore):
        await store.insert(_BASE_SIGNAL)
        await store.insert({**_BASE_SIGNAL, "person_id": "dad"})
        summary = await store.get_24h_summary(person_id="grandma")
        assert summary["total_signals"] == 1


# ---------------------------------------------------------------------------
# get_daily_trend
# ---------------------------------------------------------------------------


class TestGetDailyTrend:
    @pytest.mark.asyncio
    async def test_returns_correct_number_of_days(self, store: SignalStore):
        trend = await store.get_daily_trend("grandma", days=7)
        assert len(trend) == 7

    @pytest.mark.asyncio
    async def test_today_has_count_after_insert(self, store: SignalStore):
        await store.insert(_BASE_SIGNAL)
        trend = await store.get_daily_trend("grandma", days=1)
        assert len(trend) == 1
        assert trend[0]["count"] == 1
