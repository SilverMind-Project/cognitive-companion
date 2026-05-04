"""CTS presence smoke router for manual verification.

Provides a single GET endpoint that returns the fused presence snapshot
for a person.  When ``cts.enabled=false`` every handler returns 404 with
code ``cts.disabled``.

Routes:
    GET  /api/v1/cts/presence/{person_id}  : presence snapshot
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, status

from backend.core.config import settings
from backend.services.presence import (
    PresenceSnapshot,
)

router = APIRouter(prefix="/cts/presence", tags=["cts-presence"])


def _cts_enabled() -> None:
    if not settings.get("cts.enabled", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "cts.disabled", "message": "CTS is not enabled on this instance."},
        )


def _snapshot_to_dict(snapshot: PresenceSnapshot) -> dict:
    """Serialize a PresenceSnapshot to a JSON-friendly dict."""
    return {
        "person_id": snapshot.person_id,
        "status": snapshot.status,
        "room_id": snapshot.room_id,
        "room_name": snapshot.room_name,
        "confidence": snapshot.confidence,
        "last_seen_at": snapshot.last_seen_at.isoformat() if snapshot.last_seen_at else None,
        "dwell_minutes": snapshot.dwell_minutes,
        "sources": [
            {"name": s.name, "confidence": s.confidence, "weight": s.weight}
            for s in snapshot.sources
        ],
        "inferred_at": snapshot.inferred_at.isoformat(),
        "notes": snapshot.notes,
    }


@router.get("/{person_id}")
async def get_presence(
    person_id: str,
    request: Request,
    at: str | None = Query(
        None,
        description=(
            "ISO-8601 datetime for deterministic testing. "
            "Defaults to current time when absent."
        ),
    ),
) -> dict:
    """Return the fused presence snapshot for *person_id*."""
    _cts_enabled()

    presence_service = request.app.state.presence
    if presence_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "presence.unavailable", "message": "PresenceService not initialized."},
        )

    at_dt: datetime | None = None
    if at:
        at_dt = datetime.fromisoformat(at)

    snapshot = await presence_service.get(person_id, at=at_dt)
    return _snapshot_to_dict(snapshot)
