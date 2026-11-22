"""Visitor cluster admin router tests (identity-continuity M07).

Mirrors ``test_cts_reid_review_router.py``'s structure: the headline
guarantee is permission separation (``visitors.review`` is a distinct
biometric-admin grant, not covered by the broad ``caregiver`` role's
``GET /api/v1/*`` glob), proven by a canary that runs every route against a
caregiver-only key and a caregiver_admin key.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context, invalidate_lookup_cache
from backend.core.database import get_db
from backend.core.exceptions import register_exception_handlers
from backend.integrations.minio_client import MinioClient
from backend.routers.dependencies import (
    get_config_minio_client,
    get_identity_review_registry,
    get_visitor_admin_service,
)
from backend.routers.visitors import router
from backend.schemas.identity_review import BatchReviewResponse, ReviewItemResult
from backend.schemas.visitors import (
    NameVisitorResponse,
    VisitorClusterDetailView,
    VisitorClusterListResponse,
    VisitorClusterView,
)
from backend.services.identity_review.registry import ReviewSubject
from backend.services.visitors import PersonIDUpstreamError, VisitorPartialFailureError


def _cluster_view(**overrides) -> VisitorClusterView:
    base = {
        "cluster_id": "c1",
        "status": "surfaced",
        "display_hint": None,
        "named_person_id": None,
        "sighting_count": 3,
        "distinct_days": 3,
        "first_seen_at": "2026-07-01T10:00:00+00:00",
        "last_seen_at": "2026-07-19T10:00:00+00:00",
        "recent_crop_urls": ["https://minio/c1/1.jpg"],
    }
    base.update(overrides)
    return VisitorClusterView(**base)


def _mock_service():
    svc = MagicMock()
    svc.list_clusters = AsyncMock(
        return_value=VisitorClusterListResponse(clusters=[_cluster_view()], total=1)
    )
    svc.get_cluster = AsyncMock(
        return_value=VisitorClusterDetailView(cluster=_cluster_view(), recent_sightings=[])
    )
    svc.name_cluster = AsyncMock(
        return_value=NameVisitorResponse(
            cluster_id="c1",
            status="named",
            named_person_id="nurse-priya",
            member_name="Nurse Priya",
            embedding_count=5,
            household_member_created=True,
        )
    )
    svc.merge_clusters = AsyncMock(return_value=_cluster_view())
    return svc


def _mock_registry():
    registry = MagicMock()
    registry.decide = AsyncMock(
        return_value=BatchReviewResponse(
            results=[ReviewItemResult(id="c1", ok=True)], reviewed=1, failed=0, effect="Dismissed."
        )
    )
    return registry


def _build_app(
    roles: list[str] | None = None,
    *,
    tokens: frozenset[str] = frozenset(),
):
    svc = _mock_service()
    svc.registry = _mock_registry()
    minio = MagicMock(spec=MinioClient)
    minio.generate_presigned_url.return_value = "https://minio/presigned"
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="user", roles=list(roles or ()), tokens=tokens
    )
    app.dependency_overrides[get_visitor_admin_service] = lambda: svc
    app.dependency_overrides[get_identity_review_registry] = lambda: svc.registry
    app.dependency_overrides[get_config_minio_client] = lambda: minio

    def _mock_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _mock_db
    invalidate_lookup_cache()
    return TestClient(app), svc


# ---------------------------------------------------------------------------
# Auth canary: the central guarantee.
# ---------------------------------------------------------------------------

_ROUTES = [
    ("get", "/api/v1/visitors/clusters", None),
    ("get", "/api/v1/visitors/clusters/c1", None),
    ("post", "/api/v1/visitors/clusters/c1/name", {"person_id": "nurse-priya", "name": "Nurse"}),
    ("post", "/api/v1/visitors/clusters/review", {"cluster_ids": ["c1"], "verdict": "not_usable"}),
    ("post", "/api/v1/visitors/clusters/c1/merge/c2", {}),
]


@pytest.mark.parametrize(
    ("roles", "tokens"),
    [(["caregiver"], frozenset()), ([], frozenset({"cts.identity.gallery:review"}))],
)
def test_caregiver_alone_cannot_access_any_route(roles, tokens):
    client, _ = _build_app(roles, tokens=tokens)
    for method, path, body in _ROUTES:
        resp = (
            getattr(client, method)(path, json=body)
            if body is not None
            else getattr(client, method)(path)
        )
        assert resp.status_code == 403, (
            f"{method} {path} leaked to {roles}/{tokens}: {resp.status_code}"
        )


@pytest.mark.parametrize(
    ("roles", "tokens"),
    [
        ([], frozenset({"visitors:review"})),
        (["caregiver_admin"], frozenset()),
        (["admin"], frozenset()),
    ],
)
def test_visitors_review_token_grants_access(roles, tokens):
    client, _ = _build_app(roles, tokens=tokens)
    for method, path, body in _ROUTES:
        resp = (
            getattr(client, method)(path, json=body)
            if body is not None
            else getattr(client, method)(path)
        )
        assert resp.status_code == 200, (
            f"{method} {path} denied for {roles}/{tokens}: {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# Behaviour.
# ---------------------------------------------------------------------------


class TestListAndGet:
    def test_list_clusters_returns_envelope(self):
        client, svc = _build_app(["admin"])
        resp = client.get("/api/v1/visitors/clusters?status=surfaced")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["clusters"][0]["cluster_id"] == "c1"
        svc.list_clusters.assert_awaited_once()

    def test_get_cluster_returns_detail(self):
        client, _ = _build_app(["admin"])
        resp = client.get("/api/v1/visitors/clusters/c1")
        assert resp.status_code == 200
        assert resp.json()["cluster"]["cluster_id"] == "c1"

    def test_upstream_error_maps_to_status(self):
        client, svc = _build_app(["admin"])
        svc.list_clusters.side_effect = PersonIDUpstreamError(409, "Visitor clustering is disabled")
        resp = client.get("/api/v1/visitors/clusters")
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Visitor clustering is disabled"

    def test_upstream_5xx_maps_to_502(self):
        client, svc = _build_app(["admin"])
        svc.list_clusters.side_effect = PersonIDUpstreamError(500, "boom")
        resp = client.get("/api/v1/visitors/clusters")
        assert resp.status_code == 502


class TestNaming:
    def test_name_cluster_happy_path(self):
        client, svc = _build_app(["admin"])
        resp = client.post(
            "/api/v1/visitors/clusters/c1/name",
            json={"person_id": "nurse-priya", "name": "Nurse Priya"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["named_person_id"] == "nurse-priya"
        assert body["household_member_created"] is True
        svc.name_cluster.assert_awaited_once()

    def test_name_cluster_rejects_unknown_field(self):
        client, _ = _build_app(["admin"])
        resp = client.post(
            "/api/v1/visitors/clusters/c1/name",
            json={"person_id": "nurse-priya", "name": "Nurse Priya", "actor": "sneaky"},
        )
        assert resp.status_code == 422

    def test_name_cluster_partial_failure_returns_502_with_recovery_detail(self):
        client, svc = _build_app(["admin"])
        svc.name_cluster.side_effect = VisitorPartialFailureError("nurse-priya", "Nurse Priya")
        resp = client.post(
            "/api/v1/visitors/clusters/c1/name",
            json={"person_id": "nurse-priya", "name": "Nurse Priya"},
        )
        assert resp.status_code == 502
        detail = resp.json()["detail"]
        assert detail["code"] == "visitors.partial_failure"
        assert detail["person_id"] == "nurse-priya"


class TestReviewAndMerge:
    def test_review_passes_the_decision_and_the_key_name(self):
        client, svc = _build_app(["admin"])
        body = {"cluster_ids": ["c1"], "verdict": "is_member", "target_identity_id": "resident"}
        resp = client.post("/api/v1/visitors/clusters/review", json=body)
        assert resp.status_code == 200
        assert resp.json()["reviewed"] == 1
        args, kwargs = svc.registry.decide.await_args
        assert args == ("visitors", "is_member", [ReviewSubject(id="c1")])
        assert (kwargs["target_identity_id"], kwargs["actor"]) == ("resident", "user")

    def test_review_rejects_a_client_supplied_actor(self):
        client, _ = _build_app(["admin"])
        body = {"cluster_ids": ["c1"], "verdict": "not_usable", "actor": "someone else"}
        assert client.post("/api/v1/visitors/clusters/review", json=body).status_code == 422

    def test_review_rejects_new_person_which_only_naming_does(self):
        client, _ = _build_app(["admin"])
        body = {"cluster_ids": ["c1"], "verdict": "new_person"}
        assert client.post("/api/v1/visitors/clusters/review", json=body).status_code == 422

    def test_merge_clusters(self):
        client, svc = _build_app(["admin"])
        resp = client.post("/api/v1/visitors/clusters/c1/merge/c2")
        assert resp.status_code == 200
        svc.merge_clusters.assert_awaited_once()


# ---------------------------------------------------------------------------
# MCP exemption (mutations are a caregiver admin action, not agent-facing).
# ---------------------------------------------------------------------------


def test_no_mcp_tool_for_visitor_mutations():
    """Naming, dismissing, and merging a visitor cluster stay off MCP.

    Naming moves biometric data into the governed enrollment dataset and
    creates a live household member; letting an unattended agent do that
    without operator review would be the same category of hazard the M09
    ReID-review exemption documents.
    """
    from backend.core.config import settings

    configured = settings.get("mcp.tools", []) or []
    names = " ".join(str(t) for t in configured).lower()
    assert "visitor" not in names
