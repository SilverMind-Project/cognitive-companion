"""Tests for cts_ph BFF router."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.routers.cts_ph import router


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(router, prefix="/api/v1")
    application.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )
    return application


@pytest.fixture
def client_mock():
    mock = AsyncMock()
    mock.list_phs.return_value = {"items": [], "total": 0, "limit": 50, "offset": 0}
    return mock


@pytest.fixture
def test_client(app, client_mock):
    app.state.orchestrator_client = client_mock
    return TestClient(app)


def test_list_phs_passes_new_filter_params(test_client, client_mock):
    test_client.get(
        "/api/v1/cts/ph?state=active&search=alice&include_transient=true"
        "&min_duration_s=30&until=2026-01-02"
    )
    call_kwargs = client_mock.list_phs.call_args.kwargs
    assert call_kwargs["state"] == "active"
    assert call_kwargs["search"] == "alice"
    assert call_kwargs["include_transient"] is True
    assert call_kwargs["min_duration_s"] == 30.0
    assert call_kwargs["until"] == "2026-01-02"


def test_correct_identity_forwards_idempotency_key(test_client, client_mock):
    client_mock.correct_ph_identity.return_value = {
        "revision": {"revision_id": "rev-1", "ph_id": "ph-1", "applied_at": None}
    }
    test_client.post(
        "/api/v1/cts/ph/ph-1/correct",
        json={"new_identity_id": "alice", "reason": "test"},
        headers={"X-Idempotency-Key": "idem-abc"},
    )
    call_kwargs = client_mock.correct_ph_identity.call_args.kwargs
    assert call_kwargs["idempotency_key"] == "idem-abc"


def test_correct_identity_no_idempotency_key(test_client, client_mock):
    client_mock.correct_ph_identity.return_value = {
        "revision": {"revision_id": "rev-2", "ph_id": "ph-1", "applied_at": None}
    }
    test_client.post(
        "/api/v1/cts/ph/ph-1/correct",
        json={"new_identity_id": "alice", "reason": "test"},
    )
    call_kwargs = client_mock.correct_ph_identity.call_args.kwargs
    assert call_kwargs.get("idempotency_key") is None
