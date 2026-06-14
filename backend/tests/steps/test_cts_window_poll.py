"""Unit tests for :class:`CtsWindowPollHandler`.

Covers the success path (frames pulled from the injected CTS bucketizer), the
missing-service path (no bucketizer -> empty window, partial=True), and a
camera filter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from backend.steps.base import ServiceContainer, TriggerContext
from backend.steps.builtin.cts_window_poll import CtsWindowPollHandler


@dataclass
class _FakeExecution:
    id: int = 1


@dataclass
class _FakeStep:
    config_json: dict = field(default_factory=dict)


class _FakeBucketizer:
    """Minimal stand-in exposing the two methods the step calls."""

    def __init__(self, buffers: dict[str, list[dict]]) -> None:
        self._buffers = buffers

    def buffer_stats(self) -> dict[str, int]:
        return {cam: len(frames) for cam, frames in self._buffers.items()}

    def forward_buffer(
        self,
        window_id,
        camera_id,
        lookahead_s,
        eligible_only=False,
    ) -> list[dict]:
        frames = list(self._buffers.get(camera_id, []))
        if eligible_only:
            return [frame for frame in frames if frame.get("image_eligible")]
        return frames


class _FakeMinio:
    def generate_presigned_url(self, object_name, expiration=3600):
        return f"https://minio/{object_name}"


def _frame(camera_id: str, identity_id: str) -> dict:
    return {
        "camera_id": camera_id,
        "event_time": datetime.now(UTC).isoformat(),
        "room_name": "kitchen",
        "detections": [{"identity_id": identity_id}],
        "detection_count": 1,
        "minio_key": f"frames/{camera_id}/sample.jpg",
        "image_eligible": True,
    }


def _config(**overrides) -> dict:
    cfg = {"sample_period_s": 0.2, "lookback_s": 5, "lookahead_s": 0, "max_frames": 30}
    cfg.update(overrides)
    return cfg


async def _run(config: dict, bucketizer) -> dict:
    handler = CtsWindowPollHandler()
    services = ServiceContainer(
        db_factory=lambda: None,
        bucketizer=bucketizer,
        minio_client=_FakeMinio(),
    )
    result = await handler.execute(
        step=_FakeStep(config_json=config),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=TriggerContext(trigger_type="manual"),
        services=services,
    )
    return result.data


@pytest.mark.asyncio
async def test_returns_recent_frames_from_bucketizer():
    bucketizer = _FakeBucketizer({"cam01": [_frame("cam01", "mom")]})

    data = await _run(_config(cameras=["cam01"]), bucketizer)

    assert len(data["frames"]) == 1
    assert data["frames"][0]["minio_key"] == "frames/cam01/sample.jpg"
    assert data["cameras"] == ["cam01"]
    assert data["summary"]["distinct_identities"] == ["mom"]
    assert data["partial"] is False


@pytest.mark.asyncio
async def test_camera_filter_excludes_other_cameras():
    bucketizer = _FakeBucketizer(
        {"cam01": [_frame("cam01", "mom")], "cam02": [_frame("cam02", "dad")]}
    )

    data = await _run(_config(cameras=["cam01"]), bucketizer)

    identities = data["summary"]["distinct_identities"]
    assert identities == ["mom"]
    assert all(f["camera_id"] == "cam01" for f in data["frames"])


@pytest.mark.asyncio
async def test_missing_bucketizer_returns_partial_empty_window():
    data = await _run(_config(), bucketizer=None)

    assert data["frames"] == []
    assert data["partial"] is True


@pytest.mark.asyncio
async def test_ineligible_frame_is_excluded():
    eligible = _frame("cam01", "mom")
    ineligible = _frame("cam01", "dad")
    ineligible["image_eligible"] = False
    bucketizer = _FakeBucketizer({"cam01": [eligible, ineligible]})

    data = await _run(_config(cameras=["cam01"]), bucketizer)

    assert data["frames"] == [eligible]
