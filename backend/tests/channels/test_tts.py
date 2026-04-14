"""Tests for the HA Speaker TTS notification channel."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.channels.builtin.tts import (
    _DEFAULT_MEDIA_PLAYER,
    _MEDIA_PLAYER_WAKE_DELAY,
    HASpeakerTTSChannel,
)

_SLEEP_TARGET = "backend.channels.builtin.tts.asyncio.sleep"


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
    client.turn_on_media_player = AsyncMock()
    client.play_audio = AsyncMock()
    return client


@pytest.fixture(autouse=True)
def _instant_sleep():
    """Patch asyncio.sleep so tests do not block for the wake-up delay."""
    with patch(_SLEEP_TARGET, new_callable=AsyncMock):
        yield


class TestHASpeakerTTSMetadata:
    def test_channel_name(self):
        assert HASpeakerTTSChannel.metadata().channel_name == "ha_speaker_tts"

    def test_display_name(self):
        assert HASpeakerTTSChannel.metadata().display_name == "HA Speaker TTS"

    def test_config_schema_has_media_player_property(self):
        props = HASpeakerTTSChannel.metadata().config_schema["properties"]
        assert "ha_media_player" in props

    def test_default_media_player_constant(self):
        assert _DEFAULT_MEDIA_PLAYER == "media_player.living_room_speaker"

    def test_wake_delay_constant_is_positive(self):
        assert _MEDIA_PLAYER_WAKE_DELAY > 0


class TestHASpeakerTTSSend:
    @pytest.mark.asyncio
    async def test_plays_via_ha_media_player(self):
        tts = _make_tts_client()
        ha = _make_ha_client()
        services = FakeServices(tts_client=tts, minio_client=MagicMock(), ha_client=ha)

        result = await HASpeakerTTSChannel().send(
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
        services = FakeServices(tts_client=tts, minio_client=MagicMock(), ha_client=ha)

        await HASpeakerTTSChannel().send(
            message="Hello",
            alert_level="info",
            room_name="room",
            services=services,
        )

        ha.play_audio.assert_awaited_once_with(
            "https://minio/tts.mp3",
            _DEFAULT_MEDIA_PLAYER,
        )

    @pytest.mark.asyncio
    async def test_passes_language_and_style(self):
        tts = _make_tts_client()
        ha = _make_ha_client()
        minio = MagicMock()
        services = FakeServices(tts_client=tts, minio_client=minio, ha_client=ha)

        await HASpeakerTTSChannel().send(
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

        result = await HASpeakerTTSChannel().send(
            message="Hello",
            alert_level="info",
            room_name="room",
            services=services,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_fails_when_tts_client_missing(self):
        services = FakeServices(tts_client=None)

        result = await HASpeakerTTSChannel().send(
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
        services = FakeServices(tts_client=tts, minio_client=MagicMock(), ha_client=ha)

        result = await HASpeakerTTSChannel().send(
            message="Hello",
            alert_level="info",
            room_name="room",
            services=services,
        )

        assert result is False
        ha.turn_on_media_player.assert_not_awaited()
        ha.play_audio.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_local_fallback_without_ha(self):
        """When HA / MinIO are absent, generate audio locally and return True."""
        tts = _make_tts_client()
        services = FakeServices(tts_client=tts, minio_client=None, ha_client=None)

        result = await HASpeakerTTSChannel().send(
            message="Hello",
            alert_level="info",
            room_name="room",
            services=services,
        )

        assert result is True
        tts.generate_audio.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_local_fallback_when_ha_not_configured(self):
        """Falls back to local generation when ha_client is present but unconfigured."""
        tts = _make_tts_client()
        ha = _make_ha_client(configured=False)
        services = FakeServices(tts_client=tts, minio_client=MagicMock(), ha_client=ha)

        result = await HASpeakerTTSChannel().send(
            message="Hello",
            alert_level="info",
            room_name="room",
            services=services,
        )

        assert result is True
        tts.generate_audio.assert_awaited_once()
        ha.turn_on_media_player.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_local_fallback_returns_false_when_audio_none(self):
        tts = _make_tts_client()
        tts.generate_audio = AsyncMock(return_value=None)
        services = FakeServices(tts_client=tts, minio_client=None, ha_client=None)

        result = await HASpeakerTTSChannel().send(
            message="Hello",
            alert_level="info",
            room_name="room",
            services=services,
        )

        assert result is False


class TestMediaPlayerWakeUp:
    """turn_on_media_player must be called before play_audio on the happy path."""

    @pytest.mark.asyncio
    async def test_wakes_media_player_before_playing(self):
        tts = _make_tts_client()
        ha = _make_ha_client()
        services = FakeServices(tts_client=tts, minio_client=MagicMock(), ha_client=ha)

        await HASpeakerTTSChannel().send(
            message="Lunch is ready",
            alert_level="reminder",
            room_name="kitchen",
            config={"ha_media_player": "media_player.kitchen_speaker"},
            services=services,
        )

        ha.turn_on_media_player.assert_awaited_once_with("media_player.kitchen_speaker")

    @pytest.mark.asyncio
    async def test_wake_uses_default_entity_when_no_config(self):
        tts = _make_tts_client()
        ha = _make_ha_client()
        services = FakeServices(tts_client=tts, minio_client=MagicMock(), ha_client=ha)

        await HASpeakerTTSChannel().send(
            message="Hello",
            alert_level="info",
            room_name="room",
            services=services,
        )

        ha.turn_on_media_player.assert_awaited_once_with(_DEFAULT_MEDIA_PLAYER)

    @pytest.mark.asyncio
    async def test_sleep_called_between_wake_and_play(self):
        """Verify the wake-up pause is inserted between turn_on and play_audio."""
        tts = _make_tts_client()
        ha = _make_ha_client()
        services = FakeServices(tts_client=tts, minio_client=MagicMock(), ha_client=ha)

        call_order: list[str] = []
        ha.turn_on_media_player.side_effect = lambda *_: call_order.append("turn_on")
        ha.play_audio.side_effect = lambda *_: call_order.append("play_audio")

        with patch(_SLEEP_TARGET, new_callable=AsyncMock) as mock_sleep:
            mock_sleep.side_effect = lambda *_: call_order.append("sleep")
            await HASpeakerTTSChannel().send(
                message="Hello",
                alert_level="info",
                room_name="room",
                services=services,
            )

        assert call_order == ["turn_on", "sleep", "play_audio"]
        mock_sleep.assert_awaited_once_with(_MEDIA_PLAYER_WAKE_DELAY)

    @pytest.mark.asyncio
    async def test_no_wake_call_in_local_fallback(self):
        """Local-only path must not touch ha_client at all."""
        tts = _make_tts_client()
        ha = _make_ha_client()
        # No minio → local fallback path
        services = FakeServices(tts_client=tts, minio_client=None, ha_client=ha)

        await HASpeakerTTSChannel().send(
            message="Hello",
            alert_level="info",
            room_name="room",
            services=services,
        )

        ha.turn_on_media_player.assert_not_awaited()
        ha.play_audio.assert_not_awaited()
