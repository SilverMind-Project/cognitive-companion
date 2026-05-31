"""Tests for cts_ph BFF router."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.routers.cts_ph import router
from backend.services.cts.ph_enrichment import PHEnrichmentService


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
    mock.get_identities.return_value = []
    return mock


@pytest.fixture
def test_client(app, client_mock):
    app.state.orchestrator_client = client_mock
    app.state.ph_enrichment_service = PHEnrichmentService(client_mock)
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


def test_enrichment_populates_display_name(test_client, client_mock):
    client_mock.list_phs.return_value = {
        "items": [
            {
                "ph_id": "ph-1",
                "current_identity_id": "alice",
                "observation_count": 3,
            },
            {
                "ph_id": "ph-2",
                "current_identity_id": "missing",
                "observation_count": 1,
            },
        ],
        "total": 2,
        "limit": 50,
        "offset": 0,
    }
    client_mock.get_identities.return_value = [
        {"identity_id": "alice", "display_name": "Alice Rivera"},
    ]

    response = test_client.get("/api/v1/cts/ph")

    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["identity_display_name"] == "Alice Rivera"
    assert items[1]["identity_display_name"] == "missing"


def test_enrichment_fetches_identity_map_once_for_list(test_client, client_mock):
    client_mock.list_phs.return_value = {
        "items": [
            {"ph_id": "ph-1", "current_identity_id": "alice"},
            {"ph_id": "ph-2", "current_identity_id": "bob"},
            {"ph_id": "ph-3", "current_identity_id": "carol"},
        ],
        "total": 3,
        "limit": 50,
        "offset": 0,
    }
    client_mock.get_identities.return_value = [
        {"identity_id": "alice", "display_name": "Alice"},
        {"identity_id": "bob", "display_name": "Bob"},
        {"identity_id": "carol", "display_name": "Carol"},
    ]

    response = test_client.get("/api/v1/cts/ph")

    assert response.status_code == 200
    assert client_mock.get_identities.call_count == 1


def test_co_present_forwards_radius_and_enriches_identity_name(test_client, client_mock):
    client_mock.get_ph_co_present.return_value = {
        "ph_id": "ph-1",
        "co_present": [
            {
                "ph_id": "ph-2",
                "current_identity_id": "alice",
                "last_seen_camera": "cam-1",
            }
        ],
        "radius_m": 7.0,
    }
    client_mock.get_identities.return_value = [
        {"identity_id": "alice", "display_name": "Alice Rivera"},
    ]

    response = test_client.get("/api/v1/cts/ph/ph-1/co_present?radius_m=7")

    assert response.status_code == 200
    client_mock.get_ph_co_present.assert_awaited_once_with("ph-1", radius_m=7.0)
    item = response.json()["co_present"][0]
    assert item["identity_display_name"] == "Alice Rivera"


def test_co_present_missing_required_list_returns_502(test_client, client_mock):
    client_mock.get_ph_co_present.return_value = {
        "ph_id": "ph-1",
        "radius_m": 5.0,
    }

    response = test_client.get("/api/v1/cts/ph/ph-1/co_present")

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "cts_ph.upstream_contract"


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
