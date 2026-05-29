"""CTS bounding-box annotation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from backend.core.auth import AuthContext, require_permission
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.routers.cts_deps import cts_enabled
from backend.routers.dependencies import get_orchestrator_client
from backend.schemas.cts_bbox import BboxAnnotationResponse, BboxOverrideRequest
from backend.services.cts.bbox_annotation_service import BboxAnnotationService

router = APIRouter(prefix="/cts/identity", tags=["cts-bboxes"])

# ---------------------------------------------------------------------------
# GET /cts/identity/keyframes/{keyframe_id}/bboxes
# ---------------------------------------------------------------------------


@router.get("/keyframes/{keyframe_id}/bboxes", response_model=list[BboxAnnotationResponse])
async def get_keyframe_bboxes(
    keyframe_id: str,
    _auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    _cts: None = Depends(cts_enabled),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> list[BboxAnnotationResponse]:
    """Return bounding-box annotations for a keyframe."""
    svc = BboxAnnotationService(client)
    return await svc.get_for_keyframe(keyframe_id)


# ---------------------------------------------------------------------------
# PUT /cts/identity/bboxes/{annotation_id}/override
# ---------------------------------------------------------------------------


@router.put("/bboxes/{annotation_id}/override", response_model=BboxAnnotationResponse)
async def override_bbox(
    annotation_id: str,
    body: BboxOverrideRequest,
    auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> BboxAnnotationResponse:
    """Persist a user-drawn bounding box override."""
    svc = BboxAnnotationService(client)
    return await svc.save_override(annotation_id, body, override_by=auth.name)


# ---------------------------------------------------------------------------
# DELETE /cts/identity/bboxes/{annotation_id}
# ---------------------------------------------------------------------------


@router.delete("/bboxes/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bbox(
    annotation_id: str,
    auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> None:
    """Delete a single bounding box annotation."""
    svc = BboxAnnotationService(client)
    await svc.delete_annotation(annotation_id)


# ---------------------------------------------------------------------------
# POST /cts/identity/bboxes/batch
# ---------------------------------------------------------------------------


class BboxBatchOp(BaseModel):
    op: str = Field(..., pattern="^(create|update|delete)$")
    annotation_id: str | None = None
    data: dict | None = None


class BboxBatchRequest(BaseModel):
    keyframe_id: str
    operations: list[BboxBatchOp] = Field(..., min_length=1, max_length=50)


@router.post("/bboxes/batch")
async def apply_bbox_batch(
    body: BboxBatchRequest,
    auth: AuthContext = Depends(require_permission("cts.bboxes.write")),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Apply a batch of bbox create/update/delete operations atomically."""
    svc = BboxAnnotationService(client)
    ops = [{"op": o.op, "annotation_id": o.annotation_id, "data": o.data} for o in body.operations]
    return await svc.apply_bbox_batch(body.keyframe_id, ops)
