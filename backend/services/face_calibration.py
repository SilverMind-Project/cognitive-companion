"""Face calibration review: the operator labels sampled faces from the household's cameras.

One service method powers each thin route in ``routers/face_calibration.py``, except the batch
review, which goes through the identity review registry to ``FaceCalibrationReviewAdapter``; the read-only
progress summary also powers the ``get_face_calibration_summary`` MCP tool. Upstream failures
raise ``PersonIDUpstreamError`` (never an empty queue that looks like "nothing to label").
"""

from __future__ import annotations

from collections.abc import Callable

from backend.core.exceptions import ValidationError
from backend.integrations.person_id_client import (
    CalibrationCandidateInfo,
    PersonIDClient,
    PrototypeInfo,
)
from backend.schemas.face_calibration import (
    CalibrationCandidateListResponse,
    CalibrationCandidateView,
    CalibrationIdentityProgressView,
    FaceCalibrationSummaryEnvelope,
    PromoteCalibrationCandidateResponse,
)
from backend.schemas.identity_review import ReviewItemResult, ReviewSurface
from backend.schemas.person import (
    PersonPrototypesResponse,
    PersonPrototypeView,
    RebuildPrototypesResponse,
)
from backend.services.identity_review.registry import ReviewDecision

# Maps a MinIO key (or None) to a browser-reachable URL (or None).
Presigner = Callable[[str | None], str | None]


# The calibration label each verdict that names nobody is stored as.
_LABEL_FOR_VERDICT = {"not_enrolled": "not_enrolled", "not_usable": "not_a_face"}


def _no_presign(_key: str | None) -> str | None:
    return None


class FaceCalibrationReviewService:
    def __init__(self, client: PersonIDClient) -> None:
        self._client = client

    async def list_candidates(
        self,
        *,
        state: str | None,
        limit: int,
        cursor: str | None,
        presign: Presigner = _no_presign,
    ) -> CalibrationCandidateListResponse:
        page = await self._client.list_calibration_candidates(
            state=state, limit=limit, cursor=cursor
        )
        return CalibrationCandidateListResponse(
            candidates=[self._view(c, presign) for c in page.candidates],
            next_cursor=page.next_cursor,
        )

    async def label(
        self,
        candidate_id: str,
        *,
        label_kind: str,
        label_identity_id: str | None,
        actor: str,
        presign: Presigner = _no_presign,
    ) -> CalibrationCandidateView:
        labeled = await self._client.label_calibration_candidate(
            candidate_id,
            label_kind=label_kind,
            label_identity_id=label_identity_id,
            labeled_by=actor,
        )
        return self._view(labeled, presign)

    async def reject(
        self, candidate_id: str, *, presign: Presigner = _no_presign
    ) -> CalibrationCandidateView:
        return self._view(await self._client.reject_calibration_candidate(candidate_id), presign)

    async def delete(self, candidate_id: str) -> None:
        await self._client.delete_calibration_candidate(candidate_id)

    async def promote(
        self, candidate_id: str, *, actor: str
    ) -> PromoteCalibrationCandidateResponse:
        res = await self._client.promote_calibration_candidate(candidate_id, approved_by=actor)
        return PromoteCalibrationCandidateResponse(
            candidate_id=res.candidate_id,
            person_id=res.person_id,
            pose_bin=res.pose_bin,
            embedding_id=res.embedding_id,
            gallery_revision=res.gallery_revision,
            prototype_count=res.prototype_count,
            counts_by_bin=res.counts_by_bin,
        )

    async def list_prototypes(
        self, person_id: str, *, presign: Presigner = _no_presign
    ) -> PersonPrototypesResponse:
        info = await self._client.list_member_prototypes(person_id)
        return PersonPrototypesResponse(
            person_id=info.person_id,
            gallery_revision=info.gallery_revision,
            prototypes=[self._prototype_view(p, presign) for p in info.prototypes],
            counts_by_bin=info.counts_by_bin,
        )

    async def rebuild_prototypes(self, person_id: str) -> RebuildPrototypesResponse:
        res = await self._client.rebuild_member_prototypes(person_id)
        return RebuildPrototypesResponse(
            person_id=res.person_id,
            prototype_count=res.prototype_count,
            counts_by_bin=res.counts_by_bin,
        )

    async def delete_prototype(self, person_id: str, prototype_id: str) -> None:
        await self._client.delete_member_prototype(person_id, prototype_id)

    async def get_summary(self) -> FaceCalibrationSummaryEnvelope:
        summary = await self._client.get_calibration_summary()
        return FaceCalibrationSummaryEnvelope(
            by_state=summary.by_state,
            by_label_kind=summary.by_label_kind,
            by_quality_decile=summary.by_quality_decile,
            by_camera=summary.by_camera,
            identities=[
                CalibrationIdentityProgressView(
                    identity_id=i.identity_id,
                    labeled_faces=i.labeled_faces,
                    episodes=i.episodes,
                    target_labeled_faces=i.target_labeled_faces,
                )
                for i in summary.identities
            ],
            not_enrolled_episodes=summary.not_enrolled_episodes,
            capture_enabled=summary.capture_enabled,
            promotable_by_identity_pose=summary.promotable_by_identity_pose,
        )

    @staticmethod
    def _view(c: CalibrationCandidateInfo, presign: Presigner) -> CalibrationCandidateView:
        return CalibrationCandidateView(
            candidate_id=c.candidate_id,
            captured_at=c.captured_at,
            camera_id=c.camera_id,
            crop_url=presign(c.crop_object_key),
            quality_score=c.quality_score,
            quality_version=c.quality_version,
            interocular_px=c.interocular_px,
            yaw_deg=c.yaw_deg,
            pitch_deg=c.pitch_deg,
            nearest_person_id=c.nearest_person_id,
            nearest_similarity=c.nearest_similarity,
            label_state=c.label_state,
            label_kind=c.label_kind,
            label_identity_id=c.label_identity_id,
            labeled_by=c.labeled_by,
            labeled_at=c.labeled_at,
            pose_bin=c.pose_bin,
            promoted=c.promoted,
            promotion_eligible=c.promotion_eligible,
            promotion_ineligible_reason=c.promotion_ineligible_reason,
        )

    @staticmethod
    def _prototype_view(p: PrototypeInfo, presign: Presigner) -> PersonPrototypeView:
        return PersonPrototypeView(
            prototype_id=p.prototype_id,
            person_id=p.person_id,
            pose_bin=p.pose_bin,
            member_count=p.member_count,
            source=p.source,
            quality_score=p.quality_score,
            quality_version=p.quality_version,
            crop_url=presign(p.crop_object_key),
            approved_by=p.approved_by,
            approved_at=p.approved_at,
            created_at=p.created_at,
        )


class FaceCalibrationReviewAdapter:
    """Calibration captures as a review surface: person-id labels them in one batch.

    Only verdicts that name nobody arrive here (the registry refuses a member label for more than
    one capture, and the single-capture label route keeps its own response). ``not_usable`` is
    stored as ``not_a_face``, which the calibration fit skips. A missing capture is reported per
    item; the rest are labeled.
    """

    surface: ReviewSurface = "face_calibration"

    def __init__(self, client: PersonIDClient) -> None:
        self._client = client

    async def apply(self, decision: ReviewDecision, *, actor: str) -> list[ReviewItemResult]:
        label_kind = _LABEL_FOR_VERDICT.get(decision.verdict)
        if label_kind is None:
            raise ValidationError(f"face calibration cannot batch-apply {decision.verdict}")
        items = await self._client.label_calibration_candidates(
            [s.id for s in decision.subjects], label_kind=label_kind, labeled_by=actor
        )
        return [
            ReviewItemResult(
                id=item.candidate_id,
                ok=item.ok,
                error_code=None
                if item.ok
                else ("not_found" if item.error_code == "not_found" else "upstream_error"),
            )
            for item in items
        ]
