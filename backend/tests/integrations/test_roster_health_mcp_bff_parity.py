"""Roster health: the BFF route and the MCP tool read the same service method.

Also covers the route's permission and its mapping of upstream failures.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context, invalidate_lookup_cache
from backend.core.exceptions import register_exception_handlers
from backend.integrations.person_id_client import PersonIDUpstreamError
from backend.mcp.server import _svc
from backend.mcp.server import get_roster_health as mcp_get_roster_health
from backend.routers.dependencies import get_roster_health_service
from backend.routers.persons import router as persons_router
from backend.schemas.identity_roster import RosterHealthEnvelope, RosterMemberRef

_ENVELOPE = RosterHealthEnvelope(
    members_without_face_enrollment=[
        RosterMemberRef(member_id="amma", name="Amma", embedding_count=3)
    ],
    min_face_embeddings=5,
    visitor_clustering_enabled=True,
    surfaced_unnamed_visitor_clusters=2,
    is_complete=False,
    checked_at=datetime(2026, 10, 20, 9, 0, tzinfo=UTC),
)


def _service(result: RosterHealthEnvelope | Exception) -> MagicMock:
    svc = MagicMock()
    if isinstance(result, Exception):
        svc.get_roster_health = AsyncMock(side_effect=result)
    else:
        svc.get_roster_health = AsyncMock(return_value=result)
    return svc


def _client(svc: MagicMock, permissions: list[str]) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(persons_router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="user", permissions=permissions
    )
    app.dependency_overrides[get_roster_health_service] = lambda: svc
    invalidate_lookup_cache()
    return TestClient(app)


@pytest.fixture(autouse=True)
def _restore_mcp_services():
    original = _svc.__dict__.copy()
    yield
    for key, value in original.items():
        setattr(_svc, key, value)


async def test_route_and_mcp_tool_return_the_same_envelope() -> None:
    svc = _service(_ENVELOPE)
    _svc.roster_health_service = svc

    route_body = _client(svc, ["caregiver"]).get("/api/v1/persons/roster-health").json()
    mcp_body = await mcp_get_roster_health()

    assert route_body == mcp_body == _ENVELOPE.model_dump(mode="json")
    assert svc.get_roster_health.await_count == 2


def test_route_requires_a_permission() -> None:
    response = _client(_service(_ENVELOPE), []).get("/api/v1/persons/roster-health")
    assert response.status_code == 403


@pytest.mark.parametrize(("upstream", "expected"), [(503, 502), (504, 502), (409, 409)])
def test_route_maps_upstream_failures(upstream: int, expected: int) -> None:
    svc = _service(PersonIDUpstreamError(upstream, "person-id unavailable"))
    response = _client(svc, ["caregiver"]).get("/api/v1/persons/roster-health")
    assert response.status_code == expected


async def test_mcp_tool_reports_upstream_failure_as_error() -> None:
    _svc.roster_health_service = _service(PersonIDUpstreamError(502, "unreachable"))
    assert await mcp_get_roster_health() == {"error": "unreachable"}


async def test_mcp_tool_without_service_reports_unavailable() -> None:
    _svc.roster_health_service = None
    assert await mcp_get_roster_health() == {"error": "roster_health_service unavailable"}
