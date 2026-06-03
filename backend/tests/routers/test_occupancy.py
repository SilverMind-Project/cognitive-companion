"""Tests for GET /occupancy and MCP/BFF parity on the occupancy read-model."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.mcp.server import _svc
from backend.mcp.server import get_room_occupancy as mcp_get_room_occupancy
from backend.routers.occupancy import get_occupancy as router_get_occupancy
from backend.services.occupancy import OccupancyReadModel


def _model_with_data() -> OccupancyReadModel:
    model = OccupancyReadModel()
    now = datetime.now(UTC)
    model.record_room_presence(
        room_id=1, room_name="kitchen", ph_id="ph-a", identity_id="alice", observed_at=now
    )
    model.record_room_presence(
        room_id=1, room_name="kitchen", ph_id="ph-x", identity_id=None, observed_at=now
    )
    return model


@pytest.mark.asyncio
async def test_router_shape_includes_unknown_count():
    model = _model_with_data()
    result = await router_get_occupancy(room_name=None, auth=None, model=model)
    kitchen = result["occupancy"]["kitchen"]
    assert kitchen["occupied"] is True
    assert kitchen["person_ids"] == ["alice"]
    assert kitchen["unknown_count"] == 1
    assert kitchen["source"] == "world_tracker"


@pytest.mark.asyncio
async def test_router_and_mcp_parity():
    """D6: both surfaces read OccupancyReadModel.get_occupancy()."""
    model = _model_with_data()
    original = _svc.occupancy_read_model
    _svc.occupancy_read_model = model
    try:
        router_result = await router_get_occupancy(room_name=None, auth=None, model=model)
        mcp_result = await mcp_get_room_occupancy()
    finally:
        _svc.occupancy_read_model = original

    router_kitchen = router_result["occupancy"]["kitchen"]
    mcp_kitchen = next(r for r in mcp_result if r["room_name"] == "kitchen")
    assert router_kitchen["person_ids"] == mcp_kitchen["person_ids"]
    assert router_kitchen["unknown_count"] == mcp_kitchen["unknown_count"]
    assert router_kitchen["source"] == mcp_kitchen["source"]
    assert router_kitchen["occupied"] == mcp_kitchen["occupied"]
