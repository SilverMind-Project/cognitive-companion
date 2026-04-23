"""CTS dementia signals API endpoints.

All handlers require ``cts.signals.view``.

Routes:
    GET    /api/v1/cts/signals                  — list recent signals
    POST   /api/v1/cts/signals/{signal_id}/ack  — acknowledge a signal
    GET    /api/v1/cts/signals/unacknowledged   — unacknowledged signals
    GET    /api/v1/cts/signals/summary          — 24h summary for dashboard
    GET    /api/v1/cts/signals/trend/{person_id} — per-day trend

When ``cts.enabled=false`` every handler returns 404 with code
``cts.disabled`` so no CTS code runs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.core.auth import AuthContext, require_permission
from backend.core.config import settings
from backend.core.database import get_session
from backend.services.cts.signal_store import SignalStore

router = APIRouter(prefix="/cts/signals", tags=["cts-signals"])


def _get_signal_store() -> SignalStore:
    """Dependency: provide the SignalStore instance."""
    return SignalStore(db_factory=get_session)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cts_enabled() -> None:
    if not settings.get("cts.enabled", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "cts.disabled", "message": "CTS is not enabled on this instance."},
        )


# ---------------------------------------------------------------------------
# Signal list
# ---------------------------------------------------------------------------


@router.get("")
async def list_signals(
    person_id: str | None = Query(None, description="Filter by person ID"),
    signal_type: str | None = Query(None, description="Filter by signal type"),
    severity: str | None = Query(None, description="Filter by severity"),
    window_hours: int = Query(24, ge=1, le=720, description="Lookback window in hours"),
    limit: int = Query(200, ge=1, le=1000, description="Max results"),
    _auth: AuthContext = Depends(require_permission("cts.signals.view")),
    store: SignalStore = Depends(_get_signal_store),
) -> dict:
    """List recent dementia signals with optional filters."""
    _cts_enabled()
    signals = await store.list_recent(
        person_id=person_id,
        signal_type=signal_type,
        severity=severity,
        window_hours=window_hours,
        limit=limit,
    )
    return {"signals": signals, "count": len(signals)}


# ---------------------------------------------------------------------------
# Acknowledge
# ---------------------------------------------------------------------------


@router.post("/{signal_id}/ack")
async def acknowledge_signal(
    signal_id: int,
    _auth: AuthContext = Depends(require_permission("cts.signals.view")),
    store: SignalStore = Depends(_get_signal_store),
) -> dict:
    """Mark a dementia signal as acknowledged by a caregiver."""
    _cts_enabled()
    ok = await store.acknowledge(signal_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "signal.not_found", "message": f"Signal {signal_id} not found."},
        )
    return {"acknowledged": True, "signal_id": signal_id}


# ---------------------------------------------------------------------------
# Unacknowledged
# ---------------------------------------------------------------------------


@router.get("/unacknowledged")
async def list_unacknowledged(
    person_id: str | None = Query(None, description="Filter by person ID"),
    severity: str | None = Query(None, description="Filter by severity"),
    window_hours: int = Query(24, ge=1, le=720, description="Lookback window in hours"),
    limit: int = Query(50, ge=1, le=500, description="Max results"),
    _auth: AuthContext = Depends(require_permission("cts.signals.view")),
    store: SignalStore = Depends(_get_signal_store),
) -> dict:
    """Return unacknowledged signals (for alerting / dashboard)."""
    _cts_enabled()
    signals = await store.get_unacknowledged(
        person_id=person_id,
        severity=severity,
        window_hours=window_hours,
        limit=limit,
    )
    return {"signals": signals, "count": len(signals)}


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


@router.get("/summary")
async def get_summary(
    person_id: str | None = Query(None, description="Filter by person ID"),
    _auth: AuthContext = Depends(require_permission("cts.signals.view")),
    store: SignalStore = Depends(_get_signal_store),
) -> dict:
    """Return a 24-hour signal summary for the dashboard."""
    _cts_enabled()
    summary = await store.get_24h_summary(person_id=person_id)
    return summary


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------


@router.get("/trend/{person_id}")
async def get_trend(
    person_id: str,
    days: int = Query(7, ge=1, le=90, description="Number of days for trend"),
    _auth: AuthContext = Depends(require_permission("cts.signals.view")),
    store: SignalStore = Depends(_get_signal_store),
) -> dict:
    """Return per-day signal counts for trend charts."""
    _cts_enabled()
    trend = await store.get_daily_trend(person_id=person_id, days=days)
    return {"person_id": person_id, "days": days, "trend": trend}
