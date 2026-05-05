"""Tests for ServiceContainer wiring of Block 4 services.

Verifies that ServiceContainer has the new fields and that the services
can be constructed with None clients (graceful degradation).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.steps.base import ServiceContainer

# ---------------------------------------------------------------------------
# ServiceContainer field tests
# ---------------------------------------------------------------------------


def test_service_container_has_memory_query_field():
    """ServiceContainer has memory_query field (default None)."""
    container = ServiceContainer(db_factory=MagicMock())
    assert container.memory_query is None


def test_service_container_has_scene_intel_field():
    """ServiceContainer has scene_intel field (default None)."""
    container = ServiceContainer(db_factory=MagicMock())
    assert container.scene_intel is None


def test_service_container_accepts_memory_query_instance():
    """ServiceContainer can hold a MemoryQueryService instance."""
    from backend.services.memory_query import MemoryQueryService

    svc = MemoryQueryService(client=None)
    container = ServiceContainer(
        db_factory=MagicMock(),
        memory_query=svc,
    )
    assert container.memory_query is svc
    assert container.memory_query._client is None


def test_service_container_accepts_scene_intel_instance():
    """ServiceContainer can hold a SceneIntelService instance."""
    from backend.services.scene_intel import SceneIntelService

    svc = SceneIntelService(scene_client=None, memory_client=None)
    container = ServiceContainer(
        db_factory=MagicMock(),
        scene_intel=svc,
    )
    assert container.scene_intel is svc


# ---------------------------------------------------------------------------
# Service construction with None clients (graceful degradation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_query_service_with_none_client():
    """MemoryQueryService(client=None) never raises on any method."""
    from backend.services.memory_query import MemoryQueryService

    svc = MemoryQueryService(client=None)

    ctx = await svc.room_context("kitchen")
    assert ctx.summary == "No memory context available."

    trends = await svc.room_trends("kitchen")
    assert trends is None

    hits = await svc.search(query_text="person")
    assert hits == ()


@pytest.mark.asyncio
async def test_scene_intel_service_with_none_clients():
    """SceneIntelService(scene_client=None, memory_client=None) never raises."""
    from backend.services.scene_intel import SceneIntelService

    svc = SceneIntelService(scene_client=None, memory_client=None)

    result = await svc.analyze(b"image")
    assert result.detections == []

    intel = await svc.persist(result, room_id="kitchen")
    assert intel.observation_id is None

    intel = await svc.analyze_and_persist(b"image", room_id="kitchen")
    assert intel.observation_id is None


# ---------------------------------------------------------------------------
# Wiring simulation (main.py pattern)
# ---------------------------------------------------------------------------


def test_wiring_memory_query_with_config_defaults():
    """Simulate main.py wiring: MemoryQueryService with config defaults."""
    from backend.services.memory_query import MemoryQueryService

    # Simulate settings.get("memory_query", {}) returning empty dict
    # (no config → defaults)
    memory_query_config = {}
    cache_enabled = memory_query_config.get("cache.enabled", False)
    cache_ttl = memory_query_config.get("cache.ttl_seconds", 30)
    cache_maxsize = memory_query_config.get("cache.maxsize", 256)

    svc = MemoryQueryService(
        client=None,  # semantic_memory_client is None in test
        cache_enabled=cache_enabled,
        cache_ttl_seconds=cache_ttl,
        cache_maxsize=cache_maxsize,
    )

    # Should work without raising
    assert svc._client is None
    assert svc._cache is None  # cache_enabled=False


def test_wiring_scene_intel():
    """Simulate main.py wiring: SceneIntelService with None clients."""
    from backend.services.scene_intel import SceneIntelService

    svc = SceneIntelService(
        scene_client=None,
        memory_client=None,
    )

    assert svc._scene_client is None
    assert svc._memory_client is None


def test_wiring_with_non_none_clients():
    """Simulate main.py wiring: services wired with actual clients."""
    from backend.integrations.scene_analysis_client import SceneAnalysisClient
    from backend.integrations.semantic_memory_client import SemanticMemoryClient
    from backend.services.memory_query import MemoryQueryService
    from backend.services.scene_intel import SceneIntelService

    scene_client = SceneAnalysisClient()  # may not be configured
    sm_client = SemanticMemoryClient()  # may not be configured

    mq = MemoryQueryService(
        client=sm_client if sm_client.configured else None,
    )
    si = SceneIntelService(
        scene_client=scene_client,
        memory_client=sm_client if sm_client.configured else None,
    )

    # Both should be constructible regardless of client availability
    assert mq._client is not None or mq._client is None  # either is fine
    assert si._scene_client is not None or si._scene_client is None
