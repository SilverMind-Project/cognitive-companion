"""Tests for the PWA TTS announcement notification channel."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.channels.builtin.announcement import PWATTSAnnouncementChannel
from backend.integrations.tts import AudioStream


@dataclass
class FakeServices:
    ws_manager: MagicMock = None
    tts_client: MagicMock = None


def _make_ws_manager(has_connections: bool = True) -> MagicMock:
    manager = AsyncMock()
    manager.has_connections = has_connections
    manager.broadcast = AsyncMock()
    manager.broadcast_bytes = AsyncMock()
    return manager


def _make_tts_client(configured: bool = True, stream_result=None) -> MagicMock:
    client = MagicMock()
    client.configured = configured
    client.stream_audio = AsyncMock(return_value=stream_result)
    return client


async def _fake_chunks():
    yield b"\x00" * 4096
    yield b"\x00" * 2048


class TestPWATTSAnnouncementMetadata:
    def test_channel_name(self):
        meta = PWATTSAnnouncementChannel.metadata()
        assert meta.channel_name == "pwa_tts_announcement"

    def test_display_name(self):
        meta = PWATTSAnnouncementChannel.metadata()
        assert meta.display_name == "PWA TTS Announcement"

    def test_has_config_schema(self):
        meta = PWATTSAnnouncementChannel.metadata()
        assert "mode" in meta.config_schema["properties"]
        assert "audio_url" in meta.config_schema["properties"]
        assert "tts_language" in meta.config_schema["properties"]
        assert "tts_style" in meta.config_schema["properties"]


class TestStreamMode:
    @pytest.mark.asyncio
    async def test_streams_pcm_chunks(self):
        ws = _make_ws_manager()
        tts = _make_tts_client(stream_result=AudioStream(chunks=_fake_chunks(), sample_rate=24000))
        services = FakeServices(ws_manager=ws, tts_client=tts)

        channel = PWATTSAnnouncementChannel()
        result = await channel.send(
            message="Hello",
            alert_level="reminder",
            room_name="kitchen",
            services=services,
        )

        assert result is True

        # Verify stream_start broadcast
        start_call = ws.broadcast.call_args_list[0]
        assert start_call[0][0]["type"] == "pwa_tts_announcement"
        assert start_call[0][0]["subtype"] == "stream_start"
        assert start_call[0][0]["sample_rate"] == 24000

        # Verify binary chunks sent
        assert ws.broadcast_bytes.call_count == 2

        # Verify stream_end broadcast
        end_call = ws.broadcast.call_args_list[1]
        assert end_call[0][0]["type"] == "pwa_tts_announcement"
        assert end_call[0][0]["subtype"] == "stream_end"

    @pytest.mark.asyncio
    async def test_passes_tts_language_and_style(self):
        ws = _make_ws_manager()
        tts = _make_tts_client(stream_result=AudioStream(chunks=_fake_chunks(), sample_rate=16000))
        services = FakeServices(ws_manager=ws, tts_client=tts)

        channel = PWATTSAnnouncementChannel()
        await channel.send(
            message="Test",
            alert_level="info",
            room_name="room",
            config={"tts_language": "ta", "tts_style": "clear"},
            services=services,
        )

        tts.stream_audio.assert_awaited_once_with("Test", language="ta", style="clear")

    @pytest.mark.asyncio
    async def test_fails_without_tts_client(self):
        ws = _make_ws_manager()
        services = FakeServices(ws_manager=ws, tts_client=None)

        channel = PWATTSAnnouncementChannel()
        result = await channel.send(
            message="Hello",
            alert_level="info",
            room_name="room",
            services=services,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_fails_when_tts_not_configured(self):
        ws = _make_ws_manager()
        tts = _make_tts_client(configured=False)
        services = FakeServices(ws_manager=ws, tts_client=tts)

        channel = PWATTSAnnouncementChannel()
        result = await channel.send(
            message="Hello",
            alert_level="info",
            room_name="room",
            services=services,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_fails_when_stream_returns_none(self):
        ws = _make_ws_manager()
        tts = _make_tts_client(stream_result=None)
        services = FakeServices(ws_manager=ws, tts_client=tts)

        channel = PWATTSAnnouncementChannel()
        result = await channel.send(
            message="Hello",
            alert_level="info",
            room_name="room",
            services=services,
        )
        assert result is False


class TestFileMode:
    @pytest.mark.asyncio
    async def test_broadcasts_audio_url(self):
        ws = _make_ws_manager()
        services = FakeServices(ws_manager=ws)

        channel = PWATTSAnnouncementChannel()
        result = await channel.send(
            message="Alert",
            alert_level="warning",
            room_name="bedroom",
            config={"mode": "file", "audio_url": "https://minio/tts/abc.mp3"},
            services=services,
        )

        assert result is True
        call = ws.broadcast.call_args_list[0]
        payload = call[0][0]
        assert payload["type"] == "pwa_tts_announcement"
        assert payload["subtype"] == "audio_url"
        assert payload["url"] == "https://minio/tts/abc.mp3"

    @pytest.mark.asyncio
    async def test_fails_without_audio_url(self):
        ws = _make_ws_manager()
        services = FakeServices(ws_manager=ws)

        channel = PWATTSAnnouncementChannel()
        result = await channel.send(
            message="Alert",
            alert_level="info",
            room_name="room",
            config={"mode": "file"},
            services=services,
        )
        assert result is False


class TestNoConnections:
    @pytest.mark.asyncio
    async def test_fails_without_ws_connections(self):
        ws = _make_ws_manager(has_connections=False)
        services = FakeServices(ws_manager=ws)

        channel = PWATTSAnnouncementChannel()
        result = await channel.send(
            message="Hello",
            alert_level="info",
            room_name="room",
            services=services,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_fails_without_ws_manager(self):
        services = FakeServices(ws_manager=None)
        channel = PWATTSAnnouncementChannel()
        result = await channel.send(
            message="Hello",
            alert_level="info",
            room_name="room",
            services=services,
        )
        assert result is False
