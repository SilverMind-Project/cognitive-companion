"""Unit tests for :class:`TrackingEventSubscriber` decode + handle.

The subscriber consumes proto-encoded ``TrackingEvent`` messages off the
``tracking.events`` Redis Stream. ``decode`` is a pure function over the
raw fields dict; ``handle`` is exercised through a stub writer that
records calls.
"""

from __future__ import annotations

import time

import pytest

from backend.integrations.proto.continuoustracking.v1 import (  # type: ignore[attr-defined]
    tracking_pb2,
)
from backend.services.cts.tracking_event_subscriber import TrackingEventSubscriber


def _make_event(
    *,
    camera_id: str = "kitchen-1",
    room: str = "kitchen",
    identity_id: str = "grandma",
    confidence: float = 0.87,
    event_time_unix_ns: int = 1735305600000000000,
    capture_time_unix_ns: int = 0,
) -> tracking_pb2.TrackingEvent:
    ev = tracking_pb2.TrackingEvent(
        camera_id=camera_id,
        event_id="evt-1",
        event_time_unix_ns=event_time_unix_ns,
        room_name=room,
    )
    ev.frame_ref.minio_key = "frames/evt-1.jpg"
    ev.frame_ref.frame_index = 42
    ev.frame_ref.capture_time_unix_ns = capture_time_unix_ns
    det = ev.detections.add(
        detection_id="det-0",
        confidence=0.92,
        ph_id="gt-1",
    )
    det.bbox.x_min, det.bbox.y_min = 10, 20
    det.bbox.x_max, det.bbox.y_max = 110, 220
    det.floor_point.x_mm = 1000
    det.floor_point.y_mm = 2000
    det.floor_point.calibrated = True
    if identity_id:
        snap = ev.identity_snapshots.add()
        snap.ph_id = "gt-1"
        snap.identity_id = identity_id
        snap.top_probability = confidence
    return ev


def _proto_fields(message: tracking_pb2.TrackingEvent) -> dict[bytes, bytes]:
    return {b"event": message.SerializeToString()}


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
        consumer_id="test",  # type: ignore[arg-type]
        ws_manager=None,
        pipeline=None,
    )
    return sub, writer


class TestDecode:
    def test_decodes_proto_event(self, subscriber):
        sub, _ = subscriber
        event = sub.decode(b"0-0", _proto_fields(_make_event()))
        assert event is not None
        assert event["camera_id"] == "kitchen-1"
        assert event["room_name"] == "kitchen"
        assert event["minio_key"] == "frames/evt-1.jpg"
        assert event["frame_index"] == 42
        assert event["detection_count"] == 1

        det = event["detections"][0]
        assert det["identity_id"] == "grandma"
        assert det["identity_confidence"] == pytest.approx(0.87)
        assert det["bbox"] == {"x_min": 10, "y_min": 20, "x_max": 110, "y_max": 220}
        assert det["floor_point"] == {"x_mm": 1000, "y_mm": 2000}

    def test_event_time_falls_back_to_now_on_zero_ns(self, subscriber):
        sub, _ = subscriber
        event = sub.decode(b"0-0", _proto_fields(_make_event(event_time_unix_ns=0)))
        assert event is not None
        assert event["event_time"]

    def test_no_room_name_becomes_none(self, subscriber):
        sub, _ = subscriber
        event = sub.decode(b"0-0", _proto_fields(_make_event(room="")))
        assert event is not None
        assert event["room_name"] is None

    def test_missing_payload_returns_none(self, subscriber):
        sub, _ = subscriber
        assert sub.decode(b"0-0", {}) is None

    def test_garbage_payload_returns_none(self, subscriber):
        sub, _ = subscriber
        assert sub.decode(b"0-0", {b"event": b"not-protobuf-\xff\x01"}) is None

    def test_stale_capture_time_returns_none(self, subscriber):
        """Events with capture_time older than 30s are dropped (backlog replay guard)."""
        sub, _ = subscriber
        stale_ns = int((time.time() - 60) * 1e9)  # 60 s ago — well past the 30s gate
        assert sub.decode(b"0-0", _proto_fields(_make_event(capture_time_unix_ns=stale_ns))) is None

    def test_fresh_capture_time_passes(self, subscriber):
        """Events with a recent capture_time are decoded normally."""
        sub, _ = subscriber
        fresh_ns = int(time.time() * 1e9)
        event = sub.decode(b"0-0", _proto_fields(_make_event(capture_time_unix_ns=fresh_ns)))
        assert event is not None
        assert event["camera_id"] == "kitchen-1"

    def test_zero_capture_time_not_dropped(self, subscriber):
        """capture_time_unix_ns=0 means the field is absent; the gate must not fire."""
        sub, _ = subscriber
        event = sub.decode(b"0-0", _proto_fields(_make_event(capture_time_unix_ns=0)))
        assert event is not None


class TestHandle:
    @pytest.mark.asyncio
    async def test_forwards_to_writer_and_acks(self, subscriber):
        sub, writer = subscriber
        event = sub.decode(b"0-0", _proto_fields(_make_event()))
        assert event is not None
        ok = await sub.handle(event)
        assert ok is True



    def test_world_snapshot_omits_posterior_when_probability_is_zero(self, subscriber):
        sub, _ = subscriber
        phs = sub._build_ph_entries(
            {
                "capture_time": "2026-01-01T12:00:00Z",
                "room_name": "kitchen",
                "identity_snapshots": [
                    {"ph_id": "gt-1", "identity_id": "grandma", "top_probability": 0.0}
                ],
                "detections": [
                    {
                        "ph_id": "gt-1",
                        "floor_calibrated": True,
                        "floor_x": 1.0,
                        "floor_y": 2.0,
                    }
                ],
            }
        )

        assert phs[0]["identity_id"] == "grandma"
        assert phs[0]["posterior_top_label"] is None
        assert phs[0]["posterior_top_prob"] is None

    def test_world_snapshot_keeps_positive_posterior_probability(self, subscriber):
        sub, _ = subscriber
        phs = sub._build_ph_entries(
            {
                "capture_time": "2026-01-01T12:00:00Z",
                "room_name": "kitchen",
                "identity_snapshots": [
                    {"ph_id": "gt-1", "identity_id": "grandma", "top_probability": 0.87}
                ],
                "detections": [
                    {
                        "ph_id": "gt-1",
                        "floor_calibrated": True,
                        "floor_x": 1.0,
                        "floor_y": 2.0,
                    }
                ],
            }
        )

        assert phs[0]["posterior_top_label"] == "grandma"
        assert phs[0]["posterior_top_prob"] == pytest.approx(0.87)


class TestHandleWithBroadcast:
    """WebSocket broadcast payload contracts for cts_live_frame messages."""

    @pytest.mark.asyncio
    async def test_broadcasts_frame_url_when_minio_configured(self):
        class _StubMinio:
            def generate_presigned_url(self, key: str, expiration: int) -> str:
                return f"https://minio.example.com/{key}?exp={expiration}"

        broadcasts: list[dict] = []

        class _StubWS:
            async def broadcast(self, payload: dict) -> None:
                broadcasts.append(payload)

        writer = _StubWriter()
        sub = TrackingEventSubscriber(
            redis_url="redis://localhost:6379",
            consumer_id="test",  # type: ignore[arg-type]
            ws_manager=_StubWS(),  # type: ignore[arg-type]
            minio_client=_StubMinio(),  # type: ignore[arg-type]
        )
        event = sub.decode(b"0-0", _proto_fields(_make_event()))
        assert event is not None
        await sub.handle(event)

        # N4: cts_world_snapshot broadcast added alongside cts_live_frame
        assert len(broadcasts) >= 1
        live_msg = next((m for m in broadcasts if m["type"] == "cts_live_frame"), None)
        assert live_msg is not None
        assert live_msg["frame_url"] == "https://minio.example.com/frames/evt-1.jpg?exp=30"
        assert live_msg["minio_key"] == "frames/evt-1.jpg"

    @pytest.mark.asyncio
    async def test_broadcasts_frame_url_none_when_minio_absent(self):
        broadcasts: list[dict] = []

        class _StubWS:
            async def broadcast(self, payload: dict) -> None:
                broadcasts.append(payload)

        writer = _StubWriter()
        sub = TrackingEventSubscriber(
            redis_url="redis://localhost:6379",
            consumer_id="test",  # type: ignore[arg-type]
            ws_manager=_StubWS(),  # type: ignore[arg-type]
            minio_client=None,
        )
        event = sub.decode(b"0-0", _proto_fields(_make_event()))
        assert event is not None
        await sub.handle(event)

        # N4: cts_world_snapshot broadcast added alongside cts_live_frame
        assert len(broadcasts) >= 1
        live_msg = next((m for m in broadcasts if m["type"] == "cts_live_frame"), None)
        assert live_msg is not None
        assert live_msg["frame_url"] is None
        # minio_key is always included so the frontend proxy path works independently
        # of whether MinIO presigned URLs are configured
        assert live_msg["minio_key"] == "frames/evt-1.jpg"
