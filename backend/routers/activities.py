"""Person activity endpoints.

Provides endpoints for:
- Listing person activities
- Activity session management (open/close)
- Activity timeline aggregation
- Daily report generation and retrieval
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.auth import require_permission
from backend.core.database import get_db
from backend.models.person import PersonActivity
from backend.schemas.activity import (
    ActivitySessionCloseResult,
    ActivitySessionOpenResult,
    ActivitySessionOut,
    DailyReportOut,
    DailyReportQueryParams,
    PersonActivityOut,
)

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
    from sqlalchemy import desc

    query = db.query(PersonActivity)
    if person_id:
        query = query.filter(PersonActivity.person_id == person_id)
    if activity_type:
        query = query.filter(PersonActivity.activity_type == activity_type)
    if room_name:
        query = query.filter(PersonActivity.room_name == room_name)

    activities = query.order_by(desc(PersonActivity.detected_at)).limit(limit).all()
    return activities


# -- Activity Session Endpoints -----------------------------------------------


@router.post("/sessions/open", response_model=ActivitySessionOpenResult)
def open_activity_session(
    request: Request,
    person_id: str = Query(..., description="Household member ID"),
    activity_type: str = Query(..., description="Activity type (e.g., sleep, meal_eating)"),
    room_name: str = Query(..., description="Room where activity occurred"),
    confidence: float = Query(..., ge=0.0, le=1.0, description="Detection confidence"),
    started_at: datetime = Query(..., description="When the activity started (UTC)"),
    timeout_minutes: int | None = Query(default=None, description="Override timeout in minutes"),
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("caregiver")),
):
    """Open (or reuse) an activity session for a person.

    Idempotent: if an open session of the same type exists, returns it
    without creating a duplicate.
    """

    service = request.app.state.activity_session_service

    result = service.open_session(
        person_id=person_id,
        activity_type=activity_type,
        room_name=room_name,
        confidence=confidence,
        started_at=started_at,
        start_event_id=None,
        timeout_minutes=timeout_minutes,
    )

    return ActivitySessionOpenResult(
        session_id=result.session_id,
        person_id=result.person_id,
        activity_type=result.activity_type,
        room_name=result.room_name,
        opened_at=result.opened_at,
        timeout_minutes=result.timeout_minutes,
        was_existing=result.was_existing,
    )


@router.post("/sessions/{session_id}/close", response_model=ActivitySessionCloseResult)
def close_activity_session(
    request: Request,
    session_id: str,
    ended_at: datetime = Query(..., description="When the activity ended (UTC)"),
    closed_via: str = Query(default="explicit", description="One of: explicit, timeout, manual"),
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("caregiver")),
):
    """Close an open activity session.

    Args:
        session_id: The session ID to close.
        ended_at: When the activity ended (UTC).
        closed_via: How the session was closed.
    """
    from backend.models.person import ActivitySession

    # First, look up the session to get person_id and activity_type
    session = db.execute(
        select(ActivitySession).where(ActivitySession.id == session_id)
    ).scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    service = request.app.state.activity_session_service

    result = service.close_session(
        person_id=session.person_id,
        activity_type=session.activity_type,
        ended_at=ended_at,
        end_event_id=None,
        closed_via=closed_via,
    )

    return ActivitySessionCloseResult(
        session_id=result.session_id,
        person_id=result.person_id,
        activity_type=result.activity_type,
        room_name=result.room_name,
        opened_at=result.opened_at,
        closed_at=result.closed_at,
        duration_minutes=result.duration_minutes,
        status=result.status,
        closed_via=result.closed_via,
    )


@router.get("/sessions/open", response_model=list[ActivitySessionOut])
def list_open_sessions(
    person_id: str | None = Query(default=None, description="Filter by person ID"),
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("caregiver")),
):
    """Get all open activity sessions."""
    from backend.main import app

    service = app.state.activity_session_service

    sessions = service.get_open_sessions(person_id=person_id)
    return sessions


@router.get("/timeline", response_model=list[dict])
def get_activity_timeline(
    person_id: str = Query(..., description="Household member ID"),
    start_time: datetime | None = Query(default=None, description="Start time (UTC)"),
    end_time: datetime | None = Query(default=None, description="End time (UTC)"),
    limit: int = Query(default=100, ge=1, le=500, description="Max events to return"),
    event_types: list[str] | None = Query(
        default=None,
        description="Filter by source: activity, session, location, sighting",
    ),
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("caregiver")),
):
    """Get unified timeline events for a person.

    Combines:
    - PersonActivity events
    - ActivitySession open/close events
    - PersonLocationHistory room transitions
    - PersonSighting detections
    """
    from backend.main import app

    service = app.state.activity_timeline_service

    events = service.get_timeline(
        person_id=person_id,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        event_types=event_types,
    )

    return events


# -- Daily Report Endpoints ---------------------------------------------------


@router.get("/reports/{person_id}/{date}", response_model=DailyReportOut)
def get_daily_report(
    person_id: str,
    date: str,
    params: DailyReportQueryParams = Depends(),
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("caregiver")),
):
    """Get or generate a daily report for a person on a specific date.

    Args:
        person_id: Household member ID.
        date: Date in YYYY-MM-DD format.
        params: Optional parameters for report generation.
    """
    from backend.main import app

    service = app.state.daily_report_service

    report = service.generate_daily_report(
        person_id=person_id,
        date=date,
        tz_name=params.tz_name,
        include_llm_summary=params.include_llm_summary,
        include_room_trends=params.include_room_trends,
    )

    return DailyReportOut(**report)


@router.get("/reports/{person_id}/{date}/regenerate", response_model=DailyReportOut)
def regenerate_daily_report(
    person_id: str,
    date: str,
    params: DailyReportQueryParams = Depends(),
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("caregiver")),
):
    """Force regeneration of a daily report.

    Deletes existing report and generates a new one.
    """
    from backend.main import app

    service = app.state.daily_report_service

    # Note: The service handles upserting, so we just call generate
    report = service.generate_daily_report(
        person_id=person_id,
        date=date,
        tz_name=params.tz_name,
        include_llm_summary=params.include_llm_summary,
        include_room_trends=params.include_room_trends,
    )

    return DailyReportOut(**report)
