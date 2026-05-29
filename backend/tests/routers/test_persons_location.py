"""U2-T4: persons_location router tests — envelope shape + auth enforcement."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.database import get_db
from backend.core.exceptions import register_exception_handlers
from backend.routers.persons_location import _get_service, router
from backend.services.person_location.types import CurrentLocation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 5, 29, 10, 0, 0, tzinfo=UTC)

_LOC_ALICE = CurrentLocation(
    person_id="alice",
    room_id=1,
    room_name="bedroom",
    since=datetime(2026, 5, 29, 9, 0, 0, tzinfo=UTC),
    entry_source="observed",
    confidence=0.9,
    is_inferred=False,
    quality=0.8,
    last_observed_at=datetime(2026, 5, 29, 9, 55, 0, tzinfo=UTC),
)

_LOC_BOB = CurrentLocation(
    person_id="bob",
    room_id=2,
    room_name="kitchen",
    since=datetime(2026, 5, 29, 8, 0, 0, tzinfo=UTC),
    entry_source="inferred_transit",
    confidence=0.6,
    is_inferred=True,
    quality=0.5,
)


def _build_app(svc_mock, *, permissions: list[str] = ("*",)):
    """Return a TestClient with a mocked PersonLocationService.

    get_db is mocked via a MagicMock session because _lookup_display_name and
    _display_names_for are patched in individual tests — no real DB needed.
    """

    def _mock_db():
        yield MagicMock()

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)

    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=list(permissions)
    )
    app.dependency_overrides[get_db] = _mock_db
    app.dependency_overrides[_get_service] = lambda: svc_mock

    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/v1/persons/{person_id}/location
# ---------------------------------------------------------------------------


class TestGetPersonLocation:
    def test_returns_envelope_shape(self):
        svc = AsyncMock()
        svc.where_is = AsyncMock(return_value=_LOC_ALICE)

        client = _build_app(svc)
        with patch("backend.routers.persons_location._lookup_display_name", return_value="Grandma"):
            resp = client.get("/api/v1/persons/alice/location")

        assert resp.status_code == 200
        body = resp.json()
        # Pre-U2 fields present (D7)
        assert body["person_id"] == "alice"
        assert body["room_id"] == 1
        assert body["room_name"] == "bedroom"
        assert "since" in body
        assert body["entry_source"] == "observed"
        assert pytest.approx(body["confidence"], abs=1e-3) == 0.9
        assert body["is_inferred"] is False
        # New U2 fields
        assert pytest.approx(body["quality"], abs=1e-3) == 0.8
        assert "staleness_seconds" in body
        assert body["source"] == "observation"
        assert body["display_name"] == "Grandma"

    def test_returns_404_when_no_location(self):
        svc = AsyncMock()
        svc.where_is = AsyncMock(return_value=None)

        client = _build_app(svc)
        resp = client.get("/api/v1/persons/unknown/location")
        assert resp.status_code == 404

    def test_auth_permission_required(self):
        """Without the persons.read permission, returns 403."""
        svc = AsyncMock()
        svc.where_is = AsyncMock(return_value=_LOC_ALICE)

        client = _build_app(svc, permissions=[])  # no permissions
        with patch("backend.routers.persons_location._lookup_display_name", return_value=""):
            resp = client.get("/api/v1/persons/alice/location")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/v1/persons/locations  (batch endpoint)
# ---------------------------------------------------------------------------


class TestGetAllPersonLocations:
    def test_returns_list_of_envelopes(self):
        svc = AsyncMock()
        svc.where_is_everyone = AsyncMock(return_value={"alice": _LOC_ALICE, "bob": _LOC_BOB})

        client = _build_app(svc)

        with patch(
            "backend.routers.persons_location._display_names_for",
            return_value={"alice": "Grandma", "bob": "Bob"},
        ):
            resp = client.get("/api/v1/persons/locations")

        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 2
        ids = {e["person_id"] for e in body}
        assert ids == {"alice", "bob"}
        # Each item is an envelope
        for item in body:
            assert "quality" in item
            assert "staleness_seconds" in item
            assert "source" in item

    def test_empty_when_no_segments(self):
        svc = AsyncMock()
        svc.where_is_everyone = AsyncMock(return_value={})

        client = _build_app(svc)
        resp = client.get("/api/v1/persons/locations")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# GET /api/v1/rooms/{room_id}/occupants
# ---------------------------------------------------------------------------


class TestGetRoomOccupants:
    def test_returns_occupancy_envelope(self):
        svc = AsyncMock()
        svc.occupants_of = AsyncMock(return_value=[_LOC_ALICE])

        client = _build_app(svc)

        with patch(
            "backend.routers.persons_location._display_names_for",
            return_value={"alice": "Grandma"},
        ):
            resp = client.get("/api/v1/rooms/1/occupants")

        assert resp.status_code == 200
        body = resp.json()
        # Pre-U2 OccupantsResponse fields present (D7)
        assert "room_id" in body
        assert "as_of" in body
        assert "occupants" in body
        # New U2 field
        assert "room_name" in body
        assert body["room_id"] == 1
        assert len(body["occupants"]) == 1
        occ = body["occupants"][0]
        assert occ["person_id"] == "alice"
        assert "quality" in occ
        assert "staleness_seconds" in occ
        assert "source" in occ

    def test_empty_room(self):
        svc = AsyncMock()
        svc.occupants_of = AsyncMock(return_value=[])

        client = _build_app(svc)
        resp = client.get("/api/v1/rooms/99/occupants")
        assert resp.status_code == 200
        assert resp.json()["occupants"] == []
