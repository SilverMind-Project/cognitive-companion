"""Verification step -- verify household member activities via database queries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.core.logging import get_logger
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
                "by querying the PersonActivity table. No LLM calls -- pure database queries."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "conditions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "person_id": {"type": "string"},
                                "activity_type": {"type": "string"},
                                "completed": {"type": "boolean", "default": True},
                                "within_minutes": {"type": "number"},
                                "window_start": {"type": "string", "format": "date-time"},
                                "window_end": {"type": "string", "format": "date-time"},
                                "min_confidence": {"type": "number", "default": 0.5},
                            },
                            "required": ["person_id", "activity_type"],
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
            },
            default_config={
                "conditions": [],
                "match_mode": "all",
                "re_notify_if_failed": False,
                "re_notify_delay_minutes": 5,
            },
        )

    @staticmethod
    def _reanchor_to_today(dt: datetime) -> datetime:
        """Replace the date portion of *dt* with today, keeping the time and tzinfo."""
        today = datetime.now(dt.tzinfo or UTC).date()
        return dt.replace(year=today.year, month=today.month, day=today.day)

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

        if "prompt" in config and not conditions:
            logger.warning(
                "verification_deprecated_config",
                hint="verification no longer runs LLM prompts; "
                     "configure activity conditions instead",
            )
            return StepResult(
                data={"verification": {"verified": False, "matched_conditions": [], "unmatched_conditions": []}},
                should_continue=False,
            )

        if not conditions:
            logger.info("verification_no_conditions")
            return StepResult(
                data={"verification": {"verified": False, "matched_conditions": [], "unmatched_conditions": []}},
                should_continue=False,
            )

        matched: list[dict] = []
        unmatched: list[dict] = []

        for cond in conditions:
            person_id = cond.get("person_id", "")
            activity_type = cond.get("activity_type", "")
            completed = cond.get("completed", True)
            within_minutes = cond.get("within_minutes")
            min_confidence = cond.get("min_confidence", 0.5)

            window_start = None
            window_end = None
            if cond.get("window_start"):
                window_start = self._reanchor_to_today(
                    datetime.fromisoformat(cond["window_start"])
                )
            if cond.get("window_end"):
                window_end = self._reanchor_to_today(
                    datetime.fromisoformat(cond["window_end"])
                )

            activities: list[dict] = []
            if services.person_tracking:
                activities = await services.person_tracking.query_activities_in_window(
                    person_id=person_id,
                    activity_type=activity_type,
                    within_minutes=within_minutes,
                    window_start=window_start,
                    window_end=window_end,
                    min_confidence=min_confidence,
                )

            found = len(activities) > 0
            passed = found if completed else not found

            entry = {
                "person_id": person_id,
                "activity_type": activity_type,
                "completed": completed,
                "found": found,
                "passed": passed,
                "activity_count": len(activities),
            }
            if passed:
                matched.append(entry)
            else:
                unmatched.append(entry)

        if match_mode == "any":
            verified = len(matched) > 0
        else:
            verified = len(unmatched) == 0

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
