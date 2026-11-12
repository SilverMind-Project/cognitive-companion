"""reCamera faces are uncalibrated in CC, whatever person-identification-service reports.

The household calibration artifact is fitted on CTS person crops, so its calibrated confidence does
not describe a reCamera frame. ``_resolve_calibrated_confidence`` is the one place that decides,
and it never falls back to raw similarity.
"""

from __future__ import annotations

import pytest

from backend.integrations.person_id_client import FaceResult
from backend.services.person_tracking import _resolve_calibrated_confidence


def _make_face_result(
    calibration_status: str = "ready",
    calibrated_confidence: float | None = 0.9,
) -> FaceResult:
    return FaceResult(
        person_id="alice",
        name="Alice",
        raw_similarity=0.85,
        bbox=[0, 0, 10, 10],
        calibration_status=calibration_status,
        calibrated_confidence=calibrated_confidence,
    )


def test_a_ready_calibrated_confidence_is_still_not_trusted_for_a_recamera_face():
    face = _make_face_result(calibration_status="ready", calibrated_confidence=0.92)

    assert _resolve_calibrated_confidence(face) is None


@pytest.mark.parametrize(
    ("status", "value"),
    [("degraded_missing", 0.92), ("degraded_incompatible", None), ("ready", None)],
)
def test_degraded_or_missing_calibration_is_none(status: str, value: float | None):
    face = _make_face_result(calibration_status=status, calibrated_confidence=value)

    assert _resolve_calibrated_confidence(face) is None
