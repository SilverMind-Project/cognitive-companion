"""Tests for the HA Speaker TTS notification channel."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.channels.builtin.tts import HASpeakerTTSChannel


@dataclass
class FakeServices:
    tts_client: MagicMock = None
    minio_client: MagicMock = None
    ha_client: MagicMock = None


def _make_tts_client(
    configured: bool = True, upload_url: str | None = "https://minio/tts.mp3"
) -> MagicMock:
    client = MagicMock()
    client.configured = configured
    client.generate_and_upload = AsyncMock(return_value=upload_url)
    client.generate_audio = AsyncMock(return_value=b"\x00" * 100)
    return client


def _make_ha_client(configured: bool = True) -> MagicMock:
    client = MagicMock()
    client.configured = configured
    client.play_audio = AsyncMock()
    return client


class TestHASpeakerTTSMetadata:
    def test_channel_name(self):
        meta = HASpeakerTTSChannel.metadata()
        assert meta.channel_name == "ha_speaker_tts"

    def test_display_name(self):
        meta = HASpeakerTTSChannel.metadata()
        assert meta.display_name == "HA Speaker TTS"


class TestHASpeakerTTSSend:
    @pytest.mark.asyncio
    async def test_plays_via_ha_media_player(self):
        tts = _make_tts_client()
        ha = _make_ha_client()
        minio = MagicMock()
        services = FakeServices(tts_client=tts, minio_client=minio, ha_client=ha)

        channel = HASpeakerTTSChannel()
        result = await channel.send(
            message="Time for lunch",
            alert_level="reminder",
            room_name="kitchen",
            config={"ha_media_player": "media_player.kitchen_speaker"},
            services=services,
        )

        assert result is True
        tts.generate_and_upload.assert_awaited_once()
        ha.play_audio.assert_awaited_once_with(
            "https://minio/tts.mp3",
            "media_player.kitchen_speaker",
        )

    @pytest.mark.asyncio
    async def test_uses_default_media_player(self):
        tts = _make_tts_client()
        ha = _make_ha_client()
        minio = MagicMock()
        services = FakeServices(tts_client=tts, minio_client=minio, ha_client=ha)

        channel = HASpeakerTTSChannel()
        await channel.send(
            message="Hello",
            alert_level="info",
            room_name="room",
            services=services,
        )

        ha.play_audio.assert_awaited_once_with(
            "https://minio/tts.mp3",
            "media_player.living_room_speaker",
        )

    @pytest.mark.asyncio
    async def test_passes_language_and_style(self):
        tts = _make_tts_client()
        ha = _make_ha_client()
        minio = MagicMock()
        services = FakeServices(tts_client=tts, minio_client=minio, ha_client=ha)

        channel = HASpeakerTTSChannel()
        await channel.send(
            message="Hello",
            alert_level="info",
            room_name="room",
            config={"tts_language": "ta", "tts_style": "formal"},
            services=services,
        )

        tts.generate_and_upload.assert_awaited_once_with(
            "Hello",
            minio,
            language="ta",
            style="formal",
        )

    @pytest.mark.asyncio
    async def test_fails_when_tts_not_configured(self):
        tts = _make_tts_client(configured=False)
        services = FakeServices(tts_client=tts)

        channel = HASpeakerTTSChannel()
        result = await channel.send(
            message="Hello",
            alert_level="info",
            room_name="room",
            services=services,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_fails_when_upload_returns_none(self):
        tts = _make_tts_client(upload_url=None)
        ha = _make_ha_client()
        minio = MagicMock()
        services = FakeServices(tts_client=tts, minio_client=minio, ha_client=ha)

        channel = HASpeakerTTSChannel()
        result = await channel.send(
            message="Hello",
            alert_level="info",
            room_name="room",
            services=services,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_local_fallback_without_ha(self):
        """When HA is not configured, generate audio locally."""
        tts = _make_tts_client()
        services = FakeServices(tts_client=tts, minio_client=None, ha_client=None)

        channel = HASpeakerTTSChannel()
        result = await channel.send(
            message="Hello",
            alert_level="info",
            room_name="room",
            services=services,
        )
        assert result is True
        tts.generate_audio.assert_awaited_once()
