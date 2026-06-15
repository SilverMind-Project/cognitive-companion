"""Admin endpoints for retained media and live aggregator telemetry."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from backend.core.auth import AuthContext, require_permission
from backend.routers.dependencies import get_media_observability
from backend.schemas.media_observability import (
    AggregatorStateListEnvelope,
    MediaBufferListEnvelope,
)
from backend.services.media_observability import MediaObservabilityService

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/buffer", response_model=MediaBufferListEnvelope)
def get_media_buffer(
    sensor_id: str | None = Query(None, description="Restrict to a single sensor ID"),
    limit: int = Query(20, ge=1, le=100, description="Maximum camera rows returned"),
    offset: int = Query(0, ge=0, description="Camera rows to skip"),
    service: MediaObservabilityService = Depends(get_media_observability),
    _auth: AuthContext = Depends(require_permission("admin")),
) -> MediaBufferListEnvelope:
    """Return paginated reCamera buffers with retained media."""
    return service.media_buffer(sensor_id=sensor_id, limit=limit, offset=offset)


@router.get("/aggregators", response_model=AggregatorStateListEnvelope)
def get_aggregators(
    origin: Literal["recamera", "cts"] | None = Query(None),
    camera_id: str | None = Query(None),
    room_name: str | None = Query(None),
    q: str | None = Query(None, description="Match camera name, ID, or room"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: MediaObservabilityService = Depends(get_media_observability),
    _auth: AuthContext = Depends(require_permission("admin")),
) -> AggregatorStateListEnvelope:
    """Return live state for both camera aggregators.

    This is operational admin telemetry, not caregiver-facing domain data.
    Per the aggregator unification D6 exemption, it uses one service method
    but intentionally has no MCP tool mirror.
    """
    return service.aggregator_state(
        origin=origin,
        camera_id=camera_id,
        room_name=room_name,
        query=q,
        limit=limit,
        offset=offset,
    )
