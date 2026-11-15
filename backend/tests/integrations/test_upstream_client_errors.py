"""A stopped CTS service is reported as unavailable, never as an unexpected crash."""

from __future__ import annotations

import httpx
import pytest

from backend.core.upstream_errors import UpstreamTimeout, UpstreamUnavailable
from backend.integrations.tracking_orchestrator_client import OrchestratorClient


def _client() -> OrchestratorClient:
    client = OrchestratorClient()
    client._base = "http://orchestrator.test"
    return client


@pytest.mark.asyncio
async def test_connection_refused_is_unavailable_after_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def refuse(self: httpx.AsyncClient, method: str, url: str, **_: object) -> None:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "request", refuse)

    with pytest.raises(UpstreamUnavailable) as raised:
        await _client().calibration_status()

    assert raised.value.status == 503
    assert raised.value.service == "tracking_orchestrator"
    assert calls == 3  # the transient-failure retry covers a refused connection too


@pytest.mark.asyncio
async def test_timeout_stays_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow(self: httpx.AsyncClient, method: str, url: str, **_: object) -> None:
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(httpx.AsyncClient, "request", slow)

    with pytest.raises(UpstreamTimeout):
        await _client().calibration_status()
