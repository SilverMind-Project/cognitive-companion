"""Scene analysis pipeline step.

Calls the scene-analysis-service to run fast object detection (YOLO11x),
structured scene description (Florence-2), and optionally CLIP embeddings
on the images collected by the trigger.

Result keys written to ``pipeline_data``
-----------------------------------------
``scene_detections``
    List of object-detection dicts (label, confidence, bbox, class_id).

``scene_description``
    Structured text description from Florence-2 (empty string when
    Florence is not loaded or the describer is disabled).

``scene_embedding``
    CLIP embedding vector as a list of floats (empty list when not loaded).

``scene_hazards``
    List of hazard-alert dicts (name, severity, description, detection).

``scene_detector_available``
    bool - whether YOLO was loaded in the service.

``scene_describer_available``
    bool - whether Florence was loaded in the service.

``scene_embedder_available``
    bool - whether CLIP was loaded in the service.

The step always succeeds and always continues the pipeline.  If the
scene-analysis-service is unreachable or disabled, all result lists are
empty.
"""

from __future__ import annotations

from backend.core.logging import get_logger
from backend.integrations.scene_analysis_client import SceneAnalyzeResult
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


@StepRegistry.register
class SceneAnalysisHandler(StepHandler):
    """Pipeline step that runs YOLO + Florence-2 + CLIP on trigger images."""

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="scene_analysis",
            display_name="Scene Analysis",
            category="perception",
            icon="mdi-image-search",
            description=(
                "Run fast object detection, structured scene description, and "
                "CLIP embeddings via the scene-analysis-service."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "run_detect": {
                        "type": "boolean",
                        "default": True,
                        "description": "Run YOLO object detection.",
                    },
                    "run_describe": {
                        "type": "boolean",
                        "default": True,
                        "description": "Run Florence-2 structured description.",
                    },
                    "run_embed": {
                        "type": "boolean",
                        "default": False,
                        "description": "Run CLIP embedding (can be slow).",
                    },
                    "run_hazards": {
                        "type": "boolean",
                        "default": True,
                        "description": "Evaluate hazard rules on detections.",
                    },
                    "max_images": {
                        "type": "integer",
                        "default": 1,
                        "minimum": 1,
                        "description": "Maximum number of trigger images to analyse.",
                    },
                    "write_to_memory": {
                        "type": "boolean",
                        "default": False,
                        "description": "Automatically persist the analysis result to semantic memory.",
                    },
                },
            },
            default_config={
                "run_detect": True,
                "run_describe": True,
                "run_embed": False,
                "run_hazards": True,
                "max_images": 1,
                "write_to_memory": False,
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
        _empty = _empty_result()

        if not services.scene_analysis_client:
            return StepResult(data=_empty)

        config = step.config_json or {}
        max_images: int = config.get("max_images", 1)
        media_paths = list(trigger.media_paths)[:max_images]

        if not media_paths:
            logger.debug("scene_analysis_no_images", trigger=trigger.sensor_id)
            return StepResult(data=_empty)

        # Use the first (most recent) image for analysis.
        image_path = media_paths[0]
        image_bytes = _read_image(image_path)
        if not image_bytes:
            logger.warning("scene_analysis_image_unreadable", path=image_path)
            return StepResult(data=_empty)

        result: SceneAnalyzeResult = await services.scene_analysis_client.analyze(
            image_bytes,
            run_detect=config.get("run_detect", True),
            run_describe=config.get("run_describe", True),
            run_embed=config.get("run_embed", False),
            run_hazards=config.get("run_hazards", True),
        )

        logger.info(
            "scene_analysis_done",
            sensor_id=trigger.sensor_id,
            detections=len(result.detections),
            hazards=len(result.hazards),
            described=bool(result.description),
        )

        # -- Optional: auto-write to semantic memory --------------------------
        scene_memory_observation_id: int | None = None
        if config.get("write_to_memory", False) and services.semantic_memory_client:
            from backend.integrations.semantic_memory_client import ObservationCreate

            room_name = trigger.room_name or "unknown"
            obs = ObservationCreate(
                room_id=room_name,
                description=result.description,
                object_list=[d.label for d in result.detections],
                hazard_flags=[h.name for h in result.hazards],
                embedding=result.embedding if isinstance(result.embedding, list) else [],
                source="scene_intel",
            )
            record = await services.semantic_memory_client.create_observation(obs)
            if record:
                scene_memory_observation_id = record.id
                logger.info(
                    "scene_analysis_memory_write",
                    observation_id=record.id,
                )
            else:
                logger.warning("scene_analysis_memory_write_failed")

        return StepResult(
            data={
                "scene_detections": [
                    {
                        "label": d.label,
                        "confidence": d.confidence,
                        "bbox": d.bbox,
                        "class_id": d.class_id,
                    }
                    for d in result.detections
                ],
                "scene_description": result.description,
                "scene_embedding": result.embedding,
                "scene_hazards": [
                    {
                        "name": h.name,
                        "severity": h.severity,
                        "description": h.description,
                        "detection": {
                            "label": h.detection.label,
                            "confidence": h.detection.confidence,
                            "bbox": h.detection.bbox,
                            "class_id": h.detection.class_id,
                        },
                    }
                    for h in result.hazards
                ],
                "scene_detector_available": result.detector_available,
                "scene_describer_available": result.describer_available,
                "scene_embedder_available": result.embedder_available,
                "scene_memory_observation_id": scene_memory_observation_id,
            }
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_result() -> dict:
    return {
        "scene_detections": [],
        "scene_description": "",
        "scene_embedding": [],
        "scene_hazards": [],
        "scene_detector_available": False,
        "scene_describer_available": False,
        "scene_embedder_available": False,
    }


def _read_image(path: str) -> bytes | None:
    """Read image bytes from a local filesystem path.

    Returns ``None`` when the file is absent or unreadable.
    """
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None
