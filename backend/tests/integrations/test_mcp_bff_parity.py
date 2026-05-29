"""U2-T1: MCP tool and BFF endpoint return same data from same service (D6 parity).

For each unified concept, the MCP tool and the BFF endpoint call the same
service function so they can never diverge.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.database import get_db
from backend.core.exceptions import register_exception_handlers
from backend.mcp.server import _svc
from backend.mcp.server import get_person_locations as mcp_get_person_locations
from backend.routers.persons_location import _get_service
from backend.routers.persons_location import router as loc_router
from backend.services.person_location.types import CurrentLocation

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 5, 29, 12, 0, 0, tzinfo=UTC)

_LOC_ALICE = CurrentLocation(
    person_id="alice",
    room_id=1,
    room_name="bedroom",
    since=datetime(2026, 5, 29, 10, 0, 0, tzinfo=UTC),
    entry_source="observed",
    confidence=0.9,
    is_inferred=False,
    quality=0.75,
    last_observed_at=datetime(2026, 5, 29, 11, 55, 0, tzinfo=UTC),
)

_LOC_BOB = CurrentLocation(
    person_id="bob",
    room_id=2,
    room_name="kitchen",
    since=datetime(2026, 5, 29, 9, 0, 0, tzinfo=UTC),
    entry_source="inferred_transit",
    confidence=0.6,
    is_inferred=True,
    quality=0.5,
)

_EVERYONE = {"alice": _LOC_ALICE, "bob": _LOC_BOB}


@pytest.fixture(autouse=True)
def reset_svc():
    original = _svc.__dict__.copy()
    yield
    for k, v in original.items():
        setattr(_svc, k, v)


# ---------------------------------------------------------------------------
# Person-location parity: get_person_locations MCP vs GET /persons/locations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_bff_person_locations_same_person_ids():
    """MCP get_person_locations and BFF /persons/locations return the same person ids."""
    svc_mock = AsyncMock()
    svc_mock.where_is_everyone = AsyncMock(return_value=_EVERYONE)

    # MCP path
    _svc.person_location_service = svc_mock
    mcp_results = await mcp_get_person_locations()
    mcp_ids = {r["person_id"] for r in mcp_results}

    # BFF path
    svc_mock.where_is_everyone.reset_mock()
    svc_mock.where_is_everyone = AsyncMock(return_value=_EVERYONE)

    def _mock_db():
        yield MagicMock()

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(loc_router)
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )
    app.dependency_overrides[get_db] = _mock_db
    app.dependency_overrides[_get_service] = lambda: svc_mock

    with patch(
        "backend.routers.persons_location._display_names_for",
        return_value={"alice": "Grandma", "bob": "Bob"},
    ):
        client = TestClient(app)
        resp = client.get("/api/v1/persons/locations")

    bff_ids = {item["person_id"] for item in resp.json()}

    assert mcp_ids == bff_ids, f"MCP returned {mcp_ids}, BFF returned {bff_ids}"


@pytest.mark.asyncio
async def test_mcp_bff_person_locations_same_room_ids():
    """MCP and BFF report the same room_id for each person."""
    svc_mock = AsyncMock()
    svc_mock.where_is_everyone = AsyncMock(return_value=_EVERYONE)

    _svc.person_location_service = svc_mock
    mcp_results = await mcp_get_person_locations()
    mcp_by_person = {r["person_id"]: r["room_id"] for r in mcp_results}

    svc_mock.where_is_everyone = AsyncMock(return_value=_EVERYONE)

    def _mock_db():
        yield MagicMock()

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(loc_router)
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )
    app.dependency_overrides[get_db] = _mock_db
    app.dependency_overrides[_get_service] = lambda: svc_mock

    with patch(
        "backend.routers.persons_location._display_names_for",
        return_value={"alice": "", "bob": ""},
    ):
        client = TestClient(app)
        resp = client.get("/api/v1/persons/locations")

    bff_by_person = {item["person_id"]: item["room_id"] for item in resp.json()}

    assert mcp_by_person == bff_by_person


@pytest.mark.asyncio
async def test_mcp_person_locations_carries_quality_field():
    """MCP results carry the quality field from the SSOT (D5)."""
    svc_mock = AsyncMock()
    svc_mock.where_is_everyone = AsyncMock(return_value={"alice": _LOC_ALICE})

    _svc.person_location_service = svc_mock
    mcp_results = await mcp_get_person_locations()

    assert len(mcp_results) == 1
    assert "quality" in mcp_results[0]
    assert pytest.approx(mcp_results[0]["quality"], abs=1e-3) == 0.75


@pytest.mark.asyncio
async def test_mcp_person_locations_empty_when_no_segments():
    svc_mock = AsyncMock()
    svc_mock.where_is_everyone = AsyncMock(return_value={})

    _svc.person_location_service = svc_mock
    result = await mcp_get_person_locations()
    assert result == []
