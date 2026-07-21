"""Admin metrics endpoint: exposes CTS decode/drop error counts for the UI."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from prometheus_client import generate_latest
from pydantic import BaseModel

from backend.core.auth import AuthContext, require_permission
from backend.core.logging import get_logger
from backend.routers.dependencies import get_daily_living_health
from backend.schemas.daily_living_health import (
    ActivityLedgerHealthOut,
    ActivityTypeHealthOut,
    DailyLivingHealthOut,
    ObservationsByDayOut,
    SemanticMemoryHealthOut,
)
from backend.services.cts import metrics as cts_metrics
from backend.services.daily_living_health import DailyLivingHealthService

logger = get_logger(__name__)

router = APIRouter(tags=["metrics"])


class CtsMetricsSummary(BaseModel):
    signals_received: float
    signals_persisted: float
    signals_decode_errors: float
    signals_dropped: float
    events_received: float
    events_persisted: float
    events_decode_errors: float
    events_dropped: float
    revisions_received: float
    revisions_persisted: float
    revisions_decode_errors: float
    revisions_dropped: float


def _sum_counter(counter) -> float:
    """Sum across all label values of a Prometheus collector.

    Rule 15: raises on failure so the endpoint returns an explicit 503 rather
    than a ``0.0`` that looks like real data to a clinician or operator.
    Callers must not swallow this exception.
    """
    total = 0.0
    for s in counter.collect():
        for m in s.samples:
            total += m.value
    return total


@router.get("/metrics")
def metrics_endpoint(request: Request):
    """Prometheus /metrics endpoint (no auth in dev)."""
    return _prometheus_response()


@router.get("/api/v1/admin/cts-metrics", response_model=CtsMetricsSummary)
def cts_metrics_endpoint(
    request: Request,
    _auth: AuthContext = Depends(require_permission("admin:read")),
) -> CtsMetricsSummary:
    """Return CTS subscriber metrics for the admin dashboard.

    Returns 503 when the Prometheus counters cannot be read (e.g. CTS not
    initialised).  Rule 15: a ``0`` that looks like real data is worse than an
    explicit unavailable state — these numbers are read by operators and
    clinicians.
    """
    try:
        return CtsMetricsSummary(
            signals_received=_sum_counter(cts_metrics.cts_signals_received),
            signals_persisted=_sum_counter(cts_metrics.cts_signals_persisted),
            signals_decode_errors=_sum_counter(cts_metrics.cts_signals_decode_errors),
            signals_dropped=_sum_counter(cts_metrics.cts_signals_dropped),
            events_received=_sum_counter(cts_metrics.cts_events_received),
            events_persisted=_sum_counter(cts_metrics.cts_events_persisted),
            events_decode_errors=_sum_counter(cts_metrics.cts_events_decode_errors),
            events_dropped=_sum_counter(cts_metrics.cts_events_dropped),
            revisions_received=_sum_counter(cts_metrics.cts_revisions_received),
            revisions_persisted=_sum_counter(cts_metrics.cts_revisions_persisted),
            revisions_decode_errors=_sum_counter(cts_metrics.cts_revisions_decode_errors),
            revisions_dropped=_sum_counter(cts_metrics.cts_revisions_dropped),
        )
    except Exception as exc:
        logger.exception("cts_metrics_read_error")
        raise HTTPException(
            status_code=503,
            detail="CTS metrics unavailable: Prometheus counters could not be read",
        ) from exc


@router.get("/api/v1/admin/daily-living-health", response_model=DailyLivingHealthOut)
async def daily_living_health_endpoint(
    request: Request,
    svc: DailyLivingHealthService = Depends(get_daily_living_health),
    _auth: AuthContext = Depends(require_permission("admin:read")),
) -> DailyLivingHealthOut:
    """Return semantic-memory write recency and activity-ledger population.

    503 only if the service itself is unwired (see ``get_daily_living_health``);
    an unreachable upstream semantic-memory service is a degraded 200
    (``semantic_memory.reachable=False``, ``stale=True``), not an error, per
    the platform's optional-integration degradation contract.
    """
    snapshot = await svc.snapshot()
    return DailyLivingHealthOut(
        semantic_memory=SemanticMemoryHealthOut(
            reachable=snapshot.semantic_memory.reachable,
            last_observation_at=snapshot.semantic_memory.last_observation_at,
            last_movement_at=snapshot.semantic_memory.last_movement_at,
            observations_by_day=[
                ObservationsByDayOut(day=b.day.date().isoformat(), source=b.source, count=b.count)
                for b in snapshot.semantic_memory.observations_by_day
            ],
            total_observations=snapshot.semantic_memory.total_observations,
            total_movements=snapshot.semantic_memory.total_movements,
            stale=snapshot.semantic_memory.stale,
        ),
        activity_ledger=ActivityLedgerHealthOut(
            by_type=[
                ActivityTypeHealthOut(
                    activity_type=row.activity_type,
                    count=row.count,
                    last_opened_at=row.last_opened_at,
                )
                for row in snapshot.activity_ledger.by_type
            ],
            stale=snapshot.activity_ledger.stale,
        ),
    )


def _prometheus_response():
    from fastapi.responses import Response

    return Response(content=generate_latest(), media_type="text/plain; charset=utf-8")
