"""Unit tests for WorldSnapshotPublisher ghost eviction and posture merge."""

from __future__ import annotations

from unittest.mock import AsyncMock

from backend.services.cts.world_snapshot_publisher import WorldSnapshotPublisher


def _ph_entry(
    ph_id: str,
    *,
    identity_id: str | None = None,
    posture: str = "standing",
    floor_xy_m: tuple[float, float] = (1.0, 2.0),
    last_observed_at: str = "2026-11-25T10:00:00+00:00",
) -> dict[str, object]:
    return {
        "ph_id": ph_id,
        "identity_id": identity_id,
        "posture": posture,
        "floor_xy_m": list(floor_xy_m),
        "last_observed_at": last_observed_at,
        "uncalibrated": False,
    }


def test_stale_device_free_source_is_pruned_and_empty_mark_dirty_clears() -> None:
    clock = [100.0]
    pub = WorldSnapshotPublisher(
        ws_manager=AsyncMock(),
        stale_after_s=15.0,
        monotonic=lambda: clock[0],
    )
    pub.mark_dirty("sensor:radar-bathroom-1", [_ph_entry("ph-anon")])
    pub.mark_dirty("cam-hallway", [_ph_entry("ph-cam", identity_id="alice")])
    assert {p["ph_id"] for p in pub._flatten_phs()} == {"ph-anon", "ph-cam"}

    # Emptying a camera clears immediately.
    pub.mark_dirty("cam-hallway", [])
    assert [p["ph_id"] for p in pub._flatten_phs()] == ["ph-anon"]

    # After stale_after_s without new events, the silent sensor dot is evicted.
    clock[0] = 116.0
    assert pub._flatten_phs() == []


def test_newer_device_free_observation_preserves_camera_posture() -> None:
    pub = WorldSnapshotPublisher(ws_manager=AsyncMock())
    pub.mark_dirty(
        "cam-living",
        [
            _ph_entry(
                "ph-1",
                identity_id="alice",
                posture="sitting",
                floor_xy_m=(2.0, 3.0),
                last_observed_at="2026-11-25T10:00:00+00:00",
            )
        ],
    )
    pub.mark_dirty(
        "sensor:radar-living",
        [
            _ph_entry(
                "ph-1",
                identity_id="alice",
                posture="unknown",
                floor_xy_m=(2.4, 3.2),
                last_observed_at="2026-11-25T10:00:00.500000+00:00",
            )
        ],
    )

    [merged] = pub._flatten_phs()
    assert merged["posture"] == "sitting"
    assert merged["floor_xy_m"] == [2.2, 3.1]
