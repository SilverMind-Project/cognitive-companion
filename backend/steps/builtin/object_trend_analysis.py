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

Graceful degradation: if ``semantic_memory_client`` is ``None`` or the
service returns no data, the step writes empty results and continues.
"""

from __future__ import annotations

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

_SEVERITY_ORDER = {"ok": 0, "info": 1, "warning": 2, "critical": 3}


@StepRegistry.register
class ObjectTrendAnalysisHandler(StepHandler):
    """Pipeline step that queries room trend state for anomaly detection."""

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="object_trend_analysis",
            display_name="Object Trend Analysis",
            category="perception",
            icon="mdi-chart-line",
            description=(
                "Query the semantic-memory-service for room-level object "
                "trend state: clutter scores, persistent/novel objects, "
                "and anomaly severity."
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
        if not services.semantic_memory_client:
            config = step.config_json or {}
            output_key = config.get("output_key", "room_trends")
            return StepResult(data=_empty_output(output_key))

        config = step.config_json or {}
        room_ids: list[str] = config.get("room_ids", [])
        include_snapshots: int = config.get("include_snapshots_hours", 0)
        severity_threshold: str = config.get("severity_threshold", "info")
        output_key: str = config.get("output_key", "room_trends")

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
            try:
                result = await services.semantic_memory_client.get_room_trends(room_id)
            except Exception as exc:
                logger.warning(
                    "trend_fetch_failed",
                    room_id=room_id,
                    error=str(exc),
                )
                continue

            if not result:
                continue

            # Apply severity threshold filtering
            severity_level = _SEVERITY_ORDER.get(result.overall_severity, 0)
            threshold_level = _SEVERITY_ORDER.get(severity_threshold, 1)

            filtered_anomalies = [
                a for a in result.anomalies
                if _SEVERITY_ORDER.get(a.get("severity", "ok"), 0) >= threshold_level
            ]

            room_data = {
                "clutter_score": result.clutter_score,
                "trend_direction": result.trend_direction,
                "overall_severity": result.overall_severity,
                "persistent_objects": result.persistent_objects,
                "novel_objects": result.novel_objects,
                "anomalies": filtered_anomalies,
            }

            # Include snapshots if requested
            if include_snapshots > 0:
                try:
                    snapshots = await services.semantic_memory_client.get_snapshots(
                        room_id, since_hours=include_snapshots
                    )
                    room_data["snapshots"] = [
                        {
                            "period_start": s.period_start.isoformat() if s.period_start else None,
                            "unique_object_count": s.unique_object_count,
                            "object_counts": s.object_counts,
                            "persistent_objects": s.persistent_objects,
                            "novel_objects": s.novel_objects,
                            "embedding_variance": s.embedding_variance,
                        }
                        for s in snapshots
                    ]
                except Exception as exc:
                    logger.warning(
                        "trend_snapshots_failed",
                        room_id=room_id,
                        error=str(exc),
                    )

            trends[room_id] = room_data

            # Track max severity
            if severity_level > _SEVERITY_ORDER.get(max_severity, 0):
                max_severity = result.overall_severity
            if result.overall_severity in ("warning", "critical"):
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
