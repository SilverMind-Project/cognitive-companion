"""Unified signals-feed API.

``GET /api/v1/signals/feed`` returns the cross-source caregiver feed
(CTS dementia signals + pipeline-rule notifications). Mutations stay on the
existing per-source endpoints (``/cts/signals/{id}/ack`` and delete); the
feed itself is read-only and tags each row with what it supports.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.core.auth import AuthContext, require_permission
from backend.routers.dependencies import get_signals_feed
from backend.schemas.signals_feed import SignalEnvelope
from backend.services.signals.feed import SignalsFeedService

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("/feed", response_model=list[SignalEnvelope])
async def get_signals_feed(
    source: str | None = Query(None, description="cts | pipeline_rule"),
    severity_min: str = Query("info", description="info | warning | emergency"),
    person_id: str | None = Query(None),
    room_name: str | None = Query(None),
    window_hours: int = Query(24, ge=1, le=720),
    limit: int = Query(50, ge=1, le=200),
    svc: SignalsFeedService = Depends(get_signals_feed),
    _auth: AuthContext = Depends(require_permission("caregiver")),
) -> list[SignalEnvelope]:
    return await svc.list_feed(
        source=source,
        severity_min=severity_min,
        person_id=person_id,
        room_name=room_name,
        window_hours=window_hours,
        limit=limit,
    )
