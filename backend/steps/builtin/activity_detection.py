"""Activity detection step -- record a single activity to the PersonActivity table.

Temporal context note
---------------------
The VLM window fed to upstream ``llm_call`` steps spans
only the frames held by the EventAggregator (typically 10 s -- 1 min).  For
activities that unfold over longer durations (e.g. having a meal), configure the
upstream ``llm_call`` step with::

    image_time_filter:
      since_minutes: 30     # pull the last 30 minutes of frames from MinIO

This extends the temporal context to the vision model without any changes here.
The activity_detection step then records the *conclusion* of that analysis.

Scene description capture
--------------------------
Set ``capture_scene_description: true`` to automatically save the upstream vision
model's textual output into ``metadata_json.scene_description``.  This creates
an auditable record of *why* the activity was detected alongside the activity
record itself.  The source key defaults to ``"vision_response"`` but can be
overridden via ``scene_description_key``.

Additional arbitrary metadata can be injected via ``metadata_extra`` -- a JSON
string that supports ``{{template}}`` syntax resolved against ``pipeline_data``
and trigger context.
"""

from __future__ import annotations

import json

from backend.core.logging import get_logger
from backend.core.template import render_template
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
class ActivityDetectionHandler(StepHandler):
    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="activity_detection",
            display_name="Record Activity",
            category="state",
            icon="mdi-database-plus",
            description=(
                "Record a single activity to the PersonActivity table. "
                "All fields support {{template}} syntax resolved against pipeline_data "
                "and trigger context. Use multiple steps to record multiple activities. "
                "Enable capture_scene_description to store the upstream vision analysis "
                "output inside the activity record for full auditability."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "activity_type": {
                        "type": "string",
                        "default": "",
                        "description": (
                            "Activity type to record. Supports {{template}} syntax "
                            "(e.g. {{logic_response.activity_type}})."
                        ),
                    },
                    "person_id": {
                        "type": "string",
                        "default": "",
                        "description": (
                            "Person to attribute this activity to. Supports {{template}} syntax "
                            "(e.g. {{person_detections.0.person_id}}). "
                            "Leave empty to record as unknown person."
                        ),
                    },
                    "confidence": {
                        "type": ["number", "string"],
                        "default": 0.8,
                        "description": (
                            "Confidence score (0-1). Accepts a fixed number or "
                            "{{template}} syntax (e.g. {{logic_response.confidence}})."
                        ),
                    },
                    "room_name": {
                        "type": "string",
                        "default": "",
                        "description": (
                            "Room where the activity occurred. Supports {{template}} syntax "
                            "(e.g. {{room_name}}). Defaults to the trigger room when empty."
                        ),
                    },
                    "capture_scene_description": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "When true, capture the upstream vision model output into "
                            "metadata_json.scene_description.  Use this to create an "
                            "auditable record of what the VLM observed when the activity "
                            "was detected."
                        ),
                    },
                    "scene_description_key": {
                        "type": "string",
                        "default": "vision_response",
                        "description": (
                            "pipeline_data key to read as the scene description when "
                            "capture_scene_description is true. Defaults to 'vision_response'."
                        ),
                    },
                    "metadata_extra": {
                        "type": "string",
                        "default": "",
                        "description": (
                            "Optional JSON string of extra fields to merge into metadata_json. "
                            "Supports {{template}} syntax for dynamic values "
                            '(e.g. \'{"reasoning": "{{logic_response.reasoning}}"}\').'
                        ),
                    },
                    "trigger_cooloff": {
                        "type": "boolean",
                        "default": True,
                        "description": "If true, flags this rule for a rate-limit cool-off period after completion.",
                    },
                },
                "required": ["activity_type"],
            },
            default_config={
                "activity_type": "",
                "person_id": "",
                "confidence": 0.8,
                "room_name": "",
                "capture_scene_description": False,
                "scene_description_key": "vision_response",
                "metadata_extra": "",
                "trigger_cooloff": True,
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
        config = step.config_json or {}

        trigger_vars = {
            "room_name": trigger.room_name or "",
            "sensor_id": trigger.sensor_id or "",
        }

        activity_type = render_template(
            config.get("activity_type", ""), pipeline_data, trigger_vars
        ).strip()

        if not activity_type:
            logger.warning("activity_detection_missing_type", step_id=step.id)
            return StepResult(data={"detected_activities": []})

        person_id = (
            render_template(config.get("person_id", ""), pipeline_data, trigger_vars).strip()
            or "unknown"
        )

        room_name_tpl = config.get("room_name", "")
        room_name = (
            render_template(room_name_tpl, pipeline_data, trigger_vars).strip() or trigger.room_name
        )

        confidence_raw = config.get("confidence", 0.8)
        if isinstance(confidence_raw, str):
            resolved = render_template(confidence_raw, pipeline_data, trigger_vars).strip()
            try:
                confidence = max(0.0, min(1.0, float(resolved)))
            except (ValueError, TypeError):
                logger.warning("activity_detection_bad_confidence", raw=confidence_raw)
                confidence = 0.8
        else:
            confidence = max(0.0, min(1.0, float(confidence_raw or 0.8)))

        # --- Build metadata_json ------------------------------------------------
        metadata: dict = {}

        if config.get("capture_scene_description", False):
            scene_key = config.get("scene_description_key", "vision_response") or "vision_response"
            from backend.services.pipeline_data_manager import resolve_pipeline_value
            scene_value = resolve_pipeline_value(pipeline_data, scene_key)
            if scene_value is not None:
                metadata["scene_description"] = scene_value
                metadata["scene_description_source"] = scene_key

        metadata_extra_tpl = config.get("metadata_extra", "").strip()
        if metadata_extra_tpl:
            rendered = render_template(metadata_extra_tpl, pipeline_data, trigger_vars)
            try:
                extra = json.loads(rendered)
                if isinstance(extra, dict):
                    metadata.update(extra)
                else:
                    logger.warning(
                        "activity_detection_metadata_extra_not_dict", rendered=rendered[:120]
                    )
            except (json.JSONDecodeError, ValueError):
                logger.warning(
                    "activity_detection_metadata_extra_invalid_json", rendered=rendered[:120]
                )

        # -----------------------------------------------------------------------

        if services.person_tracking:
            try:
                await services.person_tracking.record_activity(
                    person_id=person_id,
                    activity_type=activity_type,
                    room_name=room_name,
                    confidence=confidence,
                    source_event_id=execution.event_log_id,
                    metadata=metadata or None,
                )
            except Exception:
                logger.warning(
                    "activity_record_failed",
                    person_id=person_id,
                    activity_type=activity_type,
                )

        result_data: dict = {
            "detected_activities": [
                {
                    "person_id": person_id,
                    "activity_type": activity_type,
                    "room_name": room_name,
                    "confidence": confidence,
                    **({"metadata": metadata} if metadata else {}),
                }
            ]
        }

        if config.get("trigger_cooloff", True):
            result_data["_cooloff_triggered"] = True

        return StepResult(data=result_data)
