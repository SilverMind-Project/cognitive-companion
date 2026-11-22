"""Identity readiness: the BFF route and the MCP tool read the same service method."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context, invalidate_lookup_cache
from backend.core.exceptions import register_exception_handlers
from backend.mcp.server import _svc
from backend.mcp.server import get_identity_readiness as mcp_get_identity_readiness
from backend.routers.dependencies import get_identity_readiness_service
from backend.routers.identity_readiness import router
from backend.schemas.identity_readiness import (
    IdentityReadinessEnvelope,
    ReadinessStep,
    ReviewQueue,
)

_ENVELOPE = IdentityReadinessEnvelope(
    steps=[
        ReadinessStep(
            key="roster",
            state="blocked",
            detail="1 visitor awaits review.",
            next_action="review_visitors",
        ),
        ReadinessStep(
            key="capture",
            state="unknown",
            detail="Could not read person identification; check that it is running.",
            next_action="check_service",
        ),
    ],
    blocking_step="roster",
    review_queues=[
        ReviewQueue(surface="visitors", waiting=1),
        ReviewQueue(surface="face_calibration", waiting=None),
        ReviewQueue(surface="reid_review", waiting=0),
    ],
    checked_at=datetime(2026, 11, 14, 9, 0, tzinfo=UTC),
)


def _service() -> MagicMock:
    svc = MagicMock()
    svc.get_readiness = AsyncMock(return_value=_ENVELOPE)
    return svc


def _client(
    svc: MagicMock,
    roles: list[str] | None = None,
    *,
    tokens: frozenset[str] = frozenset(),
) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="user", roles=list(roles or ()), tokens=tokens
    )
    app.dependency_overrides[get_identity_readiness_service] = lambda: svc
    invalidate_lookup_cache()
    return TestClient(app)


@pytest.fixture(autouse=True)
def _restore_mcp_services():
    original = _svc.__dict__.copy()
    yield
    for key, value in original.items():
        setattr(_svc, key, value)


async def test_route_and_mcp_tool_return_the_same_envelope() -> None:
    svc = _service()
    _svc.identity_readiness_service = svc

    route_body = (
        _client(svc, tokens=frozenset({"identity_readiness:read"}))
        .get("/api/v1/identity/readiness")
        .json()
    )
    mcp_body = await mcp_get_identity_readiness()

    assert route_body == mcp_body == _ENVELOPE.model_dump(mode="json")
    assert svc.get_readiness.await_count == 2


@pytest.mark.parametrize("role", ["caregiver", "caregiver_admin"])
def test_caregiver_roles_may_read(role: str) -> None:
    response = _client(_service(), [role]).get("/api/v1/identity/readiness")
    assert response.status_code == 200


def test_route_without_the_token_is_forbidden() -> None:
    # A key that may read rooms but not identity readiness.
    response = _client(_service(), tokens=frozenset({"rooms:read"})).get(
        "/api/v1/identity/readiness"
    )
    assert response.status_code == 403


async def test_mcp_tool_without_service_reports_unavailable() -> None:
    _svc.identity_readiness_service = None
    assert await mcp_get_identity_readiness() == {"error": "identity_readiness_service unavailable"}
