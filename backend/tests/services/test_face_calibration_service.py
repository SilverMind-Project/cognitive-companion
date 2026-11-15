"""FaceCalibrationReviewService maps person-id captures to browser views."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from backend.integrations.person_id_client import (
    CalibrationCandidateInfo,
    CalibrationCandidatePage,
    CalibrationLabelItem,
)
from backend.schemas.face_calibration import FaceCalibrationReviewRequest
from backend.services.face_calibration import FaceCalibrationReviewService
from backend.services.identity_review.vocabulary import effect_text

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


async def test_review_labels_each_capture_and_states_the_effect() -> None:
    client = MagicMock()
    client.label_calibration_candidates = AsyncMock(
        return_value=[
            CalibrationLabelItem(candidate_id="c1", ok=True, error_code=None),
            CalibrationLabelItem(candidate_id="c2", ok=False, error_code="not_found"),
            CalibrationLabelItem(candidate_id="c3", ok=False, error_code="other"),
        ]
    )
    svc = FaceCalibrationReviewService(client)

    result = await svc.review(
        FaceCalibrationReviewRequest(candidate_ids=["c1", "c2", "c3"], verdict="not_usable"),
        actor="Caregiver Admin",
    )

    # Not usable is stored as not_a_face, which the calibration fit skips.
    client.label_calibration_candidates.assert_awaited_once_with(
        ["c1", "c2", "c3"], label_kind="not_a_face", labeled_by="Caregiver Admin"
    )
    assert [(r.id, r.ok, r.error_code) for r in result.results] == [
        ("c1", True, None),
        ("c2", False, "not_found"),
        ("c3", False, "upstream_error"),
    ]
    assert (result.reviewed, result.failed) == (1, 2)
    assert result.effect == effect_text("face_calibration", "not_usable")
