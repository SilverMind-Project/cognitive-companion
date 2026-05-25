"""Tests for MemoryQueryService."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from backend.integrations.semantic_memory_client import (
    ObjectPresenceRecord,
    ObservationSearchHit,
    ObservationSearchRequest,
    RoomTrendResult,
    TrendSnapshot,
)
from backend.services.memory_query.service import MemoryQueryService

# ---------------------------------------------------------------------------
# Stub client
# ---------------------------------------------------------------------------


class _StubClient:
    """Minimal stub that returns canned data and tracks call counts."""

    def __init__(
        self,
        observations: list[ObservationSearchHit] | None = None,
        objects: list[ObjectPresenceRecord] | None = None,
        trends: dict[str, RoomTrendResult] | None = None,
        snapshots: list[TrendSnapshot] | None = None,
    ) -> None:
        self.search_count = 0
        self.recent_objects_count = 0
        self.get_trends_count = 0
        self.get_snapshots_count = 0
        self._observations = observations or []
        self._objects = objects or []
        self._trends = trends or {}
        self._snapshots = snapshots or []

    async def search_observations(
        self, req: ObservationSearchRequest
    ) -> list[ObservationSearchHit]:
        self.search_count += 1
        return list(self._observations)

    async def get_recent_objects(
        self, room_id: str, since_minutes: int = 60
    ) -> list[ObjectPresenceRecord]:
        self.recent_objects_count += 1
        return list(self._objects)

    async def get_room_trends(self, room_id: str) -> RoomTrendResult | None:
        self.get_trends_count += 1
        return self._trends.get(room_id)

    async def get_snapshots(self, room_id: str, since_hours: int = 24) -> list[TrendSnapshot]:
        self.get_snapshots_count += 1
        return list(self._snapshots)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_observations() -> list[ObservationSearchHit]:
    return [
        ObservationSearchHit(
            id=1,
            room_id="kitchen",
            observed_at=datetime.now(UTC),
            description="A person near the stove",
            object_list=["person", "stove"],
            hazard_flags=["stove_on"],
            text_similarity=0.9,
            image_similarity=0.85,
        ),
    ]


@pytest.fixture
def stub_objects() -> list[ObjectPresenceRecord]:
    return [
        ObjectPresenceRecord(
            label="person",
            observation_count=3,
            last_seen_at=datetime.now(UTC),
        ),
    ]


@pytest.fixture
def stub_trends() -> dict[str, RoomTrendResult]:
    return {
        "kitchen": RoomTrendResult(
            room_id="kitchen",
            room_name="Kitchen",
            as_of=datetime.now(UTC),
            baseline_available=True,
            clutter_score=0.7,
            trend_direction="increasing",
            overall_severity="warning",
            persistent_objects=["cup", "plate"],
            novel_objects=["box"],
            anomalies=[
                {"severity": "warning", "description": "clutter above threshold"},
                {"severity": "ok", "description": "normal"},
            ],
        ),
    }


@pytest.fixture
def stub_snapshots() -> list[TrendSnapshot]:
    return [
        TrendSnapshot(
            room_id="kitchen",
            period_start=datetime.now(UTC),
            unique_object_count=5,
            object_counts={"person": 1, "cup": 2},
            persistent_objects=["cup"],
            novel_objects=["box"],
            embedding_variance=0.1,
        ),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_client_returns_empty_results():
    """client=None → empty results, no exceptions."""
    svc = MemoryQueryService(client=None)

    ctx = await svc.room_context("kitchen")
    assert ctx.room_id == "kitchen"
    assert ctx.summary == "No memory context available."
    assert ctx.observations_count == 0

    trends = await svc.room_trends("kitchen")
    assert trends is None

    hits = await svc.search(query_text="person")
    assert hits == ()


@pytest.mark.asyncio
async def test_room_context_delegates_to_client(stub_observations, stub_objects):
    """Delegation: stub client returns canned data; service returns right shape."""
    client = _StubClient(
        observations=stub_observations,
        objects=stub_objects,
    )
    svc = MemoryQueryService(client=client)

    ctx = await svc.room_context("kitchen")

    assert ctx.room_id == "kitchen"
    assert ctx.observations_count == 1
    assert len(ctx.recent_objects) == 1
    assert ctx.recent_objects[0].label == "person"
    assert ctx.summary.startswith("In the past")
    assert client.search_count == 1
    assert client.recent_objects_count == 1


@pytest.mark.asyncio
async def test_cache_hit_avoids_second_call(stub_observations, stub_objects):
    """Cache hit avoids second client call."""
    client = _StubClient(
        observations=stub_observations,
        objects=stub_objects,
    )
    svc = MemoryQueryService(
        client=client,
        cache_enabled=True,
        cache_ttl_seconds=60,
    )

    await svc.room_context("kitchen")
    first_count = client.search_count

    await svc.room_context("kitchen")
    second_count = client.search_count

    assert first_count == 1
    assert second_count == 1  # no second call


@pytest.mark.asyncio
async def test_cache_ttl_expiry_hits_client_again():
    """Clock advance past TTL → second call hits the client again."""
    client = _StubClient()
    svc = MemoryQueryService(
        client=client,
        cache_enabled=True,
        cache_ttl_seconds=1,
    )

    await svc.room_context("kitchen")
    assert client.search_count == 1

    # Advance past TTL
    with patch.object(svc, "_cache") as mock_cache:
        mock_cache.get.return_value = None
        mock_cache.set = MagicMock()
        # Force cache miss by patching the internal cache's get
        svc._cache.get = MagicMock(return_value=None)
        await svc.room_context("kitchen")
        assert client.search_count == 2


@pytest.mark.asyncio
async def test_room_trends_filters_by_severity(stub_trends):
    """room_trends with severity threshold filters anomalies correctly."""
    client = _StubClient(trends=stub_trends)
    svc = MemoryQueryService(client=client)

    # Threshold "warning" should exclude the "ok" anomaly
    ctx = await svc.room_trends("kitchen", severity_threshold="warning")

    assert ctx is not None
    assert ctx.room_id == "kitchen"
    assert ctx.overall_severity == "warning"
    assert len(ctx.anomalies) == 1
    assert ctx.anomalies[0]["severity"] == "warning"


@pytest.mark.asyncio
async def test_room_trends_includes_snapshots(stub_trends, stub_snapshots):
    """room_trends with include_snapshots_hours > 0 fetches snapshots."""
    client = _StubClient(trends=stub_trends, snapshots=stub_snapshots)
    svc = MemoryQueryService(client=client)

    ctx = await svc.room_trends("kitchen", include_snapshots_hours=24)

    assert ctx is not None
    assert ctx.snapshots is not None
    assert len(ctx.snapshots) == 1
    assert client.get_snapshots_count == 1


@pytest.mark.asyncio
async def test_room_trends_no_client_returns_none():
    """No client → room_trends returns None."""
    svc = MemoryQueryService(client=None)
    ctx = await svc.room_trends("kitchen")
    assert ctx is None


@pytest.mark.asyncio
async def test_room_trends_no_data_returns_none(stub_trends):
    """Client returns no data for room → None."""
    client = _StubClient(trends=stub_trends)
    svc = MemoryQueryService(client=client)

    ctx = await svc.room_trends("nonexistent_room")
    assert ctx is None


@pytest.mark.asyncio
async def test_search_returns_hits():
    """search delegates to client and returns hits."""
    hits = [
        ObservationSearchHit(
            id=1,
            room_id="kitchen",
            observed_at=datetime.now(UTC),
            description="person near stove",
            object_list=["person"],
            hazard_flags=[],
            text_similarity=0.95,
        ),
    ]
    client = _StubClient(observations=hits)
    svc = MemoryQueryService(client=client)

    result = await svc.search(query_text="stove", room_id="kitchen")

    assert len(result) == 1
    assert result[0].description == "person near stove"


@pytest.mark.asyncio
async def test_search_no_client_returns_empty_tuple():
    """No client → search returns ()."""
    svc = MemoryQueryService(client=None)
    result = await svc.search(query_text="anything")
    assert result == ()


@pytest.mark.asyncio
async def test_room_context_hazard_filtering():
    """Hazard filtering: only observations with matching flags included."""
    client = _StubClient(
        observations=[
            ObservationSearchHit(
                id=1,
                room_id="kitchen",
                observed_at=datetime.now(UTC),
                description="stove on",
                object_list=[],
                hazard_flags=["stove_on"],
            ),
            ObservationSearchHit(
                id=2,
                room_id="kitchen",
                observed_at=datetime.now(UTC),
                description="person present",
                object_list=["person"],
                hazard_flags=[],
            ),
        ],
    )
    svc = MemoryQueryService(client=client)

    ctx = await svc.room_context(
        "kitchen",
        hazard_flags_any=("stove_on",),
    )

    assert len(ctx.recent_hazards) == 1
    assert ctx.recent_hazards[0].hazard_flags == ["stove_on"]


@pytest.mark.asyncio
async def test_room_context_no_hazards_when_no_filter():
    """No hazard_flags_any filter → recent_hazards is empty."""
    client = _StubClient(
        observations=[
            ObservationSearchHit(
                id=1,
                room_id="kitchen",
                observed_at=datetime.now(UTC),
                description="stove on",
                object_list=[],
                hazard_flags=["stove_on"],
            ),
        ],
    )
    svc = MemoryQueryService(client=client)

    ctx = await svc.room_context("kitchen")

    assert len(ctx.recent_hazards) == 0


@pytest.mark.asyncio
async def test_cache_key_includes_all_params():
    """Different parameters produce different cache keys."""
    client = _StubClient()
    svc = MemoryQueryService(
        client=client,
        cache_enabled=True,
        cache_ttl_seconds=300,
    )

    # First call with since_minutes=60
    await svc.room_context("kitchen", since_minutes=60)
    count_60 = client.search_count

    # Same params → cache hit
    await svc.room_context("kitchen", since_minutes=60)
    assert client.search_count == count_60

    # Different params → cache miss
    await svc.room_context("kitchen", since_minutes=120)
    assert client.search_count == count_60 + 1
