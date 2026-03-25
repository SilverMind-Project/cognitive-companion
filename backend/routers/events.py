"""
Event log viewer endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.exceptions import NotFoundError
from backend.models.event import EventLog
from backend.schemas.event import EventLogOut

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventLogOut])
def list_events(
    rule_name: str | None = Query(None),
    sensor_id: str | None = Query(None),
    status: str | None = Query(None),
    trigger_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("events:read")),
):
    """Paginated list of events with optional filters, ordered by timestamp descending."""
    q = db.query(EventLog)
    if rule_name:
        q = q.filter(EventLog.rule_name == rule_name)
    if sensor_id:
        q = q.filter(EventLog.sensor_id == sensor_id)
    if status:
        q = q.filter(EventLog.status == status)
    if trigger_type:
        q = q.filter(EventLog.trigger_type == trigger_type)
    return q.order_by(EventLog.timestamp.desc()).offset(offset).limit(limit).all()


@router.get("/{event_id}", response_model=EventLogOut)
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("events:read")),
):
    """Get a single event by ID, including full pipeline_data_json."""
    event = db.get(EventLog, event_id)
    if not event:
        raise NotFoundError("Event", event_id)
    return event
