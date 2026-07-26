"""Tests for :class:`OllamaProvider`'s admission-control wiring (DL-M09).

Every outbound HTTP call is intercepted by a mock ``httpx.AsyncClient`` so no
real Ollama instance is required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.integrations.llm.admission import LLMAdmissionController
from backend.integrations.llm.ollama import OllamaProvider

_HTTPX_TARGET = "backend.integrations.llm.ollama.httpx.AsyncClient"


def _mock_ctx(content: str = "answer") -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"message": {"content": content}}

    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=response)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=http_client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_call_without_admission_passthrough() -> None:
    provider = OllamaProvider(base_url="http://ollama-test", model="gemma3:4b")
    with patch(_HTTPX_TARGET, return_value=_mock_ctx("hello")):
        result = await provider.call(prompt="hi")
    assert result == "hello"


@pytest.mark.asyncio
async def test_call_with_admission_records_text_lane() -> None:
    """Ollama attaches no images today, so every call uses the text lane."""
    controller = LLMAdmissionController(max_concurrent_vision=1, max_concurrent_text=2)
    provider = OllamaProvider(
        base_url="http://ollama-test", model="gemma3:4b", admission=controller
    )
    with patch(_HTTPX_TARGET, return_value=_mock_ctx("hello")):
        result = await provider.call(prompt="hi", caller="rule:logic")

    assert result == "hello"
    counters = controller.counters()
    assert counters[("rule:logic", "text", "ok")] == 1
