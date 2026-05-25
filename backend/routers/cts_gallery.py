"""CTS gallery enrollment API.

Provides the single endpoint that seeds the ReID gallery with named
embeddings, unblocking the Bayesian identity resolver.  The heavy lifting
(fetching tracklet embeddings, creating named gallery rows) happens inside
the tracking-orchestrator; this router is a thin authenticated proxy.

Endpoint
--------
``POST /api/v1/cts/gallery/enroll``

Permission: ``cts.identity.correct`` (same authority as identity corrections).
When ``cts.enabled=False`` returns 404 + ``{"code": "cts.disabled"}``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.integrations._upstream_base import UpstreamError
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.models.person import HouseholdMember
from backend.routers.cts_deps import cts_enabled
from backend.routers.dependencies import get_orchestrator_client

logger = get_logger(__name__)

router = APIRouter(prefix="/cts/gallery", tags=["cts-gallery"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class EnrollRequest(BaseModel):
    """Body for ``POST /cts/gallery/enroll``."""

    identity_id: str = Field(..., min_length=1, max_length=128)
    tracklet_id: str = Field(..., min_length=1, max_length=128)
    display_name: str | None = Field(default=None, max_length=128)


# ---------------------------------------------------------------------------
# POST /cts/gallery/enroll
# ---------------------------------------------------------------------------


@router.post("/enroll")
async def enroll_tracklet(
    body: EnrollRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Promote tracklet gallery embeddings to a named identity.

    On success the orchestrator writes new :class:`GalleryEmbedding` rows
    with the given ``identity_id``; the resolver will pick them up on the
    next inference cycle.  Returns the orchestrator's enrollment receipt
    (``identity_id``, ``enrolled_count``, ``enrolled_at``).

    Returns 404 when the tracklet has no gallery embeddings yet (the person
    must appear on camera before enrollment is possible).
    """
    cts_enabled()

    member = (
        db.query(HouseholdMember)
        .filter(
            HouseholdMember.id == body.identity_id,
            HouseholdMember.is_active.is_(True),
        )
        .first()
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "cts.identity_not_found",
                "message": f"No active household member with id '{body.identity_id}'.",
            },
        )

    try:
        resp = await client.enroll_from_tracklet(
            identity_id=body.identity_id,
            tracklet_id=body.tracklet_id,
            display_name=body.display_name,
        )
    except UpstreamError as exc:
        raise HTTPException(
            status_code=exc.status or status.HTTP_502_BAD_GATEWAY,
            detail={"code": "cts.upstream_error", "message": str(exc)},
        ) from exc

    logger.info(
        "cts_gallery_enrollment_applied",
        actor=auth.name,
        identity_id=body.identity_id,
        tracklet_id=body.tracklet_id,
        enrolled_count=resp.get("enrolled_count"),
    )
    return resp
