"""Learned camera handoffs are proxied read-only from the tracking orchestrator."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.config import Settings
from backend.core.exceptions import register_exception_handlers
from backend.core.upstream_errors import UpstreamUnavailable
from backend.routers.cts_topology import router

_PAYLOAD = {
    "transitions": [
        {
            "from_camera": "side-corridor",
            "to_camera": "kitchen-cam-1",
            "observation_count": 7,
            "mean_transit_s": 6.5,
            "std_transit_s": 1.2,
            "last_updated_at": "2026-11-14T10:00:00Z",
        }
    ],
}


@pytest.fixture
def orchestrator() -> MagicMock:
    client = MagicMock()
    client.learned_transitions = AsyncMock(return_value=_PAYLOAD)
    return client


@pytest.fixture
def client(orchestrator: MagicMock) -> Iterator[TestClient]:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )
    app.state.orchestrator_client = orchestrator
    with patch("backend.routers.cts_deps.settings", Settings.from_dict({"cts": {"enabled": True}})):
        yield TestClient(app)


def test_transitions_are_returned(client: TestClient) -> None:
    body = client.get("/api/v1/cts/topology/transitions").json()

    assert body["transitions"][0]["from_camera"] == "side-corridor"
    assert body["transitions"][0]["observation_count"] == 7


def test_orchestrator_unavailable_is_503(client: TestClient, orchestrator: MagicMock) -> None:
    orchestrator.learned_transitions.side_effect = UpstreamUnavailable("tracking-orchestrator")

    r = client.get("/api/v1/cts/topology/transitions")

    assert r.status_code == 503
