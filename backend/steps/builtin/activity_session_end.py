"""Pipeline step to close an activity session and optionally record a PersonActivity.

Closes an open ActivitySession, computes duration, and optionally writes
a PersonActivity record with duration_minutes populated.

If no open session exists, logs a warning and continues (never blocks pipeline).
"""

from __future__ import annotations

from datetime import UTC, datetime

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
class ActivitySessionEndHandler(StepHandler):
    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="activity_session_end",
            display_name="End Activity Session",
            category="action",
            icon="mdi-stop",
            description=(
                "Close an open duration-aware activity session for a person. "
                "Computes duration from open to close. Optionally records a "
                "PersonActivity with duration_minutes populated. "
                "If no open session exists, logs a warning and continues."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "activity_type": {
                        "type": "string",
                        "default": "",
                        "description": ("Activity type to close. Supports {{template}} syntax."),
                    },
                    "person_id": {
                        "type": "string",
                        "default": "",
                        "description": (
                            "Person to close the session for. Supports {{template}} syntax."
                        ),
                    },
                    "write_activity_record": {
                        "type": "boolean",
                        "default": True,
                        "description": (
                            "When true, also records a PersonActivity with "
                            "duration_minutes populated."
                        ),
                    },
                    "output_key": {
                        "type": "string",
                        "default": "closed_session",
                        "description": (
                            "pipeline_data key to write the closed session result under. "
                            "Defaults to 'closed_session'."
                        ),
                    },
                },
                "required": ["activity_type"],
            },
            default_config={
                "activity_type": "",
                "person_id": "",
                "write_activity_record": True,
                "output_key": "closed_session",
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

        activity_type = (
            render_template(config.get("activity_type", ""), pipeline_data, trigger_vars).strip()
            or "other"
        )

        person_id = (
            render_template(config.get("person_id", ""), pipeline_data, trigger_vars).strip()
            or "unknown"
        )

        write_activity = config.get("write_activity_record", True)
        output_key = (
            config.get("output_key", "closed_session") or "closed_session"
        ).strip() or "closed_session"

        if services.activity:
            try:
                result = services.activity.close_session(
                    person_id=person_id,
                    activity_type=activity_type,
                    ended_at=datetime.now(UTC),
                    end_event_id=execution.event_log_id,
                    closed_via="explicit",
                )
            except ValueError:
                # No open session found: an expected, routine outcome (e.g. a
                # closing rule firing while nothing is open), not a failure.
                # success=True keeps this from showing as a failed step on
                # every quiet poll.
                logger.info(
                    "session_end_no_open_session",
                    person_id=person_id,
                    activity_type=activity_type,
                )
                return StepResult(
                    success=True,
                    data={
                        output_key: {
                            "no_open_session": True,
                            "person_id": person_id,
                            "activity_type": activity_type,
                        }
                    },
                )
            except Exception:
                logger.exception(
                    "session_end_error",
                    person_id=person_id,
                    activity_type=activity_type,
                )
                return StepResult(
                    success=False,
                    data={output_key: {"error": "failed to close activity session"}},
                )

            closed_session_data = {
                "session_id": result.session_id,
                "person_id": result.person_id,
                "activity_type": result.activity_type,
                "room_name": result.room_name,
                "started_at": result.opened_at.isoformat() if result.opened_at else None,
                "closed_at": result.closed_at.isoformat() if result.closed_at else None,
                "duration_minutes": result.duration_minutes,
                "status": result.status,
                "closed_via": result.closed_via,
            }

            # Optionally record a PersonActivity with duration
            if write_activity:
                try:
                    await services.activity.record(
                        person_id=result.person_id,
                        activity_type=result.activity_type,
                        room_name=result.room_name,
                        confidence=0.9,
                        source_event_id=execution.event_log_id,
                        metadata={
                            "session_id": result.session_id,
                            "duration_minutes": result.duration_minutes,
                            "closed_via": result.closed_via,
                        },
                    )
                    logger.info(
                        "session_end_activity_recorded",
                        session_id=result.session_id,
                        duration_minutes=result.duration_minutes,
                    )
                except Exception:
                    logger.exception(
                        "session_end_activity_record_failed",
                        session_id=result.session_id,
                    )

            logger.info(
                "session_end_result",
                session_id=result.session_id,
                duration_minutes=result.duration_minutes,
                closed_via=result.closed_via,
            )

            return StepResult(data={output_key: closed_session_data})

        else:
            logger.warning(
                "session_end_no_service",
                person_id=person_id,
                activity_type=activity_type,
            )
            return StepResult(
                data={output_key: {"error": "activity session service not available"}},
            )
