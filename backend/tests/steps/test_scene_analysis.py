"""Unit tests for :class:`~backend.steps.builtin.scene_analysis.SceneAnalysisHandler`.

All HTTP calls to the scene-analysis-service are intercepted by a mock
SceneAnalysisClient so no real service is required.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

from backend.integrations.scene_analysis_client import (
    SceneAnalysisClient,
    SceneAnalyzeResult,
    SceneDetection,
    SceneHazardAlert,
)
from backend.steps.base import ServiceContainer, TriggerContext
from backend.steps.builtin.scene_analysis import SceneAnalysisHandler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeExecution:
    id: int = 1


@dataclass
class _FakeStep:
    config_json: dict = field(default_factory=dict)


def _make_step(config: dict | None = None) -> _FakeStep:
    return _FakeStep(config_json=config or {})


def _make_trigger(
    sensor_id: str = "cam-1",
    media_paths: list[str] | None = None,
) -> TriggerContext:
    return TriggerContext(
        trigger_type="sensor_event",
        sensor_id=sensor_id,
        room_name="Kitchen",
        media_paths=media_paths or [],
    )


def _make_services(scene_analysis_client=None) -> ServiceContainer:
    return ServiceContainer(
        db_factory=MagicMock(),
        scene_analysis_client=scene_analysis_client,
    )


def _mock_client(result: SceneAnalyzeResult | None = None) -> AsyncMock:
    client = AsyncMock(spec=SceneAnalysisClient)
    client.analyze = AsyncMock(
        return_value=result
        or SceneAnalyzeResult(
            detections=[],
            description="",
            embedding=[],
            hazards=[],
        )
    )
    return client


def _tiny_jpeg_file() -> str:
    """Write a minimal JPEG to a temp file and return its path."""
    import io

    from PIL import Image

    img = Image.new("RGB", (16, 16), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.write(buf.getvalue())
    tmp.close()
    return tmp.name


_HANDLER = SceneAnalysisHandler()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestMetadata:
    def test_type_name(self):
        assert _HANDLER.metadata().type_name == "scene_analysis"

    def test_category(self):
        assert _HANDLER.metadata().category == "perception"

    def test_default_config_has_expected_keys(self):
        keys = _HANDLER.metadata().default_config.keys()
        assert "run_detect" in keys
        assert "run_describe" in keys
        assert "max_images" in keys


# ---------------------------------------------------------------------------
# Early exits
# ---------------------------------------------------------------------------


class TestEarlyExits:
    async def test_returns_empty_when_no_client(self):
        services = _make_services(scene_analysis_client=None)
        result = await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(), services
        )
        assert result.success is True
        assert result.data["scene_detections"] == []

    async def test_returns_empty_when_no_media_paths(self):
        client = _mock_client()
        services = _make_services(scene_analysis_client=client)
        result = await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(media_paths=[]), services
        )
        assert result.data["scene_detections"] == []
        client.analyze.assert_not_called()

    async def test_returns_empty_when_image_unreadable(self):
        client = _mock_client()
        services = _make_services(scene_analysis_client=client)
        result = await _HANDLER.execute(
            _make_step(),
            _FakeExecution(),
            {},
            _make_trigger(media_paths=["/nonexistent/path.jpg"]),
            services,
        )
        assert result.data["scene_detections"] == []
        client.analyze.assert_not_called()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def setup_method(self):
        self._tmp = _tiny_jpeg_file()

    def teardown_method(self):
        os.unlink(self._tmp)

    async def test_calls_analyze_with_image_bytes(self):
        client = _mock_client()
        services = _make_services(scene_analysis_client=client)
        await _HANDLER.execute(
            _make_step(),
            _FakeExecution(),
            {},
            _make_trigger(media_paths=[self._tmp]),
            services,
        )
        client.analyze.assert_called_once()
        call_kwargs = client.analyze.call_args
        assert isinstance(call_kwargs[0][0], bytes)

    async def test_result_data_has_expected_keys(self):
        client = _mock_client()
        services = _make_services(scene_analysis_client=client)
        result = await _HANDLER.execute(
            _make_step(),
            _FakeExecution(),
            {},
            _make_trigger(media_paths=[self._tmp]),
            services,
        )
        assert "scene_detections" in result.data
        assert "scene_description" in result.data
        assert "scene_embedding" in result.data
        assert "scene_hazards" in result.data
        assert "scene_detector_available" in result.data
        assert "scene_describer_available" in result.data
        assert "scene_embedder_available" in result.data

    async def test_serialises_detections(self):
        det = SceneDetection(label="person", confidence=0.9, bbox=[0, 0, 100, 100], class_id=0)
        client = _mock_client(SceneAnalyzeResult(detections=[det]))
        services = _make_services(scene_analysis_client=client)
        result = await _HANDLER.execute(
            _make_step(),
            _FakeExecution(),
            {},
            _make_trigger(media_paths=[self._tmp]),
            services,
        )
        assert len(result.data["scene_detections"]) == 1
        assert result.data["scene_detections"][0]["label"] == "person"

    async def test_serialises_hazards(self):
        det = SceneDetection(label="fire", confidence=0.88, bbox=[0, 0, 50, 50], class_id=99)
        hazard = SceneHazardAlert(
            name="fire", severity="critical", description="Fire!", detection=det
        )
        client = _mock_client(SceneAnalyzeResult(detections=[det], hazards=[hazard]))
        services = _make_services(scene_analysis_client=client)
        result = await _HANDLER.execute(
            _make_step(),
            _FakeExecution(),
            {},
            _make_trigger(media_paths=[self._tmp]),
            services,
        )
        assert len(result.data["scene_hazards"]) == 1
        h = result.data["scene_hazards"][0]
        assert h["name"] == "fire"
        assert h["severity"] == "critical"
        assert h["detection"]["label"] == "fire"

    async def test_always_continues_pipeline(self):
        client = _mock_client()
        services = _make_services(scene_analysis_client=client)
        result = await _HANDLER.execute(
            _make_step(),
            _FakeExecution(),
            {},
            _make_trigger(media_paths=[self._tmp]),
            services,
        )
        assert result.should_continue is True


# ---------------------------------------------------------------------------
# Config forwarding
# ---------------------------------------------------------------------------


class TestConfigForwarding:
    def setup_method(self):
        self._tmp = _tiny_jpeg_file()

    def teardown_method(self):
        os.unlink(self._tmp)

    async def test_run_flags_forwarded(self):
        client = _mock_client()
        services = _make_services(scene_analysis_client=client)
        config = {
            "run_detect": True,
            "run_describe": False,
            "run_embed": True,
            "run_hazards": False,
        }
        await _HANDLER.execute(
            _make_step(config),
            _FakeExecution(),
            {},
            _make_trigger(media_paths=[self._tmp]),
            services,
        )
        call_kwargs = client.analyze.call_args.kwargs
        assert call_kwargs["run_detect"] is True
        assert call_kwargs["run_describe"] is False
        assert call_kwargs["run_embed"] is True
        assert call_kwargs["run_hazards"] is False

    async def test_max_images_limits_paths(self):
        """Only the first max_images paths should be processed."""
        client = _mock_client()
        services = _make_services(scene_analysis_client=client)
        tmp2 = _tiny_jpeg_file()
        try:
            await _HANDLER.execute(
                _make_step({"max_images": 1}),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[self._tmp, tmp2]),
                services,
            )
        finally:
            os.unlink(tmp2)
        # Only one analyze call — the second image is ignored
        client.analyze.assert_called_once()
