"""Unit tests for :class:`~backend.integrations.scene_analysis_client.SceneAnalysisClient`.

Mirrors the pattern of ``test_homeassistant.py``: every outbound HTTP call is
intercepted by a mock ``httpx.AsyncClient`` so no real service is required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from backend.integrations.scene_analysis_client import (
    SceneAnalysisClient,
    SceneAnalyzeResult,
    SceneDescribeResult,
    SceneDetectResult,
)

_HTTPX_TARGET = "backend.integrations._http_base.httpx.AsyncClient"

_DETECT_RESPONSE = {
    "detections": [
        {"label": "person", "confidence": 0.95, "bbox": [0, 0, 100, 200], "class_id": 0}
    ],
    "detector_available": True,
}

_DESCRIBE_RESPONSE = {
    "description": "A person standing in a kitchen.",
    "describer_available": True,
}

_ANALYZE_RESPONSE = {
    "detections": [
        {"label": "person", "confidence": 0.95, "bbox": [0, 0, 100, 200], "class_id": 0}
    ],
    "description": "A person standing in a kitchen.",
    "embedding": [0.1, 0.2, 0.3],
    "hazards": [
        {
            "name": "fire",
            "severity": "critical",
            "description": "Fire detected.",
            "detection": {
                "label": "fire",
                "confidence": 0.88,
                "bbox": [50, 50, 150, 150],
                "class_id": 99,
            },
        }
    ],
    "detector_available": True,
    "describer_available": True,
    "embedder_available": True,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(*, enabled: bool = True) -> SceneAnalysisClient:
    """Return a SceneAnalysisClient with explicit injected config."""
    return SceneAnalysisClient(base_url="http://sas-test", timeout=5, enabled=enabled)


def _make_http_mock(json_payload: dict, status_code: int = 200) -> MagicMock:
    """Return a mock usable as ``async with httpx.AsyncClient() as client:``."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_payload
    response.raise_for_status = MagicMock()  # no-op (200)

    http_client = AsyncMock()
    http_client.get = AsyncMock(return_value=response)
    http_client.post = AsyncMock(return_value=response)

    ctx = MagicMock()
    ctx.get = http_client.get
    ctx.post = http_client.post
    ctx.__aenter__ = AsyncMock(return_value=http_client)
    ctx.__aexit__ = AsyncMock(return_value=False)

    return ctx, http_client


# ---------------------------------------------------------------------------
# Disabled client
# ---------------------------------------------------------------------------


class TestDisabledClient:
    async def test_health_check_returns_none(self):
        client = _make_client(enabled=False)
        assert await client.health_check() is None

    async def test_unconfigured_returns_false(self):
        client = SceneAnalysisClient(base_url="", timeout=5, enabled=True)
        assert client.configured is False

    async def test_detect_returns_empty(self):
        client = _make_client(enabled=False)
        result = await client.detect(b"data")
        assert isinstance(result, SceneDetectResult)
        assert result.detections == []

    async def test_describe_returns_empty(self):
        client = _make_client(enabled=False)
        result = await client.describe(b"data")
        assert isinstance(result, SceneDescribeResult)
        assert result.description == ""

    async def test_analyze_returns_empty(self):
        client = _make_client(enabled=False)
        result = await client.analyze(b"data")
        assert isinstance(result, SceneAnalyzeResult)
        assert result.detections == []
        assert result.description == ""
        assert result.embedding == []
        assert result.hazards == []


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    async def test_returns_health_dict(self):
        ctx, _http_client = _make_http_mock({"status": "ok"})
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.health_check()
        assert result == {"status": "ok"}

    async def test_returns_none_on_exception(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.health_check()
        assert result is None


# ---------------------------------------------------------------------------
# /detect
# ---------------------------------------------------------------------------


class TestDetect:
    async def test_parses_detections(self):
        ctx, _ = _make_http_mock(_DETECT_RESPONSE)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.detect(b"image-data")
        assert len(result.detections) == 1
        det = result.detections[0]
        assert det.label == "person"
        assert det.confidence == 0.95
        assert det.bbox == [0, 0, 100, 200]
        assert det.class_id == 0
        assert result.detector_available is True

    async def test_returns_empty_on_exception(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("network error"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.detect(b"image-data")
        assert result.detections == []

    async def test_posts_to_correct_url(self):
        ctx, http_client = _make_http_mock(_DETECT_RESPONSE)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            await client.detect(b"img")
        call_args = http_client.post.call_args
        assert "http://sas-test/detect" in str(call_args)

    async def test_skips_malformed_detection_entries(self):
        ctx, _ = _make_http_mock(
            {
                "detections": [
                    {"label": "person", "confidence": 0.95, "bbox": [0, 0, 1, 1], "class_id": 1},
                    {"label": "broken", "confidence": "bad", "bbox": "oops", "class_id": "x"},
                ],
                "detector_available": True,
            }
        )
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.detect(b"image-data")
        assert [item.label for item in result.detections] == ["person"]


# ---------------------------------------------------------------------------
# /describe
# ---------------------------------------------------------------------------


class TestDescribe:
    async def test_parses_description(self):
        ctx, _ = _make_http_mock(_DESCRIBE_RESPONSE)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.describe(b"image-data")
        assert result.description == "A person standing in a kitchen."
        assert result.describer_available is True

    async def test_returns_empty_on_exception(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.describe(b"image-data")
        assert result.description == ""


# ---------------------------------------------------------------------------
# /analyze
# ---------------------------------------------------------------------------


class TestAnalyze:
    async def test_parses_full_result(self):
        ctx, _ = _make_http_mock(_ANALYZE_RESPONSE)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.analyze(b"image-data")
        assert len(result.detections) == 1
        assert result.description == "A person standing in a kitchen."
        assert result.embedding == [0.1, 0.2, 0.3]
        assert len(result.hazards) == 1
        assert result.hazards[0].name == "fire"
        assert result.hazards[0].severity == "critical"
        assert result.hazards[0].detection.label == "fire"
        assert result.detector_available is True
        assert result.describer_available is True
        assert result.embedder_available is True

    async def test_returns_empty_on_exception(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.analyze(b"image-data")
        assert result.detections == []
        assert result.description == ""
        assert result.hazards == []

    async def test_passes_run_flags_as_query_params(self):
        ctx, http_client = _make_http_mock(_ANALYZE_RESPONSE)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            await client.analyze(
                b"image-data",
                run_detect=True,
                run_describe=False,
                run_embed=False,
                run_hazards=True,
            )
        call_kwargs = http_client.post.call_args.kwargs
        params = call_kwargs.get("params", {})
        assert params["run_detect"] == "true"
        assert params["run_describe"] == "false"
        assert params["run_embed"] == "false"
        assert params["run_hazards"] == "true"

    async def test_ignores_malformed_hazards_and_embedding_values(self):
        ctx, _ = _make_http_mock(
            {
                "detections": _ANALYZE_RESPONSE["detections"],
                "description": "ok",
                "embedding": [0.1, "bad", 0.3],
                "hazards": [
                    _ANALYZE_RESPONSE["hazards"][0],
                    {
                        "name": "broken",
                        "severity": "warning",
                        "description": "bad",
                        "detection": {},
                    },
                ],
                "detector_available": True,
                "describer_available": True,
                "embedder_available": True,
            }
        )
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.analyze(b"image-data")
        assert result.embedding == [0.1, 0.3]
        assert [hazard.name for hazard in result.hazards] == ["fire"]


# ---------------------------------------------------------------------------
# sensor_id header
# ---------------------------------------------------------------------------


class TestSensorIdHeader:
    async def test_detect_propagates_sensor_id(self):
        ctx, http_client = _make_http_mock(_DETECT_RESPONSE)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            await client.detect(b"img", sensor_id="cam_kitchen")
        call_args = http_client.post.call_args
        headers = call_args.kwargs.get("headers", {})
        assert headers.get("X-Sensor-Id") == "cam_kitchen"

    async def test_describe_propagates_sensor_id(self):
        ctx, http_client = _make_http_mock(_DESCRIBE_RESPONSE)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            await client.describe(b"img", sensor_id="cam_kitchen")
        call_args = http_client.post.call_args
        headers = call_args.kwargs.get("headers", {})
        assert headers.get("X-Sensor-Id") == "cam_kitchen"

    async def test_analyze_propagates_sensor_id(self):
        ctx, http_client = _make_http_mock(_ANALYZE_RESPONSE)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            await client.analyze(b"img", sensor_id="cam_kitchen")
        call_args = http_client.post.call_args
        headers = call_args.kwargs.get("headers", {})
        assert headers.get("X-Sensor-Id") == "cam_kitchen"

    async def test_no_sensor_id_when_none(self):
        ctx, http_client = _make_http_mock(_DETECT_RESPONSE)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            await client.detect(b"img")
        call_args = http_client.post.call_args
        # When sensor_id is None, no X-Sensor-Id header should be present
        headers = call_args.kwargs.get("headers", {})
        assert "X-Sensor-Id" not in headers
