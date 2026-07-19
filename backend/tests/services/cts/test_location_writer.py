"""Tests for the CTS LocationWriter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.services.cts.location_repository import InMemoryLocationRepository
from backend.services.cts.location_writer import LocationWriter
from backend.services.cts.source_authority import SourceAuthority


def _make_event(
    *,
    camera_id: str = "cam-1",
    room_name: str = "living_room",
    event_time: datetime | None = None,
    detections: list[dict] | None = None,
) -> dict:
    return {
        "event_id": "evt-001",
        "camera_id": camera_id,
        "event_time": (event_time or datetime.now(UTC)).isoformat(),
        "frame_index": 1,
        "detection_count": len(detections or []),
        "minio_key": "",
        "room_name": room_name,
        "detections": detections or [],
    }


def _make_detection(
    *,
    identity_id: str = "person-1",
    ph_id: str = "gt-001",
    identity_confidence: float = 0.9,
) -> dict:
    return {
        "id": "det-1",
        "detection_id": "tl-1",
        "ph_id": ph_id,
        "identity_id": identity_id,
        "identity_confidence": identity_confidence,
        "confidence": 0.95,
        "bbox": {"x_min": 10, "y_min": 20, "x_max": 50, "y_max": 80},
        "floor_point": {"x_mm": 1000, "y_mm": 2000},
    }


class TestLocationWriter:
    @pytest.mark.asyncio
    async def test_first_room_entry(self) -> None:
        """A new person detection creates a state row and a history row."""
        repo = InMemoryLocationRepository()
        writer = LocationWriter(lambda: repo, authority=SourceAuthority())

        event = _make_event(
            detections=[_make_detection(identity_id="alice")],
        )
        touched = await writer.apply(event)

        assert touched == ["alice"]

        state = repo.get_state("alice")
        assert state is not None
        assert state.current_room_name == "living_room"
        assert state.last_sensor_id == "cts:cam-1"

        opened = repo.get_open_history_row("alice")
        assert opened is not None
        assert opened.person_id == "alice"
        assert opened.source == "cts"
        assert opened.exited_at is None

    @pytest.mark.asyncio
    async def test_room_change_closes_prior_and_opens_new(self) -> None:
        """Moving between rooms closes the old history row and opens a new one."""
        repo = InMemoryLocationRepository()
        writer = LocationWriter(lambda: repo, authority=SourceAuthority())

        t0 = datetime.now(UTC)

        # First event: kitchen
        await writer.apply(
            _make_event(
                room_name="kitchen",
                event_time=t0,
                detections=[_make_detection(identity_id="alice")],
            )
        )

        t1 = t0 + timedelta(minutes=5)
        # Second event: living_room
        await writer.apply(
            _make_event(
                room_name="living_room",
                event_time=t1,
                detections=[_make_detection(identity_id="alice")],
            )
        )

        state = repo.get_state("alice")
        assert state is not None
        assert state.current_room_name == "living_room"

        # The old kitchen history row should be closed.
        history = repo._history
        kitchen_row = next((h for h in history if h.room_name == "kitchen"), None)
        assert kitchen_row is not None
        assert kitchen_row.exited_at is not None

        living_row = next((h for h in history if h.room_name == "living_room"), None)
        assert living_row is not None
        assert living_row.exited_at is None

    @pytest.mark.asyncio
    async def test_same_room_no_new_history(self) -> None:
        """Staying in the same room does not create additional history rows."""
        repo = InMemoryLocationRepository()
        writer = LocationWriter(lambda: repo, authority=SourceAuthority())

        t0 = datetime.now(UTC)
        await writer.apply(
            _make_event(
                room_name="living_room",
                event_time=t0,
                detections=[_make_detection(identity_id="alice")],
            )
        )

        t1 = t0 + timedelta(seconds=5)
        await writer.apply(
            _make_event(
                room_name="living_room",
                event_time=t1,
                detections=[_make_detection(identity_id="alice")],
            )
        )

        # Only one history row should exist (the first entry).
        living_rows = [h for h in repo._history if h.room_name == "living_room"]
        assert len(living_rows) == 1

    @pytest.mark.asyncio
    async def test_empty_identity_skipped(self) -> None:
        """Detections without identity_id are silently skipped."""
        repo = InMemoryLocationRepository()
        writer = LocationWriter(lambda: repo, authority=SourceAuthority())

        det = _make_detection(identity_id="")
        await writer.apply(_make_event(detections=[det]))

        assert len(repo._states) == 0
        assert len(repo._history) == 0

    @pytest.mark.asyncio
    async def test_multiple_persons_in_one_event(self) -> None:
        """An event with multiple detections writes state for each person."""
        repo = InMemoryLocationRepository()
        writer = LocationWriter(lambda: repo, authority=SourceAuthority())

        await writer.apply(
            _make_event(
                detections=[
                    _make_detection(identity_id="alice", ph_id="gt-1"),
                    _make_detection(identity_id="bob", ph_id="gt-2"),
                ]
            )
        )

        assert repo.get_state("alice") is not None
        assert repo.get_state("bob") is not None
        assert repo.get_state("alice").current_room_name == "living_room"
        assert repo.get_state("bob").current_room_name == "living_room"

    @pytest.mark.asyncio
    async def test_authority_rejection_with_recent_cts_state(self) -> None:
        """CTS write is rejected when a CTS-sourced state is newer than cts_lock_s."""
        repo = InMemoryLocationRepository()
        # Set up state from another CTS camera, updated just now.
        repo.upsert_state(
            person_id="alice",
            room_name="bedroom",
            sensor_id="cts:cam-2",
            confidence=0.95,
            status="home",
        )
        prior = repo._states["alice"]
        prior.last_seen_at = datetime.now(UTC)

        # Use a stale event_time (5s ago) so it's not newer than the current state.
        stale_time = datetime.now(UTC) - timedelta(seconds=5)
        writer = LocationWriter(lambda: repo, authority=SourceAuthority())
        await writer.apply(
            _make_event(
                room_name="kitchen",
                event_time=stale_time,
                detections=[_make_detection(identity_id="alice")],
            )
        )

        # State should be unchanged — the stale CTS event is rejected.
        state = repo.get_state("alice")
        assert state.current_room_name == "bedroom"
        assert state.last_sensor_id == "cts:cam-2"

    @pytest.mark.asyncio
    async def test_cts_always_supersedes_non_cts_source(self) -> None:
        """CTS writes over non-CTS sources even if they are recent."""
        repo = InMemoryLocationRepository()
        repo.upsert_state(
            person_id="alice",
            room_name="bedroom",
            sensor_id="ha:bed_sensor",
            confidence=1.0,
            status="home",
        )
        prior = repo._states["alice"]
        prior.last_seen_at = datetime.now(UTC)

        writer = LocationWriter(lambda: repo, authority=SourceAuthority())
        await writer.apply(
            _make_event(
                room_name="kitchen",
                detections=[_make_detection(identity_id="alice")],
            )
        )

        state = repo.get_state("alice")
        assert state.current_room_name == "kitchen"
        assert state.last_sensor_id == "cts:cam-1"
