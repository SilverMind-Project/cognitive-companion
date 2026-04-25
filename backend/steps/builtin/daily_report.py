"""Pipeline step to generate daily activity reports for household members.

Generates or updates DailyReport records via DailyReportService.
Designed to be triggered by a cron rule at end of day.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.core.config import settings
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
class DailyReportHandler(StepHandler):
    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="daily_report",
            display_name="Generate Daily Report",
            category="action",
            icon="mdi-file-chart",
            description=(
                "Generate end-of-day activity reports for one or all household members. "
                "Aggregates sleep, meals, medication, bathroom, door events, exercise, "
                "and location data into structured DailyReport records with wellness scoring."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "person_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                        "description": (
                            "List of person IDs to generate reports for. "
                            "Empty list means all active household members."
                        ),
                    },
                    "report_date_offset_days": {
                        "type": "integer",
                        "default": 0,
                        "description": (
                            "Days offset from today for the report date. "
                            "0 = today, -1 = yesterday."
                        ),
                    },
                    "generate_summary_text": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "When true, generates an LLM prose summary of the day."
                        ),
                    },
                    "summary_model_id": {
                        "type": "string",
                        "default": "",
                        "description": (
                            "LLM model ID to use for summary generation. "
                            "Defaults to gemma4_26b."
                        ),
                    },
                    "notify_on_complete": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "When true, sends a notification when reports are ready."
                        ),
                    },
                    "output_key": {
                        "type": "string",
                        "default": "daily_reports",
                        "description": (
                            "pipeline_data key to write the report results under. "
                            "Defaults to 'daily_reports'."
                        ),
                    },
                },
            },
            default_config={
                "person_ids": [],
                "report_date_offset_days": 0,
                "generate_summary_text": False,
                "summary_model_id": "gemma4_26b",
                "notify_on_complete": False,
                "output_key": "daily_reports",
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
        output_key = (config.get("output_key", "daily_reports") or "daily_reports").strip() or "daily_reports"

        if not services.daily_report_service:
            logger.warning("daily_report_no_service")
            return StepResult(
                success=False,
                data={output_key: {"error": "daily_report_service not available"}},
            )

        try:
            # Compute report date
            offset_raw = config.get("report_date_offset_days", 0)
            try:
                offset_days = int(offset_raw) if offset_raw is not None else 0
            except (ValueError, TypeError):
                offset_days = 0

            report_date = (datetime.now(UTC) + timedelta(days=offset_days)).strftime("%Y-%m-%d")

            person_ids = config.get("person_ids", [])
            if not person_ids and services.person_tracking:
                # Fetch all active household members
                db = services.person_tracking._db_factory()
                try:
                    from backend.models.person import HouseholdMember

                    members = (
                        db.query(HouseholdMember)
                        .filter(HouseholdMember.is_active == True)  # noqa: E712
                        .all()
                    )
                    person_ids = [m.id for m in members]
                finally:
                    db.close()

            if not person_ids:
                logger.info("daily_report_no_persons")
                return StepResult(data={output_key: []})

            generate_summary = config.get("generate_summary_text", False)
            tz_name = settings.get("app.timezone", "UTC")

            results = []
            for pid in person_ids:
                try:
                    report = services.daily_report_service.generate_daily_report(
                        person_id=pid,
                        date=report_date,
                        tz_name=tz_name,
                        include_llm_summary=generate_summary,
                    )
                    results.append(
                        {
                            "person_id": pid,
                            "report_date": report.get("report_date"),
                            "report_id": report.get("report_id"),
                            "wellness_score": report.get("wellness_score"),
                        }
                    )
                except Exception:
                    logger.exception(
                        "daily_report_generation_failed",
                        person_id=pid,
                        date=report_date,
                    )
                    results.append(
                        {
                            "person_id": pid,
                            "report_date": report_date,
                            "error": "generation_failed",
                        }
                    )

            logger.info(
                "daily_report_completed",
                count=len(results),
                date=report_date,
            )

            return StepResult(data={output_key: results})

        except Exception:
            logger.exception("daily_report_step_error")
            return StepResult(
                success=False,
                data={output_key: {"error": "daily report step failed"}},
            )
