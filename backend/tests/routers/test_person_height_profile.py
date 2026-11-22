"""Router, auth (403/200), validation, and CTS-fallback tests for member standing height profiles."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.core.auth as auth_module
from backend.core.auth import KeyStore
from backend.core.config import settings
from backend.core.database import get_db
from backend.core.exceptions import register_exception_handlers
from backend.core.upstream_errors import UpstreamUnavailable
from backend.models.person import HouseholdMember
from backend.routers import persons

_ADMIN_KEY = "height-admin-key"
_CAREGIVER_KEY = "height-caregiver-key"
_INGRESS_KEY = "height-ingress-key"
_READONLY_MCP_KEY = "height-mcp-key"


def _headers(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


@pytest.fixture
def height_client(db_factory, monkeypatch: pytest.MonkeyPatch):
    ks = KeyStore(
        api_keys=[
            {"key": _ADMIN_KEY, "name": "Admin", "roles": ["admin"]},
            {"key": _CAREGIVER_KEY, "name": "Caregiver", "roles": ["caregiver"]},
            {"key": _INGRESS_KEY, "name": "CTS Ingress", "roles": ["cts_ingress"]},
            {"key": _READONLY_MCP_KEY, "name": "MCP Agent", "roles": ["mcp_readonly"]},
        ],
        roles=settings.get("auth.roles", {}),
    )
    monkeypatch.setattr(auth_module, "_default_keystore", ks)

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(persons.router, prefix="/api/v1")

    orch = MagicMock()
    orch.get_identity_height_profile = AsyncMock(return_value=None)
    app.state.orchestrator_client = orch
    app.state.person_id_client = MagicMock(get_members=AsyncMock(return_value=[]))

    def _override_db():
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, app, orch


def _seed_members(db_factory) -> None:
    with db_factory() as db:
        db.add(HouseholdMember(id="alice", name="Alice", height_cm=158.0))
        db.add(HouseholdMember(id="bob", name="Bob", height_cm=None))
        db.commit()


def test_heights_sync_endpoint_strict_auth_and_payload(height_client, db_factory) -> None:
    """GET /persons/heights requires persons:heights_sync (cts_ingress/admin); 403 for caregiver/mcp."""
    client, _, _ = height_client
    _seed_members(db_factory)

    assert (
        client.get("/api/v1/persons/heights", headers=_headers(_CAREGIVER_KEY)).status_code == 403
    )
    assert (
        client.get("/api/v1/persons/heights", headers=_headers(_READONLY_MCP_KEY)).status_code
        == 403
    )

    for key in (_INGRESS_KEY, _ADMIN_KEY):
        resp = client.get("/api/v1/persons/heights", headers=_headers(key))
        assert resp.status_code == 200
        assert resp.json() == [
            {"person_id": "alice", "height_cm": 158.0},
            {"person_id": "bob", "height_cm": None},
        ]


def test_member_create_and_patch_validate_height_cm_bounds(height_client) -> None:
    client, _, _ = height_client

    # Create with valid height_cm succeeds.
    ok = client.post(
        "/api/v1/persons",
        json={"id": "carol", "name": "Carol", "height_cm": 164.5},
        headers=_headers(_ADMIN_KEY),
    )
    assert ok.status_code == 201
    assert ok.json()["height_cm"] == pytest.approx(164.5)

    # Out-of-bounds height rejected with 422.
    too_short = client.patch(
        "/api/v1/persons/carol",
        json={"height_cm": 85.0},
        headers=_headers(_ADMIN_KEY),
    )
    assert too_short.status_code == 422
    too_tall = client.patch(
        "/api/v1/persons/carol",
        json={"height_cm": 230.0},
        headers=_headers(_ADMIN_KEY),
    )
    assert too_tall.status_code == 422

    # Clearing height_cm to null succeeds.
    cleared = client.patch(
        "/api/v1/persons/carol",
        json={"height_cm": None},
        headers=_headers(_ADMIN_KEY),
    )
    assert cleared.status_code == 200
    assert cleared.json()["height_cm"] is None


def test_height_profile_merges_cc_and_cts_and_degrades_when_cts_down(
    height_client, db_factory
) -> None:
    client, app, orch = height_client
    _seed_members(db_factory)

    # 1. Learned CTS profile merged with local operator_height_cm.
    orch.get_identity_height_profile.return_value = {
        "identity_id": "alice",
        "height_m": 1.54,
        "height_sigma_m": 0.032,
        "source": "learned",
        "samples": 260,
        "cameras": 3,
        "updated_at": "2026-11-21T10:00:00Z",
    }
    resp = client.get("/api/v1/persons/alice/height-profile", headers=_headers(_CAREGIVER_KEY))
    assert resp.status_code == 200
    body = resp.json()
    assert body["person_id"] == "alice"
    assert body["operator_height_cm"] == pytest.approx(158.0)
    assert body["effective_height_m"] == pytest.approx(1.54)
    assert body["effective_sigma_m"] == pytest.approx(0.032)
    assert body["source"] == "learned"
    assert body["samples"] == 260
    assert body["cameras"] == 3
    assert body["cts_available"] is True

    # 2. No CTS profile yet (404 -> None) -> cts_available=True with empty effective fields.
    orch.get_identity_height_profile.return_value = None
    resp_empty = client.get("/api/v1/persons/bob/height-profile", headers=_headers(_CAREGIVER_KEY))
    assert resp_empty.status_code == 200
    assert resp_empty.json()["effective_height_m"] is None
    assert resp_empty.json()["cts_available"] is True

    # 3. CTS unreachable -> degrades cleanly with cts_available=False + local operator height.
    orch.get_identity_height_profile.side_effect = UpstreamUnavailable("tracking_orchestrator")
    resp_down = client.get("/api/v1/persons/alice/height-profile", headers=_headers(_CAREGIVER_KEY))
    assert resp_down.status_code == 200
    assert resp_down.json()["operator_height_cm"] == pytest.approx(158.0)
    assert resp_down.json()["effective_height_m"] is None
    assert resp_down.json()["cts_available"] is False

    # 4. CTS disabled (no orchestrator_client) -> same clean fallback.
    app.state.orchestrator_client = None
    resp_disabled = client.get(
        "/api/v1/persons/alice/height-profile", headers=_headers(_CAREGIVER_KEY)
    )
    assert resp_disabled.status_code == 200
    assert resp_disabled.json()["cts_available"] is False

    # 5. Unknown person -> 404.
    assert (
        client.get(
            "/api/v1/persons/nobody/height-profile", headers=_headers(_CAREGIVER_KEY)
        ).status_code
        == 404
    )
