"""Pipeline run read-model endpoints (U5 W1).

GET /pipeline/runs?status=active  -- list runs, optionally filtered
GET /pipeline/runs/{execution_id} -- single run envelope
GET /pipeline/ingest/activity     -- recent ingest events

All endpoints require the ``caregiver`` permission (same gate as
``/workflows``).  A missing execution returns 404; no fabricated envelope
(rule 15).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.core.auth import AuthContext, require_permission
from backend.core.logging import get_logger
from backend.schemas.pipeline_run import (
    IngestActivityEnvelope,
    PipelineRunEnvelope,
)
from backend.services.pipeline_run_service import PipelineRunService as _PipelineRunService

logger = get_logger(__name__)

router = APIRouter(prefix="/pipeline", tags=["pipeline-runs"])


def _get_run_service(request: Request) -> _PipelineRunService:
    svc: _PipelineRunService | None = getattr(request.app.state, "pipeline_run_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="pipeline_run_service not available")
    return svc


@router.get("/runs", response_model=list[PipelineRunEnvelope])
def list_pipeline_runs(
    request: Request,
    status: str | None = Query(
        default=None,
        description="Filter by status; 'active' returns running+waiting executions",
    ),
    limit: int = Query(default=20, ge=1, le=100),
    _auth: AuthContext = Depends(require_permission("caregiver")),
) -> list[PipelineRunEnvelope]:
    """Return pipeline run envelopes, newest first.

    ``?status=active`` returns only running/waiting executions so the live
    panel can seed itself without a full history scan.
    """
    svc = _get_run_service(request)
    if status == "active":
        return svc.list_active_runs()
    return svc.recent_runs(limit=limit, status=status if status else None)


@router.get("/runs/{execution_id}", response_model=PipelineRunEnvelope)
def get_pipeline_run(
    execution_id: int,
    request: Request,
    _auth: AuthContext = Depends(require_permission("caregiver")),
) -> PipelineRunEnvelope:
    """Return the run envelope for a specific execution.

    Rule 15: 404 when the execution does not exist; never an empty fabricated envelope.
    """
    svc = _get_run_service(request)
    envelope = svc.get_run(execution_id)
    if envelope is None:
        raise HTTPException(
            status_code=404,
            detail=f"Pipeline execution {execution_id} not found",
        )
    return envelope


@router.get("/ingest/activity", response_model=list[IngestActivityEnvelope])
def list_ingest_activity(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    _auth: AuthContext = Depends(require_permission("caregiver")),
) -> list[IngestActivityEnvelope]:
    """Return recent ReCamera ingest + rule-triggered events.

    Sourced from MediaCache (frame_received) and EventLog (rule_triggered).
    Returns an explicit empty list when there is no ingest (rule 15: never
    a fabricated frame or a silent error).
    """
    svc = _get_run_service(request)
    return svc.list_ingest_activity(limit=limit)
