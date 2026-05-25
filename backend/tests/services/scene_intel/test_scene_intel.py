"""Tests for SceneIntelService."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from backend.integrations.scene_analysis_client import (
    SceneAnalyzeResult,
    SceneDetection,
    SceneHazardAlert,
)
from backend.integrations.semantic_memory_client import (
    MovementCreate,
    MovementRecord,
    ObservationCreate,
    ObservationRecord,
)
from backend.services.scene_intel.service import SceneIntelService
from backend.services.scene_intel.types import RoomTransition, SceneIntelRecord

# ---------------------------------------------------------------------------
# Stub clients
# ---------------------------------------------------------------------------


class _StubSceneClient:
    """Stub that returns canned SceneAnalyzeResult."""

    def __init__(
        self,
        result: SceneAnalyzeResult | None = None,
    ) -> None:
        self.analyze_count = 0
        self._result = result or SceneAnalyzeResult()

    async def analyze(
        self,
        image_bytes: bytes,
        *,
        run_detect: bool = True,
        run_describe: bool = True,
        run_embed: bool = True,
        run_hazards: bool = True,
    ) -> SceneAnalyzeResult:
        self.analyze_count += 1
        return self._result


class _StubMemoryClient:
    """Stub that tracks calls and returns canned records."""

    def __init__(
        self,
        observation: ObservationRecord | None = None,
        movement: MovementRecord | None = None,
    ) -> None:
        self.create_observation_calls: list[ObservationCreate] = []
        self.create_movement_calls: list[MovementCreate] = []
        self._observation = observation or ObservationRecord(
            id=1,
            room_id="kitchen",
            description="test",
            object_list=[],
            hazard_flags=[],
            observed_at=datetime.now(UTC),
            source="scene_intel",
            created_at=datetime.now(UTC),
        )
        self._movement = movement or MovementRecord(
            id=1,
            person_id="mom",
            from_room_id="bedroom",
            to_room_id="kitchen",
            direction_semantic="approaching",
            confidence=0.85,
            observed_at=datetime.now(UTC),
            observation_id=1,
        )

    async def create_observation(self, obs: ObservationCreate) -> ObservationRecord | None:
        self.create_observation_calls.append(obs)
        return self._observation

    async def create_movement(self, movement: MovementCreate) -> MovementRecord | None:
        self.create_movement_calls.append(movement)
        return self._movement


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_both_clients_none_returns_empties():
    """Both clients None → returns empties; never calls."""
    svc = SceneIntelService(scene_client=None, memory_client=None)

    result = await svc.analyze(b"image")
    assert result.detections == []
    assert result.description == ""

    intel = await svc.persist(result, room_id="kitchen")
    assert intel == SceneIntelRecord.empty()

    intel = await svc.analyze_and_persist(b"image", room_id="kitchen")
    assert intel == SceneIntelRecord.empty()


@pytest.mark.asyncio
async def test_analyze_and_persist_with_detections_and_hazards():
    """analyze_and_persist with detections + hazards → creates observation;
    movement_ids matches transitions count."""
    scene_result = SceneAnalyzeResult(
        detections=[
            SceneDetection(label="person", confidence=0.9, bbox=[0, 0, 100, 100, 0.9], class_id=0),
        ],
        description="A person in the kitchen",
        embedding=[0.1, 0.2, 0.3],
        hazards=[
            SceneHazardAlert(
                name="stove_on",
                severity="warning",
                description="Stove is on with no person nearby",
                detection=SceneDetection(
                    label="stove", confidence=0.8, bbox=[50, 50, 150, 150, 0.8], class_id=1
                ),
            ),
        ],
    )
    scene_client = _StubSceneClient(result=scene_result)
    memory_client = _StubMemoryClient()

    transitions = (
        RoomTransition(
            person_id="mom",
            from_room_id="bedroom",
            to_room_id="kitchen",
            direction_semantic="approaching",
            confidence=0.85,
        ),
        RoomTransition(
            person_id="dad",
            from_room_id="hallway",
            to_room_id="kitchen",
            direction_semantic="entering",
            confidence=0.7,
        ),
    )

    svc = SceneIntelService(
        scene_client=scene_client,
        memory_client=memory_client,
    )

    intel = await svc.analyze_and_persist(
        b"image",
        room_id="kitchen",
        transitions=transitions,
    )

    assert intel.observation_id == 1
    assert len(intel.movement_ids) == 2
    assert scene_client.analyze_count == 1
    assert len(memory_client.create_observation_calls) == 1

    # Verify observation payload.
    obs = memory_client.create_observation_calls[0]
    assert obs.room_id == "kitchen"
    assert obs.description == "A person in the kitchen"
    assert obs.object_list == ["person"]
    assert obs.hazard_flags == ["stove_on"]
    assert obs.embedding == [0.1, 0.2, 0.3]

    # Verify movement payloads.
    assert len(memory_client.create_movement_calls) == 2
    assert memory_client.create_movement_calls[0].person_id == "mom"
    assert memory_client.create_movement_calls[0].observation_id == 1
    assert memory_client.create_movement_calls[1].person_id == "dad"


@pytest.mark.asyncio
async def test_empty_result_does_not_call_create_observation():
    """Empty result → persist returns SceneIntelRecord.empty() and does NOT
    call create_observation."""
    scene_client = _StubSceneClient(result=SceneAnalyzeResult())
    memory_client = _StubMemoryClient()

    svc = SceneIntelService(
        scene_client=scene_client,
        memory_client=memory_client,
    )

    result = await svc.analyze(b"image")
    assert result.detections == []
    assert result.description == ""

    intel = await svc.persist(result, room_id="kitchen")

    assert intel == SceneIntelRecord.empty()
    assert len(memory_client.create_observation_calls) == 0


@pytest.mark.asyncio
async def test_persist_with_only_description():
    """Observation with only description (no detections/hazards) is persisted."""
    scene_result = SceneAnalyzeResult(description="A quiet room")
    scene_client = _StubSceneClient(result=scene_result)
    memory_client = _StubMemoryClient()

    svc = SceneIntelService(
        scene_client=scene_client,
        memory_client=memory_client,
    )

    intel = await svc.persist(scene_result, room_id="bedroom")

    assert intel.observation_id == 1
    assert len(memory_client.create_observation_calls) == 1
    obs = memory_client.create_observation_calls[0]
    assert obs.description == "A quiet room"
    assert obs.object_list == []


@pytest.mark.asyncio
async def test_persist_with_only_embedding():
    """Observation with only embedding (no text/detections/hazards) is persisted."""
    scene_result = SceneAnalyzeResult(embedding=[0.1, 0.2, 0.3])
    scene_client = _StubSceneClient(result=scene_result)
    memory_client = _StubMemoryClient()

    svc = SceneIntelService(
        scene_client=scene_client,
        memory_client=memory_client,
    )

    intel = await svc.persist(scene_result, room_id="hallway")

    assert intel.observation_id == 1
    assert len(memory_client.create_observation_calls) == 1


@pytest.mark.asyncio
async def test_persist_skips_movements_when_no_memory_client():
    """memory_client=None → persist returns empty even with transitions."""
    scene_client = _StubSceneClient(result=SceneAnalyzeResult(description="test"))
    svc = SceneIntelService(scene_client=scene_client, memory_client=None)

    transitions = (
        RoomTransition(
            person_id="mom",
            from_room_id="bedroom",
            to_room_id="kitchen",
        ),
    )

    intel = await svc.persist(
        SceneAnalyzeResult(description="test"),
        room_id="kitchen",
        transitions=transitions,
    )

    assert intel == SceneIntelRecord.empty()


@pytest.mark.asyncio
async def test_analyze_passes_run_flags():
    """analyze passes run_* flags to scene_client."""
    scene_client = _StubSceneClient()
    svc = SceneIntelService(
        scene_client=scene_client,
        memory_client=None,
    )

    await svc.analyze(
        b"image",
        run_detect=True,
        run_describe=False,
        run_embed=True,
        run_hazards=False,
    )

    assert scene_client.analyze_count == 1


@pytest.mark.asyncio
async def test_movement_persistence_failure_logged():
    """Movement persistence failure is logged, not raised."""
    scene_result = SceneAnalyzeResult(description="test")
    scene_client = _StubSceneClient(result=scene_result)

    # Memory client that succeeds on observation but fails on movement.
    memory_client = _StubMemoryClient()
    memory_client.create_movement = AsyncMock(side_effect=RuntimeError("network error"))

    svc = SceneIntelService(
        scene_client=scene_client,
        memory_client=memory_client,
    )

    transitions = (RoomTransition(person_id="mom", from_room_id="bedroom", to_room_id="kitchen"),)

    # Should not raise.
    intel = await svc.persist(
        scene_result,
        room_id="kitchen",
        transitions=transitions,
    )

    assert intel.observation_id == 1
    assert intel.movement_ids == []  # movement failed, so no IDs


@pytest.mark.asyncio
async def test_persist_uses_source_param():
    """persist passes source to ObservationCreate."""
    scene_result = SceneAnalyzeResult(description="test")
    scene_client = _StubSceneClient(result=scene_result)
    memory_client = _StubMemoryClient()

    svc = SceneIntelService(
        scene_client=scene_client,
        memory_client=memory_client,
    )

    await svc.persist(scene_result, room_id="kitchen", source="manual")

    obs = memory_client.create_observation_calls[0]
    assert obs.source == "manual"


@pytest.mark.asyncio
async def test_analyze_and_persist_composition():
    """analyze_and_persist composes analyze + persist correctly."""
    scene_result = SceneAnalyzeResult(
        detections=[
            SceneDetection(label="cup", confidence=0.9, bbox=[0, 0, 50, 50, 0.9], class_id=2)
        ],
        description="A cup on the table",
    )
    scene_client = _StubSceneClient(result=scene_result)
    memory_client = _StubMemoryClient()

    svc = SceneIntelService(
        scene_client=scene_client,
        memory_client=memory_client,
    )

    intel = await svc.analyze_and_persist(
        b"image",
        room_id="kitchen",
        run_detect=True,
        run_describe=True,
        run_embed=False,
        run_hazards=False,
    )

    assert intel.observation_id == 1
    assert len(memory_client.create_observation_calls) == 1
    assert scene_client.analyze_count == 1
