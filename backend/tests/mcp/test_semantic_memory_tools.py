"""Unit tests for semantic-memory MCP read tools.

Tests cover:
- Each tool returns the correct shape when the injected mock client has data.
- Each tool returns a documented error dict when ``_svc.semantic_memory_client``
  is ``None``.
- ``search_similar_scenes`` strips any ``embedding`` field even if present upstream.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.mcp.server import _svc

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_semantic_memory_client():
    """Restore None after each test so tests stay independent."""
    yield
    _svc.semantic_memory_client = None


def _make_mock_client(data: dict[str, Any] | None = None) -> MagicMock:
    """Return a MagicMock SemanticMemoryClient with the given method overrides."""
    client = MagicMock()
    client.configured = True
    for method_name, result in (data or {}).items():
        setattr(client, method_name, AsyncMock(return_value=result))
    return client


def _make_presence(label: str = "cup", count: int = 3, minutes_ago: int = 10):
    from backend.integrations.semantic_memory_client import ObjectPresenceRecord

    return ObjectPresenceRecord(
        label=label,
        observation_count=count,
        last_seen_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )


def _make_hit(
    id_: int = 1,
    room_id: str = "room1",
    description: str = "A cup on the table",
    objects: list[str] | None = None,
    hazards: list[str] | None = None,
):
    from backend.integrations.semantic_memory_client import ObservationSearchHit

    return ObservationSearchHit(
        id=id_,
        room_id=room_id,
        observed_at=datetime.now(UTC) - timedelta(minutes=5),
        description=description,
        object_list=objects or [],
        hazard_flags=hazards or [],
    )


def _make_transition(
    id_: int = 1,
    person_id: str = "p1",
    from_room: str = "bedroom",
    to_room: str = "kitchen",
    semantic: str = "entering",
    confidence: float = 0.9,
):
    from backend.integrations.semantic_memory_client import MovementTransitionRecord

    return MovementTransitionRecord(
        id=id_,
        person_id=person_id,
        from_room_id=from_room,
        to_room_id=to_room,
        direction_semantic=semantic,
        confidence=confidence,
        observed_at=datetime.now(UTC) - timedelta(minutes=10),
    )


def _make_trend(
    room_id: str = "room1",
    clutter: float = 0.3,
    trend: str = "decreasing",
    severity: str = "ok",
):
    from backend.integrations.semantic_memory_client import RoomTrendResult

    return RoomTrendResult(
        room_id=room_id,
        room_name="Room 1",
        as_of=datetime.now(UTC),
        baseline_available=True,
        clutter_score=clutter,
        trend_direction=trend,
        overall_severity=severity,
        persistent_objects=["chair"],
        novel_objects=["box"],
        anomalies=[],
    )


# ---------------------------------------------------------------------------
# get_recent_scene_objects
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_recent_scene_objects_with_data():
    from backend.mcp.server import get_recent_scene_objects

    client = _make_mock_client({
        "get_recent_objects": [_make_presence("mug", 5, 15)],
    })
    _svc.semantic_memory_client = client

    result = await get_recent_scene_objects(room_id="kitchen", minutes=60)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["label"] == "mug"
    assert result[0]["observation_count"] == 5
    assert "last_seen_minutes_ago" in result[0]


@pytest.mark.asyncio
async def test_get_recent_scene_objects_no_client():
    from backend.mcp.server import get_recent_scene_objects

    result = await get_recent_scene_objects(room_id="kitchen")
    assert result == [{"error": "Semantic memory service not available"}]


# ---------------------------------------------------------------------------
# get_scene_observations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_scene_observations_with_data():
    from backend.mcp.server import get_scene_observations

    client = _make_mock_client({
        "search_observations": [
            _make_hit(id_=1, description="A person sitting"),
            _make_hit(id_=2, description="A door open", hazards=["door_unsafe"]),
        ],
    })
    _svc.semantic_memory_client = client

    result = await get_scene_observations(room_id="living_room", limit=5)

    assert len(result) == 2
    assert result[0]["id"] == 1
    assert result[0]["description"] == "A person sitting"
    assert result[1]["hazard_flags"] == ["door_unsafe"]


@pytest.mark.asyncio
async def test_get_scene_observations_no_client():
    from backend.mcp.server import get_scene_observations

    result = await get_scene_observations()
    assert result == [{"error": "Semantic memory service not available"}]


# ---------------------------------------------------------------------------
# get_person_movements
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_person_movements_with_data():
    from backend.mcp.server import get_person_movements

    client = _make_mock_client({
        "get_transitions": [
            _make_transition(to_room="kitchen", semantic="entering"),
        ],
    })
    _svc.semantic_memory_client = client

    result = await get_person_movements(person_id="p1", minutes=60)

    assert len(result) == 1
    assert result[0]["person_id"] == "p1"
    assert result[0]["to_room_id"] == "kitchen"
    assert result[0]["direction_semantic"] == "entering"
    assert result[0]["confidence"] == 0.9


@pytest.mark.asyncio
async def test_get_person_movements_no_client():
    from backend.mcp.server import get_person_movements

    result = await get_person_movements(person_id="p1")
    assert result == [{"error": "Semantic memory service not available"}]


# ---------------------------------------------------------------------------
# get_room_trend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_room_trend_with_data():
    from backend.mcp.server import get_room_trend

    client = _make_mock_client({
        "get_room_trends": _make_trend(clutter=0.7, severity="warning"),
    })
    _svc.semantic_memory_client = client

    result = await get_room_trend(room_id="kitchen")

    assert result["room_id"] == "room1"
    assert result["clutter_score"] == 0.7
    assert result["overall_severity"] == "warning"
    assert result["persistent_objects"] == ["chair"]
    assert result["novel_objects"] == ["box"]


@pytest.mark.asyncio
async def test_get_room_trend_none_result():
    from backend.mcp.server import get_room_trend

    client = _make_mock_client({"get_room_trends": None})
    _svc.semantic_memory_client = client

    result = await get_room_trend(room_id="unknown")
    assert result == {"room_id": "unknown", "trend_direction": "unknown"}


@pytest.mark.asyncio
async def test_get_room_trend_no_client():
    from backend.mcp.server import get_room_trend

    result = await get_room_trend(room_id="kitchen")
    assert result == {"error": "Semantic memory service not available"}


# ---------------------------------------------------------------------------
# search_similar_scenes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_similar_scenes_with_data():
    from backend.mcp.server import search_similar_scenes

    client = _make_mock_client({
        "search_observations": [_make_hit(description="Person on floor")],
    })
    _svc.semantic_memory_client = client

    result = await search_similar_scenes(query_text="person sitting", limit=3)

    assert len(result) == 1
    assert result[0]["description"] == "Person on floor"
    # Similarity scores should be present (defaults from dataclass)
    assert "text_similarity" in result[0]


@pytest.mark.asyncio
async def test_search_similar_scenes_strips_embedding():
    """Verify that embedding fields are never returned in the output.

    The MCP tool builds dicts from ObservationSearchHit fields which do not
    include ``embedding``, so even if the raw API returned one it would be
    stripped.
    """
    from backend.mcp.server import search_similar_scenes

    client = _make_mock_client({
        "search_observations": [_make_hit(description="Test scene")],
    })
    _svc.semantic_memory_client = client

    result = await search_similar_scenes(query_text="test")

    assert len(result) == 1
    assert "embedding" not in result[0]
    # Verify the expected keys are present
    assert set(result[0].keys()) == {
        "id", "observed_at", "room_id", "description",
        "object_list", "hazard_flags", "text_similarity",
        "image_similarity", "source",
    }


@pytest.mark.asyncio
async def test_search_similar_scenes_no_client():
    from backend.mcp.server import search_similar_scenes

    result = await search_similar_scenes(query_text="test")
    assert result == [{"error": "Semantic memory service not available"}]
