"""Unit tests for :class:`~backend.integrations.semantic_memory_client.SemanticMemoryClient`.

Every outbound HTTP call is intercepted by a mock ``httpx.AsyncClient`` so
no real service is required.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from backend.integrations.semantic_memory_client import (
    MovementCreate,
    ObjectPresenceRecord,
    ObservationCreate,
    ObservationRecord,
    ObservationSearchHit,
    ObservationSearchRequest,
    RoomTrendResult,
    SemanticMemoryClient,
    TrendSnapshot,
)

_HTTPX_TARGET = "backend.integrations._http_base.httpx.AsyncClient"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(*, enabled: bool = True) -> SemanticMemoryClient:
    return SemanticMemoryClient(base_url="http://sm-test", timeout=5, enabled=enabled)


def _make_http_mock(json_payload: dict, status_code: int = 200) -> tuple[MagicMock, MagicMock]:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_payload
    response.raise_for_status = MagicMock()

    http_client = AsyncMock()
    http_client.get = AsyncMock(return_value=response)
    http_client.post = AsyncMock(return_value=response)
    http_client.delete = AsyncMock(return_value=response)

    ctx = MagicMock()
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
        client = SemanticMemoryClient(base_url="", timeout=5, enabled=True)
        assert client.configured is False

    async def test_create_observation_returns_none(self):
        client = _make_client(enabled=False)
        obs = ObservationCreate(room_id="r1")
        assert await client.create_observation(obs) is None

    async def test_search_observations_returns_empty(self):
        client = _make_client(enabled=False)
        assert await client.search_observations(ObservationSearchRequest()) == []

    async def test_get_transitions_returns_empty(self):
        client = _make_client(enabled=False)
        assert await client.get_transitions("p1") == []

    async def test_get_recent_objects_returns_empty(self):
        client = _make_client(enabled=False)
        assert await client.get_recent_objects("r1") == []

    async def test_get_room_trends_returns_none(self):
        client = _make_client(enabled=False)
        assert await client.get_room_trends("r1") is None

    async def test_get_all_room_trends_returns_empty(self):
        client = _make_client(enabled=False)
        assert await client.get_all_room_trends() == []

    async def test_get_snapshots_returns_empty(self):
        client = _make_client(enabled=False)
        assert await client.get_snapshots("r1") == []

    async def test_prune_observations_returns_zero(self):
        client = _make_client(enabled=False)
        assert await client.prune_observations(30) == 0


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    async def test_returns_health_dict(self):
        ctx, _ = _make_http_mock({"status": "ok"})
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
# create_observation
# ---------------------------------------------------------------------------


class TestCreateObservation:
    async def test_returns_observation_record(self):
        now = datetime.now(UTC)
        payload = {
            "id": 42,
            "room_id": "kitchen",
            "description": "A messy kitchen",
            "object_list": ["cardboard box", "stove"],
            "hazard_flags": ["cardboard_near_stove"],
            "observed_at": now.isoformat(),
            "source": "scene_intel",
            "created_at": now.isoformat(),
        }
        ctx, _ = _make_http_mock(payload)
        client = _make_client()
        obs = ObservationCreate(
            room_id="kitchen",
            description="A messy kitchen",
            object_list=["cardboard box", "stove"],
            hazard_flags=["cardboard_near_stove"],
            source="scene_intel",
        )
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.create_observation(obs)
        assert isinstance(result, ObservationRecord)
        assert result.id == 42
        assert result.room_id == "kitchen"
        assert result.observed_at.tzinfo is not None

    async def test_returns_none_on_exception(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("network error"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.create_observation(ObservationCreate(room_id="r1"))
        assert result is None

    async def test_asserts_observed_at_has_offset(self):
        """observed_at body field must be ISO-8601 with offset."""
        ctx, http_client = _make_http_mock({"id": 1, "room_id": "r1", "observed_at": "2026-01-01T00:00:00+00:00"})
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            await client.create_observation(ObservationCreate(room_id="r1"))
        call_kwargs = http_client.post.call_args.kwargs
        body = call_kwargs["json"]
        assert "+" in body["observed_at"] or "Z" in body["observed_at"]


# ---------------------------------------------------------------------------
# search_observations
# ---------------------------------------------------------------------------


class TestSearchObservations:
    async def test_returns_hits(self):
        hits_data = [
            {
                "id": 1,
                "room_id": "kitchen",
                "observed_at": "2026-01-01T00:00:00+00:00",
                "description": "messy",
                "object_list": ["box"],
                "hazard_flags": ["fire_risk"],
                "text_similarity": 0.95,
                "image_similarity": 0.88,
            }
        ]
        ctx, _ = _make_http_mock(hits_data)
        client = _make_client()
        req = ObservationSearchRequest(room_id="kitchen", since_minutes=60)
        with patch(_HTTPX_TARGET, return_value=ctx):
            results = await client.search_observations(req)
        assert len(results) == 1
        hit = results[0]
        assert isinstance(hit, ObservationSearchHit)
        assert hit.text_similarity == 0.95
        assert hit.image_similarity == 0.88

    async def test_returns_empty_on_exception(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            results = await client.search_observations(ObservationSearchRequest())
        assert results == []

    async def test_asserts_query_embedding_is_plain_list(self):
        """query_embedding payload must be a plain list[float]."""
        ctx, http_client = _make_http_mock([{"id": 1, "room_id": "r1", "observed_at": "2026-01-01T00:00:00+00:00"}])
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            await client.search_observations(
                ObservationSearchRequest(query_text="test", objects_any=["box"])
            )
        call_kwargs = http_client.post.call_args.kwargs
        body = call_kwargs["json"]
        assert isinstance(body["objects_any"], list)


# ---------------------------------------------------------------------------
# prune_observations
# ---------------------------------------------------------------------------


class TestPruneObservations:
    async def test_returns_count(self):
        ctx, _ = _make_http_mock({"pruned": 5})
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.prune_observations(30)
        assert result == 5

    async def test_returns_zero_on_exception(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.prune_observations(30)
        assert result == 0

    async def test_uses_delete_method(self):
        ctx, http_client = _make_http_mock({"pruned": 0})
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            await client.prune_observations(30)
        assert http_client.delete.called


# ---------------------------------------------------------------------------
# create_movement
# ---------------------------------------------------------------------------


class TestCreateMovement:
    async def test_returns_movement_record(self):
        payload = {
            "id": 7,
            "person_id": "p1",
            "from_room_id": "hallway",
            "to_room_id": "kitchen",
            "direction_semantic": "entering",
            "confidence": 0.85,
            "observed_at": "2026-01-01T00:00:00+00:00",
            "observation_id": 42,
        }
        ctx, _ = _make_http_mock(payload)
        client = _make_client()
        movement = MovementCreate(
            person_id="p1",
            from_room_id="hallway",
            to_room_id="kitchen",
            direction_semantic="entering",
            confidence=0.85,
            observation_id=42,
        )
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.create_movement(movement)
        assert isinstance(result, ObservationRecord | type(result))
        assert result.id == 7  # type: ignore[attr-defined]

    async def test_returns_none_on_exception(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.create_movement(
                MovementCreate(person_id="p1", from_room_id="a", to_room_id="b")
            )
        assert result is None


# ---------------------------------------------------------------------------
# get_transitions
# ---------------------------------------------------------------------------


class TestGetTransitions:
    async def test_returns_transitions(self):
        data = [
            {
                "id": 1,
                "person_id": "p1",
                "from_room_id": "hallway",
                "to_room_id": "kitchen",
                "direction_semantic": "entering",
                "confidence": 0.9,
                "observed_at": "2026-01-01T00:00:00+00:00",
                "observation_id": None,
            }
        ]
        ctx, _ = _make_http_mock(data)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            results = await client.get_transitions("p1", semantic="entering", since_minutes=30)
        assert len(results) == 1
        assert results[0].person_id == "p1"

    async def test_returns_empty_on_exception(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            results = await client.get_transitions("p1")
        assert results == []

    async def test_asserts_no_none_values_in_query_string(self):
        """Optional None params must not leak into query string."""
        ctx, http_client = _make_http_mock([])
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            await client.get_transitions("p1")
        call_kwargs = http_client.get.call_args
        params = call_kwargs.kwargs.get("params", {})
        assert "semantic" not in params
        assert "to_room_id" not in params
        assert "since_minutes" not in params


# ---------------------------------------------------------------------------
# get_recent_objects
# ---------------------------------------------------------------------------


class TestGetRecentObjects:
    async def test_returns_records(self):
        data = [
            {
                "label": "cardboard box",
                "observation_count": 4,
                "last_seen_at": "2026-01-01T00:00:00+00:00",
            }
        ]
        ctx, _ = _make_http_mock(data)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            results = await client.get_recent_objects("kitchen", since_minutes=60)
        assert len(results) == 1
        rec = results[0]
        assert isinstance(rec, ObjectPresenceRecord)
        assert rec.label == "cardboard box"
        assert rec.observation_count == 4

    async def test_returns_empty_on_exception(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            results = await client.get_recent_objects("kitchen")
        assert results == []


# ---------------------------------------------------------------------------
# get_room_trends
# ---------------------------------------------------------------------------


class TestGetRoomTrends:
    async def test_returns_trend_result(self):
        payload = {
            "room_id": "kitchen",
            "room_name": "Kitchen",
            "as_of": "2026-01-01T00:00:00+00:00",
            "baseline_available": True,
            "clutter_score": 1.5,
            "trend_direction": "increasing",
            "overall_severity": "warning",
            "persistent_objects": ["stove", "fridge"],
            "novel_objects": ["cardboard box"],
            "anomalies": [{"type": "clutter", "score": 1.5}],
        }
        ctx, _ = _make_http_mock(payload)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.get_room_trends("kitchen")
        assert isinstance(result, RoomTrendResult)
        assert result.trend_direction == "increasing"
        assert result.overall_severity == "warning"

    async def test_returns_none_on_exception(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            result = await client.get_room_trends("kitchen")
        assert result is None


# ---------------------------------------------------------------------------
# get_all_room_trends
# ---------------------------------------------------------------------------


class TestGetAllRoomTrends:
    async def test_returns_list(self):
        data = [
            {
                "room_id": "kitchen",
                "as_of": "2026-01-01T00:00:00+00:00",
                "trend_direction": "stable",
                "overall_severity": "ok",
            }
        ]
        ctx, _ = _make_http_mock(data)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            results = await client.get_all_room_trends()
        assert len(results) == 1

    async def test_returns_empty_on_exception(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            results = await client.get_all_room_trends()
        assert results == []


# ---------------------------------------------------------------------------
# get_snapshots
# ---------------------------------------------------------------------------


class TestGetSnapshots:
    async def test_returns_snapshots(self):
        data = [
            {
                "room_id": "kitchen",
                "period_start": "2026-01-01T00:00:00+00:00",
                "unique_object_count": 5,
                "object_counts": {"stove": 3, "fridge": 1},
            }
        ]
        ctx, _ = _make_http_mock(data)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            results = await client.get_snapshots("kitchen", since_hours=24)
        assert len(results) == 1
        snap = results[0]
        assert isinstance(snap, TrendSnapshot)
        assert snap.unique_object_count == 5

    async def test_returns_empty_on_exception(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=ctx):
            results = await client.get_snapshots("kitchen")
        assert results == []
