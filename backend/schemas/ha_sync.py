"""Home Assistant sync/query response schemas."""

from __future__ import annotations

from backend.schemas.common import OutSchema


class HaSyncRoomsOut(OutSchema):
    """Result of syncing HA areas into rooms.

    Every field is optional because the endpoint returns one of two disjoint shapes with a 200:
    ``{"error": "Home Assistant not configured"}`` or ``{"created", "updated", "total_areas"}``.
    This models the contract as it is rather than pretending; the union is the underlying
    problem (a missing integration should be a typed 503, and `RoomsView.vue:121` renders
    "Created undefined" today when it hits the error branch), but changing the status code is a
    behavioral change outside M17's scope.
    """

    error: str | None = None
    created: int | None = None
    updated: int | None = None
    total_areas: int | None = None


class HaSyncSensorsOut(OutSchema):
    """Result of syncing HA entities into sensors. Same two-shape caveat as HaSyncRoomsOut."""

    error: str | None = None
    created: int | None = None
    updated: int | None = None
    skipped: int | None = None


class HaEntityOut(OutSchema):
    """One Home Assistant entity, as the step-config dropdowns consume it."""

    entity_id: str
    name: str
