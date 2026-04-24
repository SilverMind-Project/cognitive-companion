"""Semantic memory query pipeline step.

Fetches recent scene observations, object presence, and hazard data from the
semantic-memory-service and injects structured results plus a compact
LLM-ready summary into ``pipeline_data``.

Result keys written to ``pipeline_data``
-----------------------------------------
``<output_key>``
    Dict with keys:
    - ``recent_objects``: list of object presence records
    - ``recent_hazards``: list of matching hazard observations
    - ``observations``: list of observation search hits
    - ``summary``: compact text summary for LLM prompt injection
    - ``observations_count``: integer count of observations

The step always succeeds and always continues the pipeline.  If the
semantic-memory-service is unreachable or disabled, the output dict
contains empty lists and a "No memory context available." summary.
"""

from __future__ import annotations

from backend.core.logging import get_logger
from backend.integrations.semantic_memory_client import (
    ObservationSearchRequest,
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


def _empty_output(output_key: str) -> dict:
    return {output_key: {"recent_objects": [], "recent_hazards": [], "observations": [], "summary": "No memory context available.", "observations_count": 0}}


@StepRegistry.register
class SemanticMemoryQueryHandler(StepHandler):
    """Pipeline step that queries semantic memory for scene context."""

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="semantic_memory_query",
            display_name="Semantic Memory Query",
            category="perception",
            icon="mdi-database-search-outline",
            description=(
                "Query the semantic memory service for recent scene observations "
                "and inject the results into pipeline_data as both structured "
                "data and a compact LLM-ready summary."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "room_id": {
                        "type": "string",
                        "description": "Explicit room ID to query. Overrides use_trigger_room.",
                    },
                    "use_trigger_room": {
                        "type": "boolean",
                        "default": True,
                        "description": "Use the trigger's room as the query room.",
                    },
                    "since_minutes": {
                        "type": "integer",
                        "minimum": 1,
                        "default": 60,
                        "description": "Lookback window in minutes.",
                    },
                    "objects_any": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                        "description": "Only include observations containing any of these object labels.",
                    },
                    "hazard_flags_any": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                        "description": "Only include observations containing any of these hazard flags.",
                    },
                    "query_text": {
                        "type": "string",
                        "default": "",
                        "description": "Text query for semantic search.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "default": 5,
                        "description": "Maximum number of observations to return.",
                    },
                    "output_key": {
                        "type": "string",
                        "default": "memory_context",
                        "description": "Pipeline data key for the output dict.",
                    },
                },
            },
            default_config={
                "room_id": "",
                "use_trigger_room": True,
                "since_minutes": 60,
                "objects_any": [],
                "hazard_flags_any": [],
                "query_text": "",
                "limit": 5,
                "output_key": "memory_context",
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
        output_key: str = step.config_json.get("output_key", "memory_context") if step.config_json else "memory_context"

        if not services.semantic_memory_client:
            return StepResult(data=_empty_output(output_key))

        config = step.config_json or {}

        # Resolve room_id
        room_id: str | None = config.get("room_id") or None
        if not room_id and config.get("use_trigger_room", True) and trigger.room_name:
            room_id = trigger.room_name

        since_minutes: int = config.get("since_minutes", 60)
        objects_any: list[str] = config.get("objects_any", [])
        hazard_flags_any: list[str] = config.get("hazard_flags_any", [])
        query_text: str = config.get("query_text", "")
        limit: int = config.get("limit", 5)

        # -- Search observations -----------------------------------------------
        req = ObservationSearchRequest(
            room_id=room_id,
            since_minutes=since_minutes,
            objects_any=objects_any,
            hazard_flags_any=hazard_flags_any,
            query_text=query_text,
            limit=limit,
        )
        observations = await services.semantic_memory_client.search_observations(req)

        # -- Recent objects ----------------------------------------------------
        recent_objects: list[dict] = []
        if room_id:
            obj_records = await services.semantic_memory_client.get_recent_objects(
                room_id, since_minutes=since_minutes
            )
            recent_objects = [
                {
                    "label": r.label,
                    "observation_count": r.observation_count,
                    "last_seen_at": r.last_seen_at.isoformat(),
                }
                for r in obj_records
            ]

        # -- Format hazards from observations ----------------------------------
        recent_hazards: list[dict] = []
        if hazard_flags_any:
            recent_hazards = [
                {
                    "id": o.id,
                    "room_id": o.room_id,
                    "observed_at": o.observed_at.isoformat(),
                    "hazard_flags": o.hazard_flags,
                    "description": o.description,
                }
                for o in observations
                if o.hazard_flags
            ]

        # -- Build summary -----------------------------------------------------
        if observations or recent_objects:
            parts: list[str] = []
            if room_id:
                parts.append(f"In the past {since_minutes} min in {room_id}:")
            if recent_objects:
                obj_strs = [f"{r['label']} ({r['observation_count']}x)" for r in recent_objects]
                parts.append(", ".join(obj_strs))
            if recent_hazards:
                hazard_names = set()
                for h in recent_hazards:
                    hazard_names.update(h["hazard_flags"])
                parts.append(f"{len(hazard_names)} hazard(s): {', '.join(sorted(hazard_names))}.")
            summary = " ".join(parts)
        else:
            summary = "No memory context available."

        output_data = {
            "recent_objects": recent_objects,
            "recent_hazards": recent_hazards,
            "observations": [
                {
                    "id": o.id,
                    "room_id": o.room_id,
                    "observed_at": o.observed_at.isoformat(),
                    "description": o.description,
                    "object_list": o.object_list,
                    "hazard_flags": o.hazard_flags,
                    "text_similarity": o.text_similarity,
                    "image_similarity": o.image_similarity,
                }
                for o in observations
            ],
            "summary": summary,
            "observations_count": len(observations),
        }

        return StepResult(data={output_key: output_data})
