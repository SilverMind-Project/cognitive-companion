"""U2-T6: MCP tools with unavailable dependencies raise, never return fake records.

Rule 15: no silent fallbacks. A missing dependency is a contract violation;
the tool must raise (so the MCP protocol represents it as a failure) not
return a list-of-one fabricated message like {"message": "...not available"}.
"""

from __future__ import annotations

import pytest

from backend.mcp.server import (
    _svc,
    get_person_activities,
    get_person_location,
    get_person_locations,
    get_person_sightings,
    get_room_occupancy,
)


@pytest.fixture(autouse=True)
def reset_svc():
    """Ensure _svc is clean around each test."""
    original = _svc.__dict__.copy()
    yield
    for k, v in original.items():
        setattr(_svc, k, v)


# ---------------------------------------------------------------------------
# get_person_locations: raises RuntimeError when PersonLocationService is None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_person_locations_raises_when_pls_unavailable():
    _svc.person_location_service = None
    with pytest.raises(RuntimeError, match="PersonLocationService not available"):
        await get_person_locations()


@pytest.mark.asyncio
async def test_get_person_locations_never_returns_message_dict():
    """Must never return [{"message": ...}]."""
    _svc.person_location_service = None
    try:
        result = await get_person_locations()
    except RuntimeError:
        return  # correct path
    # If it somehow returned, assert it's not a fake message
    if isinstance(result, list) and result:
        for item in result:
            assert "message" not in item, "Silent fallback message record returned"


# ---------------------------------------------------------------------------
# get_person_location (single): raises when PLS unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_person_location_raises_when_pls_unavailable():
    _svc.person_location_service = None
    with pytest.raises(RuntimeError, match="PersonLocationService not available"):
        await get_person_location("alice")


# ---------------------------------------------------------------------------
# get_room_occupancy: raises when the occupancy read-model is unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_room_occupancy_raises_when_model_unavailable():
    _svc.occupancy_read_model = None
    with pytest.raises(RuntimeError, match="OccupancyReadModel not available"):
        await get_room_occupancy()


@pytest.mark.asyncio
async def test_get_room_occupancy_never_returns_message_dict():
    _svc.occupancy_read_model = None
    try:
        result = await get_room_occupancy()
    except RuntimeError:
        return
    if isinstance(result, dict):
        assert "message" not in result, "Silent fallback message dict returned"


# ---------------------------------------------------------------------------
# get_person_sightings: raises when person_tracking unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_person_sightings_raises_when_tracking_unavailable():
    _svc.person_tracking = None
    with pytest.raises(RuntimeError, match="PersonTrackingService not available"):
        await get_person_sightings("alice")


@pytest.mark.asyncio
async def test_get_person_sightings_never_returns_message_dict():
    _svc.person_tracking = None
    try:
        result = await get_person_sightings("alice")
    except RuntimeError:
        return
    if isinstance(result, list) and result:
        for item in result:
            assert "message" not in item, "Silent fallback message record returned"


# ---------------------------------------------------------------------------
# get_person_activities: raises when person_tracking unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_person_activities_raises_when_tracking_unavailable():
    _svc.person_tracking = None
    with pytest.raises(RuntimeError, match="PersonTrackingService not available"):
        await get_person_activities("alice")


@pytest.mark.asyncio
async def test_get_person_activities_never_returns_message_dict():
    _svc.person_tracking = None
    try:
        result = await get_person_activities("alice")
    except RuntimeError:
        return
    if isinstance(result, list) and result:
        for item in result:
            assert "message" not in item, "Silent fallback message record returned"
