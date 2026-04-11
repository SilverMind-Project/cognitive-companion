"""Tests for LLM provider thinking support and sampling overrides."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.integrations.llm.base import strip_thinking
from backend.integrations.llm.chain import LLMProviderChain, LLMProviderPool
from backend.integrations.llm.vllm import VLLMVisionProvider

# ---------------------------------------------------------------------------
# strip_thinking helper (now lives in base)
# ---------------------------------------------------------------------------


class TestStripThinking:
    def test_strips_think_block(self):
        raw = "<think>\nSome internal reasoning.\n</think>\nFinal answer."
        assert strip_thinking(raw) == "Final answer."

    def test_strips_multiline_think_block(self):
        raw = "<think>\nLine one.\nLine two.\n</think>\n\nFinal answer."
        assert strip_thinking(raw) == "Final answer."

    def test_no_think_block_unchanged(self):
        raw = "Plain response without thinking."
        assert strip_thinking(raw) == raw

    def test_strips_trailing_whitespace_after_block(self):
        raw = "<think>reasoning</think>   \n  Answer here."
        assert strip_thinking(raw) == "Answer here."

    def test_empty_string(self):
        assert strip_thinking("") == ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_vision_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return resp


def _patch_httpx(fake_post):
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=fake_post)
    return patch("httpx.AsyncClient", return_value=mock_client)


# ---------------------------------------------------------------------------
# VLLMVisionProvider — thinking=False (default)
# ---------------------------------------------------------------------------


class TestVLLMVisionProviderThinkingDisabled:
    @pytest.mark.asyncio
    async def test_no_thinking_instruction_in_payload(self):
        provider = VLLMVisionProvider(base_url="http://vllm:8000")
        captured: list[dict] = []

        async def _fake_post(url, json, **_):
            captured.append(json)
            return _make_vision_response("A cat.")

        with _patch_httpx(_fake_post):
            result = await provider.call(prompt="Describe this.", thinking=False)

        assert result == "A cat."
        texts = [c["text"] for c in captured[0]["messages"][0]["content"] if c["type"] == "text"]
        assert not any("</think>" in t for t in texts)

    @pytest.mark.asyncio
    async def test_returns_raw_response_without_stripping(self):
        provider = VLLMVisionProvider(base_url="http://vllm:8000")
        raw = "<think>reasoning</think>Answer"

        async def _fake_post(url, json, **_):
            return _make_vision_response(raw)

        with _patch_httpx(_fake_post):
            result = await provider.call(prompt="Describe.", thinking=False)

        assert result == raw


# ---------------------------------------------------------------------------
# VLLMVisionProvider — thinking=True
# ---------------------------------------------------------------------------


class TestVLLMVisionProviderThinkingEnabled:
    @pytest.mark.asyncio
    async def test_thinking_instruction_appended_to_content(self):
        provider = VLLMVisionProvider(base_url="http://vllm:8000")
        captured: list[dict] = []

        async def _fake_post(url, json, **_):
            captured.append(json)
            return _make_vision_response("Answer here.")

        with _patch_httpx(_fake_post):
            await provider.call(prompt="What do you see?", thinking=True)

        texts = [c["text"] for c in captured[0]["messages"][0]["content"] if c["type"] == "text"]
        assert texts[0] == "What do you see?"
        assert "</think>" in texts[1]

    @pytest.mark.asyncio
    async def test_think_block_stripped_from_response(self):
        provider = VLLMVisionProvider(base_url="http://vllm:8000")
        raw = "<think>\nInternal reasoning.\n</think>\nA dog is sitting."

        async def _fake_post(url, json, **_):
            return _make_vision_response(raw)

        with _patch_httpx(_fake_post):
            result = await provider.call(prompt="Describe.", thinking=True)

        assert result == "A dog is sitting."
        assert "<think>" not in result

    @pytest.mark.asyncio
    async def test_empty_content_with_thinking_returns_empty_string(self):
        provider = VLLMVisionProvider(base_url="http://vllm:8000")

        async def _fake_post(url, json, **_):
            return _make_vision_response(None)

        with _patch_httpx(_fake_post):
            result = await provider.call(prompt="Describe.", thinking=True)

        assert result == ""


# ---------------------------------------------------------------------------
# VLLMVisionProvider — sampling overrides
# ---------------------------------------------------------------------------


class TestVLLMVisionProviderSampling:
    @pytest.mark.asyncio
    async def test_instance_defaults_sent_in_payload(self):
        provider = VLLMVisionProvider(
            base_url="http://vllm:8000",
            temperature=0.7,
            top_p=0.9,
            max_tokens=1024,
        )
        captured: list[dict] = []

        async def _fake_post(url, json, **_):
            captured.append(json)
            return _make_vision_response("ok")

        with _patch_httpx(_fake_post):
            await provider.call(prompt="Q?")

        payload = captured[0]
        assert payload["temperature"] == 0.7
        assert payload["top_p"] == 0.9
        assert payload["max_tokens"] == 1024

    @pytest.mark.asyncio
    async def test_call_time_overrides_win(self):
        provider = VLLMVisionProvider(
            base_url="http://vllm:8000",
            temperature=0.7,
            top_p=0.9,
        )
        captured: list[dict] = []

        async def _fake_post(url, json, **_):
            captured.append(json)
            return _make_vision_response("ok")

        with _patch_httpx(_fake_post):
            await provider.call(prompt="Q?", temperature=0.1, top_p=0.5, max_tokens=512)

        payload = captured[0]
        assert payload["temperature"] == 0.1
        assert payload["top_p"] == 0.5
        assert payload["max_tokens"] == 512

    @pytest.mark.asyncio
    async def test_none_defaults_omit_fields_from_payload(self):
        """Provider with no defaults and no call-time overrides omits temp/top_p."""
        provider = VLLMVisionProvider(base_url="http://vllm:8000")  # temperature=None, top_p=None
        captured: list[dict] = []

        async def _fake_post(url, json, **_):
            captured.append(json)
            return _make_vision_response("ok")

        with _patch_httpx(_fake_post):
            await provider.call(prompt="Q?")

        payload = captured[0]
        assert "temperature" not in payload
        assert "top_p" not in payload


# ---------------------------------------------------------------------------
# LLMProviderChain — sampling params forwarded
# ---------------------------------------------------------------------------


class TestLLMProviderChainSampling:
    @pytest.mark.asyncio
    async def test_sampling_overrides_forwarded(self):
        mock_provider = AsyncMock()
        mock_provider.call = AsyncMock(return_value="answer")
        chain = LLMProviderChain(providers=[mock_provider])

        await chain.call(prompt="Q?", thinking=True, temperature=0.5, top_p=0.8, max_tokens=256)

        mock_provider.call.assert_awaited_once_with(
            prompt="Q?",
            media_paths=None,
            media_type=None,
            response_schema=None,
            thinking=True,
            temperature=0.5,
            top_p=0.8,
            max_tokens=256,
        )

    @pytest.mark.asyncio
    async def test_thinking_false_by_default(self):
        mock_provider = AsyncMock()
        mock_provider.call = AsyncMock(return_value="answer")
        chain = LLMProviderChain(providers=[mock_provider])

        await chain.call(prompt="Q?")

        _, kwargs = mock_provider.call.call_args
        assert kwargs.get("thinking") is False
        assert kwargs.get("temperature") is None
        assert kwargs.get("top_p") is None
        assert kwargs.get("max_tokens") is None


# ---------------------------------------------------------------------------
# LLMProviderPool — sampling params forwarded
# ---------------------------------------------------------------------------


class TestLLMProviderPoolSampling:
    @pytest.mark.asyncio
    async def test_sampling_overrides_forwarded(self):
        mock_provider = AsyncMock()
        mock_provider.call = AsyncMock(return_value="pooled answer")
        pool = LLMProviderPool(providers=[mock_provider])

        result = await pool.call(prompt="Q?", thinking=True, temperature=0.3, top_p=0.95)

        assert result == "pooled answer"
        mock_provider.call.assert_awaited_once_with(
            prompt="Q?",
            media_paths=None,
            media_type=None,
            response_schema=None,
            thinking=True,
            temperature=0.3,
            top_p=0.95,
            max_tokens=None,
        )
