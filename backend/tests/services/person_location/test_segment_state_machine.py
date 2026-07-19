"""M38 Part F: segment_state_machine.decide() additions.

Same-room refresh (including the out-of-order monotonicity guard) and
TIMEOUT_TICK quiet-gap closure for observed/manual segments. Existing
inferred-dwell TIMEOUT_TICK behavior is exercised elsewhere
(``test_cts_to_signals_e2e.py``) and is untouched by this milestone.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from backend.services.person_location.segment_state_machine import (
    EventKind,
    IncomingEvent,
    decide,
)
from backend.services.person_location.types import PresenceSegment

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _open_segment(
    *,
    room_id: int = 1,
    entered_at: datetime = T0,
    last_observed_at: datetime | None = None,
    entry_source: str = "observed",
    last_source: str | None = "world_tracker",
) -> PresenceSegment:
    metadata: dict[str, object] = {}
    if last_source is not None:
        metadata["last_source"] = last_source
    return PresenceSegment(
        id=uuid4(),
        person_id="alice",
        room_id=room_id,
        entered_at=entered_at,
        exited_at=None,
        entry_source=entry_source,  # type: ignore[arg-type]
        exit_source=None,
        confidence=0.7,
        quality=0.5,
        last_observed_at=last_observed_at,
        superseded_by=None,
        metadata=metadata,
    )


class TestSameRoomRefresh:
    def test_newer_same_room_observation_refreshes_evidence(self):
        seg = _open_segment(last_observed_at=T0)
        event = IncomingEvent(
            kind=EventKind.OBSERVATION,
            person_id="alice",
            room_id=1,
            at=T0 + timedelta(seconds=10),
            confidence=0.9,
            quality=0.8,
            source="world_tracker",
        )

        decision = decide(seg, event, inferred_dwell_max_s=14400.0)

        assert not decision.writes
        assert not decision.closes
        assert len(decision.refreshes) == 1
        refreshed = decision.refreshes[0].segment
        assert refreshed.id == seg.id
        assert refreshed.last_observed_at == T0 + timedelta(seconds=10)
        assert refreshed.confidence == 0.9
        assert refreshed.quality == 0.8
        assert refreshed.metadata["last_source"] == "world_tracker"

    def test_refresh_seeds_last_source_when_absent(self):
        """A segment opened before M38 (no last_source yet) gets one from
        its first refresh."""
        seg = _open_segment(last_observed_at=T0, last_source=None)
        event = IncomingEvent(
            kind=EventKind.OBSERVATION,
            person_id="alice",
            room_id=1,
            at=T0 + timedelta(seconds=5),
            confidence=0.8,
            source="recamera_vlm",
        )

        decision = decide(seg, event, inferred_dwell_max_s=14400.0)

        assert decision.refreshes[0].segment.metadata["last_source"] == "recamera_vlm"

    def test_out_of_order_same_room_event_is_noop_not_regression(self):
        """The regression this guards: a delayed world_tracker capture-time
        event arriving after a reCamera ingest-time refresh must not move
        last_observed_at backward (advisor-flagged correctness gap)."""
        seg = _open_segment(last_observed_at=T0 + timedelta(seconds=30))
        stale_event = IncomingEvent(
            kind=EventKind.OBSERVATION,
            person_id="alice",
            room_id=1,
            at=T0 + timedelta(seconds=10),  # older than the segment's evidence
            confidence=0.99,
            source="world_tracker",
        )

        decision = decide(seg, stale_event, inferred_dwell_max_s=14400.0)

        assert not decision.refreshes
        assert not decision.writes
        assert not decision.closes

    def test_event_exactly_at_last_observed_at_is_noop(self):
        """Boundary: not strictly newer means no-op (idempotent redelivery)."""
        seg = _open_segment(last_observed_at=T0)
        event = IncomingEvent(
            kind=EventKind.OBSERVATION,
            person_id="alice",
            room_id=1,
            at=T0,
            confidence=0.9,
            source="world_tracker",
        )

        decision = decide(seg, event, inferred_dwell_max_s=14400.0)

        assert not decision.refreshes

    def test_refresh_uses_entered_at_when_last_observed_at_never_set(self):
        """A manual-opened segment has last_observed_at=None; the guard must
        fall back to entered_at rather than crashing or always-refreshing."""
        seg = _open_segment(
            entered_at=T0, last_observed_at=None, entry_source="manual", last_source="manual"
        )
        newer_event = IncomingEvent(
            kind=EventKind.OBSERVATION,
            person_id="alice",
            room_id=1,
            at=T0 + timedelta(seconds=1),
            confidence=0.8,
            source="world_tracker",
        )

        decision = decide(seg, newer_event, inferred_dwell_max_s=14400.0)

        assert len(decision.refreshes) == 1
        assert decision.refreshes[0].segment.last_observed_at == T0 + timedelta(seconds=1)


class TestQuietGapClosure:
    def test_observed_segment_closes_after_quiet_gap(self):
        seg = _open_segment(last_observed_at=T0, last_source="recamera_vlm")
        tick = IncomingEvent(
            kind=EventKind.TIMEOUT_TICK,
            person_id="alice",
            room_id=1,
            at=T0 + timedelta(seconds=2701),
            confidence=0.7,
        )

        decision = decide(seg, tick, inferred_dwell_max_s=14400.0, quiet_gap_s=2700.0)

        assert len(decision.closes) == 1
        assert decision.closes[0].exit_source == "timeout"

    def test_observed_segment_stays_open_before_quiet_gap(self):
        seg = _open_segment(last_observed_at=T0, last_source="recamera_vlm")
        tick = IncomingEvent(
            kind=EventKind.TIMEOUT_TICK,
            person_id="alice",
            room_id=1,
            at=T0 + timedelta(seconds=2699),
            confidence=0.7,
        )

        decision = decide(seg, tick, inferred_dwell_max_s=14400.0, quiet_gap_s=2700.0)

        assert not decision.closes

    def test_none_quiet_gap_means_exempt_never_ages(self):
        """manual (or any source the caller resolves to no gap) never ages here."""
        seg = _open_segment(
            entered_at=T0, last_observed_at=T0, entry_source="manual", last_source="manual"
        )
        tick = IncomingEvent(
            kind=EventKind.TIMEOUT_TICK,
            person_id="alice",
            room_id=1,
            at=T0 + timedelta(days=30),
            confidence=1.0,
        )

        decision = decide(seg, tick, inferred_dwell_max_s=14400.0, quiet_gap_s=None)

        assert not decision.closes

    def test_quiet_gap_measured_from_entered_at_when_never_refreshed(self):
        seg = _open_segment(entered_at=T0, last_observed_at=None, last_source="sensor")
        tick = IncomingEvent(
            kind=EventKind.TIMEOUT_TICK,
            person_id="alice",
            room_id=1,
            at=T0 + timedelta(seconds=1801),
            confidence=0.6,
        )

        decision = decide(seg, tick, inferred_dwell_max_s=14400.0, quiet_gap_s=1800.0)

        assert len(decision.closes) == 1

    def test_inferred_segment_ignores_quiet_gap_uses_inferred_dwell_max(self):
        """Regression guard: inferred segments must keep using
        inferred_dwell_max_s exclusively, never the passed quiet_gap_s."""
        seg = _open_segment(entered_at=T0, entry_source="inferred_transit", last_source=None)
        tick = IncomingEvent(
            kind=EventKind.TIMEOUT_TICK,
            person_id="alice",
            room_id=1,
            at=T0 + timedelta(seconds=100),
            confidence=0.5,
        )

        # quiet_gap_s=50 would close it if (wrongly) applied to an inferred
        # segment; inferred_dwell_max_s=14400 must be what actually gates it.
        decision = decide(seg, tick, inferred_dwell_max_s=14400.0, quiet_gap_s=50.0)

        assert not decision.closes
