"""Unit tests for :class:`~backend.steps.builtin.media_presign.MediaPresignHandler`."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest

from backend.steps._testing import assert_output_conforms_to_schema
from backend.steps.base import ServiceContainer, TriggerContext
from backend.steps.builtin.media_presign import MediaPresignHandler


class _FakeMinio:
    def __init__(self, known_objects: set[str] | None = None):
        self.known_objects = known_objects or set()
        self.presign_calls: list[str] = []

    async def async_object_exists(self, object_name):
        return object_name in self.known_objects

    def generate_presigned_url(self, object_name, expiration=3600):
        self.presign_calls.append(object_name)
        return f"http://minio.local/bucket/{object_name}?sig=test"


@dataclass
class _FakeStep:
    config_json: dict = field(default_factory=dict)
    id: int = 1
    label: str = "media_presign_1"


@dataclass
class _FakeExecution:
    id: int = 100


def _make_trigger() -> TriggerContext:
    return TriggerContext(trigger_type="dementia_signal")


def _make_mock_db() -> MagicMock:
    session = MagicMock()
    session.query.return_value = session
    session.filter.return_value = session
    session.first.return_value = None
    return session


def _make_services(minio_client=None, db=None) -> ServiceContainer:
    db = db if db is not None else _make_mock_db()
    return ServiceContainer(db_factory=lambda: db, minio_client=minio_client)


class TestMissingClient:
    @pytest.mark.asyncio
    async def test_no_minio_returns_failure(self):
        handler = MediaPresignHandler()
        result = await handler.execute(
            _FakeStep(config_json={"object_names_key": ["trigger_event.evidence.x"]}),
            _FakeExecution(),
            {"trigger_event": {"evidence": {"x": ["obj1.jpg"]}}},
            _make_trigger(),
            _make_services(minio_client=None),
        )

        assert result.success is False
        assert result.data["count"] == 0
        assert result.data.get("error")


class TestPresign:
    @pytest.mark.asyncio
    async def test_success_path_presigns_and_registers(self):
        fake_minio = _FakeMinio(known_objects={"cts/yesterday.jpg", "cts/today.jpg"})
        pipeline_data = {
            "trigger_event": {
                "evidence": {
                    "yesterday_best_keyframe_objects": ["cts/yesterday.jpg"],
                    "today_best_keyframe_objects": ["cts/today.jpg"],
                }
            }
        }
        step = _FakeStep(
            config_json={
                "object_names_key": [
                    "trigger_event.evidence.yesterday_best_keyframe_objects",
                    "trigger_event.evidence.today_best_keyframe_objects",
                ]
            }
        )
        handler = MediaPresignHandler()
        result = await handler.execute(
            step,
            _FakeExecution(),
            pipeline_data,
            _make_trigger(),
            _make_services(minio_client=fake_minio),
        )

        assert result.success
        assert result.data["count"] == 2
        assert result.data["presigned_images"] == [
            "http://minio.local/bucket/cts/yesterday.jpg?sig=test",
            "http://minio.local/bucket/cts/today.jpg?sig=test",
        ]
        assert result.data["skipped"] == []
        assert set(fake_minio.presign_calls) == {"cts/yesterday.jpg", "cts/today.jpg"}
        assert_output_conforms_to_schema(handler, result)

    @pytest.mark.asyncio
    async def test_unknown_object_is_a_structured_skip(self):
        fake_minio = _FakeMinio(known_objects={"cts/today.jpg"})
        pipeline_data = {
            "trigger_event": {
                "evidence": {
                    "yesterday_best_keyframe_objects": ["cts/missing.jpg"],
                    "today_best_keyframe_objects": ["cts/today.jpg"],
                }
            }
        }
        step = _FakeStep(
            config_json={
                "object_names_key": [
                    "trigger_event.evidence.yesterday_best_keyframe_objects",
                    "trigger_event.evidence.today_best_keyframe_objects",
                ]
            }
        )
        handler = MediaPresignHandler()
        result = await handler.execute(
            step,
            _FakeExecution(),
            pipeline_data,
            _make_trigger(),
            _make_services(minio_client=fake_minio),
        )

        assert result.success
        assert result.data["count"] == 1
        assert result.data["skipped"] == [
            {"object_name": "cts/missing.jpg", "reason": "not_found"}
        ]

    @pytest.mark.asyncio
    async def test_empty_object_names_returns_empty_success(self):
        handler = MediaPresignHandler()
        result = await handler.execute(
            _FakeStep(config_json={"object_names_key": []}),
            _FakeExecution(),
            {},
            _make_trigger(),
            _make_services(minio_client=_FakeMinio()),
        )

        assert result.success
        assert result.data["count"] == 0
        assert result.data["presigned_images"] == []
        assert result.data["skipped"] == []

    @pytest.mark.asyncio
    async def test_deduplicates_object_names_across_paths(self):
        fake_minio = _FakeMinio(known_objects={"cts/shared.jpg"})
        pipeline_data = {
            "trigger_event": {
                "evidence": {
                    "a": ["cts/shared.jpg"],
                    "b": ["cts/shared.jpg"],
                }
            }
        }
        step = _FakeStep(
            config_json={
                "object_names_key": [
                    "trigger_event.evidence.a",
                    "trigger_event.evidence.b",
                ]
            }
        )
        handler = MediaPresignHandler()
        result = await handler.execute(
            step,
            _FakeExecution(),
            pipeline_data,
            _make_trigger(),
            _make_services(minio_client=fake_minio),
        )

        assert result.data["count"] == 1
        assert fake_minio.presign_calls == ["cts/shared.jpg"]

    @pytest.mark.asyncio
    async def test_custom_output_key(self):
        fake_minio = _FakeMinio(known_objects={"cts/today.jpg"})
        pipeline_data = {"trigger_event": {"evidence": {"x": ["cts/today.jpg"]}}}
        step = _FakeStep(
            config_json={
                "object_names_key": ["trigger_event.evidence.x"],
                "output_key": "hygiene_images",
            }
        )
        handler = MediaPresignHandler()
        result = await handler.execute(
            step,
            _FakeExecution(),
            pipeline_data,
            _make_trigger(),
            _make_services(minio_client=fake_minio),
        )

        assert result.data["hygiene_images"] == [
            "http://minio.local/bucket/cts/today.jpg?sig=test"
        ]
