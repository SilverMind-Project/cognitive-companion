"""Tests for the PWA popup text notification channel."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.channels.builtin.websocket import PWAPopupTextChannel


@dataclass
class FakeServices:
    ws_manager: MagicMock = None


def _make_ws_manager() -> MagicMock:
    manager = AsyncMock()
    manager.broadcast = AsyncMock()
    return manager


class TestPWAPopupTextMetadata:
    def test_channel_name(self):
        meta = PWAPopupTextChannel.metadata()
        assert meta.channel_name == "pwa_popup_text"

    def test_display_name(self):
        meta = PWAPopupTextChannel.metadata()
        assert meta.display_name == "PWA Popup Text"


class TestPWAPopupTextSend:
    @pytest.mark.asyncio
    async def test_broadcasts_alert_payload(self):
        ws = _make_ws_manager()
        services = FakeServices(ws_manager=ws)

        channel = PWAPopupTextChannel()
        result = await channel.send(
            message="Kitchen alert",
            alert_level="warning",
            room_name="kitchen",
            services=services,
        )

        assert result is True
        call = ws.broadcast.call_args_list[0]
        payload = call[0][0]
        assert payload["type"] == "warning"
        assert payload["message"] == "Kitchen alert"
        assert payload["room"] == "kitchen"
        assert "image_url" not in payload

    @pytest.mark.asyncio
    async def test_includes_image_url_when_provided(self):
        ws = _make_ws_manager()
        services = FakeServices(ws_manager=ws)

        channel = PWAPopupTextChannel()
        await channel.send(
            message="Alert",
            alert_level="emergency",
            room_name="bedroom",
            image_url="https://minio/image.jpg",
            services=services,
        )

        call = ws.broadcast.call_args_list[0]
        payload = call[0][0]
        assert payload["image_url"] == "https://minio/image.jpg"

    @pytest.mark.asyncio
    async def test_fails_without_ws_manager(self):
        services = FakeServices(ws_manager=None)

        channel = PWAPopupTextChannel()
        result = await channel.send(
            message="Test", alert_level="info", room_name="room", services=services,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_fails_on_broadcast_error(self):
        ws = _make_ws_manager()
        ws.broadcast.side_effect = RuntimeError("connection closed")
        services = FakeServices(ws_manager=ws)

        channel = PWAPopupTextChannel()
        result = await channel.send(
            message="Test", alert_level="info", room_name="room", services=services,
        )
        assert result is False
