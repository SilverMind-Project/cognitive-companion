"""Tests for CTS calibration validation."""

from backend.services.cts.calibration_validator import validate_homography


def test_polygon_check_uses_homography_metres_without_mpp_scaling():
    matrix = [[1.0, 0.0, 10.0], [0.0, 1.0, 10.0], [0.0, 0.0, 1.0]]
    room_polygon = [(9.0, 9.0), (12.0, 9.0), (12.0, 12.0), (9.0, 12.0)]

    result = validate_homography(
        matrix=matrix,
        residuals=[0.01],
        floor_plan_mpp=0.05,
        camera_room_polygon=room_polygon,
        image_width=1,
        image_height=1,
    )

    assert result.ok
    assert result.severity == "ok"
