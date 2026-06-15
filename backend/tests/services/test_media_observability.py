"""Tests for unified media observability query behavior."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from backend.models.cts_camera import CtsCamera
from backend.models.media_cache import MediaCache
from backend.models.room import Room
from backend.models.sensor import Sensor
from backend.services.aggregation import CameraBufferState
from backend.services.media_observability import MediaObservabilityService


class _FakeAggregator:
    def __init__(self, states: list[CameraBufferState]) -> None:
        self._states = states

    def buffer_state(self) -> list[CameraBufferState]:
        return self._states


def _state(
    camera_id: str,
    origin: str,
    *,
    depth: int = 1,
    eligible: int = 2,
    dropped: int = 1,
) -> CameraBufferState:
    return CameraBufferState(
        camera_id=camera_id,
        origin=origin,
        buffer_depth=depth,
        buffer_capacity=512 if origin == "cts" else None,
        pending_flush=depth if origin == "recamera" else None,
        cooldown_remaining_seconds=1.5 if origin == "recamera" else None,
        rate_per_second=0.5,
        tokens_available=1.0,
        images_eligible_total=eligible,
        images_dropped_total=dropped,
        last_event_at="2026-06-14T12:00:00+00:00" if origin == "cts" else None,
    )


def _seed_cameras(db_factory) -> None:
    db = db_factory()
    try:
        room = Room(name="Kitchen")
        db.add(room)
        db.flush()
        db.add(
            Sensor(
                id="recamera-1",
                name="Kitchen reCamera",
                room_id=room.id,
                sensor_type="camera",
                enabled=True,
            )
        )
        db.add(
            CtsCamera(
                id="cts-1",
                name="Kitchen CTS",
                room_name="Kitchen",
                rtsp_url="rtsp://example.test/stream",
            )
        )
        db.commit()
    finally:
        db.close()


def _service(db_factory, recamera_states, cts_states) -> MediaObservabilityService:
    recamera = _FakeAggregator(recamera_states) if recamera_states is not None else None
    bucketizer = _FakeAggregator(cts_states) if cts_states is not None else None
    return MediaObservabilityService(
        db_factory=db_factory,
        event_aggregator=recamera,
        get_bucketizer=lambda: bucketizer,
        minio_client=None,
    )


def test_aggregator_state_merges_both_origins(db_factory) -> None:
    _seed_cameras(db_factory)
    service = _service(
        db_factory,
        [_state("recamera-1", "recamera")],
        [_state("cts-1", "cts")],
    )

    result = service.aggregator_state()

    assert result.total == 2
    assert {item.origin for item in result.items} == {"recamera", "cts"}


def test_aggregator_state_filters_by_origin(db_factory) -> None:
    service = _service(
        db_factory,
        [_state("recamera-1", "recamera")],
        [_state("cts-1", "cts")],
    )

    result = service.aggregator_state(origin="cts")

    assert result.total == 1
    assert result.items[0].camera_id == "cts-1"


def test_aggregator_state_filters_by_camera_id(db_factory) -> None:
    service = _service(
        db_factory,
        [_state("recamera-1", "recamera")],
        [_state("cts-1", "cts")],
    )

    result = service.aggregator_state(camera_id="recamera-1")

    assert result.total == 1
    assert result.items[0].origin == "recamera"


def test_aggregator_state_filters_by_room_name(db_factory) -> None:
    _seed_cameras(db_factory)
    service = _service(
        db_factory,
        [_state("recamera-1", "recamera")],
        [_state("cts-1", "cts")],
    )

    result = service.aggregator_state(room_name="kitchen")

    assert result.total == 2


def test_aggregator_state_query_matches_name_or_camera_id(db_factory) -> None:
    _seed_cameras(db_factory)
    service = _service(
        db_factory,
        [_state("recamera-1", "recamera")],
        [_state("cts-1", "cts")],
    )

    name_result = service.aggregator_state(query="kitchen cts")
    id_result = service.aggregator_state(query="recamera-1")

    assert [item.camera_id for item in name_result.items] == ["cts-1"]
    assert [item.camera_id for item in id_result.items] == ["recamera-1"]


def test_aggregator_state_paginates_and_reports_total(db_factory) -> None:
    service = _service(
        db_factory,
        [_state("recamera-2", "recamera"), _state("recamera-1", "recamera")],
        [_state("cts-1", "cts")],
    )

    result = service.aggregator_state(limit=1, offset=1)

    assert result.total == 3
    assert len(result.items) == 1
    assert result.items[0].camera_id == "recamera-1"


def test_aggregator_state_enriches_names_from_each_namespace(db_factory) -> None:
    _seed_cameras(db_factory)
    service = _service(
        db_factory,
        [_state("recamera-1", "recamera")],
        [_state("cts-1", "cts")],
    )

    result = service.aggregator_state()
    by_id = {item.camera_id: item for item in result.items}

    assert by_id["recamera-1"].display_name == "Kitchen reCamera"
    assert by_id["recamera-1"].room_name == "Kitchen"
    assert by_id["cts-1"].display_name == "Kitchen CTS"
    assert by_id["cts-1"].room_name == "Kitchen"


def test_aggregator_state_no_aggregators_returns_empty_and_logs(
    db_factory,
    caplog,
) -> None:
    service = _service(db_factory, None, None)

    with caplog.at_level(logging.WARNING):
        result = service.aggregator_state()

    assert result.model_dump() == {"items": [], "total": 0}
    assert "event_aggregator" in caplog.text
    assert "cts_bucketizer" in caplog.text


def test_media_buffer_returns_items_total_shape(db_factory) -> None:
    _seed_cameras(db_factory)
    now = datetime.now(UTC)
    db = db_factory()
    try:
        db.add(
            MediaCache(
                object_name="camera/image.jpg",
                presigned_url="https://old.example/image.jpg",
                sensor_id="recamera-1",
                captured_at=now,
                expires_at=now + timedelta(minutes=5),
                deleted=False,
            )
        )
        db.commit()
    finally:
        db.close()
    service = _service(
        db_factory,
        [_state("recamera-1", "recamera", depth=3)],
        [],
    )

    result = service.media_buffer()

    assert result.total == 1
    assert result.items[0].sensor_id == "recamera-1"
    assert result.items[0].buffer_pending == 3
    assert result.items[0].images[0].object_name == "camera/image.jpg"


def test_media_buffer_presign_failure_skips_image(db_factory) -> None:
    _seed_cameras(db_factory)
    now = datetime.now(UTC)
    db = db_factory()
    try:
        db.add(
            MediaCache(
                object_name="camera/broken.jpg",
                sensor_id="recamera-1",
                captured_at=now,
                expires_at=now + timedelta(minutes=5),
                deleted=False,
            )
        )
        db.commit()
    finally:
        db.close()
    minio = MagicMock()
    minio.generate_presigned_url.side_effect = RuntimeError("presign failed")
    service = MediaObservabilityService(
        db_factory=db_factory,
        event_aggregator=_FakeAggregator([]),
        get_bucketizer=lambda: None,
        minio_client=minio,
    )

    result = service.media_buffer()

    assert result.items[0].images == []
