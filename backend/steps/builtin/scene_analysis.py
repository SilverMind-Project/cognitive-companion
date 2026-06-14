"""Scene analysis pipeline step.

Calls the scene-analysis-service to run fast object detection (YOLO),
structured scene description (Florence-2), and optionally CLIP embeddings
on the images collected by the trigger or selected cameras.

Result keys written to ``pipeline_data``
-----------------------------------------
``scene_images``
    Per-image list of dicts, one entry per analysed image:
    ``{image_path, scene_description, scene_detections, scene_hazards, scene_embedding}``.
    Use ``jq()`` in condition steps to filter individual images.

``scene_detections``
    Aggregated list of object-detection dicts across all images
    (label, confidence, bbox, class_id).

``scene_description``
    All non-empty Florence-2 descriptions joined by ``\\n---\\n``.

``scene_embedding``
    CLIP embedding vector as a list of floats — first non-empty result
    across all images.

``scene_hazards``
    Aggregated list of hazard-alert dicts across all images
    (name, severity, description, detection).

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

import httpx

from backend.core.logging import get_logger
from backend.integrations.scene_analysis_client import SceneAnalyzeResult
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.steps import StepRegistry
from backend.steps._image_utils import resolve_image_sources
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
                    "image_source": {
                        "type": "string",
                        "enum": [
                            "trigger",
                            "additional",
                            "both",
                            "pipeline",
                            "media_window",
                            "cts_window",
                        ],
                        "default": "trigger",
                        "description": "Which images to analyse.",
                    },
                    "pipeline_image_path": {
                        "type": "string",
                        "default": "",
                        "description": "Dotted pipeline_data path to a prior step image output.",
                    },
                    "pipeline_image_url_field": {
                        "type": "string",
                        "default": "url",
                    },
                    "pipeline_image_object_name_field": {
                        "type": "string",
                        "default": "object_name",
                    },
                    "cts_frames_path": {
                        "type": "string",
                        "default": "steps.cts_window_poll_1.outputs.frames",
                    },
                    "max_images": {
                        "type": "integer",
                        "default": 1,
                        "minimum": 1,
                        "description": "Hard cap on total images to analyse.",
                    },
                    "trigger_images_count": {
                        "type": "integer",
                        "default": 0,
                        "minimum": 0,
                        "description": "Max frames from the trigger camera. 0 = all available.",
                    },
                    "additional_sensor_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                        "description": "Sensor IDs to pull additional frames from.",
                    },
                    "additional_room_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                        "description": "Pull recent frames from all cameras in these rooms.",
                    },
                    "images_per_sensor": {
                        "type": "integer",
                        "default": 1,
                        "minimum": 1,
                        "description": "Default frames per additional camera.",
                    },
                    "sensor_frame_limits": {
                        "type": "object",
                        "default": {},
                        "description": "Per-sensor frame count overrides.",
                    },
                    "image_time_filter": {
                        "type": "object",
                        "default": {},
                        "description": "Optional time window for additional image queries.",
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
                "image_source": "trigger",
                "max_images": 1,
                "trigger_images_count": 0,
                "additional_sensor_ids": [],
                "additional_room_names": [],
                "images_per_sensor": 1,
                "sensor_frame_limits": {},
                "image_time_filter": {},
                "write_to_memory": False,
                "pipeline_image_path": "",
                "pipeline_image_url_field": "url",
                "pipeline_image_object_name_field": "object_name",
                "cts_frames_path": "steps.cts_window_poll_1.outputs.frames",
            },
            output_schema={
                "type": "object",
                "properties": {
                    "scene_images": {"type": "array", "items": {"type": "object"}},
                    "scene_detections": {"type": "array", "items": {"type": "object"}},
                    "scene_description": {"type": "string"},
                    "scene_embedding": {"type": "array", "items": {"type": "number"}},
                    "scene_hazards": {"type": "array", "items": {"type": "object"}},
                    "scene_detector_available": {"type": "boolean"},
                    "scene_describer_available": {"type": "boolean"},
                    "scene_embedder_available": {"type": "boolean"},
                    "scene_memory_observation_id": {"type": ["integer", "null"]},
                },
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

        if not services.scene_analysis_client or not services.scene_analysis_client.configured:
            logger.debug("scene_analysis_disabled")
            return StepResult(data=_empty)

        config = step.config_json or {}
        media_paths = await resolve_image_sources(
            config,
            trigger,
            services.event_aggregator,
            pipeline_data=pipeline_data,
            minio_client=services.minio_client,
            default_max_images=int(config.get("max_images", 1)),
        )

        if not media_paths:
            logger.debug("scene_analysis_no_images", trigger=trigger.sensor_id)
            return StepResult(data=_empty)

        image_results: list[dict] = []
        all_detections = []
        all_hazards = []
        all_descriptions: list[str] = []
        embedding: list = []
        detector_available = False
        describer_available = False
        embedder_available = False

        for image_path in media_paths:
            image_bytes = await _fetch_image(image_path)
            if not image_bytes:
                logger.warning("scene_analysis_image_unreadable", path=image_path)
                continue

            result: SceneAnalyzeResult = await services.scene_analysis_client.analyze(
                image_bytes,
                run_detect=config.get("run_detect", True),
                run_describe=config.get("run_describe", True),
                run_embed=config.get("run_embed", False),
                run_hazards=config.get("run_hazards", True),
            )

            per_image_detections = [
                {
                    "label": d.label,
                    "confidence": d.confidence,
                    "bbox": d.bbox,
                    "class_id": d.class_id,
                }
                for d in result.detections
            ]
            per_image_hazards = [
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
            ]
            image_results.append(
                {
                    "image_path": image_path,
                    "scene_description": result.description or "",
                    "scene_detections": per_image_detections,
                    "scene_hazards": per_image_hazards,
                    "scene_embedding": result.embedding or [],
                }
            )

            all_detections.extend(result.detections)
            all_hazards.extend(result.hazards)
            if result.description:
                all_descriptions.append(result.description)
            if not embedding and result.embedding:
                embedding = result.embedding
            detector_available = detector_available or result.detector_available
            describer_available = describer_available or result.describer_available
            embedder_available = embedder_available or result.embedder_available

        description = "\n---\n".join(all_descriptions)

        logger.info(
            "scene_analysis_done",
            sensor_id=trigger.sensor_id,
            images=len(media_paths),
            detections=len(all_detections),
            hazards=len(all_hazards),
            described=bool(description),
        )

        # -- Optional: auto-write to semantic memory --------------------------
        scene_memory_observation_id: int | None = None
        if config.get("write_to_memory", False) and services.scene_intel:
            room_name = trigger.room_name or "unknown"
            intel_record = await services.scene_intel.persist(
                SceneAnalyzeResult(
                    detections=list(all_detections),
                    description=description or "",
                    hazards=list(all_hazards),
                    embedding=embedding if isinstance(embedding, list) else [],
                ),
                room_id=room_name,
                source="scene_intel",
            )
            if intel_record.observation_id:
                scene_memory_observation_id = intel_record.observation_id
                logger.info(
                    "scene_analysis_memory_write",
                    observation_id=intel_record.observation_id,
                )
            else:
                logger.warning("scene_analysis_memory_write_failed")

        return StepResult(
            data={
                "scene_images": image_results,
                "scene_detections": [
                    {
                        "label": d.label,
                        "confidence": d.confidence,
                        "bbox": d.bbox,
                        "class_id": d.class_id,
                    }
                    for d in all_detections
                ],
                "scene_description": description,
                "scene_embedding": embedding,
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
                    for h in all_hazards
                ],
                "scene_detector_available": detector_available,
                "scene_describer_available": describer_available,
                "scene_embedder_available": embedder_available,
                "scene_memory_observation_id": scene_memory_observation_id,
            }
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_result() -> dict:
    return {
        "scene_images": [],
        "scene_detections": [],
        "scene_description": "",
        "scene_embedding": [],
        "scene_hazards": [],
        "scene_detector_available": False,
        "scene_describer_available": False,
        "scene_embedder_available": False,
        "scene_memory_observation_id": None,
    }


async def _fetch_image(url: str) -> bytes | None:
    """Fetch image bytes from an HTTP(S) URL (e.g. presigned MinIO).

    Returns ``None`` on any network or HTTP error.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
    except Exception:  # noqa: BLE001
        return None
