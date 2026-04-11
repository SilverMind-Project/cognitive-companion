"""Person identification step -- face recognition via person-ID service."""

from __future__ import annotations

from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.steps import StepRegistry
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)


@StepRegistry.register
class PersonIdentificationHandler(StepHandler):
    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="person_identification",
            display_name="Person Identification",
            category="perception",
            icon="mdi-face-recognition",
            description="Identify persons in camera frames using face recognition.",
            config_schema={
                "type": "object",
                "properties": {
                    "target_persons": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Person IDs to filter for (empty = all)",
                    },
                    "min_confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "default": 0.6,
                    },
                    "include_annotated_image": {"type": "boolean", "default": True},
                    "include_motion": {"type": "boolean", "default": False},
                    "save_guest_images": {"type": "boolean", "default": False},
                    "additional_sensor_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
            default_config={
                "target_persons": [],
                "min_confidence": 0.6,
                "include_annotated_image": True,
                "include_motion": False,
                "save_guest_images": False,
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
        if not services.person_tracking:
            return StepResult(data={"person_detections": []})

        config = step.config_json or {}
        media_paths = list(trigger.media_paths)

        # Gather additional camera images if aggregator available
        additional_sensors = config.get("additional_sensor_ids", [])
        if additional_sensors and services.event_aggregator:
            for sensor_id in additional_sensors:
                extra = await services.event_aggregator.get_recent_images(sensor_id, limit=3)
                media_paths.extend(extra)

        room_name = trigger.room_name or "Unknown"
        sensor_id = trigger.sensor_id or "unknown"

        detections = await services.person_tracking.process_camera_event(
            sensor_id=sensor_id,
            media_paths=media_paths,
            room_name=room_name,
            include_annotated_image=config.get("include_annotated_image", False),
            save_guest_images=config.get("save_guest_images", False),
        )

        # Enrich each detection dict with the source_media_path so that downstream
        # steps can correlate the bbox with the exact frame it was detected in.
        detection_dicts = []
        for det in detections:
            d = det.dict()
            if det.frame_index is not None and det.frame_index < len(media_paths):
                d["source_media_path"] = media_paths[det.frame_index]
            detection_dicts.append(d)
        result_data: dict = {"person_detections": detection_dicts}

        # Store annotated image if available
        if detections and hasattr(detections[0], "annotated_image"):
            annotated = getattr(detections[0], "annotated_image", None)
            if annotated:
                result_data["annotated_image"] = annotated

        # Check target person filter
        target_persons = config.get("target_persons", [])
        min_confidence = config.get("min_confidence", 0.0)

        if target_persons:
            detected_ids = {d.person_id for d in detections if d.confidence >= min_confidence}
            if not detected_ids.intersection(set(target_persons)):
                result_data["skip_reason"] = "target_person_not_detected"
                return StepResult(data=result_data, should_continue=False)

        return StepResult(data=result_data)
