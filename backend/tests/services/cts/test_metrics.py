"""Tests for CTS subscriber metrics."""

from __future__ import annotations

from backend.services.cts import metrics


class TestDementiaSignalMetrics:
    def test_received_increments(self):
        before = _sum(metrics.cts_signals_received)
        metrics.cts_signals_received.labels(signal_kind="pacing").inc()
        assert _sum(metrics.cts_signals_received) == before + 1

    def test_persisted_increments(self):
        before = _sum(metrics.cts_signals_persisted)
        metrics.cts_signals_persisted.labels(signal_kind="pacing").inc()
        assert _sum(metrics.cts_signals_persisted) == before + 1

    def test_decode_errors_increments(self):
        before = _sum(metrics.cts_signals_decode_errors)
        metrics.cts_signals_decode_errors.inc()
        assert _sum(metrics.cts_signals_decode_errors) == before + 1

    def test_dropped_increments(self):
        before = _sum(metrics.cts_signals_dropped)
        metrics.cts_signals_dropped.labels(signal_kind="absence").inc()
        assert _sum(metrics.cts_signals_dropped) == before + 1


class TestTrackingEventMetrics:
    def test_received_and_persisted(self):
        r_before = _sum(metrics.cts_events_received)
        p_before = _sum(metrics.cts_events_persisted)
        metrics.cts_events_received.labels(event_type="cam_01").inc()
        metrics.cts_events_persisted.labels(event_type="cam_01").inc()
        assert _sum(metrics.cts_events_received) == r_before + 1
        assert _sum(metrics.cts_events_persisted) == p_before + 1

    def test_decode_errors_increments(self):
        before = _sum(metrics.cts_events_decode_errors)
        metrics.cts_events_decode_errors.inc()
        assert _sum(metrics.cts_events_decode_errors) == before + 1

    def test_dropped_increments(self):
        before = _sum(metrics.cts_events_dropped)
        metrics.cts_events_dropped.labels(event_type="cam_02").inc()
        assert _sum(metrics.cts_events_dropped) == before + 1


class TestIdentityRevisionMetrics:
    def test_received_and_persisted(self):
        r_before = _sum(metrics.cts_revisions_received)
        p_before = _sum(metrics.cts_revisions_persisted)
        metrics.cts_revisions_received.inc()
        metrics.cts_revisions_persisted.inc()
        assert _sum(metrics.cts_revisions_received) == r_before + 1
        assert _sum(metrics.cts_revisions_persisted) == p_before + 1

    def test_decode_errors_increments(self):
        before = _sum(metrics.cts_revisions_decode_errors)
        metrics.cts_revisions_decode_errors.inc()
        assert _sum(metrics.cts_revisions_decode_errors) == before + 1

    def test_dropped_increments(self):
        before = _sum(metrics.cts_revisions_dropped)
        metrics.cts_revisions_dropped.inc()
        assert _sum(metrics.cts_revisions_dropped) == before + 1


def _sum(counter) -> float:
    """Sum only _total samples (not _created timestamps)."""
    total = 0.0
    for s in counter.collect():
        for m in s.samples:
            if m.name.endswith("_total"):
                total += m.value
    return total
