"""The household members an operator may assign a face, body, or track to.

``GET /api/v1/identity/targets`` is the one target list behind every identity decision in the
admin UI (track and keyframe corrections, ReID relabels, visitor attribution, face calibration
labels). It does not depend on CTS: with tracking disabled the list still returns, without
gallery counts.

``GET /api/v1/identity/review-vocabulary`` is the other half of every review form: the verdicts
each surface accepts and what each one changes, so the browser previews the server's own words.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.core.auth import AuthContext, require_permission
from backend.routers.dependencies import get_identity_targets_service
from backend.schemas.identity_review import (
    IdentityTargetOut,
    IdentityTargetsEnvelope,
    ReviewVocabularyEnvelope,
)
from backend.services.identity_review.vocabulary import vocabulary_envelope
from backend.services.identity_targets import IdentityTargetsService

router = APIRouter(prefix="/identity", tags=["identity-targets"])


@router.get("/targets", response_model=IdentityTargetsEnvelope)
async def get_identity_targets(
    svc: IdentityTargetsService = Depends(get_identity_targets_service),
    _auth: AuthContext = Depends(require_permission("identity_targets:read")),
) -> IdentityTargetsEnvelope:
    result = await svc.list_targets()
    return IdentityTargetsEnvelope(
        targets=[
            IdentityTargetOut(
                identity_id=t.identity_id,
                display_name=t.display_name,
                is_active=t.is_active,
                is_guest=t.is_guest,
                face_enrolled=t.face_enrolled,
                gallery_entry_count=t.gallery_entry_count,
                gallery_verified_count=t.gallery_verified_count,
            )
            for t in result.targets
        ],
        enrollment_available=result.enrollment_available,
        gallery_available=result.gallery_available,
    )


@router.get("/review-vocabulary", response_model=ReviewVocabularyEnvelope)
async def get_review_vocabulary(
    _auth: AuthContext = Depends(require_permission("identity_review:read")),
) -> ReviewVocabularyEnvelope:
    return vocabulary_envelope()
