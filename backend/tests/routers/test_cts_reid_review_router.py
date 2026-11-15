"""M09: ReID review-queue BFF routes.

The headline guarantee is permission separation: gallery review is gated by the
strict ``cts.identity.gallery_review`` token, not by the broad ``GET
/api/v1/*`` / ``POST /api/v1/cts/identity/*`` role globs that also cover this
path. The first test is the canary that proves it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context, invalidate_lookup_cache
from backend.core.config import Settings, settings
from backend.core.exceptions import register_exception_handlers
from backend.routers.cts_reid_review import router
from backend.routers.dependencies import get_identity_review_registry, get_reid_review_service
from backend.schemas.cts_reid_review import (
    EligibilityView,
    ReviewCandidateDetailResponse,
    ReviewCandidateListResponse,
    ReviewCandidateView,
    ReviewCountsResponse,
    ReviewEventsResponse,
)
from backend.schemas.identity_review import BatchReviewResponse, ReviewItemResult
from backend.services.cts.reid_review_service import ReviewUpstreamError
from backend.services.identity_review.registry import ReviewSubject


def _candidate(
    state: str = "pending_review", crop_url: str | None = "https://x/crop"
) -> ReviewCandidateView:
    return ReviewCandidateView(
        candidate_id="c1",
        identity_id="amma",
        proposed_identity_id="amma",
        effective_identity_id="amma",
        person_id="amma",
        state=state,
        candidate_reason="multiview",
        model_version="v1",
        preprocessing_version="v1",
        orientation=4,
        quality=0.8,
        is_truncated=False,
        is_occluded=False,
        audit_version=1,
        crop_url=crop_url,
        frame_url=None,
    )


def _detail() -> ReviewCandidateDetailResponse:
    return ReviewCandidateDetailResponse(
        candidate=_candidate(),
        events=[],
        eligibility=EligibilityView(eligible=True, model_compatible=True, reasons=[]),
    )


def _mock_service() -> MagicMock:
    svc = MagicMock()
    svc.list_candidates = AsyncMock(
        return_value=ReviewCandidateListResponse(
            candidates=[_candidate()], total=1, limit=50, offset=0
        )
    )
    svc.get_detail = AsyncMock(return_value=_detail())
    svc.list_events = AsyncMock(return_value=ReviewEventsResponse(events=[]))
    svc.counts = AsyncMock(
        return_value=ReviewCountsResponse(
            pending_review=1, auto_verified=0, operator_verified=0, rejected=0
        )
    )
    svc.approve = AsyncMock(return_value=_candidate(state="operator_verified"))
    svc.relabel = AsyncMock(return_value=_candidate(state="operator_verified"))
    svc.demote = AsyncMock(return_value=_candidate(state="pending_review"))
    svc.reject = AsyncMock(return_value=_candidate(state="rejected", crop_url=None))
    svc.registry = MagicMock()
    svc.registry.decide = AsyncMock(
        return_value=BatchReviewResponse(
            results=[ReviewItemResult(id="c1", ok=True)], reviewed=1, failed=0, effect="Rejected."
        )
    )
    svc.compensate = AsyncMock(return_value=_candidate())
    return svc


def _build_app(permissions: list[str]):
    cfg = Settings.from_dict({"cts": {"enabled": True}})
    svc = _mock_service()
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="user", permissions=permissions
    )
    app.dependency_overrides[get_reid_review_service] = lambda: svc
    app.dependency_overrides[get_identity_review_registry] = lambda: svc.registry
    patcher = patch("backend.routers.cts_deps.settings", cfg)
    patcher.start()
    # require_token resolves permissions through the real keystore (auth.yaml).
    invalidate_lookup_cache()
    return TestClient(app), svc, patcher


# ---------------------------------------------------------------------------
# Auth canary: the central guarantee.
# ---------------------------------------------------------------------------

_ROUTES = [
    ("get", "/api/v1/cts/identity/reid-review/candidates", None),
    ("get", "/api/v1/cts/identity/reid-review/candidates/c1", None),
    ("get", "/api/v1/cts/identity/reid-review/candidates/c1/events", None),
    ("get", "/api/v1/cts/identity/reid-review/counts", None),
    ("post", "/api/v1/cts/identity/reid-review/candidates/c1/approve", {"base_audit_version": 1}),
    (
        "post",
        "/api/v1/cts/identity/reid-review/candidates/c1/relabel",
        {"base_audit_version": 1, "target_identity_id": "appa"},
    ),
    (
        "post",
        "/api/v1/cts/identity/reid-review/candidates/c1/demote",
        {"base_audit_version": 1},
    ),
    (
        "post",
        "/api/v1/cts/identity/reid-review/candidates/c1/reject",
        {"base_audit_version": 1, "reason": "wrong_person"},
    ),
    (
        "post",
        "/api/v1/cts/identity/reid-review/review",
        {"verdict": "not_enrolled", "items": [{"candidate_id": "c1", "base_audit_version": 1}]},
    ),
    ("post", "/api/v1/cts/identity/reid-review/candidates/c1/compensate", {}),
]


@pytest.mark.parametrize("perms", [["cts.identity.view"], ["cts.identity.correct"], ["caregiver"]])
def test_view_or_correct_alone_cannot_access_any_route(perms):
    client, _, patcher = _build_app(perms)
    try:
        for method, path, body in _ROUTES:
            resp = (
                getattr(client, method)(path, json=body)
                if body is not None
                else getattr(client, method)(path)
            )
            assert resp.status_code == 403, f"{method} {path} leaked to {perms}: {resp.status_code}"
    finally:
        patcher.stop()


@pytest.mark.parametrize("perms", [["cts.identity.gallery_review"], ["caregiver_admin"], ["*"]])
def test_gallery_review_token_grants_access(perms):
    client, _, patcher = _build_app(perms)
    try:
        for method, path, body in _ROUTES:
            resp = (
                getattr(client, method)(path, json=body)
                if body is not None
                else getattr(client, method)(path)
            )
            assert resp.status_code == 200, (
                f"{method} {path} denied for {perms}: {resp.status_code}"
            )
    finally:
        patcher.stop()


# ---------------------------------------------------------------------------
# Behaviour with the gallery-review grant.
# ---------------------------------------------------------------------------


@pytest.fixture
def client_authorized():
    c, svc, p = _build_app(["cts.identity.gallery_review"])
    yield c, svc
    p.stop()


def test_list_returns_candidates(client_authorized):
    client, _ = client_authorized
    body = client.get("/api/v1/cts/identity/reid-review/candidates").json()
    assert body["total"] == 1
    assert body["candidates"][0]["person_id"] == "amma"


def test_detail_includes_eligibility(client_authorized):
    client, _ = client_authorized
    body = client.get("/api/v1/cts/identity/reid-review/candidates/c1").json()
    assert body["eligibility"]["eligible"] is True


def test_actor_is_server_injected_not_from_body(client_authorized):
    client, svc = client_authorized
    # A browser-supplied actor must be ignored (extra=forbid rejects it).
    resp = client.post(
        "/api/v1/cts/identity/reid-review/candidates/c1/approve",
        json={"base_audit_version": 1, "actor": "attacker"},
    )
    assert resp.status_code == 422  # extra="forbid"
    # The valid call injects the auth-context subject.
    resp2 = client.post(
        "/api/v1/cts/identity/reid-review/candidates/c1/approve",
        json={"base_audit_version": 1},
    )
    assert resp2.status_code == 200
    assert svc.approve.await_args.kwargs["actor"] != "attacker"


def test_demote_returns_pending_review(client_authorized):
    """M02: demote un-trusts an auto_verified row back to pending_review."""
    client, svc = client_authorized
    resp = client.post(
        "/api/v1/cts/identity/reid-review/candidates/c1/demote",
        json={"base_audit_version": 1},
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "pending_review"
    assert svc.demote.await_args.kwargs["actor"] != "attacker"


def test_demote_actor_is_server_injected_not_from_body(client_authorized):
    client, _ = client_authorized
    resp = client.post(
        "/api/v1/cts/identity/reid-review/candidates/c1/demote",
        json={"base_audit_version": 1, "actor": "attacker"},
    )
    assert resp.status_code == 422  # extra="forbid"


def test_no_bulk_approve_route(client_authorized):
    client, _ = client_authorized
    assert client.post("/api/v1/cts/identity/reid-review/approve-batch", json={}).status_code == 404


def test_batch_review_reports_results_and_records_the_caller(client_authorized):
    client, svc = client_authorized
    resp = client.post(
        "/api/v1/cts/identity/reid-review/review",
        json={
            "verdict": "not_usable",
            "reason": "low_quality",
            "items": [{"candidate_id": "c1", "base_audit_version": 1}],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["reviewed"] == 1
    args, kwargs = svc.registry.decide.await_args
    assert args == ("reid_review", "not_usable", [ReviewSubject("c1", 1)])
    assert (kwargs["reason"], kwargs["note"]) == ("low_quality", None)
    assert kwargs["actor"]


@pytest.mark.parametrize(
    "body",
    [
        {"verdict": "not_usable", "items": [{"candidate_id": "c1", "base_audit_version": 1}]},
        {
            "verdict": "not_enrolled",
            "reason": "low_quality",
            "items": [{"candidate_id": "c1", "base_audit_version": 1}],
        },
        {"verdict": "is_member", "items": [{"candidate_id": "c1", "base_audit_version": 1}]},
        {"verdict": "not_usable", "reason": "wrong_person", "items": []},
    ],
)
def test_batch_review_refuses_approval_and_mismatched_reasons(client_authorized, body):
    client, svc = client_authorized
    resp = client.post("/api/v1/cts/identity/reid-review/review", json=body)
    assert resp.status_code == 422
    svc.registry.decide.assert_not_called()


def test_the_old_batch_reject_route_is_gone(client_authorized):
    client, _ = client_authorized
    assert client.post("/api/v1/cts/identity/reid-review/reject-batch", json={}).status_code in (
        404,
        405,
    )


def test_stale_upstream_409_passthrough(client_authorized):
    client, svc = client_authorized
    svc.approve = AsyncMock(
        side_effect=ReviewUpstreamError(status=409, code="reid_review.stale", message="moved")
    )
    resp = client.post(
        "/api/v1/cts/identity/reid-review/candidates/c1/approve",
        json={"base_audit_version": 1},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "reid_review.stale"


def test_ineligible_upstream_409_passthrough(client_authorized):
    client, svc = client_authorized
    svc.approve = AsyncMock(
        side_effect=ReviewUpstreamError(
            status=409, code="reid_review.ineligible", message="incompatible_model:v0"
        )
    )
    resp = client.post(
        "/api/v1/cts/identity/reid-review/candidates/c1/approve",
        json={"base_audit_version": 1},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "reid_review.ineligible"


# ---------------------------------------------------------------------------
# MCP exemption (operational biometric-admin surface, not agent-facing).
# ---------------------------------------------------------------------------


def test_no_mcp_tool_for_reid_review():
    """Gallery review is intentionally not an MCP tool (documented exemption).

    Exposing approve/relabel/demote/reject to an unattended agent would let it
    re-identify a household member, or silently un-trust a machine-verified
    one, without operator review. M02 adds demote to the same exemption.
    """
    configured = settings.get("mcp.tools", []) or []
    names = " ".join(str(t) for t in configured).lower()
    assert "reid_review" not in names
    assert "gallery_review" not in names
    assert "demote" not in names
