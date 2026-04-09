"""Tests for the PWA Realtime AI notification channel."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.channels.builtin.realtime_voice import PWARealtimeAIChannel


@dataclass
class FakeServices:
    ws_manager: MagicMock = None


def _make_ws_manager() -> MagicMock:
    manager = AsyncMock()
    manager.send_backend_task = AsyncMock()
    return manager


class TestPWARealtimeAIMetadata:
    def test_channel_name(self):
        meta = PWARealtimeAIChannel.metadata()
        assert meta.channel_name == "pwa_realtime_ai"

    def test_display_name(self):
        meta = PWARealtimeAIChannel.metadata()
        assert meta.display_name == "PWA Realtime AI"


class TestPWARealtimeAISend:
    @pytest.mark.asyncio
    async def test_queues_prompt(self):
        ws = _make_ws_manager()
        services = FakeServices(ws_manager=ws)

        channel = PWARealtimeAIChannel()
        result = await channel.send(
            message="Have you taken your medication?",
            alert_level="reminder",
            room_name="bedroom",
            services=services,
        )

        assert result is True
        ws.send_backend_task.assert_awaited_once()
        call_kwargs = ws.send_backend_task.call_args[1]
        assert call_kwargs["prompt"] == "Have you taken your medication?"

    @pytest.mark.asyncio
    async def test_fails_without_ws_manager(self):
        services = FakeServices(ws_manager=None)

        channel = PWARealtimeAIChannel()
        result = await channel.send(
            message="Test", alert_level="info", room_name="room", services=services,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_fails_on_send_error(self):
        ws = _make_ws_manager()
        ws.send_backend_task.side_effect = RuntimeError("no session")
        services = FakeServices(ws_manager=ws)

        channel = PWARealtimeAIChannel()
        result = await channel.send(
            message="Test", alert_level="info", room_name="room", services=services,
        )
        assert result is False
