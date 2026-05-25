"""API router for interactive responses."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from backend.core.auth import require_permission
from backend.core.database import get_db
from backend.models.interactive_response import InteractiveResponse

router = APIRouter(prefix="/interactive-responses", tags=["interactive-responses"])


@router.get("")
async def get_interactive_responses(
    channel: str | None = Query(None, description="Filter by channel"),
    action: str | None = Query(None, description="Filter by action"),
    date_from: date | None = Query(None, description="Filter from date (inclusive)"),
    date_to: date | None = Query(None, description="Filter to date (inclusive)"),
    limit: int = Query(100, ge=1, le=1000, description="Max results to return"),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("GET /api/v1/interactive-responses")),
):
    """
    Get interactive responses with optional filtering.

    Returns a list of interactive response records ordered by created_at descending.
    Supports filtering by channel, action, and date range.
    """
    query = db.query(InteractiveResponse)

    # Apply filters
    filters = []
    if channel:
        filters.append(InteractiveResponse.channel == channel)
    if action:
        filters.append(InteractiveResponse.action == action)
    if date_from:
        filters.append(
            InteractiveResponse.created_at >= datetime.combine(date_from, datetime.min.time())
        )
    if date_to:
        filters.append(
            InteractiveResponse.created_at < datetime.combine(date_to, datetime.max.time())
        )

    if filters:
        query = query.filter(and_(*filters))

    # Order by created_at descending and limit
    query = query.order_by(desc(InteractiveResponse.created_at)).limit(limit)

    responses = query.all()

    # Calculate latency for each response (if possible)
    result = []
    for resp in responses:
        item = {
            "id": resp.id,
            "execution_id": resp.execution_id,
            "step_id": resp.step_id,
            "channel": resp.channel,
            "action": resp.action,
            "timestamp": resp.timestamp.isoformat() if resp.timestamp else None,
            "created_at": resp.created_at.isoformat() if resp.created_at else None,
            "raw_response_json": resp.raw_response_json,
            "latency_ms": None,
        }

        # Calculate latency if both timestamps are available
        if resp.timestamp and resp.created_at:
            latency = (resp.created_at - resp.timestamp).total_seconds() * 1000
            item["latency_ms"] = int(latency)

        result.append(item)

    return result
