"""Unit tests for :class:`SourceAuthority`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.services.cts.source_authority import SourceAuthority


class TestCTSSupersedes:
    def test_empty_state_accepts_cts(self) -> None:
        sa = SourceAuthority()
        assert sa.cts_supersedes(
            current_source="",
            current_updated_at=None,
            event_time=datetime.now(UTC),
        )

    def test_non_cts_state_is_overwritten(self) -> None:
        sa = SourceAuthority()
        now = datetime.now(UTC)
        assert sa.cts_supersedes(
            current_source="ha_presence",
            current_updated_at=now,
            event_time=now + timedelta(seconds=1),
        )

    def test_stale_cts_state_yields_to_fresh_event(self) -> None:
        sa = SourceAuthority(cts_lock_s=10)
        t0 = datetime.now(UTC) - timedelta(seconds=120)
        t1 = datetime.now(UTC)
        assert sa.cts_supersedes(
            current_source="cts",
            current_updated_at=t0,
            event_time=t1,
        )

    def test_recent_cts_state_rejects_out_of_order_event(self) -> None:
        sa = SourceAuthority(cts_lock_s=60)
        t0 = datetime.now(UTC)
        earlier = t0 - timedelta(seconds=5)
        assert not sa.cts_supersedes(
            current_source="cts",
            current_updated_at=t0,
            event_time=earlier,
        )

    def test_strictly_equal_event_is_rejected(self) -> None:
        sa = SourceAuthority()
        t0 = datetime.now(UTC)
        assert not sa.cts_supersedes(
            current_source="cts",
            current_updated_at=t0,
            event_time=t0,
        )
