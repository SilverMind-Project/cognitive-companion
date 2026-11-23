"""Served-model probe: a configured model id the inference server does not serve."""

from __future__ import annotations

import logging

import httpx
import pytest

from backend.services import llm_model_health
from backend.services.llm_model_health import check_served_models, log_unserved_models

SERVED = "qwen-3.8-27b"


def _model(model_id: str, base_url: str = "http://llm.local") -> dict:
    return {"id": model_id, "name": model_id, "base_url": base_url, "model": model_id}


@pytest.fixture
def llm_server(monkeypatch):
    """Route the probe's AsyncClient to an in-memory server that serves only SERVED."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "down.local":
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json={"data": [{"id": SERVED}]})

    real_client = httpx.AsyncClient

    def client(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(llm_model_health.httpx, "AsyncClient", client)


@pytest.mark.asyncio
async def test_reports_served_unserved_and_unreachable_models(llm_server) -> None:
    results = await check_served_models(
        [_model(SERVED), _model("gemma-4-26B-A4B-it"), _model("x", base_url="http://down.local")]
    )

    assert [r["status"] for r in results] == ["success", "warning", "error"]
    assert SERVED in results[1]["detail"]


@pytest.mark.asyncio
async def test_unserved_required_model_is_an_error_naming_the_setting(llm_server, caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="backend.services.llm_model_health"):
        await log_unserved_models(
            [_model(SERVED), _model("gemma-4-26B-A4B-it"), _model("qwen-3.6-35b")],
            required_ids={
                "knowledge.answer_model": "gemma-4-26B-A4B-it",
                "knowledge.paraphrase_model": SERVED,
            },
        )

    by_model = {
        r.getMessage().split("model_id=")[1].split()[0]: r
        for r in caplog.records
        if r.getMessage().startswith("llm_model_not_served")
    }
    assert set(by_model) == {"gemma-4-26B-A4B-it", "qwen-3.6-35b"}
    assert by_model["gemma-4-26B-A4B-it"].levelno == logging.ERROR
    assert "knowledge.answer_model" in by_model["gemma-4-26B-A4B-it"].getMessage()
    assert by_model["qwen-3.6-35b"].levelno == logging.WARNING
