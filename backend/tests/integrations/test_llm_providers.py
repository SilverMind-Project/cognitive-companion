"""Tests for LLM provider thinking support and sampling overrides."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.integrations.llm.base import strip_thinking
from backend.integrations.llm.chain import LLMProviderChain, LLMProviderPool

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


# ---------------------------------------------------------------------------
# LLMProviderChain: sampling params forwarded
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
# LLMProviderPool: sampling params forwarded
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
