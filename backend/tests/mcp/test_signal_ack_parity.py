"""Parity tests for the acknowledge_dementia_signal MCP tool.

Verifies that the MCP tool and the router endpoint produce the same outcome
when acknowledging a signal with caregiver feedback.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.models  # noqa: F401 - ensure all ORM models are registered
from backend.core.auth import AuthContext, get_auth_context
from backend.core.config import Settings
from backend.core.exceptions import register_exception_handlers
from backend.routers.cts_signals import _get_signal_store, router
from backend.services.cts.signal_store import SignalStore

_EXPERIMENTAL_SIGNAL: dict = {
    "person_id": "grandma",
    "signal_type": "agitation_index",
    "severity": "info",
    "window_start": "2026-06-12T08:00:00+00:00",
    "window_end": "2026-06-12T08:30:00+00:00",
    "value": 1.4,
    "evidence_grade": "experimental",
}

_BASE_SIGNAL: dict = {
    "person_id": "grandma",
    "signal_type": "pacing",
    "severity": "warning",
    "window_start": "2026-06-12T08:00:00+00:00",
    "window_end": "2026-06-12T08:30:00+00:00",
    "value": 5.0,
}


def _build_router_client(db_factory):
    cfg = Settings.from_dict({"cts": {"enabled": True}})
    store = SignalStore(db_factory=db_factory)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )
    app.dependency_overrides[_get_signal_store] = lambda: store
    patcher = patch("backend.routers.cts_deps.settings", cfg)
    patcher.start()
    return TestClient(app), store, patcher


@pytest.fixture
def setup(db_factory):
    client, store, patcher = _build_router_client(db_factory)
    yield client, store, db_factory
    patcher.stop()


class TestAcknowledgeSignalParity:
    def test_router_and_mcp_produce_same_feedback_outcome(self, setup):
        """Router POST /ack and MCP acknowledge_dementia_signal must both
        persist feedback on experimental signals and leave it NULL elsewhere."""
        client, store, db_factory = setup
        from backend.mcp.server import _svc, acknowledge_dementia_signal

        _svc.db_factory = db_factory

        # Insert two experimental signals — one acked via router, one via MCP.
        sid_router = asyncio.run(store.insert(_EXPERIMENTAL_SIGNAL))
        sid_mcp = asyncio.run(store.insert(_EXPERIMENTAL_SIGNAL))

        r = client.post(f"/api/v1/cts/signals/{sid_router}/ack", json={"feedback": "accurate"})
        assert r.status_code == 200

        mcp_result = asyncio.run(acknowledge_dementia_signal(sid_mcp, feedback="accurate"))
        assert mcp_result.get("acknowledged") is True

        rows, _ = asyncio.run(store.list_recent())
        by_id = {row["id"]: row for row in rows}
        assert by_id[sid_router]["feedback"] == "accurate"
        assert by_id[sid_mcp]["feedback"] == "accurate"

    def test_mcp_not_found_returns_error(self, setup):
        _client, _store, db_factory = setup
        from backend.mcp.server import _svc, acknowledge_dementia_signal

        _svc.db_factory = db_factory
        result = asyncio.run(acknowledge_dementia_signal(99999))
        assert "error" in result

    def test_mcp_invalid_feedback_returns_error(self, setup):
        _client, store, db_factory = setup
        from backend.mcp.server import _svc, acknowledge_dementia_signal

        _svc.db_factory = db_factory
        sid = asyncio.run(store.insert(_EXPERIMENTAL_SIGNAL))
        result = asyncio.run(acknowledge_dementia_signal(sid, feedback="bad_value"))
        assert "error" in result

    def test_feedback_ignored_for_non_experimental_via_mcp(self, setup):
        _client, store, db_factory = setup
        from backend.mcp.server import _svc, acknowledge_dementia_signal

        _svc.db_factory = db_factory
        sid = asyncio.run(store.insert(_BASE_SIGNAL))
        result = asyncio.run(acknowledge_dementia_signal(sid, feedback="accurate"))
        assert result.get("acknowledged") is True
        rows, _ = asyncio.run(store.list_recent())
        assert rows[0]["feedback"] is None
