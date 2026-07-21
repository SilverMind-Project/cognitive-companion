"""Identity-continuity M09: calibration field forwarding in PersonTrackingService.

Covers _resolve_calibrated_confidence's fail-closed gate (only "ready" status
is trusted, mirroring CTS's FaceIdentityStage) and the PersonDetection/
FaceResult round trip that carries calibrated_confidence through to
FaceSightingIngest.
"""

from __future__ import annotations

from backend.integrations.person_id_client import FaceResult
from backend.services.person_tracking import _resolve_calibrated_confidence


def _make_face_result(
    calibration_status: str = "ready",
    calibrated_confidence: float | None = 0.9,
) -> FaceResult:
    return FaceResult(
        person_id="alice",
        name="Alice",
        confidence=0.85,
        bbox=[0, 0, 10, 10],
        calibration_status=calibration_status,
        calibrated_confidence=calibrated_confidence,
    )


def test_resolve_calibrated_confidence_with_ready_status_returns_value():
    # Arrange
    face = _make_face_result(calibration_status="ready", calibrated_confidence=0.92)

    # Act
    result = _resolve_calibrated_confidence(face)

    # Assert
    assert result == 0.92


def test_resolve_calibrated_confidence_with_degraded_status_returns_none():
    # Arrange
    face = _make_face_result(calibration_status="degraded_missing", calibrated_confidence=0.92)

    # Act
    result = _resolve_calibrated_confidence(face)

    # Assert
    assert result is None


def test_resolve_calibrated_confidence_never_falls_back_to_raw_similarity():
    # Arrange: a degraded status with no calibrated_confidence at all.
    face = _make_face_result(calibration_status="degraded_incompatible", calibrated_confidence=None)

    # Act
    result = _resolve_calibrated_confidence(face)

    # Assert
    assert result is None
