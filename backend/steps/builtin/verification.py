"""Verification step -- verify household member activities via database queries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from backend.core.config import settings
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
class VerificationHandler(StepHandler):
    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="verification",
            display_name="Verify Activity",
            category="state",
            icon="mdi-check-decagram",
            description=(
                "Verify whether household members completed specific activities "
                "by querying the PersonActivity table. No LLM calls -- pure database queries. "
                "Supports optional person and room filters, each with {{template}} syntax."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "conditions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "person_id": {
                                    "type": "string",
                                    "description": (
                                        "Person to check. Supports {{template}} syntax. "
                                        "Leave empty to match any person."
                                    ),
                                },
                                "activity_type": {"type": "string"},
                                "completed": {"type": "boolean", "default": True},
                                "within_minutes": {"type": "number"},
                                "window_start": {"type": "string", "format": "date-time"},
                                "window_end": {"type": "string", "format": "date-time"},
                                "min_confidence": {"type": "number", "default": 0.5},
                                "room_name": {
                                    "type": "string",
                                    "description": (
                                        "Optional room filter. Supports {{template}} syntax. "
                                        "Leave empty to match any room."
                                    ),
                                },
                            },
                            "required": ["activity_type"],
                        },
                    },
                    "match_mode": {
                        "type": "string",
                        "enum": ["all", "any"],
                        "default": "all",
                    },
                    "re_notify_if_failed": {"type": "boolean", "default": False},
                    "re_notify_delay_minutes": {"type": "number", "default": 5},
                },
                "additionalProperties": False,
            },
            default_config={
                "conditions": [],
                "match_mode": "all",
                "re_notify_if_failed": False,
                "re_notify_delay_minutes": 5,
            },
        )

    @staticmethod
    def _reanchor_to_local_today(dt: datetime, local_tz: ZoneInfo) -> datetime:
        """Extract the local wall-clock time from dt, anchor it to today's local date, and return UTC."""
        dt_local = dt.astimezone(local_tz)
        today_local = datetime.now(local_tz).date()
        new_local = datetime.combine(today_local, dt_local.time(), tzinfo=local_tz)
        return new_local.astimezone(UTC)

    async def execute(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
        services: ServiceContainer,
    ) -> StepResult:
        config = step.config_json or {}
        conditions = config.get("conditions", [])
        match_mode = config.get("match_mode", "all")
        re_notify_if_failed = config.get("re_notify_if_failed", False)
        re_notify_delay = config.get("re_notify_delay_minutes", 5)

        trigger_vars = {
            "room_name": trigger.room_name or "",
            "sensor_id": trigger.sensor_id or "",
        }

        if not conditions:
            logger.info("verification_no_conditions")
            return StepResult(
                data={
                    "verification": {
                        "verified": False,
                        "matched_conditions": [],
                        "unmatched_conditions": [],
                    }
                },
                should_continue=False,
            )

        matched: list[dict] = []
        unmatched: list[dict] = []

        for cond in conditions:
            # Resolve person_id: supports template expressions; empty = any person.
            person_id_raw = cond.get("person_id", "")
            person_id = (
                render_template(person_id_raw, pipeline_data, trigger_vars).strip()
                if person_id_raw
                else ""
            )

            # Resolve room_name: supports template expressions; empty = any room.
            room_name_raw = cond.get("room_name", "")
            room_name = (
                render_template(room_name_raw, pipeline_data, trigger_vars).strip()
                if room_name_raw
                else None
            )

            activity_type = cond.get("activity_type", "")
            completed = cond.get("completed", True)
            within_minutes = cond.get("within_minutes")
            min_confidence = cond.get("min_confidence", 0.5)

            window_start = None
            window_end = None
            local_tz = ZoneInfo(settings.as_str("app.timezone"))
            if cond.get("window_start"):
                window_start = self._reanchor_to_local_today(
                    datetime.fromisoformat(cond["window_start"]), local_tz
                )
            if cond.get("window_end"):
                window_end = self._reanchor_to_local_today(
                    datetime.fromisoformat(cond["window_end"]), local_tz
                )

            activities: list[dict] = []
            if services.activity:
                activities = await services.activity.query_in_window(
                    person_id=person_id or None,
                    activity_type=activity_type,
                    within_minutes=within_minutes,
                    window_start=window_start,
                    window_end=window_end,
                    min_confidence=min_confidence,
                    room_name=room_name,
                )

            found = len(activities) > 0
            passed = found if completed else not found

            entry = {
                "person_id": person_id or None,
                "activity_type": activity_type,
                "room_name": room_name,
                "completed": completed,
                "found": found,
                "passed": passed,
                "activity_count": len(activities),
            }
            if passed:
                matched.append(entry)
            else:
                unmatched.append(entry)

        verified = len(matched) > 0 if match_mode == "any" else len(unmatched) == 0

        result_data: dict = {
            "verification": {
                "verified": verified,
                "match_mode": match_mode,
                "matched_conditions": matched,
                "unmatched_conditions": unmatched,
            }
        }

        if not verified and re_notify_if_failed:
            resume_at = datetime.now(UTC) + timedelta(minutes=re_notify_delay)
            return StepResult(data=result_data, wait_until=resume_at)

        return StepResult(data=result_data, should_continue=verified)
