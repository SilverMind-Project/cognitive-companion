"""End-to-end smoke test: CTS signal persistence and querying via SignalStore.

Validates the write and read paths for dementia signals through the
real PostgreSQL test container, confirming the SignalStore works
end-to-end with the database.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def signal_store(db_factory):
    from backend.services.cts.signal_store import SignalStore

    return SignalStore(db_factory)


class TestCtsSignalPersistence:
    """End-to-end: SignalStore insert + query through the test DB."""

    async def test_insert_and_query_pacing_signal(self, signal_store):
        signal_id = await signal_store.insert(
            {
                "signal_id": "sig-test-001",
                "person_id": "person-1",
                "signal_type": "pacing",
                "severity": "warning",
                "value": 1.5,
                "baseline": 0.5,
                "z_score": 2.1,
                "window_start": "2026-05-06T00:00:00+00:00",
                "window_end": "2026-05-06T01:00:00+00:00",
                "context_json": {},
            }
        )
        assert signal_id > 0

        signals, total = await signal_store.list_recent(
            person_id="person-1",
            signal_type="pacing",
            window_hours=2,
        )
        assert total == 1
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "pacing"
        assert signals[0]["severity"] == "warning"
        assert signals[0]["value"] == 1.5
        assert signals[0]["z_score"] == 2.1

    async def test_insert_multiple_signal_kinds(self, signal_store):
        for kind in ["bathroom_dwell_anomaly", "nighttime_movement", "stillness_anomaly"]:
            sid = await signal_store.insert(
                {
                    "signal_id": f"sig-{kind}",
                    "person_id": "person-1",
                    "signal_type": kind,
                    "severity": "warning",
                    "value": 2.0,
                    "window_start": "2026-05-06T00:00:00+00:00",
                    "window_end": "2026-05-06T01:00:00+00:00",
                    "context_json": {},
                }
            )
            assert sid > 0

        all_signals, total = await signal_store.list_recent(person_id="person-1", window_hours=2)
        assert total == 3
        assert len(all_signals) == 3

    async def test_query_filters_by_signal_type(self, signal_store):
        await signal_store.insert(
            {
                "signal_id": "sig-kind-a",
                "person_id": "person-1",
                "signal_type": "pacing",
                "severity": "info",
                "value": 1.0,
                "window_start": "2026-05-06T00:00:00+00:00",
                "window_end": "2026-05-06T01:00:00+00:00",
                "context_json": {},
            }
        )
        await signal_store.insert(
            {
                "signal_id": "sig-kind-b",
                "person_id": "person-1",
                "signal_type": "absence",
                "severity": "warning",
                "value": 3.0,
                "window_start": "2026-05-06T00:00:00+00:00",
                "window_end": "2026-05-06T01:00:00+00:00",
                "context_json": {},
            }
        )

        pacing, pacing_total = await signal_store.list_recent(
            person_id="person-1", signal_type="pacing", window_hours=2
        )
        absence, absence_total = await signal_store.list_recent(
            person_id="person-1", signal_type="absence", window_hours=2
        )
        assert pacing_total == 1
        assert absence_total == 1
        assert len(pacing) == 1
        assert len(absence) == 1

    async def test_query_filters_by_severity(self, signal_store):
        await signal_store.insert(
            {
                "signal_id": "sig-sev-info",
                "person_id": "person-1",
                "signal_type": "pacing",
                "severity": "info",
                "value": 1.0,
                "window_start": "2026-05-06T00:00:00+00:00",
                "window_end": "2026-05-06T01:00:00+00:00",
                "context_json": {},
            }
        )
        await signal_store.insert(
            {
                "signal_id": "sig-sev-emergency",
                "person_id": "person-1",
                "signal_type": "pacing",
                "severity": "emergency",
                "value": 5.0,
                "window_start": "2026-05-06T00:00:00+00:00",
                "window_end": "2026-05-06T01:00:00+00:00",
                "context_json": {},
            }
        )

        results, total = await signal_store.list_recent(
            person_id="person-1", signal_type="pacing", severity="emergency", window_hours=2
        )
        assert total == 1
        assert len(results) == 1
        assert results[0]["severity"] == "emergency"
