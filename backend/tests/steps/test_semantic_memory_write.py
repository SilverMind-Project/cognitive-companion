"""Unit tests for :class:`~backend.steps.builtin.semantic_memory_write.SemanticMemoryWriteHandler`.

DL-M02 characterization: this step already goes through the ``scene_intel``
write seam (``services.scene_intel.persist``), so the refactor does not touch
it. These tests pin its current input/output contract, including a known
pre-existing defect (see the note on ``test_detections_and_hazards_from_pipeline_data_are_not_forwarded``):
the step resolves ``object_list``/``hazard_flags`` from pipeline_data but
never places them on the ``SceneAnalyzeResult`` it hands to ``persist()``, so
``persist()`` (which derives them from ``result.detections``/``result.hazards``)
always sees them empty for this caller. Filed as a dated correction in
``daily-living-m00-program-overview-and-findings.md`` rather than fixed here,
per the milestone's pure-refactor scope (DL-M01 found zero
``semantic_memory_write`` executions in the live database, so there is no
live-traffic urgency).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

from backend.services.scene_intel.types import RoomTransition, SceneIntelRecord
from backend.steps.base import ServiceContainer, TriggerContext
from backend.steps.builtin.semantic_memory_write import SemanticMemoryWriteHandler

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeExecution:
    id: int = 1


@dataclass
class _FakeStep:
    config_json: dict = field(default_factory=dict)


def _make_step(config: dict | None = None) -> _FakeStep:
    return _FakeStep(config_json=config or {})


def _make_trigger(room_name: str | None = "Kitchen") -> TriggerContext:
    return TriggerContext(trigger_type="sensor_event", room_name=room_name)


def _make_services(scene_intel=None) -> ServiceContainer:
    return ServiceContainer(db_factory=MagicMock(), scene_intel=scene_intel)


def _make_scene_intel(record: SceneIntelRecord | None = None) -> MagicMock:
    scene_intel = MagicMock()
    scene_intel.persist = AsyncMock(
        return_value=record or SceneIntelRecord(observation_id=5, movement_ids=[9], source="scene_intel")
    )
    return scene_intel


_HANDLER = SemanticMemoryWriteHandler()


# ---------------------------------------------------------------------------
# Missing-service path
# ---------------------------------------------------------------------------


class TestNoSceneIntel:
    async def test_returns_empty_output(self):
        services = _make_services(scene_intel=None)

        result = await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(), services
        )

        assert result.data == {
            "semantic_memory_observation_id": None,
            "semantic_memory_movement_ids": [],
            "semantic_memory_write_available": False,
            "semantic_memory_persons_count": None,
            "semantic_memory_persons_per_frame": [],
        }


# ---------------------------------------------------------------------------
# Success path / payload characterization
# ---------------------------------------------------------------------------


class TestPersistPayload:
    async def test_success_calls_persist_with_expected_args(self):
        scene_intel = _make_scene_intel()
        services = _make_services(scene_intel=scene_intel)
        pipeline_data = {
            "scene_description": "A person in the kitchen",
            "scene_detections": [{"label": "person"}],
            "scene_embedding": [0.1, 0.2, 0.3],
            "scene_hazards": [{"name": "stove_on"}],
            "room_transitions": [
                {
                    "person_id": "mom",
                    "from_room_id": "bedroom",
                    "to_room_id": "kitchen",
                    "direction_semantic": "entering",
                    "confidence": 0.9,
                }
            ],
        }

        result = await _HANDLER.execute(
            _make_step({"source": "manual"}),
            _FakeExecution(),
            pipeline_data,
            _make_trigger(room_name="Kitchen"),
            services,
        )

        scene_intel.persist.assert_awaited_once()
        call = scene_intel.persist.await_args
        analyzed_result = call.args[0]
        assert analyzed_result.description == "A person in the kitchen"
        assert analyzed_result.embedding == [0.1, 0.2, 0.3]
        assert call.kwargs["room_id"] == "Kitchen"
        assert call.kwargs["source"] == "manual"
        transitions = call.kwargs["transitions"]
        assert len(transitions) == 1
        assert transitions[0] == RoomTransition(
            person_id="mom",
            from_room_id="bedroom",
            to_room_id="kitchen",
            direction_semantic="entering",
            confidence=0.9,
        )

        assert result.data == {
            "semantic_memory_observation_id": 5,
            "semantic_memory_movement_ids": [9],
            "semantic_memory_write_available": True,
            # No frames_key in this pipeline_data, so no count is claimed.
            "semantic_memory_persons_count": None,
            "semantic_memory_persons_per_frame": [],
        }

    async def test_detections_and_hazards_from_pipeline_data_are_not_forwarded(self):
        """Pre-existing defect, preserved by this pure refactor (see module docstring):
        the step resolves object_list/hazard_flags from pipeline_data but never
        attaches them to the SceneAnalyzeResult passed to persist(), so persist()
        (which reads result.detections/result.hazards) always sees them empty here."""
        scene_intel = _make_scene_intel()
        services = _make_services(scene_intel=scene_intel)
        pipeline_data = {
            "scene_detections": [{"label": "person"}, {"label": "stove"}],
            "scene_hazards": [{"name": "stove_on"}],
        }

        await _HANDLER.execute(
            _make_step(), _FakeExecution(), pipeline_data, _make_trigger(), services
        )

        analyzed_result = scene_intel.persist.await_args.args[0]
        assert analyzed_result.detections == []
        assert analyzed_result.hazards == []

    async def test_room_name_defaults_to_unknown_when_trigger_room_missing(self):
        scene_intel = _make_scene_intel()
        services = _make_services(scene_intel=scene_intel)

        await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(room_name=None), services
        )

        assert scene_intel.persist.await_args.kwargs["room_id"] == "unknown"

    async def test_write_observation_false_sends_empty_description_and_embedding(self):
        scene_intel = _make_scene_intel()
        services = _make_services(scene_intel=scene_intel)
        pipeline_data = {
            "scene_description": "A person in the kitchen",
            "scene_embedding": [0.1, 0.2, 0.3],
        }

        await _HANDLER.execute(
            _make_step({"write_observation": False}),
            _FakeExecution(),
            pipeline_data,
            _make_trigger(),
            services,
        )

        analyzed_result = scene_intel.persist.await_args.args[0]
        assert analyzed_result.description == ""
        assert analyzed_result.embedding == []

    async def test_write_movements_false_sends_no_transitions(self):
        scene_intel = _make_scene_intel()
        services = _make_services(scene_intel=scene_intel)
        pipeline_data = {
            "room_transitions": [
                {"person_id": "mom", "from_room_id": "bedroom", "to_room_id": "kitchen"}
            ]
        }

        await _HANDLER.execute(
            _make_step({"write_movements": False}),
            _FakeExecution(),
            pipeline_data,
            _make_trigger(),
            services,
        )

        assert scene_intel.persist.await_args.kwargs["transitions"] == ()

    async def test_default_config_keys_used_when_step_config_empty(self):
        scene_intel = _make_scene_intel()
        services = _make_services(scene_intel=scene_intel)

        await _HANDLER.execute(
            _make_step(), _FakeExecution(), {"scene_description": "quiet"}, _make_trigger(), services
        )

        analyzed_result = scene_intel.persist.await_args.args[0]
        assert analyzed_result.description == "quiet"
        assert scene_intel.persist.await_args.kwargs["source"] == "scene_intel"
