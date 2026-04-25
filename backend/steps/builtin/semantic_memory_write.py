"""Semantic memory write pipeline step.

Persists scene observations and person movements to the semantic-memory-service
for later retrieval by filters, the memory query step, and MCP tools.

Result keys written to ``pipeline_data``
-----------------------------------------
``semantic_memory_observation_id``
    The ID of the created observation record, or ``None``.

``semantic_memory_movement_ids``
    List of movement record IDs created (may be empty).

``semantic_memory_write_available``
    ``True`` if the semantic memory client is configured and a write
    was attempted; ``False`` if the client is unavailable.
"""

from __future__ import annotations

from backend.core.logging import get_logger
from backend.integrations.semantic_memory_client import (
    MovementCreate,
    ObservationCreate,
)
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.steps import StepRegistry
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

logger = get_logger(__name__)


def _empty_output() -> dict:
    return {
        "semantic_memory_observation_id": None,
        "semantic_memory_movement_ids": [],
        "semantic_memory_write_available": False,
    }


@StepRegistry.register
class SemanticMemoryWriteHandler(StepHandler):
    """Pipeline step that persists scene/movement data to semantic memory."""

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="semantic_memory_write",
            display_name="Semantic Memory Write",
            category="state",
            icon="mdi-database-plus-outline",
            description=(
                "Persist scene observations and person movements to the semantic "
                "memory service for later retrieval by filters, the memory query "
                "step, and MCP tools."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": ["scene_intel", "llm_vision", "manual"],
                        "default": "scene_intel",
                        "description": "Source tag for the observation record.",
                    },
                    "write_observation": {
                        "type": "boolean",
                        "default": True,
                        "description": "Persist a scene observation.",
                    },
                    "write_movements": {
                        "type": "boolean",
                        "default": True,
                        "description": "Persist person movement transitions.",
                    },
                    "description_key": {
                        "type": "string",
                        "default": "scene_description",
                        "description": "Pipeline data key containing the scene description.",
                    },
                    "detections_key": {
                        "type": "string",
                        "default": "scene_detections",
                        "description": "Pipeline data key containing detection objects.",
                    },
                    "embedding_key": {
                        "type": "string",
                        "default": "scene_embedding",
                        "description": "Pipeline data key containing the CLIP embedding.",
                    },
                    "hazards_key": {
                        "type": "string",
                        "default": "scene_hazards",
                        "description": "Pipeline data key containing hazard alerts.",
                    },
                    "movements_key": {
                        "type": "string",
                        "default": "room_transitions",
                        "description": "Pipeline data key containing room transition dicts.",
                    },
                },
            },
            default_config={
                "source": "scene_intel",
                "write_observation": True,
                "write_movements": True,
                "description_key": "scene_description",
                "detections_key": "scene_detections",
                "embedding_key": "scene_embedding",
                "hazards_key": "scene_hazards",
                "movements_key": "room_transitions",
            },
        )

    async def execute(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
        services: ServiceContainer,
    ) -> StepResult:
        if not services.semantic_memory_client:
            return StepResult(data=_empty_output())

        config = step.config_json or {}
        source: str = config.get("source", "scene_intel")
        write_obs: bool = config.get("write_observation", True)
        write_mov: bool = config.get("write_movements", True)
        desc_key: str = config.get("description_key", "scene_description")
        det_key: str = config.get("detections_key", "scene_detections")
        emb_key: str = config.get("embedding_key", "scene_embedding")
        haz_key: str = config.get("hazards_key", "scene_hazards")
        mov_key: str = config.get("movements_key", "room_transitions")

        # Resolve room from trigger
        room_name = trigger.room_name or "unknown"
        room_id = room_name  # simplified: use room_name as room_id

        observation_id: int | None = None
        movement_ids: list[int] = []

        # -- Observation write ------------------------------------------------
        if write_obs:
            from backend.services.pipeline_data_manager import resolve_pipeline_value
            description = resolve_pipeline_value(pipeline_data, desc_key, default="")
            detections = resolve_pipeline_value(pipeline_data, det_key, default=[])
            embedding = resolve_pipeline_value(pipeline_data, emb_key, default=[])
            hazards = resolve_pipeline_value(pipeline_data, haz_key, default=[])

            object_list: list[str] = []
            if isinstance(detections, list):
                object_list = [
                    d.get("label", "") if isinstance(d, dict) else ""
                    for d in detections
                ]
                object_list = [o for o in object_list if o]

            hazard_flags: list[str] = []
            if isinstance(hazards, list):
                hazard_flags = [
                    h.get("name", "") if isinstance(h, dict) else ""
                    for h in hazards
                ]
                hazard_flags = [h for h in hazard_flags if h]

            if description or object_list or hazard_flags:
                obs = ObservationCreate(
                    room_id=room_id,
                    description=description,
                    object_list=object_list,
                    hazard_flags=hazard_flags,
                    embedding=embedding if isinstance(embedding, list) else [],
                    source=source,
                )
                record = await services.semantic_memory_client.create_observation(obs)
                if record:
                    observation_id = record.id
                    logger.info(
                        "semantic_memory_observation_created",
                        observation_id=observation_id,
                        room_id=room_id,
                    )
                else:
                    logger.warning(
                        "semantic_memory_observation_write_failed",
                        room_id=room_id,
                    )

        # -- Movement writes --------------------------------------------------
        if write_mov:
            from backend.services.pipeline_data_manager import resolve_pipeline_value
            transitions = resolve_pipeline_value(pipeline_data, mov_key, default=[])
            if isinstance(transitions, list):
                for transition in transitions:
                    if not isinstance(transition, dict):
                        continue
                    movement = MovementCreate(
                        person_id=transition.get("person_id", "unknown"),
                        from_room_id=transition.get("from_room_id", "unknown"),
                        to_room_id=transition.get("to_room_id", "unknown"),
                        direction_semantic=transition.get(
                            "direction_semantic", "any"
                        ),
                        confidence=transition.get("confidence", 0.8),
                        observation_id=observation_id,
                    )
                    record = await services.semantic_memory_client.create_movement(
                        movement
                    )
                    if record:
                        movement_ids.append(record.id)
                    else:
                        logger.warning(
                            "semantic_memory_movement_write_failed",
                            person_id=movement.person_id,
                        )

        logger.info(
            "semantic_memory_write_done",
            observation_id=observation_id,
            movements=len(movement_ids),
        )

        return StepResult(
            data={
                "semantic_memory_observation_id": observation_id,
                "semantic_memory_movement_ids": movement_ids,
                "semantic_memory_write_available": True,
            }
        )
