"""Person identification step -- face recognition via person-ID service."""

from __future__ import annotations

from sqlalchemy import select

from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.models.sensor import Sensor
from backend.services.person_tracking import CameraFrameContext
from backend.steps import StepRegistry
from backend.steps._pipeline_images import (
    image_refs_to_urls,
    resolve_pipeline_image_refs,
)
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
                    "write_movements_to_memory": {
                        "type": "boolean",
                        "default": False,
                        "description": "Persist room transitions to semantic memory.",
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
                    },
                    "pipeline_image_path": {
                        "type": "string",
                        "default": "",
                        "description": "Dotted path to image URLs or image refs from a previous step.",
                    },
                    "cts_frames_path": {
                        "type": "string",
                        "default": "steps.media_window_poll_1.outputs.frames",
                    },
                    "record_presence": {
                        "type": "boolean",
                        "default": True,
                        "description": "DEPRECATED (R2): PersonLocationState and PersonLocationHistory are superseded by PersonLocationService.",
                    },
                    "record_sightings": {
                        "type": "boolean",
                        "default": True,
                        "description": "When false, PersonSighting rows are not written.",
                    },
                    "presence_room_source": {
                        "type": "string",
                        "enum": ["trigger", "source_image", "custom"],
                        "default": "trigger",
                    },
                    "presence_room_name": {
                        "type": "string",
                        "default": "",
                    },
                },
            },
            default_config={
                "target_persons": [],
                "min_confidence": 0.6,
                "include_annotated_image": True,
                "include_motion": False,
                "save_guest_images": False,
                "write_movements_to_memory": False,
                "image_source": "trigger",
                "pipeline_image_path": "",
                "cts_frames_path": "steps.media_window_poll_1.outputs.frames",
                "record_presence": True,
                "record_sightings": True,
                "presence_room_source": "trigger",
                "presence_room_name": "",
            },
            output_schema={
                "type": "object",
                "properties": {
                    "person_detections": {"type": "array", "items": {"type": "object"}},
                    "room_transitions": {"type": "array", "items": {"type": "object"}},
                    "annotated_image": {"type": "string"},
                    "semantic_memory_movement_ids": {"type": "array", "items": {"type": "integer"}},
                    "skip_reason": {"type": "string"},
                },
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

        # Resolve image refs via the shared layer.
        image_refs = await resolve_pipeline_image_refs(
            config,
            pipeline_data,
            trigger,
            services,
            default_image_source="trigger",
            default_max_images=10,
        )

        if not image_refs:
            return StepResult(data={"person_detections": [], "room_transitions": []})

        media_paths = image_refs_to_urls(image_refs, minio_client=services.minio_client)
        if not media_paths:
            return StepResult(data={"person_detections": [], "room_transitions": []})

        # Determine presence room per config.
        presence_room_source = config.get("presence_room_source", "trigger")
        custom_room = config.get("presence_room_name", "")
        default_room = trigger.room_name or "Unknown"

        # Build CameraFrameContext per ref.
        frame_contexts: list[CameraFrameContext] = []
        for ref in image_refs:
            ref_sensor_id = (
                ref.source_sensor_id or ref.source_camera_id or trigger.sensor_id or "unknown"
            )

            if presence_room_source == "source_image":
                ctx_room = ref.source_room_name or default_room
            elif presence_room_source == "custom":
                ctx_room = custom_room or default_room
            else:
                ctx_room = default_room

            sensor_cfg = self._load_sensor_config(services, ref.source_sensor_id)

            frame_contexts.append(
                CameraFrameContext(
                    sensor_id=ref_sensor_id,
                    room_name=ctx_room,
                    media_path=ref.url or ref.object_name or "",
                    sensor_config=sensor_cfg,
                )
            )

        sensor_id = trigger.sensor_id or "unknown"
        room_name = trigger.room_name or "Unknown"

        camera_result = await services.person_tracking.process_camera_event(
            sensor_id=sensor_id,
            media_paths=media_paths,
            room_name=room_name,
            include_annotated_image=config.get("include_annotated_image", False),
            save_guest_images=config.get("save_guest_images", False),
            sensor_config=self._load_sensor_config(services, trigger.sensor_id),
            frame_contexts=frame_contexts,
            record_sightings=config.get("record_sightings", True),
            record_presence=config.get("record_presence", True),
        )

        detections = camera_result.detections

        # Enrich detection dicts with source metadata.
        detection_dicts = []
        for det in detections:
            d = det.dict()
            if det.frame_index is not None and det.frame_index < len(media_paths):
                d["source_media_path"] = media_paths[det.frame_index]
            if det.frame_index is not None and det.frame_index < len(image_refs):
                ref = image_refs[det.frame_index]
                d["source_sensor_id"] = ref.source_sensor_id
                d["source_camera_id"] = ref.source_camera_id
                d["source_room_name"] = ref.source_room_name
                d["source_object_name"] = ref.object_name
                meta = dict(ref.metadata) if ref.metadata else {}
                if "region_id" in meta:
                    d["crop_region_id"] = meta["region_id"]
                if "region_name" in meta:
                    d["crop_region_name"] = meta["region_name"]
            detection_dicts.append(d)

        result_data: dict = {
            "person_detections": detection_dicts,
            "room_transitions": [t.to_dict() for t in camera_result.room_transitions],
        }

        # -- Optional: write movements to semantic memory --------------------
        if config.get("write_movements_to_memory", False) and services.semantic_memory_client:
            from backend.integrations.semantic_memory_client import MovementCreate

            movement_ids: list[int] = []
            for t in camera_result.room_transitions:
                movement = MovementCreate(
                    person_id=t.person_id or "unknown",
                    from_room_id=t.from_room_id or "unknown",
                    to_room_id=t.to_room_id or "unknown",
                    direction_semantic=t.direction_semantic or "any",
                    confidence=t.confidence or 0.8,
                )
                record = await services.semantic_memory_client.create_movement(movement)
                if record:
                    movement_ids.append(record.id)
            result_data["semantic_memory_movement_ids"] = movement_ids

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
