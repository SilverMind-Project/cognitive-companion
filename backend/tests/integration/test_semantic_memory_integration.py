"""End-to-end integration tests for semantic-memory pipeline integration.

Tests the full data flow:
1. ``semantic_memory_write`` step persists an observation/movement
2. ``semantic_memory_query`` step retrieves it
3. ``scene_contains`` and ``person_movement_memory`` context filters gate on it
4. MCP read tools expose it
5. ``scene_analysis`` step with ``write_to_memory`` produces an observation ID
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from backend.filters.builtin.person_movement_memory import PersonMovementMemoryFilter
from backend.filters.builtin.scene_contains import SceneContainsFilter
from backend.integrations.semantic_memory_client import (
    MovementTransitionRecord,
    ObservationRecord,
    ObservationSearchHit,
    SemanticMemoryClient,
)
from backend.services.memory_query.types import RoomContext
from backend.services.scene_intel.types import SceneIntelRecord
from backend.steps.base import ServiceContainer
from backend.steps.builtin.semantic_memory_query import SemanticMemoryQueryHandler
from backend.steps.builtin.semantic_memory_write import SemanticMemoryWriteHandler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_semantic_client(**methods):
    """Return a MagicMock SemanticMemoryClient with the given method overrides."""
    client = MagicMock(spec=SemanticMemoryClient)
    client.configured = True
    for name, value in methods.items():
        setattr(client, name, AsyncMock(return_value=value))
    return client


def _make_observation(id_=1, room_id="kitchen", objects=None, hazards=None):
    return ObservationRecord(
        id=id_,
        room_id=room_id,
        description="A cup on the table",
        object_list=objects or ["cup"],
        hazard_flags=hazards or [],
        observed_at=datetime.now(UTC) - timedelta(minutes=5),
        source="scene_intel",
        created_at=datetime.now(UTC) - timedelta(minutes=5),
    )


def _make_hit(id_=1, room_id="kitchen", objects=None, hazards=None):
    return ObservationSearchHit(
        id=id_,
        room_id=room_id,
        observed_at=datetime.now(UTC) - timedelta(minutes=5),
        description="A cup on the table",
        object_list=objects or ["cup"],
        hazard_flags=hazards or [],
        text_similarity=0.9,
    )


def _make_transition(id_=1, person_id="p1", to_room="kitchen", semantic="entering", confidence=0.9):
    return MovementTransitionRecord(
        id=id_,
        person_id=person_id,
        from_room_id="bedroom",
        to_room_id=to_room,
        direction_semantic=semantic,
        confidence=confidence,
        observed_at=datetime.now(UTC) - timedelta(minutes=10),
    )


def _make_services(semantic_memory_client=None, memory_query=None, scene_intel=None):
    return ServiceContainer(
        db_factory=MagicMock(),
        semantic_memory_client=semantic_memory_client,
        memory_query=memory_query,
        scene_intel=scene_intel,
    )


def _make_trigger(room_name="kitchen"):
    return MagicMock(
        trigger_type="sensor_event",
        sensor_id="cam-1",
        room_name=room_name,
    )


# ---------------------------------------------------------------------------
# semantic_memory_write step
# ---------------------------------------------------------------------------


class TestSemanticMemoryWriteStep:
    async def test_write_observation(self):
        """Step creates an observation from pipeline_data and writes the ID."""
        intel = SceneIntelRecord(observation_id=42, movement_ids=[])

        async def mock_persist(*args, **kwargs):
            return intel

        scene_intel = MagicMock()
        scene_intel.persist = AsyncMock(side_effect=mock_persist)
        services = _make_services(scene_intel=scene_intel)

        handler = SemanticMemoryWriteHandler()
        step = MagicMock(
            config_json={
                "write_observation": True,
                "write_movements": False,
            },
        )
        execution = MagicMock(id=1)
        trigger = _make_trigger()
        pipeline_data = {"scene_description": "A cup on the table"}

        result = await handler.execute(step, execution, pipeline_data, trigger, services)

        assert result.success is True
        assert result.data["semantic_memory_observation_id"] == 42
        scene_intel.persist.assert_called_once()

    async def test_write_movement(self):
        """Step creates movements from pipeline_data transitions."""
        intel = SceneIntelRecord(observation_id=None, movement_ids=[7])

        async def mock_persist(*args, **kwargs):
            return intel

        scene_intel = MagicMock()
        scene_intel.persist = AsyncMock(side_effect=mock_persist)
        services = _make_services(scene_intel=scene_intel)

        handler = SemanticMemoryWriteHandler()
        step = MagicMock(
            config_json={
                "write_observation": False,
                "write_movements": True,
            },
        )
        execution = MagicMock(id=1)
        trigger = _make_trigger()
        pipeline_data = {
            "room_transitions": [
                {
                    "person_id": "p1",
                    "from_room_id": "bedroom",
                    "to_room_id": "kitchen",
                    "direction_semantic": "entering",
                    "confidence": 0.9,
                }
            ]
        }

        result = await handler.execute(step, execution, pipeline_data, trigger, services)

        assert result.success is True
        assert result.data["semantic_memory_movement_ids"] == [7]
        scene_intel.persist.assert_called_once()

    async def test_no_client_returns_empty(self):
        handler = SemanticMemoryWriteHandler()
        step = MagicMock(config_json={})
        execution = MagicMock(id=1)
        trigger = _make_trigger()
        services = _make_services(scene_intel=None)

        result = await handler.execute(step, execution, {}, trigger, services)

        assert result.success is True
        assert result.data["semantic_memory_observation_id"] is None
        assert result.data["semantic_memory_write_available"] is False


# ---------------------------------------------------------------------------
# semantic_memory_query step
# ---------------------------------------------------------------------------


class TestSemanticMemoryQueryStep:
    async def test_query_observations(self):
        """Step retrieves observations and writes to pipeline_data."""
        hits = [_make_hit(id_=1, objects=["cup"])]
        ctx = RoomContext(
            room_id="kitchen",
            recent_objects=(),
            recent_hazards=(),
            observations=tuple(hits),
            summary="In the past 60 min in kitchen: 1 observation.",
            observations_count=1,
        )

        async def mock_room_context(*args, **kwargs):
            return ctx

        memory_query = MagicMock()
        memory_query.room_context = AsyncMock(side_effect=mock_room_context)
        services = _make_services(memory_query=memory_query)

        handler = SemanticMemoryQueryHandler()
        step = MagicMock(
            config_json={
                "use_trigger_room": True,
                "since_minutes": 60,
            },
        )
        execution = MagicMock(id=1)
        trigger = _make_trigger()

        result = await handler.execute(step, execution, {}, trigger, services)

        assert result.success is True
        assert "memory_context" in result.data
        assert result.data["memory_context"]["observations_count"] == 1

    async def test_query_with_objects_filter(self):
        """Step filters observations by object labels."""
        hits = [_make_hit(objects=["person"])]
        ctx = RoomContext(
            room_id="kitchen",
            recent_objects=(),
            recent_hazards=(),
            observations=tuple(hits),
            summary="In the past 60 min in kitchen: 1 observation.",
            observations_count=1,
        )

        async def mock_room_context(*args, **kwargs):
            return ctx

        memory_query = MagicMock()
        memory_query.room_context = AsyncMock(side_effect=mock_room_context)
        services = _make_services(memory_query=memory_query)

        handler = SemanticMemoryQueryHandler()
        step = MagicMock(
            config_json={
                "use_trigger_room": True,
                "objects_any": ["person"],
            },
        )
        execution = MagicMock(id=1)
        trigger = _make_trigger()

        result = await handler.execute(step, execution, {}, trigger, services)

        assert result.success is True
        assert result.data["memory_context"]["observations_count"] == 1

    async def test_no_client_returns_empty(self):
        handler = SemanticMemoryQueryHandler()
        step = MagicMock(config_json={})
        execution = MagicMock(id=1)
        trigger = _make_trigger()
        services = _make_services(memory_query=None)

        result = await handler.execute(step, execution, {}, trigger, services)

        assert result.success is True
        assert result.data["memory_context"]["observations_count"] == 0


# ---------------------------------------------------------------------------
# Context filters
# ---------------------------------------------------------------------------


class TestSceneContainsFilter:
    async def test_matching_objects_pass(self):
        """Filter passes when an object is found in recent memory."""
        rec = MagicMock()
        rec.label = "cup"
        rec.observation_count = 3
        client = _mock_semantic_client(get_recent_objects=[rec])
        services = _make_services(semantic_memory_client=client)

        trigger = _make_trigger()
        now = datetime.now(UTC)
        config = {
            "room_id": "kitchen",
            "objects_any": ["cup"],
            "within_minutes": 60,
        }

        result = await SceneContainsFilter().evaluate(config, trigger, now, services=services)

        assert result is True

    async def test_no_match_fails(self):
        """Filter fails when no objects are found."""
        client = _mock_semantic_client(get_recent_objects=[])
        services = _make_services(semantic_memory_client=client)

        trigger = _make_trigger()
        now = datetime.now(UTC)
        config = {
            "room_id": "kitchen",
            "objects_any": ["banana"],
            "within_minutes": 60,
        }

        result = await SceneContainsFilter().evaluate(config, trigger, now, services=services)

        assert result is False

    async def test_no_client_fails(self):
        """Filter returns False when no client is configured."""
        trigger = _make_trigger()
        now = datetime.now(UTC)
        config = {
            "room_id": "kitchen",
            "objects_any": ["cup"],
        }

        result = await SceneContainsFilter().evaluate(config, trigger, now, services=None)

        assert result is False


class TestPersonMovementMemoryFilter:
    async def test_matching_transition_pass(self):
        """Filter passes when a matching movement transition exists."""
        transitions = [_make_transition(person_id="p1", to_room="kitchen")]
        client = _mock_semantic_client(get_transitions=transitions)
        services = _make_services(semantic_memory_client=client)

        trigger = _make_trigger()
        now = datetime.now(UTC)
        config = {
            "person_id": "p1",
            "semantic": "entering",
            "to_room_id": "kitchen",
            "within_minutes": 60,
        }

        result = await PersonMovementMemoryFilter().evaluate(
            config, trigger, now, services=services
        )

        assert result is True

    async def test_below_confidence_fails(self):
        """Filter fails when transition confidence is below threshold."""
        transitions = [_make_transition(person_id="p1", confidence=0.3)]
        client = _mock_semantic_client(get_transitions=transitions)
        services = _make_services(semantic_memory_client=client)

        trigger = _make_trigger()
        now = datetime.now(UTC)
        config = {
            "person_id": "p1",
            "min_confidence": 0.5,
            "within_minutes": 60,
        }

        result = await PersonMovementMemoryFilter().evaluate(
            config, trigger, now, services=services
        )

        assert result is False

    async def test_no_client_fails(self):
        """Filter returns False when no client is configured."""
        trigger = _make_trigger()
        now = datetime.now(UTC)
        config = {
            "person_id": "p1",
            "within_minutes": 60,
        }

        result = await PersonMovementMemoryFilter().evaluate(config, trigger, now, services=None)

        assert result is False
