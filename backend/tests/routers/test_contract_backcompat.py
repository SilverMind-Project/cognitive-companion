"""U2-T9: D7 back-compat gate — BFF envelopes are strict supersets of pre-U2 shapes.

For each reshaped BFF endpoint, the response contains every field name it
returned before U2. A renamed or dropped key fails this test, proving U2
is independently deployable and does not break the live UI or openclaw.

Pre-U2 shapes (frozen):
  CurrentLocationOut: {person_id, room_id, room_name, since, entry_source, confidence, is_inferred}
  OccupantsResponse:  {room_id, as_of, occupants}
    occupants[*]:     same as CurrentLocationOut

MCP back-compat notes (documented per D7 escape hatch):
  get_person_location and get_room_occupancy have intentionally changed shape
  because their data source changed from legacy tables/sensor_polling to
  PersonLocationService SSOT. These are dev-stage; external MCP back-compat
  is intentionally dropped for these two tools. This test covers BFF only.
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
from backend.routers.persons_location import _get_service
from backend.routers.persons_location import router as loc_router
from backend.services.person_location.types import CurrentLocation

# ---------------------------------------------------------------------------
# Pre-U2 field sets (frozen reference — do not update without a breaking-change note)
# ---------------------------------------------------------------------------

PRE_U2_CURRENT_LOCATION_OUT_FIELDS = frozenset(
    {
        "person_id",
        "room_id",
        "room_name",
        "since",
        "entry_source",
        "confidence",
        "is_inferred",
    }
)

PRE_U2_OCCUPANTS_RESPONSE_FIELDS = frozenset(
    {
        "room_id",
        "as_of",
        "occupants",
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LOC = CurrentLocation(
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


def _build_app(svc_mock):
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
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /persons/{person_id}/location
# ---------------------------------------------------------------------------


class TestPersonLocationBackCompat:
    def test_single_location_is_superset_of_pre_u2(self):
        svc = AsyncMock()
        svc.where_is = AsyncMock(return_value=_LOC)
        client = _build_app(svc)

        with patch("backend.routers.persons_location._lookup_display_name", return_value=""):
            resp = client.get("/api/v1/persons/alice/location")

        assert resp.status_code == 200
        body = resp.json()
        missing = PRE_U2_CURRENT_LOCATION_OUT_FIELDS - set(body.keys())
        assert not missing, f"GET /persons/{{id}}/location dropped pre-U2 fields: {missing}"

    def test_all_pre_u2_field_values_preserved(self):
        """Verify field values, not just presence."""
        svc = AsyncMock()
        svc.where_is = AsyncMock(return_value=_LOC)
        client = _build_app(svc)

        with patch("backend.routers.persons_location._lookup_display_name", return_value=""):
            resp = client.get("/api/v1/persons/alice/location")

        body = resp.json()
        assert body["person_id"] == "alice"
        assert body["room_id"] == 1
        assert body["room_name"] == "bedroom"
        assert body["entry_source"] == "observed"
        assert pytest.approx(body["confidence"], abs=1e-3) == 0.9
        assert body["is_inferred"] is False
        assert "since" in body


# ---------------------------------------------------------------------------
# GET /persons/locations (batch)
# ---------------------------------------------------------------------------


class TestBatchLocationsBackCompat:
    def test_batch_items_are_supersets_of_pre_u2(self):
        svc = AsyncMock()
        svc.where_is_everyone = AsyncMock(return_value={"alice": _LOC})
        client = _build_app(svc)

        with patch(
            "backend.routers.persons_location._display_names_for",
            return_value={"alice": ""},
        ):
            resp = client.get("/api/v1/persons/locations")

        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        missing = PRE_U2_CURRENT_LOCATION_OUT_FIELDS - set(items[0].keys())
        assert not missing, f"Batch endpoint dropped pre-U2 fields: {missing}"


# ---------------------------------------------------------------------------
# GET /rooms/{room_id}/occupants
# ---------------------------------------------------------------------------


class TestRoomOccupantsBackCompat:
    def test_occupancy_response_is_superset_of_pre_u2(self):
        svc = AsyncMock()
        svc.occupants_of = AsyncMock(return_value=[_LOC])
        client = _build_app(svc)

        with patch(
            "backend.routers.persons_location._display_names_for",
            return_value={"alice": ""},
        ):
            resp = client.get("/api/v1/rooms/1/occupants")

        assert resp.status_code == 200
        body = resp.json()

        # Top-level OccupantsResponse fields
        missing_top = PRE_U2_OCCUPANTS_RESPONSE_FIELDS - set(body.keys())
        assert not missing_top, f"Room occupancy dropped pre-U2 top-level fields: {missing_top}"

        # Each occupant is a superset of pre-U2 CurrentLocationOut
        assert isinstance(body["occupants"], list)
        for occ in body["occupants"]:
            missing_occ = PRE_U2_CURRENT_LOCATION_OUT_FIELDS - set(occ.keys())
            assert not missing_occ, f"Occupant dropped pre-U2 fields: {missing_occ}"
