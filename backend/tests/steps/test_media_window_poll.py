"""Tests for the unified media window poll step and compatibility aliases."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from backend.steps import StepRegistry
from backend.steps.base import ServiceContainer, TriggerContext
from backend.steps.builtin.media_window_poll import MediaWindowPollHandler


@dataclass
class _FakeExecution:
    id: int = 42


@dataclass
class _FakeStep:
    config_json: dict = field(default_factory=dict)


class _FakeBucketizer:
    def __init__(self, buffers: dict[str, list[dict]]) -> None:
        self._buffers = buffers
        self.eligible_only_calls: list[bool] = []

    def buffer_stats(self) -> dict[str, int]:
        return {camera_id: len(frames) for camera_id, frames in self._buffers.items()}

    def forward_buffer(
        self,
        window_id: str,
        camera_id: str,
        lookahead_s: float,
        eligible_only: bool = False,
    ) -> list[dict]:
        self.eligible_only_calls.append(eligible_only)
        frames = list(self._buffers.get(camera_id, []))
        if eligible_only:
            return [frame for frame in frames if frame.get("image_eligible")]
        return frames


class _FakeMinio:
    def __init__(self) -> None:
        self.presigned: list[str] = []

    def generate_presigned_url(self, object_name: str, expiration: int = 3600) -> str:
        self.presigned.append(object_name)
        return f"https://minio/{object_name}"

    async def async_get_object(self, object_name: str) -> bytes:
        return object_name.encode()


def _frame(
    *,
    camera_id: str = "cam-1",
    seconds_ago: float = 1.0,
    eligible: bool = True,
    identities: tuple[str, ...] = ("resident-1",),
    room_name: str = "kitchen",
) -> dict:
    return {
        "camera_id": camera_id,
        "event_time": (datetime.now(UTC) - timedelta(seconds=seconds_ago)).isoformat(),
        "room_name": room_name,
        "detections": [{"identity_id": identity_id} for identity_id in identities],
        "detection_count": len(identities),
        "minio_key": f"frames/{camera_id}/{seconds_ago}.jpg",
        "image_eligible": eligible,
    }


async def _execute(
    config: dict,
    *,
    handler: MediaWindowPollHandler | None = None,
    bucketizer: _FakeBucketizer | None = None,
    event_aggregator=None,
    minio_client=None,
) -> dict:
    result = await (handler or MediaWindowPollHandler()).execute(
        step=_FakeStep(config_json=config),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=TriggerContext(trigger_type="manual"),
        services=ServiceContainer(
            db_factory=lambda: None,
            bucketizer=bucketizer,
            event_aggregator=event_aggregator,
            minio_client=minio_client,
        ),
    )
    return result.data


def test_registry_resolves_media_window_poll() -> None:
    assert isinstance(StepRegistry.get("media_window_poll"), MediaWindowPollHandler)


def test_legacy_alias_step_types_are_unregistered() -> None:
    names = StepRegistry.type_names()
    assert "cts_window_poll" not in names
    assert "recamera_media_poll" not in names


async def test_auto_source_prefers_cts_when_bucketizer_present() -> None:
    data = await _execute(
        {"source": "auto"},
        bucketizer=_FakeBucketizer({}),
        minio_client=_FakeMinio(),
    )

    assert data["source"] == "cts"


async def test_auto_source_uses_recamera_when_no_bucketizer() -> None:
    aggregator = AsyncMock()
    aggregator.query_recent_media.return_value = []

    data = await _execute({"source": "auto"}, event_aggregator=aggregator)

    assert data["source"] == "recamera"


async def test_cts_returns_only_eligible_frames() -> None:
    bucketizer = _FakeBucketizer(
        {"cam-1": [_frame(eligible=True), _frame(seconds_ago=0.5, eligible=False)]}
    )

    data = await _execute(
        {"source": "cts", "sample_period_s": 0.2},
        bucketizer=bucketizer,
        minio_client=_FakeMinio(),
    )

    assert len(data["frames"]) == 1
    assert len(data["images"]) == 1
    assert bucketizer.eligible_only_calls == [True]


async def test_cts_downsamples_by_sample_period_s() -> None:
    bucketizer = _FakeBucketizer(
        {
            "cam-1": [
                _frame(seconds_ago=4.0),
                _frame(seconds_ago=3.5),
                _frame(seconds_ago=2.0),
            ]
        }
    )

    data = await _execute(
        {"source": "cts", "sample_period_s": 1.0, "lookback_s": 5},
        bucketizer=bucketizer,
        minio_client=_FakeMinio(),
    )

    assert len(data["frames"]) == 2


async def test_cts_caps_at_max_frames() -> None:
    bucketizer = _FakeBucketizer(
        {"cam-1": [_frame(seconds_ago=4), _frame(seconds_ago=3), _frame(seconds_ago=2)]}
    )

    data = await _execute(
        {"source": "cts", "sample_period_s": 0.2, "max_frames": 2},
        bucketizer=bucketizer,
        minio_client=_FakeMinio(),
    )

    assert len(data["frames"]) == 2
    assert len(data["images"]) == 2


async def test_cts_presigns_minio_keys_into_images() -> None:
    minio = _FakeMinio()

    data = await _execute(
        {"source": "cts"},
        bucketizer=_FakeBucketizer({"cam-1": [_frame()]}),
        minio_client=minio,
    )

    assert data["images"] == ["https://minio/frames/cam-1/1.0.jpg"]
    assert minio.presigned == ["frames/cam-1/1.0.jpg"]


async def test_cts_missing_bucketizer_returns_partial_true() -> None:
    data = await _execute({"source": "cts"}, minio_client=_FakeMinio())

    assert data["frames"] == []
    assert data["images"] == []
    assert data["partial"] is True


async def test_cts_summary_counts_detections_and_identities() -> None:
    bucketizer = _FakeBucketizer(
        {
            "cam-1": [
                _frame(seconds_ago=2, identities=("resident-1", "resident-2")),
                _frame(seconds_ago=1, identities=("resident-1",)),
            ]
        }
    )

    data = await _execute(
        {"source": "cts", "sample_period_s": 0.2},
        bucketizer=bucketizer,
        minio_client=_FakeMinio(),
    )

    assert data["summary"]["detection_count"] == 3
    assert data["summary"]["distinct_identities"] == ["resident-1", "resident-2"]
    assert data["summary"]["rooms"] == ["kitchen"]


async def test_recamera_returns_images_from_aggregator() -> None:
    aggregator = AsyncMock()
    aggregator.query_recent_media.return_value = ["https://minio/one.jpg"]

    data = await _execute(
        {"source": "recamera", "max_images": 5},
        event_aggregator=aggregator,
    )

    assert data["images"] == ["https://minio/one.jpg"]
    assert data["count"] == 1
    assert data["frames"] == []


async def test_recamera_missing_aggregator_returns_empty_partial() -> None:
    data = await _execute({"source": "recamera"})

    assert data["images"] == []
    assert data["count"] == 0
    assert data["partial"] is True


async def test_recamera_respects_sensor_and_room_filters() -> None:
    aggregator = AsyncMock()
    aggregator.query_media_by_sensor.return_value = ["https://minio/sensor.jpg"]

    sensor_data = await _execute(
        {
            "source": "recamera",
            "sensor_ids": ["sensor-1"],
            "room_names": ["kitchen"],
            "images_per_sensor": 2,
            "max_images": 4,
        },
        event_aggregator=aggregator,
    )

    assert sensor_data["cameras"] == ["sensor-1"]
    assert sensor_data["rooms"] == ["kitchen"]
    aggregator.query_media_by_sensor.assert_awaited_once_with(
        sensor_ids_ordered=["sensor-1"],
        images_per_sensor=2,
        sensor_frame_limits=None,
        max_images=4,
        since_minutes=5.0,
        chronological=True,
    )

    aggregator.reset_mock()
    aggregator.query_recent_media.return_value = ["https://minio/room.jpg"]
    await _execute(
        {"source": "recamera", "room_names": ["living room"]},
        event_aggregator=aggregator,
    )
    aggregator.query_recent_media.assert_awaited_once_with(
        sensor_ids=None,
        room_names=["living room"],
        limit=10,
        since_minutes=5.0,
    )
