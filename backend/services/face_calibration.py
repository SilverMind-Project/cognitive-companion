"""Face calibration review: the operator labels sampled faces from the household's cameras.

One service method powers each thin route in ``routers/face_calibration.py``; the read-only
progress summary also powers the ``get_face_calibration_summary`` MCP tool. Upstream failures
raise ``PersonIDUpstreamError`` (never an empty queue that looks like "nothing to label").
"""

from __future__ import annotations

from collections.abc import Callable

from backend.integrations.person_id_client import CalibrationCandidateInfo, PersonIDClient
from backend.schemas.face_calibration import (
    CalibrationCandidateListResponse,
    CalibrationCandidateView,
    CalibrationIdentityProgressView,
    FaceCalibrationReviewRequest,
    FaceCalibrationSummaryEnvelope,
)
from backend.schemas.identity_review import BatchReviewResponse, ReviewItemResult
from backend.services.identity_review.vocabulary import effect_text

# Maps a MinIO key (or None) to a browser-reachable URL (or None).
Presigner = Callable[[str | None], str | None]


# The calibration label each batch verdict is stored as.
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

    async def review(
        self, request: FaceCalibrationReviewRequest, *, actor: str
    ) -> BatchReviewResponse:
        """Label several captures as someone not in the household, or not usable.

        ``not_usable`` is stored as ``not_a_face``, which the calibration fit skips. A missing
        capture is reported per item; the rest are labeled.
        """
        items = await self._client.label_calibration_candidates(
            request.candidate_ids,
            label_kind=_LABEL_FOR_VERDICT[request.verdict],
            labeled_by=actor,
        )
        results = [
            ReviewItemResult(
                id=item.candidate_id,
                ok=item.ok,
                error_code=None
                if item.ok
                else ("not_found" if item.error_code == "not_found" else "upstream_error"),
            )
            for item in items
        ]
        reviewed = sum(1 for r in results if r.ok)
        return BatchReviewResponse(
            results=results,
            reviewed=reviewed,
            failed=len(results) - reviewed,
            effect=effect_text("face_calibration", request.verdict),
        )

    async def reject(
        self, candidate_id: str, *, presign: Presigner = _no_presign
    ) -> CalibrationCandidateView:
        return self._view(await self._client.reject_calibration_candidate(candidate_id), presign)

    async def delete(self, candidate_id: str) -> None:
        await self._client.delete_calibration_candidate(candidate_id)

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
        )
