"""Regression tests for image expiry handling."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.mcp import server as mcp_server
from backend.models.image_state import ActiveImageState
from backend.routers import image as image_router


class TestServeImageForSensor:
    def test_expired_timestamp_falls_back_to_default(
        self, db_session, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        default_template = tmp_path / "default.png"
        default_template.write_bytes(b"default")

        active_image = tmp_path / "active.png"
        active_image.write_bytes(b"active")

        db_session.add(
            ActiveImageState(
                sensor_id="display-1",
                expires_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            )
        )
        db_session.commit()

        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    eink_renderer=SimpleNamespace(
                        get_active_image_path=lambda _sensor_id: active_image
                    )
                )
            )
        )
        monkeypatch.setattr(image_router, "_DEFAULT_TEMPLATE", default_template)

        response = image_router._serve_image_for_sensor("display-1", db_session, request)

        assert response.path == default_template


class TestGetEinkDisplayStatus:
    @pytest.mark.asyncio
    async def test_expiry_status_uses_utc_aware_timestamps(
        self, db_session, db_factory, monkeypatch
    ) -> None:
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
