"""GET /api/v1/identity/targets: one list for every identity decision, without CTS."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context, invalidate_lookup_cache
from backend.core.exceptions import register_exception_handlers
from backend.routers.dependencies import get_identity_targets_service
from backend.routers.identity_targets import router
from backend.services.identity_targets import IdentityTarget, IdentityTargetsResult

_RESULT = IdentityTargetsResult(
    targets=[
        IdentityTarget(
            identity_id="resident",
            display_name="Resident",
            is_active=True,
            is_guest=False,
            face_enrolled=True,
        ),
        IdentityTarget(
            identity_id="helper",
            display_name="Helper",
            is_active=True,
            is_guest=True,
            face_enrolled=False,
        ),
    ],
    gallery_available=False,
    gallery_error="cts disabled",
    enrollment_available=True,
)


def _client(permissions: list[str]) -> TestClient:
    svc = MagicMock()
    svc.list_targets = AsyncMock(return_value=_RESULT)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="user", permissions=permissions
    )
    app.dependency_overrides[get_identity_targets_service] = lambda: svc
    invalidate_lookup_cache()
    return TestClient(app)


@pytest.mark.parametrize("role", ["caregiver", "caregiver_admin"])
def test_caregiver_roles_get_the_targets(role: str) -> None:
    body = _client([role]).get("/api/v1/identity/targets").json()

    assert [(t["identity_id"], t["face_enrolled"], t["is_guest"]) for t in body["targets"]] == [
        ("resident", True, False),
        ("helper", False, True),
    ]
    assert (body["enrollment_available"], body["gallery_available"]) == (True, False)


def test_a_key_without_the_token_is_forbidden() -> None:
    assert _client(["rooms:read"]).get("/api/v1/identity/targets").status_code == 403


@pytest.mark.parametrize("role", ["caregiver", "caregiver_admin"])
def test_caregiver_roles_read_the_review_vocabulary(role: str) -> None:
    body = _client([role]).get("/api/v1/identity/review-vocabulary").json()

    by_surface = {s["surface"]: s for s in body["surfaces"]}
    assert set(by_surface) == {"visitors", "face_calibration", "reid_review"}
    visitors = {v["verdict"]: v for v in by_surface["visitors"]["verdicts"]}
    assert visitors["is_member"]["needs_enrolled_face"] is True
    assert body["member_placeholder"] in visitors["is_member"]["effect"]


def test_review_vocabulary_needs_its_token() -> None:
    assert (
        _client(["identity_targets:read"]).get("/api/v1/identity/review-vocabulary").status_code
        == 403
    )
