"""Tests for per-device image serving with refresh suppression.

Strategy
--------
``_serve_image_for_sensor`` is a pure function of its arguments (session, a
lightweight request stub, and a MinIO stub).  Every scenario is exercised by
injecting known image bytes via a fake MinioClient, recording a matching or
mismatching ``ActiveImageState``, and asserting on the HTTP response returned.

The ``db_session`` fixture is function-scoped and backed by the shared
PostgreSQL test database, so commits inside the helper do not bleed across
tests.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from backend.core.config import Settings
from backend.core.exceptions import NotFoundError
from backend.models.image_state import ActiveImageState
from backend.routers import image as image_router

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ACTIVE_KEY_PREFIX = "eink/active"
_TEMPLATE_KEY_PREFIX = "eink/templates"


def _minio_stub(active_bytes: bytes | None, default_bytes: bytes | None = None) -> MagicMock:
    """Return a MinioClient stub whose ``get_object`` maps prefixes to bytes."""

    def _get_object(key: str) -> bytes | None:
        if key.startswith(f"{_ACTIVE_KEY_PREFIX}/"):
            return active_bytes
        if key.startswith(f"{_TEMPLATE_KEY_PREFIX}/"):
            return default_bytes
        return None

    stub = MagicMock()
    stub.get_object.side_effect = _get_object
    return stub


def _request() -> SimpleNamespace:
    """Minimal request stub whose eink_renderer exposes MinIO key helpers."""
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                eink_renderer=SimpleNamespace(
                    get_active_image_key=lambda sid: f"{_ACTIVE_KEY_PREFIX}/{sid}.png",
                    get_template_key=lambda filename: f"{_TEMPLATE_KEY_PREFIX}/{filename}",
                )
            )
        )
    )


def _settings(refresh_window_minutes: int) -> Settings:
    return Settings.from_dict(
        {
            "image": {
                "refresh_window_minutes": refresh_window_minutes,
                "default_template": "default",
            }
        }
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Core serving behaviour
# ---------------------------------------------------------------------------


class TestServeImageForSensor:
    # -- baseline cases -------------------------------------------------------

    def test_first_poll_serves_image(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """First request for a device (no prior state) always delivers the image."""
        minio = _minio_stub(active_bytes=b"first-frame")
        monkeypatch.setattr(image_router, "settings", _settings(60))

        response = image_router._serve_image_for_sensor(
            "device-a", db_session, _request(), minio
        )

        assert response.status_code == 200
        assert response.body == b"first-frame"
        assert response.media_type == "image/png"

    def test_first_poll_creates_delivery_state(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Serving the image records last_served_hash and last_served_at."""
        minio = _minio_stub(active_bytes=b"img-bytes")
        monkeypatch.setattr(image_router, "settings", _settings(60))

        before = datetime.now(UTC)
        image_router._serve_image_for_sensor("device-b", db_session, _request(), minio)

        state = db_session.execute(
            select(ActiveImageState).where(ActiveImageState.sensor_id == "device-b")
        ).scalar_one()

        assert state.last_served_hash == _sha256(b"img-bytes")
        assert state.last_served_at is not None
        assert state.last_served_at >= before

    # -- refresh-suppression: no refresh needed -------------------------------

    def test_returns_204_when_content_unchanged_within_window(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """204 No Content is returned when the image has not changed and the
        forced-refresh window has not elapsed."""
        minio = _minio_stub(active_bytes=b"stable-frame")

        db_session.add(
            ActiveImageState(
                sensor_id="device-c",
                last_served_hash=_sha256(b"stable-frame"),
                last_served_at=datetime.now(UTC) - timedelta(minutes=30),
            )
        )
        db_session.commit()

        monkeypatch.setattr(image_router, "settings", _settings(60))

        response = image_router._serve_image_for_sensor(
            "device-c", db_session, _request(), minio
        )

        assert response.status_code == 204

    def test_204_has_empty_body(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The 204 response carries no body, so the display driver has nothing to render."""
        minio = _minio_stub(active_bytes=b"same-content")

        db_session.add(
            ActiveImageState(
                sensor_id="device-d",
                last_served_hash=_sha256(b"same-content"),
                last_served_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )
        db_session.commit()

        monkeypatch.setattr(image_router, "settings", _settings(60))

        response = image_router._serve_image_for_sensor(
            "device-d", db_session, _request(), minio
        )

        assert not response.body

    # -- refresh-suppression: refresh required --------------------------------

    def test_serves_image_when_content_changed(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A new image is always served even if the window has not elapsed."""
        minio = _minio_stub(active_bytes=b"new-frame")

        db_session.add(
            ActiveImageState(
                sensor_id="device-e",
                last_served_hash=_sha256(b"old-frame"),
                last_served_at=datetime.now(UTC) - timedelta(minutes=5),
            )
        )
        db_session.commit()

        monkeypatch.setattr(image_router, "settings", _settings(60))

        response = image_router._serve_image_for_sensor(
            "device-e", db_session, _request(), minio
        )

        assert response.status_code == 200
        assert response.body == b"new-frame"

    def test_serves_image_when_window_elapsed(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even unchanged content is re-delivered once the refresh window expires."""
        minio = _minio_stub(active_bytes=b"periodic-frame")

        db_session.add(
            ActiveImageState(
                sensor_id="device-f",
                last_served_hash=_sha256(b"periodic-frame"),
                last_served_at=datetime.now(UTC) - timedelta(minutes=90),
            )
        )
        db_session.commit()

        monkeypatch.setattr(image_router, "settings", _settings(60))

        response = image_router._serve_image_for_sensor(
            "device-f", db_session, _request(), minio
        )

        assert response.status_code == 200
        assert response.body == b"periodic-frame"

    def test_window_zero_disables_suppression(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """refresh_window_minutes=0 always delivers the image regardless of hash."""
        minio = _minio_stub(active_bytes=b"always-refresh")

        db_session.add(
            ActiveImageState(
                sensor_id="device-g",
                last_served_hash=_sha256(b"always-refresh"),
                last_served_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        db_session.commit()

        monkeypatch.setattr(image_router, "settings", _settings(0))

        response = image_router._serve_image_for_sensor(
            "device-g", db_session, _request(), minio
        )

        assert response.status_code == 200

    def test_serves_image_when_last_served_at_is_none(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """State exists with a matching hash but no last_served_at triggers a refresh."""
        minio = _minio_stub(active_bytes=b"needs-refresh")

        db_session.add(
            ActiveImageState(
                sensor_id="device-h",
                last_served_hash=_sha256(b"needs-refresh"),
                last_served_at=None,
            )
        )
        db_session.commit()

        monkeypatch.setattr(image_router, "settings", _settings(60))

        response = image_router._serve_image_for_sensor(
            "device-h", db_session, _request(), minio
        )

        assert response.status_code == 200

    # -- state update on delivery ---------------------------------------------

    def test_delivery_state_updated_after_serve(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """last_served_hash and last_served_at are updated when a new image is sent."""
        minio = _minio_stub(active_bytes=b"updated-img")

        db_session.add(
            ActiveImageState(
                sensor_id="device-i",
                last_served_hash=_sha256(b"old-img"),
                last_served_at=datetime(2024, 1, 1, tzinfo=UTC),
            )
        )
        db_session.commit()

        before = datetime.now(UTC)

        monkeypatch.setattr(image_router, "settings", _settings(60))

        image_router._serve_image_for_sensor("device-i", db_session, _request(), minio)

        state = db_session.execute(
            select(ActiveImageState).where(ActiveImageState.sensor_id == "device-i")
        ).scalar_one()

        assert state.last_served_hash == _sha256(b"updated-img")
        assert state.last_served_at >= before

    def test_no_state_update_on_204(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When 204 is returned, the stored last_served_at is not advanced."""
        minio = _minio_stub(active_bytes=b"unchanged")

        original_time = datetime.now(UTC) - timedelta(minutes=10)
        db_session.add(
            ActiveImageState(
                sensor_id="device-j",
                last_served_hash=_sha256(b"unchanged"),
                last_served_at=original_time,
            )
        )
        db_session.commit()

        monkeypatch.setattr(image_router, "settings", _settings(60))

        image_router._serve_image_for_sensor("device-j", db_session, _request(), minio)

        state = db_session.execute(
            select(ActiveImageState).where(ActiveImageState.sensor_id == "device-j")
        ).scalar_one()

        assert abs((state.last_served_at - original_time).total_seconds()) < 1

    # -- fallback and error cases ---------------------------------------------

    def test_expired_content_falls_back_to_default(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When active image state is expired, the default template is served."""
        minio = _minio_stub(
            active_bytes=b"active-content",
            default_bytes=b"default-content",
        )

        db_session.add(
            ActiveImageState(
                sensor_id="device-k",
                expires_at=datetime(2024, 1, 1, tzinfo=UTC),
            )
        )
        db_session.commit()

        monkeypatch.setattr(image_router, "settings", _settings(60))

        response = image_router._serve_image_for_sensor(
            "device-k", db_session, _request(), minio
        )

        assert response.status_code == 200
        assert response.body == b"default-content"
        assert response.media_type == "image/png"

    def test_falls_back_to_default_when_no_active_image_in_minio(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the active image key is absent in MinIO, the default template is served."""
        minio = _minio_stub(active_bytes=None, default_bytes=b"default-fallback")
        monkeypatch.setattr(image_router, "settings", _settings(60))

        response = image_router._serve_image_for_sensor(
            "device-l", db_session, _request(), minio
        )

        assert response.status_code == 200
        assert response.body == b"default-fallback"

    def test_raises_not_found_when_no_image_at_all(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """NotFoundError is raised when neither active image nor default template exists."""
        minio = _minio_stub(active_bytes=None, default_bytes=None)
        monkeypatch.setattr(image_router, "settings", _settings(60))

        with pytest.raises(NotFoundError):
            image_router._serve_image_for_sensor(
                "device-m", db_session, _request(), minio
            )


# ---------------------------------------------------------------------------
# MCP get_eink_display_status (unchanged from previous suite)
# ---------------------------------------------------------------------------


class TestGetEinkDisplayStatus:
    @pytest.mark.asyncio
    async def test_expiry_status_uses_utc_aware_timestamps(
        self, db_session, db_factory, monkeypatch
    ) -> None:
        from backend.mcp import server as mcp_server

        db_session.add(
            ActiveImageState(
                sensor_id="display-1",
                expires_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            )
        )
        db_session.commit()

        monkeypatch.setattr(mcp_server._svc, "db_factory", db_factory)

        result = await mcp_server.get_eink_display_status(sensor_id="display-1")

        assert len(result) == 1
        assert result[0]["sensor_id"] == "display-1"
        assert result[0]["expired"] is True
