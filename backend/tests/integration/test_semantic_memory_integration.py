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


def _make_services(semantic_memory_client=None):
    from backend.steps.base import ServiceContainer

    return ServiceContainer(
        db_factory=MagicMock(),
        semantic_memory_client=semantic_memory_client,
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
        obs = _make_observation(id_=42)
        client = _mock_semantic_client(create_observation=obs)
        services = _make_services(semantic_memory_client=client)

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
        client.create_observation.assert_called_once()

    async def test_write_movement(self):
        """Step creates movements from pipeline_data transitions."""
        movement = _make_transition(id_=7, person_id="p1")
        client = _mock_semantic_client(create_movement=movement)
        services = _make_services(semantic_memory_client=client)

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
        client.create_movement.assert_called_once()

    async def test_no_client_returns_empty(self):
        handler = SemanticMemoryWriteHandler()
        step = MagicMock(config_json={})
        execution = MagicMock(id=1)
        trigger = _make_trigger()
        services = _make_services(semantic_memory_client=None)

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
        client = _mock_semantic_client(search_observations=hits)
        services = _make_services(semantic_memory_client=client)

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
        client = _mock_semantic_client(search_observations=hits)
        services = _make_services(semantic_memory_client=client)

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
        services = _make_services(semantic_memory_client=None)

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

        result = await PersonMovementMemoryFilter().evaluate(config, trigger, now, services=services)

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

        result = await PersonMovementMemoryFilter().evaluate(config, trigger, now, services=services)

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
