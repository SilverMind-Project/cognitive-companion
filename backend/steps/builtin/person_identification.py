"""Person identification step -- face recognition via person-ID service."""

from __future__ import annotations

from sqlalchemy import select

from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.models.sensor import Sensor
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_sensor_config(services: ServiceContainer, sensor_id: str | None) -> dict | None:
        """Return ``Sensor.config_json`` for *sensor_id*, or ``None`` when absent.

        Uses a short-lived DB session that is always closed in the finally block
        so the connection is returned to the pool regardless of outcome.
        """
        if not sensor_id:
            return None
        db = services.db_factory()
        try:
            row = db.execute(select(Sensor).where(Sensor.id == sensor_id)).scalar_one_or_none()
            return row.config_json if row is not None else None
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    async def execute(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
        services: ServiceContainer,
    ) -> StepResult:
        if not services.person_tracking:
            return StepResult(data={"person_detections": [], "room_transitions": []})

        config = step.config_json or {}
        media_paths = list(trigger.media_paths)

        # Gather additional camera images if aggregator available.
        additional_sensors = config.get("additional_sensor_ids", [])
        if additional_sensors and services.event_aggregator:
            for sid in additional_sensors:
                extra = await services.event_aggregator.get_recent_images(sid, limit=3)
                media_paths.extend(extra)

        room_name = trigger.room_name or "Unknown"
        sensor_id = trigger.sensor_id or "unknown"

        # Fetch the sensor's camera-topology config so the tracking service
        # can map raw movement directions to semantic room transitions.
        sensor_config = self._load_sensor_config(services, trigger.sensor_id)

        camera_result = await services.person_tracking.process_camera_event(
            sensor_id=sensor_id,
            media_paths=media_paths,
            room_name=room_name,
            include_annotated_image=config.get("include_annotated_image", False),
            save_guest_images=config.get("save_guest_images", False),
            sensor_config=sensor_config,
        )

        detections = camera_result.detections

        # Enrich each detection dict with the source_media_path so that downstream
        # steps can correlate the bbox with the exact frame it was detected in.
        detection_dicts = []
        for det in detections:
            d = det.dict()
            if det.frame_index is not None and det.frame_index < len(media_paths):
                d["source_media_path"] = media_paths[det.frame_index]
            detection_dicts.append(d)

        result_data: dict = {
            "person_detections": detection_dicts,
            "room_transitions": [t.to_dict() for t in camera_result.room_transitions],
        }

        # Store annotated image if available.
        if detections and hasattr(detections[0], "annotated_image"):
            annotated = getattr(detections[0], "annotated_image", None)
            if annotated:
                result_data["annotated_image"] = annotated

        # Apply target-person filter.
        target_persons = config.get("target_persons", [])
        min_confidence = config.get("min_confidence", 0.0)

        if target_persons:
            detected_ids = {d.person_id for d in detections if d.confidence >= min_confidence}
            if not detected_ids.intersection(set(target_persons)):
                result_data["skip_reason"] = "target_person_not_detected"
                return StepResult(data=result_data, should_continue=False)

        return StepResult(data=result_data)
