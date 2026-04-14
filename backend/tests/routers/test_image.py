"""Tests for per-device image serving with refresh suppression.

Strategy
--------
``_serve_image_for_sensor`` is a pure function of its arguments (session, tmp
files, a lightweight request stub).  Every scenario is exercised by injecting
known image bytes, recording a matching or mismatching ``ActiveImageState``,
and asserting on the HTTP response returned.

The ``db_session`` fixture is function-scoped (fresh in-memory SQLite per
test), so commits inside the helper do not bleed across tests.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.core.config import Settings
from backend.core.exceptions import NotFoundError
from backend.models.image_state import ActiveImageState
from backend.routers import image as image_router

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _request(active_path):
    """Minimal request stub whose eink_renderer always returns *active_path*."""
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                eink_renderer=SimpleNamespace(
                    get_active_image_path=lambda _: active_path,
                )
            )
        )
    )


def _settings(refresh_window_minutes: int) -> Settings:
    return Settings.from_dict({"image": {"refresh_window_minutes": refresh_window_minutes}})


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Core serving behaviour
# ---------------------------------------------------------------------------


class TestServeImageForSensor:
    # -- baseline cases -------------------------------------------------------

    def test_first_poll_serves_image(
        self, db_session, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """First request for a device (no prior state) always delivers the image."""
        active = tmp_path / "active.png"
        active.write_bytes(b"first-frame")

        monkeypatch.setattr(image_router, "_DEFAULT_TEMPLATE", tmp_path / "default.png")
        monkeypatch.setattr(image_router, "settings", _settings(60))

        response = image_router._serve_image_for_sensor("device-a", db_session, _request(active))

        assert response.status_code == 200
        assert response.body == b"first-frame"
        assert response.media_type == "image/png"

    def test_first_poll_creates_delivery_state(
        self, db_session, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Serving the image records last_served_hash and last_served_at."""
        active = tmp_path / "active.png"
        active.write_bytes(b"img-bytes")

        monkeypatch.setattr(image_router, "_DEFAULT_TEMPLATE", tmp_path / "default.png")
        monkeypatch.setattr(image_router, "settings", _settings(60))

        before = datetime.now(UTC)
        image_router._serve_image_for_sensor("device-b", db_session, _request(active))

        state = db_session.execute(
            select(ActiveImageState).where(ActiveImageState.sensor_id == "device-b")
        ).scalar_one()

        assert state.last_served_hash == _sha256(b"img-bytes")
        assert state.last_served_at is not None
        assert state.last_served_at >= before

    # -- refresh-suppression: no refresh needed -------------------------------

    def test_returns_204_when_content_unchanged_within_window(
        self, db_session, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """204 No Content is returned when the image has not changed and the
        forced-refresh window has not elapsed."""
        active = tmp_path / "active.png"
        active.write_bytes(b"stable-frame")

        db_session.add(
            ActiveImageState(
                sensor_id="device-c",
                last_served_hash=_sha256(b"stable-frame"),
                last_served_at=datetime.now(UTC) - timedelta(minutes=30),
            )
        )
        db_session.commit()

        monkeypatch.setattr(image_router, "_DEFAULT_TEMPLATE", tmp_path / "default.png")
        monkeypatch.setattr(image_router, "settings", _settings(60))

        response = image_router._serve_image_for_sensor("device-c", db_session, _request(active))

        assert response.status_code == 204

    def test_204_has_empty_body(
        self, db_session, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """The 204 response carries no body, so the display driver has nothing to render."""
        active = tmp_path / "active.png"
        active.write_bytes(b"same-content")

        db_session.add(
            ActiveImageState(
                sensor_id="device-d",
                last_served_hash=_sha256(b"same-content"),
                last_served_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )
        db_session.commit()

        monkeypatch.setattr(image_router, "_DEFAULT_TEMPLATE", tmp_path / "default.png")
        monkeypatch.setattr(image_router, "settings", _settings(60))

        response = image_router._serve_image_for_sensor("device-d", db_session, _request(active))

        assert not response.body

    # -- refresh-suppression: refresh required --------------------------------

    def test_serves_image_when_content_changed(
        self, db_session, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """A new image is always served even if the window has not elapsed."""
        active = tmp_path / "active.png"
        active.write_bytes(b"new-frame")

        db_session.add(
            ActiveImageState(
                sensor_id="device-e",
                last_served_hash=_sha256(b"old-frame"),
                last_served_at=datetime.now(UTC) - timedelta(minutes=5),
            )
        )
        db_session.commit()

        monkeypatch.setattr(image_router, "_DEFAULT_TEMPLATE", tmp_path / "default.png")
        monkeypatch.setattr(image_router, "settings", _settings(60))

        response = image_router._serve_image_for_sensor("device-e", db_session, _request(active))

        assert response.status_code == 200
        assert response.body == b"new-frame"

    def test_serves_image_when_window_elapsed(
        self, db_session, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Even unchanged content is re-delivered once the refresh window expires."""
        active = tmp_path / "active.png"
        active.write_bytes(b"periodic-frame")

        db_session.add(
            ActiveImageState(
                sensor_id="device-f",
                last_served_hash=_sha256(b"periodic-frame"),
                last_served_at=datetime.now(UTC) - timedelta(minutes=90),
            )
        )
        db_session.commit()

        monkeypatch.setattr(image_router, "_DEFAULT_TEMPLATE", tmp_path / "default.png")
        monkeypatch.setattr(image_router, "settings", _settings(60))

        response = image_router._serve_image_for_sensor("device-f", db_session, _request(active))

        assert response.status_code == 200
        assert response.body == b"periodic-frame"

    def test_window_zero_disables_suppression(
        self, db_session, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """refresh_window_minutes=0 always delivers the image regardless of hash."""
        active = tmp_path / "active.png"
        active.write_bytes(b"always-refresh")

        db_session.add(
            ActiveImageState(
                sensor_id="device-g",
                last_served_hash=_sha256(b"always-refresh"),
                last_served_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        db_session.commit()

        monkeypatch.setattr(image_router, "_DEFAULT_TEMPLATE", tmp_path / "default.png")
        monkeypatch.setattr(image_router, "settings", _settings(0))

        response = image_router._serve_image_for_sensor("device-g", db_session, _request(active))

        assert response.status_code == 200

    def test_serves_image_when_last_served_at_is_none(
        self, db_session, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """State exists with a matching hash but no last_served_at triggers a refresh."""
        active = tmp_path / "active.png"
        active.write_bytes(b"needs-refresh")

        db_session.add(
            ActiveImageState(
                sensor_id="device-h",
                last_served_hash=_sha256(b"needs-refresh"),
                last_served_at=None,
            )
        )
        db_session.commit()

        monkeypatch.setattr(image_router, "_DEFAULT_TEMPLATE", tmp_path / "default.png")
        monkeypatch.setattr(image_router, "settings", _settings(60))

        response = image_router._serve_image_for_sensor("device-h", db_session, _request(active))

        assert response.status_code == 200

    # -- state update on delivery ---------------------------------------------

    def test_delivery_state_updated_after_serve(
        self, db_session, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """last_served_hash and last_served_at are updated when a new image is sent."""
        active = tmp_path / "active.png"
        active.write_bytes(b"updated-img")

        db_session.add(
            ActiveImageState(
                sensor_id="device-i",
                last_served_hash=_sha256(b"old-img"),
                last_served_at=datetime(2024, 1, 1, tzinfo=UTC),
            )
        )
        db_session.commit()

        before = datetime.now(UTC)

        monkeypatch.setattr(image_router, "_DEFAULT_TEMPLATE", tmp_path / "default.png")
        monkeypatch.setattr(image_router, "settings", _settings(60))

        image_router._serve_image_for_sensor("device-i", db_session, _request(active))

        state = db_session.execute(
            select(ActiveImageState).where(ActiveImageState.sensor_id == "device-i")
        ).scalar_one()

        assert state.last_served_hash == _sha256(b"updated-img")
        assert state.last_served_at >= before

    def test_no_state_update_on_204(
        self, db_session, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """When 204 is returned, the stored last_served_at is not advanced."""
        active = tmp_path / "active.png"
        active.write_bytes(b"unchanged")

        original_time = datetime.now(UTC) - timedelta(minutes=10)
        db_session.add(
            ActiveImageState(
                sensor_id="device-j",
                last_served_hash=_sha256(b"unchanged"),
                last_served_at=original_time,
            )
        )
        db_session.commit()

        monkeypatch.setattr(image_router, "_DEFAULT_TEMPLATE", tmp_path / "default.png")
        monkeypatch.setattr(image_router, "settings", _settings(60))

        image_router._serve_image_for_sensor("device-j", db_session, _request(active))

        state = db_session.execute(
            select(ActiveImageState).where(ActiveImageState.sensor_id == "device-j")
        ).scalar_one()

        # last_served_at must not change when the response was a no-op 204.
        assert abs((state.last_served_at - original_time).total_seconds()) < 1

    # -- fallback and error cases ---------------------------------------------

    def test_expired_content_falls_back_to_default(
        self, db_session, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """When active image state is expired, the default template is served."""
        default = tmp_path / "default.png"
        default.write_bytes(b"default-content")
        active = tmp_path / "active.png"
        active.write_bytes(b"active-content")

        db_session.add(
            ActiveImageState(
                sensor_id="device-k",
                expires_at=datetime(2024, 1, 1, tzinfo=UTC),
            )
        )
        db_session.commit()

        monkeypatch.setattr(image_router, "_DEFAULT_TEMPLATE", default)
        monkeypatch.setattr(image_router, "settings", _settings(60))

        response = image_router._serve_image_for_sensor("device-k", db_session, _request(active))

        assert response.status_code == 200
        assert response.body == b"default-content"
        assert response.media_type == "image/png"

    def test_falls_back_to_default_when_no_active_file(
        self, db_session, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """When the active image file is absent, the default template is served."""
        default = tmp_path / "default.png"
        default.write_bytes(b"default-fallback")
        missing_active = tmp_path / "active_missing.png"  # deliberately absent

        monkeypatch.setattr(image_router, "_DEFAULT_TEMPLATE", default)
        monkeypatch.setattr(image_router, "settings", _settings(60))

        response = image_router._serve_image_for_sensor(
            "device-l", db_session, _request(missing_active)
        )

        assert response.status_code == 200
        assert response.body == b"default-fallback"

    def test_raises_not_found_when_no_image_at_all(
        self, db_session, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """NotFoundError is raised when neither active image nor default template exists."""
        monkeypatch.setattr(image_router, "_DEFAULT_TEMPLATE", tmp_path / "missing.png")
        monkeypatch.setattr(image_router, "settings", _settings(60))

        with pytest.raises(NotFoundError):
            image_router._serve_image_for_sensor(
                "device-m",
                db_session,
                _request(tmp_path / "also_missing.png"),
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
