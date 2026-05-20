"""CTS dementia signals API endpoints.

All read handlers require ``cts.signals.view``.
Delete handlers require ``cts.signals.delete``.

Routes:
    GET    /api/v1/cts/signals                 : list recent signals (paginated)
    POST   /api/v1/cts/signals/{signal_id}/ack : acknowledge a signal
    DELETE /api/v1/cts/signals/{signal_id}     : hard-delete a single signal
    DELETE /api/v1/cts/signals/batch           : hard-delete multiple signals
    GET    /api/v1/cts/signals/unacknowledged  : unacknowledged signals
    GET    /api/v1/cts/signals/summary         : 24h summary for dashboard
    GET    /api/v1/cts/signals/trend/{person_id}: per-day trend

When ``cts.enabled=false`` every handler returns 404 with code
``cts.disabled`` so no CTS code runs.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db, get_session
from backend.models.person import HouseholdMember
from backend.routers.cts_deps import cts_enabled
from backend.services.cts.signal_config import is_signal_enabled
from backend.services.cts.signal_store import SignalStore

router = APIRouter(prefix="/cts/signals", tags=["cts-signals"])


def _get_signal_store() -> SignalStore:
    """Dependency: provide the SignalStore instance."""
    return SignalStore(db_factory=get_session)


def _filter_by_person_config(
    signals: list[dict],
    db: Session,
) -> list[dict]:
    """Remove signals that are disabled by the person's cts_alert_config.

    Loads all HouseholdMember configs in one query and applies the check
    in Python so the signal store remains config-agnostic.
    """
    members = {m.id: m for m in db.query(HouseholdMember).all()}
    result = []
    for s in signals:
        member = members.get(s.get("person_id", ""))
        cfg = member.cts_alert_config if member is not None else None
        if is_signal_enabled(cfg, s.get("signal_type", ""), s.get("severity", "info")):
            result.append(s)
    return result


# ---------------------------------------------------------------------------
# Signal list
# ---------------------------------------------------------------------------


@router.get("")
async def list_signals(
    person_id: str | None = Query(None, description="Filter by person ID"),
    signal_type: str | None = Query(None, description="Filter by signal type"),
    severity: str | None = Query(None, description="Filter by severity"),
    window_hours: int = Query(24, ge=1, le=720, description="Lookback window in hours"),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    _auth: AuthContext = Depends(require_permission("cts.signals.view")),
    store: SignalStore = Depends(_get_signal_store),
    db: Session = Depends(get_db),
) -> dict:
    """List recent dementia signals, filtered by each person's alert config."""
    cts_enabled()
    signals, total = await store.list_recent(
        person_id=person_id,
        signal_type=signal_type,
        severity=severity,
        window_hours=window_hours,
        limit=limit,
        offset=offset,
    )
    signals = _filter_by_person_config(signals, db)
    return {"signals": signals, "count": len(signals), "total": total, "offset": offset, "limit": limit}


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
    cts_enabled()
    ok = await store.acknowledge(signal_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "signal.not_found", "message": f"Signal {signal_id} not found."},
        )
    return {"acknowledged": True, "signal_id": signal_id}


# ---------------------------------------------------------------------------
# Delete (single + batch)
# ---------------------------------------------------------------------------


@router.delete("/batch", status_code=status.HTTP_200_OK)
async def batch_delete_signals(
    signal_ids: list[int] = Body(..., embed=True, description="Row IDs to delete"),
    _auth: AuthContext = Depends(require_permission("cts.signals.delete")),
    store: SignalStore = Depends(_get_signal_store),
) -> dict:
    """Hard-delete multiple dementia signals.  Returns deleted count."""
    cts_enabled()
    if len(signal_ids) > 500:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "signal.batch_too_large", "message": "Batch limit is 500 IDs."},
        )
    deleted = await store.batch_delete(signal_ids)
    return {"deleted": deleted}


@router.delete("/{signal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_signal(
    signal_id: int,
    _auth: AuthContext = Depends(require_permission("cts.signals.delete")),
    store: SignalStore = Depends(_get_signal_store),
) -> None:
    """Hard-delete a single dementia signal by row ID."""
    cts_enabled()
    ok = await store.delete(signal_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "signal.not_found", "message": f"Signal {signal_id} not found."},
        )


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
    db: Session = Depends(get_db),
) -> dict:
    """Return unacknowledged signals, filtered by each person's alert config."""
    cts_enabled()
    signals = await store.get_unacknowledged(
        person_id=person_id,
        severity=severity,
        window_hours=window_hours,
        limit=limit,
    )
    signals = _filter_by_person_config(signals, db)
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
    cts_enabled()
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
    cts_enabled()
    trend = await store.get_daily_trend(person_id=person_id, days=days)
    return {"person_id": person_id, "days": days, "trend": trend}
