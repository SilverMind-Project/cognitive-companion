"""
Alert management endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.exceptions import NotFoundError
from backend.models.alert import EmergencyAlert
from backend.schemas.alert import AlertAction, AlertOut

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
def list_alerts(
    resolved: bool | None = Query(None),
    room_name: str | None = Query(None),
    alert_type: str | None = Query(None),
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("alerts:read")),
):
    """List alerts with optional filters, ordered by timestamp descending."""
    q = db.query(EmergencyAlert)
    if resolved is not None:
        q = q.filter(EmergencyAlert.resolved == resolved)
    if room_name:
        q = q.filter(EmergencyAlert.room_name == room_name)
    if alert_type:
        q = q.filter(EmergencyAlert.alert_type == alert_type)
    return q.order_by(EmergencyAlert.timestamp.desc()).all()


@router.get("/{alert_id}", response_model=AlertOut)
def get_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("alerts:read")),
):
    """Get a single alert by ID."""
    alert = db.get(EmergencyAlert, alert_id)
    if not alert:
        raise NotFoundError("Alert", alert_id)
    return alert


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("alerts:write")),
) -> None:
    """Hard-delete a rule alert by ID."""
    alert = db.get(EmergencyAlert, alert_id)
    if not alert:
        raise NotFoundError("Alert", alert_id)
    db.delete(alert)
    db.commit()


@router.post("/{alert_id}/action")
def alert_action(
    alert_id: int,
    payload: AlertAction,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("alerts:write")),
):
    """Perform an action on an alert (dismiss or assist)."""
    alert = db.get(EmergencyAlert, alert_id)
    if not alert:
        raise NotFoundError("Alert", alert_id)

    if payload.action == "dismiss":
        alert.resolved = True
    elif payload.action == "assist":
        alert.assistance_needed = True

    db.commit()
    db.refresh(alert)
    return AlertOut.model_validate(alert)
