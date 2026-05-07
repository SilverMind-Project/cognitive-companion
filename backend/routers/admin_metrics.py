"""Admin metrics endpoint: exposes CTS decode/drop error counts for the UI."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from prometheus_client import generate_latest
from pydantic import BaseModel

from backend.core.auth import AuthContext, require_permission
from backend.services.cts import metrics as cts_metrics

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


def _counter_value(counter, **labels) -> float:
    """Safely read a counter value from prometheus_client."""
    try:
        sample = counter.labels(**labels)
        val = 0.0
        for s in sample.collect():
            for m in s.samples:
                val += m.value
        return val
    except Exception:
        return 0.0


def _sum_counter(counter) -> float:
    """Sum across all label values of a collector."""
    try:
        total = 0.0
        for s in counter.collect():
            for m in s.samples:
                total += m.value
        return total
    except Exception:
        return 0.0


@router.get("/metrics")
def metrics_endpoint(request: Request):
    """Prometheus /metrics endpoint (no auth in dev)."""
    return _prometheus_response()


@router.get("/api/v1/admin/cts-metrics", response_model=CtsMetricsSummary)
def cts_metrics_endpoint(
    request: Request,
    _auth: AuthContext = Depends(require_permission("admin:read")),
) -> CtsMetricsSummary:
    """Return CTS subscriber metrics for the admin dashboard."""
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


def _prometheus_response():
    from fastapi.responses import Response
    return Response(content=generate_latest(), media_type="text/plain; charset=utf-8")
