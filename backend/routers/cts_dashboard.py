"""CTS dashboard proxy endpoints.

Proxies the three dashboard endpoints and the keyframe query endpoint
from the tracking-orchestrator to the frontend.

Routes:
    GET /api/v1/cts/dashboard/signals
    GET /api/v1/cts/dashboard/trajectory
    GET /api/v1/cts/dashboard/dwell_summary
    GET /api/v1/cts/keyframes          (already in cts_keyframes.py: not duplicated)

When ``cts.enabled=false`` every handler returns 404 with code
``cts.disabled``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_session
from backend.core.logging import get_logger
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.routers.cts_deps import cts_enabled

logger = get_logger(__name__)

router = APIRouter(prefix="/cts/dashboard", tags=["cts-dashboard"])


def _get_orchestrator_client() -> OrchestratorClient:
    return OrchestratorClient()


# ---------------------------------------------------------------------------
# GET /cts/dashboard/signals
# ---------------------------------------------------------------------------


@router.get("/signals")
async def get_signals(
    person_id: str | None = Query(None, description="Filter by person ID"),
    window_hours: int = Query(24, ge=1, le=720, description="Lookback window in hours"),
    signal_kind: str | None = Query(None, description="Filter by signal kind"),
    limit: int = Query(200, ge=1, le=1000),
    _auth: AuthContext = Depends(require_permission("cts.signals.view")),
    client: OrchestratorClient = Depends(_get_orchestrator_client),
) -> dict:
    """Return recent dementia signals from the orchestrator."""
    cts_enabled()
    return await client.get_dashboard_signals(
        person_id=person_id,
        window_hours=window_hours,
        signal_kind=signal_kind,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# GET /cts/dashboard/trajectory
# ---------------------------------------------------------------------------


@router.get("/trajectory")
async def get_trajectory(
    person_id: str = Query(..., description="Person ID (required)"),
    start: str | None = Query(None, description="ISO-8601 start time"),
    end: str | None = Query(None, description="ISO-8601 end time"),
    limit: int = Query(500, ge=1, le=5000),
    _auth: AuthContext = Depends(require_permission("cts.signals.view")),
    client: OrchestratorClient = Depends(_get_orchestrator_client),
) -> dict:
    """Return trajectory points for floor-plan overlay."""
    cts_enabled()
    return await client.get_dashboard_trajectory(
        person_id=person_id,
        start=start,
        end=end,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# GET /cts/dashboard/dwell_summary
# ---------------------------------------------------------------------------


@router.get("/dwell_summary")
async def get_dwell_summary(
    person_id: str = Query(..., description="Person ID (required)"),
    date: str | None = Query(None, description="ISO-8601 date (YYYY-MM-DD); defaults to today"),
    _auth: AuthContext = Depends(require_permission("cts.signals.view")),
    client: OrchestratorClient = Depends(_get_orchestrator_client),
) -> dict:
    """Return room dwell aggregation (time-in-room) for one day."""
    cts_enabled()
    return await client.get_dashboard_dwell_summary(
        person_id=person_id,
        date=date,
    )


# ---------------------------------------------------------------------------
# GET /cts/dashboard/overview
# ---------------------------------------------------------------------------


class SuppressionIn(BaseModel):
    person_id: str = Field(..., min_length=1, max_length=64)
    signal_kind: str | None = None
    duration_hours: float = Field(default=1.0, ge=0.25, le=8760)  # max 1 year
    reason: str = ""


@router.get("/overview")
async def get_overview(
    _auth: AuthContext = Depends(require_permission("cts.signals.view")),
    client: OrchestratorClient = Depends(_get_orchestrator_client),
) -> dict:
    """Return aggregated data for the dashboard."""
    cts_enabled()
    db = get_session()
    try:
        # Active suppressions
        suppressions = db.execute(
            text(
                "SELECT id, person_id, signal_kind, suppressed_until, reason "
                "FROM cts_alert_suppressions "
                "WHERE suppressed_until > now() "
                "ORDER BY suppressed_until"
            )
        ).fetchall()
        active_suppressions = [
            {
                "id": s.id,
                "person_id": s.person_id,
                "signal_kind": s.signal_kind,
                "suppressed_until": s.suppressed_until.isoformat(),
                "reason": s.reason,
            }
            for s in suppressions
        ]
    finally:
        db.close()

    return {
        "suppressions": active_suppressions,
    }


# ---------------------------------------------------------------------------
# Alert suppression CRUD
# ---------------------------------------------------------------------------


@router.post("/suppressions")
async def create_suppression(
    body: SuppressionIn,
    _auth: AuthContext = Depends(require_permission("cts.signals.view")),
) -> dict:
    cts_enabled()
    db = get_session()
    try:
        suppressed_until = datetime.now(UTC) + timedelta(hours=body.duration_hours)
        result = db.execute(
            text(
                "INSERT INTO cts_alert_suppressions "
                "(person_id, signal_kind, suppressed_until, created_by, reason) "
                "VALUES (:person_id, :signal_kind, :until, :actor, :reason) "
                "RETURNING id"
            ),
            {
                "person_id": body.person_id,
                "signal_kind": body.signal_kind,
                "until": suppressed_until,
                "actor": _auth.name,
                "reason": body.reason,
            },
        )
        row = result.fetchone()
        db.commit()
        return {"id": row.id, "suppressed_until": suppressed_until.isoformat()}
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create suppression",
        ) from exc
    finally:
        db.close()


@router.delete("/suppressions/{suppression_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_suppression(
    suppression_id: int,
    _auth: AuthContext = Depends(require_permission("cts.signals.view")),
) -> None:
    cts_enabled()
    db = get_session()
    try:
        db.execute(
            text("DELETE FROM cts_alert_suppressions WHERE id = :id"),
            {"id": suppression_id},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.get("/unacknowledged-count")
async def unacknowledged_count(
    _auth: AuthContext = Depends(require_permission("cts.signals.view")),
    client: OrchestratorClient = Depends(_get_orchestrator_client),
) -> dict:
    """Return count of unacknowledged signals for the alert ticker."""
    cts_enabled()
    try:
        data = await client.get_dashboard_signals(
            window_hours=24,
            limit=100,
        )
        signals = data.get("signals", [])
        unacked = [s for s in signals if not s.get("acknowledged_at")]
        return {"count": len(unacked), "signals": unacked[:5]}
    except Exception:
        return {"count": 0, "signals": []}
