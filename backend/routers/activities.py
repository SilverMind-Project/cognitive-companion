"""Person activity endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.core.auth import require_permission
from backend.core.database import get_db
from backend.models.person import PersonActivity
from backend.schemas.activity import PersonActivityOut

router = APIRouter(prefix="/activities", tags=["activities"])


@router.get("", response_model=list[PersonActivityOut])
def list_activities(
    person_id: str | None = Query(default=None),
    activity_type: str | None = Query(default=None),
    room_name: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("caregiver")),
):
    """List detected activities with optional filters."""
    query = db.query(PersonActivity)
    if person_id:
        query = query.filter(PersonActivity.person_id == person_id)
    if activity_type:
        query = query.filter(PersonActivity.activity_type == activity_type)
    if room_name:
        query = query.filter(PersonActivity.room_name == room_name)

    activities = (
        query.order_by(desc(PersonActivity.detected_at)).limit(limit).all()
    )
    return activities
