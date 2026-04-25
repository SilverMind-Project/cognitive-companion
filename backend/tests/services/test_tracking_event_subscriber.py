"""Unit tests for :class:`TrackingEventSubscriber` decode + handle.

We never talk to Redis here: the ``decode`` method is a pure function and
``handle`` is exercised by passing a stub writer that records calls.
"""

from __future__ import annotations

import pytest

from backend.services.cts.location_writer import LocationWriter
from backend.services.cts.tracking_event_subscriber import TrackingEventSubscriber


def _make_fields(room: str = "kitchen", identity_id: str = "grandma") -> dict:
    return {
        b"event_id": b"evt-1",
        b"camera_id": b"kitchen-1",
        b"event_time_unix_ns": b"1735305600000000000",
        b"frame_index": b"42",
        b"detection_count": b"1",
        b"minio_key": b"frames/evt-1.jpg",
        b"room_name": room.encode(),
        b"detection.0.id": b"det-0",
        b"detection.0.bbox_xmin": b"10",
        b"detection.0.bbox_ymin": b"20",
        b"detection.0.bbox_xmax": b"110",
        b"detection.0.bbox_ymax": b"220",
        b"detection.0.confidence": b"0.92",
        b"detection.0.tracklet_id": b"t-1",
        b"detection.0.global_track_id": b"gt-1",
        b"detection.0.identity_id": identity_id.encode(),
        b"detection.0.identity_confidence": b"0.87",
        b"detection.0.floor_x_mm": b"1000",
        b"detection.0.floor_y_mm": b"2000",
    }


class _StubWriter:
    def __init__(self) -> None:
        self.apply_calls: list[dict] = []

    async def apply(self, event: dict) -> list[str]:
        self.apply_calls.append(event)
        return [d["identity_id"] for d in event.get("detections", []) if d.get("identity_id")]


@pytest.fixture
def subscriber():
    writer = _StubWriter()
    sub = TrackingEventSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test",
        writer=writer,  # type: ignore[arg-type]
        ws_manager=None,
        pipeline=None,
    )
    return sub, writer


class TestDecode:
    def test_reassembles_detection_fields(self, subscriber):
        sub, _ = subscriber
        event = sub.decode(b"0-0", _make_fields())
        assert event is not None
        assert event["camera_id"] == "kitchen-1"
        assert event["room_name"] == "kitchen"
        assert len(event["detections"]) == 1
        det = event["detections"][0]
        assert det["identity_id"] == "grandma"
        assert det["bbox"] == {
            "x_min": 10,
            "y_min": 20,
            "x_max": 110,
            "y_max": 220,
        }
        assert det["identity_confidence"] == pytest.approx(0.87)

    def test_event_time_falls_back_to_now_on_zero_ns(self, subscriber):
        sub, _ = subscriber
        fields = _make_fields()
        fields[b"event_time_unix_ns"] = b"0"
        event = sub.decode(b"0-0", fields)
        assert event is not None
        assert event["event_time"]

    def test_no_room_name_becomes_none(self, subscriber):
        sub, _ = subscriber
        fields = _make_fields(room="")
        event = sub.decode(b"0-0", fields)
        assert event is not None
        assert event["room_name"] is None


class TestHandle:
    @pytest.mark.asyncio
    async def test_forwards_to_writer_and_acks(self, subscriber):
        sub, writer = subscriber
        event = sub.decode(b"0-0", _make_fields())
        assert event is not None
        ok = await sub.handle(event)
        assert ok is True
        assert writer.apply_calls
        assert writer.apply_calls[0]["camera_id"] == "kitchen-1"

    @pytest.mark.asyncio
    async def test_writer_error_returns_false(self, subscriber):
        sub, _ = subscriber

        class _BoomWriter:
            async def apply(self, _event: dict) -> list[str]:
                raise RuntimeError("db_broken")

        sub._writer = _BoomWriter()  # type: ignore[assignment]
        event = sub.decode(b"0-0", _make_fields())
        assert event is not None
        ok = await sub.handle(event)
        assert ok is False


def test_uses_in_memory_writer(db_factory):
    """End-to-end: real :class:`LocationWriter`, decoded event, assertion on state."""
    from backend.models.person import HouseholdMember
    from backend.services.cts.location_repository import SqlAlchemyLocationRepository

    db = db_factory()
    try:
        db.add(HouseholdMember(id="grandma", name="Grandma"))
        db.commit()
    finally:
        db.close()

    def _repo_factory() -> SqlAlchemyLocationRepository:
        return SqlAlchemyLocationRepository(db_factory())

    writer = LocationWriter(repo_factory=_repo_factory)
    sub = TrackingEventSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test",
        writer=writer,
        ws_manager=None,
        pipeline=None,
    )
    event = sub.decode(b"0-0", _make_fields())
    assert event is not None
    import asyncio

    result = asyncio.run(writer.apply(event))
    assert result == ["grandma"]
