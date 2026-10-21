"""Face calibration review routes (browser-facing BFF).

Every route requires ``require_token("face_calibration.review")``, a strict biometric-admin grant
like visitor review: the broad role globs do not unlock it. Like visitor review, it depends only
on person-identification-service, never on ``cts.enabled``. The labeler recorded upstream is the
authenticated caller.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from backend.core.auth import AuthContext, require_token
from backend.core.logging import get_logger
from backend.integrations.minio_client import MinioClient
from backend.integrations.person_id_client import PersonIDUpstreamError
from backend.routers.dependencies import get_config_minio_client, get_face_calibration_service
from backend.schemas.face_calibration import (
    CalibrationCandidateListResponse,
    CalibrationCandidateView,
    FaceCalibrationSummaryEnvelope,
    LabelCalibrationCandidateRequest,
)
from backend.services.face_calibration import FaceCalibrationReviewService

logger = get_logger(__name__)

router = APIRouter(prefix="/face-calibration", tags=["face-calibration"])

_REVIEW = "face_calibration.review"
_PRESIGN_TTL = 3600  # 1 hour; sized for one labeling session


def _presigner(minio: MinioClient):
    def presign(key: str | None) -> str | None:
        if not key:
            return None
        return minio.generate_presigned_url(key, expiration=_PRESIGN_TTL)

    return presign


def _upstream(exc: PersonIDUpstreamError) -> HTTPException:
    return HTTPException(status_code=502 if exc.status >= 500 else exc.status, detail=exc.message)


@router.get("/candidates", response_model=CalibrationCandidateListResponse)
async def list_calibration_candidates(
    state: Literal["unlabeled", "labeled", "rejected"] | None = "unlabeled",
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    svc: FaceCalibrationReviewService = Depends(get_face_calibration_service),
    minio: MinioClient = Depends(get_config_minio_client),
    _auth: AuthContext = Depends(require_token(_REVIEW)),
) -> CalibrationCandidateListResponse:
    try:
        return await svc.list_candidates(
            state=state, limit=limit, cursor=cursor, presign=_presigner(minio)
        )
    except PersonIDUpstreamError as exc:
        raise _upstream(exc) from exc


@router.post("/candidates/{candidate_id}/label", response_model=CalibrationCandidateView)
async def label_calibration_candidate(
    candidate_id: str,
    body: LabelCalibrationCandidateRequest,
    svc: FaceCalibrationReviewService = Depends(get_face_calibration_service),
    minio: MinioClient = Depends(get_config_minio_client),
    auth: AuthContext = Depends(require_token(_REVIEW)),
) -> CalibrationCandidateView:
    actor = auth.name
    try:
        result = await svc.label(
            candidate_id,
            label_kind=body.label_kind,
            label_identity_id=body.label_identity_id,
            actor=actor,
            presign=_presigner(minio),
        )
    except PersonIDUpstreamError as exc:
        raise _upstream(exc) from exc
    logger.info(
        "face_calibration_labeled",
        candidate_id=candidate_id,
        label_kind=body.label_kind,
        actor=actor,
    )
    return result


@router.post("/candidates/{candidate_id}/reject", response_model=CalibrationCandidateView)
async def reject_calibration_candidate(
    candidate_id: str,
    svc: FaceCalibrationReviewService = Depends(get_face_calibration_service),
    minio: MinioClient = Depends(get_config_minio_client),
    auth: AuthContext = Depends(require_token(_REVIEW)),
) -> CalibrationCandidateView:
    try:
        result = await svc.reject(candidate_id, presign=_presigner(minio))
    except PersonIDUpstreamError as exc:
        raise _upstream(exc) from exc
    logger.info("face_calibration_rejected", candidate_id=candidate_id, actor=auth.name)
    return result


@router.delete("/candidates/{candidate_id}", status_code=204)
async def delete_calibration_candidate(
    candidate_id: str,
    svc: FaceCalibrationReviewService = Depends(get_face_calibration_service),
    auth: AuthContext = Depends(require_token(_REVIEW)),
) -> Response:
    try:
        await svc.delete(candidate_id)
    except PersonIDUpstreamError as exc:
        raise _upstream(exc) from exc
    logger.info("face_calibration_deleted", candidate_id=candidate_id, actor=auth.name)
    return Response(status_code=204)


@router.get("/summary", response_model=FaceCalibrationSummaryEnvelope)
async def get_face_calibration_summary(
    svc: FaceCalibrationReviewService = Depends(get_face_calibration_service),
    _auth: AuthContext = Depends(require_token(_REVIEW)),
) -> FaceCalibrationSummaryEnvelope:
    try:
        return await svc.get_summary()
    except PersonIDUpstreamError as exc:
        raise _upstream(exc) from exc
