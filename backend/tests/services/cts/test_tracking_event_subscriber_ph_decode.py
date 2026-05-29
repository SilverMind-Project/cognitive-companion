"""WTR3/R3: TrackingEventSubscriber PH-native decode tests.

Tests that the subscriber decodes Detection.ph_id into local ph_id,
uses identity_snapshots (now with ph_id field after R3 rename) for identity,
and does not require identity_revisions.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from backend.integrations.proto.continuoustracking.v1 import tracking_pb2
from backend.services.cts.location_writer import LocationWriter
from backend.services.cts.tracking_event_subscriber import (
    TrackingEventSubscriber,
)

# Use a recent timestamp so the stale-event check doesn't drop them.
_NOW_NS = int(time.time() * 1e9)


def _build_event(
    camera_id: str = "cam-1",
    detections: list[dict] | None = None,
    identity_snapshots: list[dict] | None = None,
) -> tracking_pb2.TrackingEvent:
    event = tracking_pb2.TrackingEvent(
        camera_id=camera_id,
        event_time_unix_ns=_NOW_NS,
        room_name="living_room",
        event_id="evt-1",
    )
    event.frame_ref.minio_key = "frames/cam-1/001.jpg"
    event.frame_ref.frame_index = 1
    event.frame_ref.width = 1920
    event.frame_ref.height = 1080
    event.frame_ref.capture_time_unix_ns = _NOW_NS

    for det in detections or []:
        d = event.detections.add(
            detection_id=det.get("detection_id", "d-1"),
            confidence=det.get("confidence", 0.9),
            ph_id=det.get("ph_id", ""),
        )
        d.bbox.x_min = 10
        d.bbox.y_min = 20
        d.bbox.x_max = 110
        d.bbox.y_max = 220
        d.floor_point.x_mm = 1000
        d.floor_point.y_mm = 2000
        d.floor_point.calibrated = True
        d.floor_x = 1.0
        d.floor_y = 2.0

    for snap in identity_snapshots or []:
        s = event.identity_snapshots.add()
        s.ph_id = snap.get("ph_id", "")  # R3: field renamed from ph_id
        s.identity_id = snap.get("identity_id", "")
        s.top_probability = snap.get("top_probability", 0.0)
        s.posterior_entropy = snap.get("posterior_entropy", 0.0)
        s.direct_face_evidence = snap.get("direct_face_evidence", False)

    return event


@pytest.mark.asyncio
async def test_identity_snapshots_set_detection_identity():
    """Identity from identity_snapshots (field 8) is decoded into detections."""
    writer = MagicMock(spec=LocationWriter)
    writer.apply = MagicMock(return_value=[])
    subscriber = TrackingEventSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test-cc",
        writer=writer,
    )

    event = _build_event(
        detections=[
            {"detection_id": "d-1", "ph_id": "ph-aaa"},
        ],
        identity_snapshots=[
            {"ph_id": "ph-aaa", "identity_id": "alice", "top_probability": 0.9},
        ],
    )

    decoded = subscriber.decode(b"msg-1", {b"event": event.SerializeToString()})
    assert decoded is not None
    detections = decoded["detections"]
    assert len(detections) == 1
    assert detections[0]["ph_id"] == "ph-aaa"
    assert detections[0]["identity_id"] == "alice"
    assert abs(detections[0]["identity_confidence"] - 0.9) < 0.001


@pytest.mark.asyncio
async def test_ph_id_becomes_ph_id_in_local_dict():
    """The proto's Detection.ph_id field is decoded as ph_id."""
    writer = MagicMock(spec=LocationWriter)
    writer.apply = MagicMock(return_value=[])
    subscriber = TrackingEventSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test-cc",
        writer=writer,
    )

    event = _build_event(
        detections=[
            {"detection_id": "d-1", "ph_id": "ph-xyz"},
        ],
        identity_snapshots=[
            {"ph_id": "ph-xyz", "identity_id": "bob", "top_probability": 0.85},
        ],
    )

    decoded = subscriber.decode(b"msg-1", {b"event": event.SerializeToString()})
    assert decoded is not None
    det = decoded["detections"][0]
    # R3: Detection.ph_id from proto is decoded as ph_id in the local dict.
    assert det["ph_id"] == "ph-xyz"
    assert "global_track_id" not in det
    assert "tracklet_id" not in det


@pytest.mark.asyncio
async def test_no_identity_revisions_needed_for_current_identity():
    """When identity_snapshots are present, identity_revisions are not needed."""
    writer = MagicMock(spec=LocationWriter)
    writer.apply = MagicMock(return_value=[])
    subscriber = TrackingEventSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test-cc",
        writer=writer,
    )

    # Build event with NO identity_revisions (deprecated field 5), only
    # identity_snapshots (field 8).
    event = _build_event(
        detections=[
            {"detection_id": "d-1", "ph_id": "ph-1"},
        ],
        identity_snapshots=[
            {"ph_id": "ph-1", "identity_id": "carol", "top_probability": 0.95},
        ],
    )

    decoded = subscriber.decode(b"msg-1", {b"event": event.SerializeToString()})
    assert decoded is not None
    detections = decoded["detections"]
    assert detections[0]["identity_id"] == "carol"
