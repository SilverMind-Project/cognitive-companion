"""Read service over the LLM admission controller's in-memory telemetry (DL-M09).

Operational telemetry only (the ring buffer resets on restart), mirroring
``MediaObservabilityService``'s aggregator-state precedent: one service
method backs the admin endpoint, no MCP mirror (this is not caregiver-facing
domain data).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from backend.integrations.llm.admission import AdmissionRecord, Lane, LLMAdmissionController
from backend.schemas.inference_telemetry import (
    CallerLaneOutcomeOut,
    HourlyCallBucketOut,
    InferenceTelemetryOut,
    QueueDepthOut,
)

_LANES: tuple[Lane, ...] = ("vision", "text")


def _percentile(sorted_values: list[int], pct: float) -> float | None:
    """Nearest-rank percentile over pre-sorted values. ``None`` when empty."""
    if not sorted_values:
        return None
    idx = min(len(sorted_values) - 1, round(pct * (len(sorted_values) - 1)))
    return float(sorted_values[idx])


class InferenceTelemetryService:
    """Summarizes :class:`LLMAdmissionController` records for the admin dashboard."""

    def __init__(
        self,
        controller: LLMAdmissionController,
        *,
        window_minutes: int = 60,
        time_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._controller = controller
        self._window_minutes = window_minutes
        self._time_fn = time_fn

    def get_telemetry(self) -> InferenceTelemetryOut:
        """Return admission telemetry for the last ``window_minutes``."""
        all_records = self._controller.snapshot()
        window_start = self._time_fn() - timedelta(minutes=self._window_minutes)
        records = [r for r in all_records if r.at >= window_start]

        return InferenceTelemetryOut(
            window_minutes=self._window_minutes,
            totals_by_caller_lane=self._totals_by_caller_lane(records),
            queue_depth=[
                QueueDepthOut(lane=lane, depth=self._controller.queue_depth(lane))
                for lane in _LANES
            ],
            queue_wait_p50_ms=_percentile(
                sorted(r.queue_wait_ms for r in records), 0.50
            ),
            queue_wait_p95_ms=_percentile(
                sorted(r.queue_wait_ms for r in records), 0.95
            ),
            timeouts_total=sum(1 for r in records if r.outcome == "timeout"),
            calls_per_hour=self._calls_per_hour(records),
            ring_buffer_size=len(all_records),
            ring_buffer_capacity=self._controller.ring_buffer_capacity,
        )

    @staticmethod
    def _totals_by_caller_lane(records: list[AdmissionRecord]) -> list[CallerLaneOutcomeOut]:
        totals: dict[tuple[str, str], dict[str, int]] = {}
        for r in records:
            bucket = totals.setdefault((r.caller, r.lane), {"ok": 0, "timeout": 0, "error": 0})
            bucket[r.outcome] += 1
        return [
            CallerLaneOutcomeOut(
                caller=caller, lane=lane, ok=b["ok"], timeout=b["timeout"], error=b["error"]
            )
            for (caller, lane), b in sorted(totals.items())
        ]

    @staticmethod
    def _calls_per_hour(records: list[AdmissionRecord]) -> list[HourlyCallBucketOut]:
        hourly: dict[tuple[str, str], int] = {}
        for r in records:
            hour_start = r.at.replace(minute=0, second=0, microsecond=0)
            key = (hour_start.isoformat(), r.lane)
            hourly[key] = hourly.get(key, 0) + 1
        return [
            HourlyCallBucketOut(hour=hour, lane=lane, calls=count)
            for (hour, lane), count in sorted(hourly.items())
        ]
