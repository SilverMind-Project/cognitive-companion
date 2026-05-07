"""Object trend analysis pipeline step.

Queries the semantic-memory-service for the current trend state of one or
more rooms and injects both structured data and a compact text summary into
``pipeline_data``. Designed to precede a ``condition`` step (for rule
branching) or an ``llm_call`` step (for LLM-enriched reasoning).

Result keys written to ``pipeline_data``
-----------------------------------------
``room_trends``
    Dict mapping room_id to trend result dicts.

``room_trends_any_warning``
    bool - whether any room has severity >= warning.

``room_trends_max_severity``
    str - highest severity across all rooms ("ok" | "info" | "warning" | "critical").

``room_trends_summary``
    Compact single-line text ready for LLM prompt injection.

Graceful degradation: if ``memory_query`` is ``None`` or the
service returns no data, the step writes empty results and continues.
"""

from __future__ import annotations

from datetime import UTC

from backend.core.logging import get_logger
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.services.memory_query.types import RoomTrendContext
from backend.steps import StepRegistry
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

logger = get_logger(__name__)

_SEVERITY_ORDER = {"ok": 0, "info": 1, "warning": 2, "critical": 3}


@StepRegistry.register
class ObjectTrendAnalysisHandler(StepHandler):
    """Pipeline step that queries room trend state for anomaly detection."""

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="object_trend_analysis",
            display_name="Room Trend Query",
            category="perception",
            icon="mdi-chart-line",
            description=(
                "Query the semantic-memory-service for room-level trend state "
                "(clutter score, persistent objects, novel objects, anomaly "
                "severity). Use Semantic Memory Query if you also need recent "
                "observations or hazard flags."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "room_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                        "description": (
                            "Room IDs to query. Empty = use the trigger room."
                        ),
                    },
                    "include_snapshots_hours": {
                        "type": "integer",
                        "minimum": 0,
                        "default": 0,
                        "description": (
                            "If > 0, fetch raw hourly snapshots for LLM context."
                        ),
                    },
                    "severity_threshold": {
                        "type": "string",
                        "enum": ["ok", "info", "warning", "critical"],
                        "default": "info",
                        "description": (
                            "Anomalies below this severity are stripped."
                        ),
                    },
                    "output_key": {
                        "type": "string",
                        "default": "room_trends",
                        "description": (
                            "Key under which the result map is written."
                        ),
                    },
                },
            },
            default_config={
                "room_ids": [],
                "include_snapshots_hours": 0,
                "severity_threshold": "info",
                "output_key": "room_trends",
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
        output_key: str = config.get("output_key", "room_trends")

        if not services.memory_query:
            return StepResult(data=_empty_output(output_key))

        room_ids: list[str] = config.get("room_ids", [])
        include_snapshots: int = config.get("include_snapshots_hours", 0)
        severity_threshold: str = config.get("severity_threshold", "info")

        # Resolve room IDs: empty list -> use trigger room
        if not room_ids and trigger.room_name:
            room_ids = [trigger.room_name]

        if not room_ids:
            return StepResult(data=_empty_output(output_key))

        # Fetch trends for each room
        trends: dict = {}
        max_severity = "ok"
        any_warning = False

        for room_id in room_ids:
            ctx = await services.memory_query.room_trends(
                room_id,
                include_snapshots_hours=include_snapshots,
                severity_threshold=severity_threshold,
            )
            if ctx is None:
                continue

            room_data = _format_trend_context(ctx)

            trends[room_id] = room_data

            # Track max severity
            severity_level = _SEVERITY_ORDER.get(ctx.overall_severity, 0)
            if severity_level > _SEVERITY_ORDER.get(max_severity, 0):
                max_severity = ctx.overall_severity
            if ctx.overall_severity in ("warning", "critical"):
                any_warning = True

        summary = _build_summary(trends, max_severity)

        output = {
            output_key: trends,
            "room_trends_any_warning": any_warning,
            "room_trends_max_severity": max_severity,
            "room_trends_summary": summary,
        }

        logger.info(
            "object_trend_analysis_done",
            rooms=len(trends),
            max_severity=max_severity,
            any_warning=any_warning,
        )

        return StepResult(data=output)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_output(output_key: str = "room_trends") -> dict:
    return {
        output_key: {},
        "room_trends_any_warning": False,
        "room_trends_max_severity": "ok",
        "room_trends_summary": "No trend data available.",
    }


def _format_trend_context(ctx: RoomTrendContext) -> dict:
    """Format a RoomTrendContext into the dict shape expected by pipeline_data."""
    room_data: dict = {
        "clutter_score": ctx.clutter_score,
        "trend_direction": ctx.trend_direction,
        "overall_severity": ctx.overall_severity,
        "persistent_objects": ctx.persistent_objects,
        "novel_objects": ctx.novel_objects,
        "anomalies": list(ctx.anomalies),
    }

    if ctx.snapshots:
        room_data["snapshots"] = [
            {
                "period_start": s.period_start.astimezone(UTC).isoformat() if s.period_start else None,
                "unique_object_count": s.unique_object_count,
                "object_counts": s.object_counts,
                "persistent_objects": s.persistent_objects,
                "novel_objects": s.novel_objects,
                "embedding_variance": s.embedding_variance,
            }
            for s in ctx.snapshots
        ]

    return room_data


def _build_summary(trends: dict, max_severity: str) -> str:
    """Build a compact single-line summary for LLM prompt injection."""
    if not trends:
        return "No trend data available."

    parts: list[str] = []
    for room_id, data in trends.items():
        severity = data.get("overall_severity", "ok")
        clutter = data.get("clutter_score", 0)
        direction = data.get("trend_direction", "stable")
        persistent = data.get("persistent_objects", [])
        novel = data.get("novel_objects", [])

        segments = [f"{room_id}: {severity.upper() if severity != 'ok' else 'OK'} clutter (z={clutter:.1f}, {direction} trend)"]
        if persistent:
            segments.append(f"Persistent: {', '.join(persistent[:5])}")
        if novel:
            segments.append(f"Novel: {', '.join(novel[:5])}")

        parts.append(" | ".join(segments))

    return "; ".join(parts)
