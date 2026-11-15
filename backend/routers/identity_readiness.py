"""Identity readiness: which step of identity setup is broken, and what to do next.

``GET /api/v1/identity/readiness`` is read-only. A source that cannot be read marks its own steps
``unknown``; the route itself answers 200 so the page can diagnose a partial outage.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.core.auth import AuthContext, require_permission
from backend.routers.dependencies import get_identity_readiness_service
from backend.schemas.identity_readiness import IdentityReadinessEnvelope
from backend.services.identity_readiness import IdentityReadinessService

router = APIRouter(prefix="/identity", tags=["identity-readiness"])


@router.get("/readiness", response_model=IdentityReadinessEnvelope)
async def get_identity_readiness(
    svc: IdentityReadinessService = Depends(get_identity_readiness_service),
    _auth: AuthContext = Depends(require_permission("identity_readiness:read")),
) -> IdentityReadinessEnvelope:
    return await svc.get_readiness()
