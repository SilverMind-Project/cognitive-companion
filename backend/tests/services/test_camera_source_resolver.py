from __future__ import annotations

from backend.models.cts_camera import CtsCamera
from backend.models.sensor import Sensor
from backend.services.guided_task.camera_selection import CameraSourceResolverService


def test_cts_id_resolves_cts(db_session, db_factory) -> None:
    # Arrange
    cam = CtsCamera(id="cts-cam-1", name="CTS Camera 1", rtsp_url="rtsp://test", enabled=True)
    db_session.add(cam)
    db_session.commit()

    resolver = CameraSourceResolverService(db_factory)

    # Act & Assert
    assert resolver("cts-cam-1") == "cts"


def test_recamera_sensor_resolves_recamera(db_session, db_factory) -> None:
    # Arrange
    sensor = Sensor(id="recamera-1", name="reCamera 1", sensor_type="camera", enabled=True)
    db_session.add(sensor)
    db_session.commit()

    resolver = CameraSourceResolverService(db_factory)

    # Act & Assert
    assert resolver("recamera-1") == "recamera"
    assert resolver("recamera:recamera-1") == "recamera"


def test_unknown_returns_none(db_session, db_factory) -> None:
    # Arrange
    resolver = CameraSourceResolverService(db_factory)

    # Act & Assert
    assert resolver("unknown-camera") is None
