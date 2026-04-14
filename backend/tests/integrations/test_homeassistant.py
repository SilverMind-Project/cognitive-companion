"""Tests for the HomeAssistantClient integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.integrations.homeassistant import HomeAssistantClient

_HTTPX_TARGET = "backend.integrations.homeassistant.httpx.AsyncClient"


def _make_client(configured: bool = True) -> HomeAssistantClient:
    """Build a HomeAssistantClient without reading settings."""
    client = HomeAssistantClient.__new__(HomeAssistantClient)
    client.base_url = "http://ha.local:8123" if configured else ""
    client.token = "test-token" if configured else ""
    client._headers = {
        "Authorization": f"Bearer {client.token}",
        "Content-Type": "application/json",
    }
    return client


def _make_httpx_client() -> MagicMock:
    """Return a mock httpx.AsyncClient usable as an async context manager."""
    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)
    mock_http.post = AsyncMock(return_value=MagicMock(raise_for_status=MagicMock()))
    mock_http.get = AsyncMock(return_value=MagicMock(raise_for_status=MagicMock()))
    return mock_http


class TestConfigured:
    def test_configured_when_url_and_token_set(self):
        client = _make_client(configured=True)
        assert client.configured is True

    def test_not_configured_when_url_empty(self):
        client = _make_client(configured=False)
        assert client.configured is False


class TestCallService:
    @pytest.mark.asyncio
    async def test_posts_to_correct_url(self):
        client = _make_client()
        mock_http = _make_httpx_client()

        with patch(_HTTPX_TARGET, return_value=mock_http):
            await client._call_service("media_player", "turn_on", {"entity_id": "mp.speaker"})

        mock_http.post.assert_awaited_once_with(
            "http://ha.local:8123/api/services/media_player/turn_on",
            headers=client._headers,
            json={"entity_id": "mp.speaker"},
        )

    @pytest.mark.asyncio
    async def test_returns_early_when_not_configured(self):
        client = _make_client(configured=False)

        with patch(_HTTPX_TARGET, return_value=_make_httpx_client()) as mock_cls:
            await client._call_service("media_player", "turn_on", {})

        mock_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_swallows_http_exception(self):
        """Exceptions must not propagate to callers."""
        client = _make_client()
        mock_http = _make_httpx_client()
        mock_http.post.side_effect = Exception("connection refused")

        with patch(_HTTPX_TARGET, return_value=mock_http):
            # Should not raise
            await client._call_service("media_player", "turn_on", {})


class TestTurnOnMediaPlayer:
    @pytest.mark.asyncio
    async def test_delegates_to_call_service(self):
        client = _make_client()

        with patch.object(client, "_call_service", new_callable=AsyncMock) as mock_svc:
            await client.turn_on_media_player("media_player.kitchen_speaker")

        mock_svc.assert_awaited_once_with(
            "media_player",
            "turn_on",
            {"entity_id": "media_player.kitchen_speaker"},
        )

    @pytest.mark.asyncio
    async def test_propagates_entity_id(self):
        client = _make_client()

        with patch.object(client, "_call_service", new_callable=AsyncMock) as mock_svc:
            await client.turn_on_media_player("media_player.living_room_speaker")

        _, _, data = mock_svc.call_args.args
        assert data == {"entity_id": "media_player.living_room_speaker"}

    @pytest.mark.asyncio
    async def test_not_configured_skips_http(self):
        client = _make_client(configured=False)

        with patch(_HTTPX_TARGET, return_value=_make_httpx_client()) as mock_cls:
            await client.turn_on_media_player("media_player.speaker")

        mock_cls.assert_not_called()


class TestPlayAudio:
    @pytest.mark.asyncio
    async def test_posts_play_media(self):
        client = _make_client()
        mock_http = _make_httpx_client()

        with patch(_HTTPX_TARGET, return_value=mock_http):
            await client.play_audio("https://minio/tts.mp3", "media_player.kitchen_speaker")

        mock_http.post.assert_awaited_once_with(
            "http://ha.local:8123/api/services/media_player/play_media",
            headers=client._headers,
            json={
                "entity_id": "media_player.kitchen_speaker",
                "media_content_id": "https://minio/tts.mp3",
                "media_content_type": "music",
            },
        )

    @pytest.mark.asyncio
    async def test_uses_default_entity_id(self):
        client = _make_client()
        mock_http = _make_httpx_client()

        with patch(_HTTPX_TARGET, return_value=mock_http):
            await client.play_audio("https://minio/tts.mp3")

        _, kwargs = mock_http.post.call_args
        assert kwargs["json"]["entity_id"] == "media_player.living_room_speaker"

    @pytest.mark.asyncio
    async def test_returns_early_when_not_configured(self):
        client = _make_client(configured=False)

        with patch(_HTTPX_TARGET, return_value=_make_httpx_client()) as mock_cls:
            await client.play_audio("https://minio/tts.mp3")

        mock_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_swallows_http_exception(self):
        client = _make_client()
        mock_http = _make_httpx_client()
        mock_http.post.side_effect = Exception("timeout")

        with patch(_HTTPX_TARGET, return_value=mock_http):
            # Should not raise
            await client.play_audio("https://minio/tts.mp3", "media_player.speaker")
