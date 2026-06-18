from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from backend.services.guided_task.completion.vision import VisionEvaluator


@dataclass
class _Session:
    id: int = 1
    person_id: str = "resident-1"


@dataclass
class _Step:
    ord: int = 0
    camera_ids: list[str] | None = None
    zone_id: int | None = None


class _Provider:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict] = []

    async def call(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return self.response


@dataclass
class _ModelConfig:
    id: str = "vision-model"
    capabilities: list[str] = None

    def __post_init__(self) -> None:
        if self.capabilities is None:
            self.capabilities = ["text", "vision"]


class _Registry:
    def __init__(self, provider: _Provider) -> None:
        self.provider = provider
        self.cfg = _ModelConfig()

    def all_configs(self):
        return [self.cfg]

    def get_config(self, model_id: str):
        return self.cfg if model_id == self.cfg.id else None

    def get_provider(self, model_id: str):
        return self.provider if model_id == self.cfg.id else None


class _Bucketizer:
    def buffer_stats(self) -> dict[str, int]:
        return {"cam-1": 1}

    def forward_buffer(self, window_id, camera_id, lookahead_s, eligible_only=False):
        return [
            {
                "camera_id": camera_id,
                "event_time": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
                "detections": [{"identity_id": "resident-1"}],
                "minio_key": "frames/cam-1.jpg",
                "image_eligible": True,
            }
        ]


class _Minio:
    def generate_presigned_url(self, object_name: str, expiration: int = 3600) -> str:
        return f"https://minio/{object_name}"


def _evaluator(provider: _Provider, events: list[dict] | None = None) -> VisionEvaluator:
    def record(session_id: int, step_ord: int | None, detail: dict) -> None:
        if events is not None:
            events.append({"session_id": session_id, "step_ord": step_ord, **detail})

    return VisionEvaluator(
        gate_config={"vision": {"done_description": "the cup is filled", "min_confidence": 0.7}},
        zone_service=None,
        person_location=None,
        bucketizer=_Bucketizer(),
        camera_topology=None,
        identity_resolver=lambda _person_id: {"resident-1"},
        llm_model_registry=_Registry(provider),
        minio_client=_Minio(),
        event_recorder=record,
    )


async def test_vlm_says_complete_returns_complete() -> None:
    provider = _Provider('{"complete": true, "confidence": 0.93, "reason": "cup filled"}')
    evaluator = _evaluator(provider)

    result = await evaluator.is_complete(session=_Session(), step=_Step(), evidence={})

    assert result.complete is True
    assert provider.calls[0]["media_paths"] == ["https://minio/frames/cam-1.jpg"]


async def test_vlm_uncertain_returns_not_complete() -> None:
    provider = _Provider('{"complete": true, "confidence": 0.4, "reason": "maybe"}')
    evaluator = _evaluator(provider)

    result = await evaluator.is_complete(session=_Session(), step=_Step(), evidence={})

    assert result.complete is False
    assert result.reason == "low_confidence"


async def test_vlm_parse_failure_fails_closed() -> None:
    provider = _Provider("not json")
    evaluator = _evaluator(provider)

    result = await evaluator.is_complete(session=_Session(), step=_Step(), evidence={})

    assert result.complete is False
    assert result.reason == "parse_failed"


async def test_no_cameras_returns_not_complete() -> None:
    provider = _Provider('{"complete": true, "confidence": 1, "reason": "done"}')
    evaluator = VisionEvaluator(
        gate_config={},
        zone_service=None,
        person_location=None,
        bucketizer=None,
        camera_topology=None,
        identity_resolver=None,
        llm_model_registry=_Registry(provider),
        minio_client=_Minio(),
    )

    result = await evaluator.is_complete(session=_Session(), step=_Step(), evidence={})

    assert result.complete is False
    assert result.reason == "no_cameras"


async def test_emits_vision_confirm_event() -> None:
    events: list[dict] = []
    provider = _Provider('{"complete": true, "confidence": 0.9, "reason": "done"}')
    evaluator = _evaluator(provider, events)

    await evaluator.is_complete(session=_Session(), step=_Step(), evidence={})

    assert events == [
        {
            "session_id": 1,
            "step_ord": 0,
            "cameras": ["cam-1"],
            "complete": True,
            "confidence": 0.9,
            "reason": "done",
        }
    ]


async def test_reuses_frame_collection_helper(monkeypatch) -> None:
    from backend.services.guided_task.completion import vision
    from backend.services.media_window_frames import CtsFrameWindow

    called = False

    async def fake_collect_recent_cts_frames(*, bucketizer, minio_client, config):
        nonlocal called
        called = True
        return CtsFrameWindow(
            window_start=datetime.now(UTC),
            window_end=datetime.now(UTC),
            target_cameras=["cam-1"],
            frames=[{"camera_id": "cam-1"}],
            images=["https://minio/frame.jpg"],
        )

    monkeypatch.setattr(vision, "collect_recent_cts_frames", fake_collect_recent_cts_frames)
    provider = _Provider('{"complete": true, "confidence": 0.9, "reason": "done"}')
    evaluator = _evaluator(provider)

    result = await evaluator.is_complete(session=_Session(), step=_Step(), evidence={})

    assert called is True
    assert result.complete is True
