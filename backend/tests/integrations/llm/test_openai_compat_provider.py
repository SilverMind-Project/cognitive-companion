"""Tests for :class:`OpenAICompatibleProvider`'s admission-control wiring (DL-M09).

Every outbound HTTP call is intercepted by a mock ``httpx.AsyncClient`` so no
real vLLM/llama.cpp server is required.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.integrations.llm.admission import LLMAdmissionController, LLMAdmissionTimeout
from backend.integrations.llm.openai_compat import OpenAICompatibleProvider

_HTTPX_TARGET = "backend.integrations.llm.openai_compat.httpx.AsyncClient"


def _mock_ctx(content: str = "answer") -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"choices": [{"message": {"content": content}}]}

    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=response)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=http_client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_call_without_admission_passthrough() -> None:
    """No admission controller injected: call() behaves exactly as before DL-M09."""
    provider = OpenAICompatibleProvider(base_url="http://vllm-test", model="test-model")
    with patch(_HTTPX_TARGET, return_value=_mock_ctx("hello")):
        result = await provider.call(prompt="hi")
    assert result == "hello"


@pytest.mark.asyncio
async def test_call_with_admission_records_lane_and_caller() -> None:
    """An injected controller records the call under the given caller/lane."""
    controller = LLMAdmissionController(max_concurrent_vision=1, max_concurrent_text=2)
    provider = OpenAICompatibleProvider(
        base_url="http://vllm-test", model="cosmos_reason2", admission=controller
    )
    with patch(_HTTPX_TARGET, return_value=_mock_ctx("hello")):
        result = await provider.call(prompt="hi", caller="rule:tea_intent")

    assert result == "hello"
    counters = controller.counters()
    assert counters[("rule:tea_intent", "text", "ok")] == 1


@pytest.mark.asyncio
async def test_vision_lane_selected_when_media_paths_present() -> None:
    controller = LLMAdmissionController(max_concurrent_vision=1, max_concurrent_text=2)
    provider = OpenAICompatibleProvider(
        base_url="http://vllm-test", model="cosmos_reason2", admission=controller
    )
    with patch(_HTTPX_TARGET, return_value=_mock_ctx("hello")), patch(
        "backend.integrations.llm.openai_compat.encode_image_data_uri",
        AsyncMock(return_value="data:image/jpeg;base64,abc"),
    ):
        await provider.call(
            prompt="hi", media_paths=["frame.jpg"], media_type="image", caller="rule:hygiene"
        )

    counters = controller.counters()
    assert counters[("rule:hygiene", "vision", "ok")] == 1


@pytest.mark.asyncio
async def test_admission_timeout_propagates_from_call() -> None:
    """A queue timeout on the admission controller surfaces as LLMAdmissionTimeout."""
    controller = LLMAdmissionController(
        max_concurrent_vision=1, max_concurrent_text=2, queue_timeout_s=0.05
    )
    provider = OpenAICompatibleProvider(
        base_url="http://vllm-test", model="cosmos_reason2", admission=controller
    )
    holder_started = asyncio.Event()
    keep_holding = asyncio.Event()

    async def holder() -> None:
        async with controller.admit("vision", "holder"):
            holder_started.set()
            await keep_holding.wait()

    task = asyncio.create_task(holder())
    await holder_started.wait()

    with (
        patch(_HTTPX_TARGET, return_value=_mock_ctx("hello")),
        patch(
            "backend.integrations.llm.openai_compat.encode_image_data_uri",
            AsyncMock(return_value="data:image/jpeg;base64,abc"),
        ),
        pytest.raises(LLMAdmissionTimeout),
    ):
        await provider.call(prompt="hi", media_paths=["frame.jpg"], media_type="image")

    keep_holding.set()
    await task
