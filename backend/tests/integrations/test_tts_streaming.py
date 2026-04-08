"""Tests for TTSClient streaming audio support."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.integrations.tts import AudioStream, TTSClient


class TestAudioStream:
    @pytest.mark.asyncio
    async def test_iterates_chunks(self):
        async def _gen():
            yield b"chunk1"
            yield b"chunk2"

        stream = AudioStream(chunks=_gen(), sample_rate=24000)
        collected = []
        async for chunk in stream.chunks:
            collected.append(chunk)
        assert collected == [b"chunk1", b"chunk2"]


class TestTTSClientStreamAudio:
    @pytest.mark.asyncio
    async def test_returns_none_when_not_configured(self):
        client = TTSClient()
        client.base_url = ""
        result = await client.stream_audio("hello")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_audio_stream_on_success(self):
        """Test with mocked httpx streaming response."""

        async def _fake_aiter(chunk_size):
            yield b"\x00" * 4096
            yield b"\x00" * 2048

        mock_response = AsyncMock()
        mock_response.headers = {"X-Sample-Rate": "24000"}
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_bytes = _fake_aiter
        mock_response.aclose = AsyncMock()

        mock_client = AsyncMock()
        mock_client.build_request = MagicMock(return_value=MagicMock())
        mock_client.send = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()

        with patch("backend.integrations.tts.httpx.AsyncClient", return_value=mock_client):
            client = TTSClient()
            client.base_url = "http://tts:8200/v1"
            client.default_model = "svara"
            client.default_voice = "speaker_0"
            client.default_speed = 1.0
            client.default_language = None
            client.default_style = None

            result = await client.stream_audio("hello")

        assert result is not None
        assert isinstance(result, AudioStream)
        assert result.sample_rate == 24000

        # Consume chunks
        chunks = []
        async for chunk in result.chunks:
            chunks.append(chunk)
        assert len(chunks) == 2

    @pytest.mark.asyncio
    async def test_returns_none_on_http_error(self):
        """Test error handling when the TTS service returns an error."""
        mock_client = AsyncMock()
        mock_client.build_request = MagicMock(return_value=MagicMock())
        mock_client.send = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.aclose = AsyncMock()

        with patch("backend.integrations.tts.httpx.AsyncClient", return_value=mock_client):
            client = TTSClient()
            client.base_url = "http://tts:8200/v1"
            client.default_model = "svara"
            client.default_voice = "speaker_0"
            client.default_speed = 1.0
            client.default_language = None
            client.default_style = None

            result = await client.stream_audio("hello")
        assert result is None
