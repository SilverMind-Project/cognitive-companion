"""Unit tests for :class:`~backend.services.cts.signal_store.SignalStore`.

Uses the shared PostgreSQL fixture from conftest so no mocking is needed.
"""

from __future__ import annotations

import pytest

from backend.services.cts.signal_store import SignalStore, derive_signal_id

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
            {
                **_BASE_SIGNAL,
                "window_start": "2026-04-23T10:00:00",
                "window_end": "2026-04-23T10:30:00",
            }
        )
        assert sid > 0


# ---------------------------------------------------------------------------
# list_recent
# ---------------------------------------------------------------------------


class TestListRecent:
    @pytest.mark.asyncio
    async def test_returns_inserted_signal(self, store: SignalStore):
        await store.insert(_BASE_SIGNAL)
        results, total = await store.list_recent(window_hours=24)
        assert len(results) == 1
        assert total == 1
        assert results[0]["person_id"] == "grandma"
        assert results[0]["signal_type"] == "pacing"

    @pytest.mark.asyncio
    async def test_filter_by_person_id(self, store: SignalStore):
        await store.insert(_BASE_SIGNAL)
        await store.insert({**_BASE_SIGNAL, "person_id": "dad"})
        results, _ = await store.list_recent(person_id="grandma")
        assert all(r["person_id"] == "grandma" for r in results)

    @pytest.mark.asyncio
    async def test_filter_by_signal_type(self, store: SignalStore):
        await store.insert(_BASE_SIGNAL)
        await store.insert({**_BASE_SIGNAL, "signal_type": "sundowning"})
        results, _ = await store.list_recent(signal_type="pacing")
        assert all(r["signal_type"] == "pacing" for r in results)

    @pytest.mark.asyncio
    async def test_filter_by_severity(self, store: SignalStore):
        await store.insert(_BASE_SIGNAL)
        await store.insert({**_BASE_SIGNAL, "severity": "emergency"})
        results, _ = await store.list_recent(severity="emergency")
        assert all(r["severity"] == "emergency" for r in results)

    @pytest.mark.asyncio
    async def test_empty_when_no_signals(self, store: SignalStore):
        results, total = await store.list_recent()
        assert results == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_pagination_offset(self, store: SignalStore):
        for _ in range(5):
            await store.insert(_BASE_SIGNAL)
        results, total = await store.list_recent(window_hours=24, limit=2, offset=0)
        assert len(results) == 2
        assert total == 5
        results_p2, _ = await store.list_recent(window_hours=24, limit=2, offset=2)
        assert len(results_p2) == 2
        assert results[0]["id"] != results_p2[0]["id"]


# ---------------------------------------------------------------------------
# acknowledge
# ---------------------------------------------------------------------------


_EXPERIMENTAL_SIGNAL: dict = {
    **_BASE_SIGNAL,
    "signal_type": "agitation_index",
    "evidence_grade": "experimental",
}


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
        results, _ = await store.list_recent()
        assert results[0]["acknowledged_at"] is not None

    @pytest.mark.asyncio
    async def test_feedback_stored_for_experimental_signal(self, store: SignalStore):
        sid = await store.insert(_EXPERIMENTAL_SIGNAL)
        ok = await store.acknowledge(sid, feedback="accurate")
        assert ok is True
        results, _ = await store.list_recent()
        assert results[0]["feedback"] == "accurate"

    @pytest.mark.asyncio
    async def test_feedback_ignored_for_non_experimental_signal(self, store: SignalStore):
        sid = await store.insert(_BASE_SIGNAL)
        ok = await store.acknowledge(sid, feedback="accurate")
        assert ok is True
        results, _ = await store.list_recent()
        assert results[0]["feedback"] is None

    @pytest.mark.asyncio
    async def test_evidence_grade_round_trips(self, store: SignalStore):
        await store.insert(_EXPERIMENTAL_SIGNAL)
        results, _ = await store.list_recent()
        assert results[0]["evidence_grade"] == "experimental"


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


# ---------------------------------------------------------------------------
# derive_signal_id()
# ---------------------------------------------------------------------------


class TestDeriveSignalId:
    def test_golden_vector_matches_cts_producer(self):
        """Pinned UUID. The identical assertion exists in the CTS suite
        (tracking-orchestrator/tests/test_dementia_signals.py::
        TestStableSignalIdVector) so the two derivations cannot drift
        silently.
        """
        result = derive_signal_id(
            "amma", "pacing", "2026-07-01T10:00:00+00:00", "2026-07-01T10:30:00+00:00"
        )
        assert result == "9c66218f-54ac-5ee4-bf71-4c3d6e1f4a24"

    def test_differs_by_identity(self):
        window_start = "2026-07-01T10:00:00+00:00"
        window_end = "2026-07-01T10:30:00+00:00"
        a = derive_signal_id("amma", "pacing", window_start, window_end)
        b = derive_signal_id("grandma", "pacing", window_start, window_end)
        assert a != b

    def test_is_deterministic(self):
        window_start = "2026-07-01T10:00:00+00:00"
        window_end = "2026-07-01T10:30:00+00:00"
        a = derive_signal_id("amma", "pacing", window_start, window_end)
        b = derive_signal_id("amma", "pacing", window_start, window_end)
        assert a == b
