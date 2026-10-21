"""FaceCalibrationReviewService maps person-id captures to browser views."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from backend.integrations.person_id_client import CalibrationCandidateInfo, CalibrationCandidatePage
from backend.services.face_calibration import FaceCalibrationReviewService

_INFO = CalibrationCandidateInfo(
    candidate_id="c1",
    captured_at=datetime(2026, 10, 21, 9, 0, tzinfo=UTC),
    camera_id="cam-1",
    crop_object_key="calibration/c1.png",
    quality_score=0.4,
    quality_version="heuristic-v1",
    interocular_px=None,
    yaw_deg=0.0,
    pitch_deg=0.0,
    nearest_person_id=None,
    nearest_similarity=0.1,
    label_state="unlabeled",
    label_kind=None,
    label_identity_id=None,
    labeled_by=None,
    labeled_at=None,
)


async def test_list_presigns_crop_keys_and_keeps_the_cursor() -> None:
    client = MagicMock()
    client.list_calibration_candidates = AsyncMock(
        return_value=CalibrationCandidatePage(candidates=[_INFO], next_cursor="k2")
    )
    service = FaceCalibrationReviewService(client)

    page = await service.list_candidates(
        state="unlabeled", limit=10, cursor="k1", presign=lambda key: f"signed:{key}"
    )

    assert page.next_cursor == "k2"
    assert page.candidates[0].crop_url == "signed:calibration/c1.png"
    client.list_calibration_candidates.assert_awaited_once_with(
        state="unlabeled", limit=10, cursor="k1"
    )


async def test_label_passes_the_actor_as_labeler() -> None:
    client = MagicMock()
    client.label_calibration_candidate = AsyncMock(return_value=_INFO)
    service = FaceCalibrationReviewService(client)

    view = await service.label(
        "c1", label_kind="not_enrolled", label_identity_id=None, actor="admin"
    )

    client.label_calibration_candidate.assert_awaited_once_with(
        "c1", label_kind="not_enrolled", label_identity_id=None, labeled_by="admin"
    )
    assert view.crop_url is None  # no presigner given
