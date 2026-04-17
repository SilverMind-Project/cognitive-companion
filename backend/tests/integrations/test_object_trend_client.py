"""Unit tests for :class:`~backend.integrations.object_trend_client.ObjectTrendClient`.

Every outbound HTTP call is intercepted by a mock ``httpx.AsyncClient`` so
no real semantic-memory-service is required.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from backend.integrations.object_trend_client import (
    ObjectTrendClient,
    RoomTrendResult,
    TrendSnapshot,
)

_HTTPX_TARGET = "backend.integrations.object_trend_client.httpx.AsyncClient"

_TREND_RESPONSE = {
    "room_id": "living-room",
    "room_name": "Living Room",
    "as_of": "2026-04-17T14:30:00+00:00",
    "baseline_available": True,
    "clutter_score": 1.8,
    "trend_direction": "increasing",
    "overall_severity": "warning",
    "persistent_objects": ["sofa", "table"],
    "novel_objects": ["umbrella", "shoes"],
    "anomalies": [
        {
            "type": "clutter_spike",
            "severity": "warning",
            "description": "Clutter z-score above threshold.",
        }
    ],
}

_ROOMS_RESPONSE = [
    {
        "room_id": "living-room",
        "room_name": "Living Room",
        "as_of": "2026-04-17T14:30:00+00:00",
        "baseline_available": True,
        "clutter_score": 1.8,
        "trend_direction": "increasing",
        "overall_severity": "warning",
        "persistent_objects": ["sofa"],
        "novel_objects": ["umbrella"],
        "anomalies": [],
    },
    {
        "room_id": "kitchen",
        "room_name": "Kitchen",
        "as_of": "2026-04-17T14:25:00+00:00",
        "baseline_available": False,
        "clutter_score": 0.0,
        "trend_direction": "stable",
        "overall_severity": "ok",
        "persistent_objects": [],
        "novel_objects": [],
        "anomalies": [],
    },
]

_SNAPSHOTS_RESPONSE = [
    {
        "room_id": "living-room",
        "period_start": "2026-04-17T10:00:00+00:00",
        "unique_object_count": 5,
        "object_counts": {"sofa": 1, "table": 1},
        "persistent_objects": ["sofa", "table"],
        "novel_objects": [],
        "embedding_variance": 0.12,
    },
    {
        "room_id": "living-room",
        "period_start": "2026-04-17T11:00:00+00:00",
        "unique_object_count": 8,
        "object_counts": {"sofa": 1, "table": 1, "umbrella": 1},
        "persistent_objects": ["sofa"],
        "novel_objects": ["umbrella"],
        "embedding_variance": 0.35,
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client() -> ObjectTrendClient:
    return ObjectTrendClient(base_url="http://trend-test", timeout=5)


def _make_http_mock(json_payload: dict | list, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_payload
    response.raise_for_status = MagicMock()

    http_client = AsyncMock()
    http_client.get = AsyncMock(return_value=response)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=http_client)
    ctx.__aexit__ = AsyncMock(return_value=False)

    return ctx, http_client


# ---------------------------------------------------------------------------
# Configured / unconfigured
# ---------------------------------------------------------------------------


class TestConfigured:
    async def test_configured_returns_true(self):
        assert _make_client().configured is True

    async def test_unconfigured_returns_false(self):
        client = ObjectTrendClient(base_url="", timeout=5)
        assert client.configured is False


# ---------------------------------------------------------------------------
# get_room_trends
# ---------------------------------------------------------------------------


class TestGetRoomTrends:
    async def test_returns_room_trend_result(self):
        ctx, _ = _make_http_mock(_TREND_RESPONSE)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.get_room_trends("living-room")
        assert isinstance(result, RoomTrendResult)
        assert result.room_id == "living-room"
        assert result.room_name == "Living Room"
        assert result.clutter_score == 1.8
        assert result.trend_direction == "increasing"
        assert result.overall_severity == "warning"
        assert result.persistent_objects == ["sofa", "table"]
        assert result.novel_objects == ["umbrella", "shoes"]
        assert len(result.anomalies) == 1
        assert result.anomalies[0]["type"] == "clutter_spike"

    async def test_returns_none_on_exception(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.get_room_trends("living-room")
        assert result is None

    async def test_returns_none_when_not_configured(self):
        client = ObjectTrendClient(base_url="", timeout=5)
        result = await client.get_room_trends("living-room")
        assert result is None

    async def test_uses_correct_url(self):
        ctx, http_client = _make_http_mock(_TREND_RESPONSE)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            await client.get_room_trends("kitchen")
        call_args = http_client.get.call_args
        assert "kitchen/current" in str(call_args)

    async def test_falls_back_to_now_when_no_as_of(self):
        resp = dict(_TREND_RESPONSE)
        resp["as_of"] = ""
        ctx, _ = _make_http_mock(resp)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.get_room_trends("living-room")
        assert isinstance(result.as_of, datetime)


# ---------------------------------------------------------------------------
# get_all_room_trends
# ---------------------------------------------------------------------------


class TestGetAllRoomTrends:
    async def test_returns_list_of_results(self):
        ctx, _ = _make_http_mock(_ROOMS_RESPONSE)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            results = await client.get_all_room_trends()
        assert len(results) == 2
        assert results[0].room_id == "living-room"
        assert results[0].overall_severity == "warning"
        assert results[1].room_id == "kitchen"
        assert results[1].overall_severity == "ok"

    async def test_returns_empty_on_exception(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("refused"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            results = await client.get_all_room_trends()
        assert results == []

    async def test_returns_empty_when_not_configured(self):
        client = ObjectTrendClient(base_url="", timeout=5)
        results = await client.get_all_room_trends()
        assert results == []


# ---------------------------------------------------------------------------
# get_snapshots
# ---------------------------------------------------------------------------


class TestGetSnapshots:
    async def test_returns_snapshot_list(self):
        ctx, _ = _make_http_mock(_SNAPSHOTS_RESPONSE)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            snapshots = await client.get_snapshots("living-room", since_hours=12)
        assert len(snapshots) == 2
        assert isinstance(snapshots[0], TrendSnapshot)
        assert snapshots[0].unique_object_count == 5
        assert snapshots[1].unique_object_count == 8
        assert snapshots[1].embedding_variance == 0.35

    async def test_passes_since_hours_param(self):
        ctx, http_client = _make_http_mock(_SNAPSHOTS_RESPONSE)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            await client.get_snapshots("living-room", since_hours=6)
        call_kwargs = http_client.get.call_args
        params = call_kwargs.kwargs.get("params", {})
        assert params["since_hours"] == 6

    async def test_returns_empty_on_exception(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            snapshots = await client.get_snapshots("living-room")
        assert snapshots == []

    async def test_returns_empty_when_not_configured(self):
        client = ObjectTrendClient(base_url="", timeout=5)
        snapshots = await client.get_snapshots("living-room")
        assert snapshots == []

    async def test_defaults_embedding_variance(self):
        item = dict(_SNAPSHOTS_RESPONSE[0])
        del item["embedding_variance"]
        ctx, _ = _make_http_mock([item])
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            snapshots = await client.get_snapshots("living-room")
        assert snapshots[0].embedding_variance == 0.0


