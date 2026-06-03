"""GET /signals/feed + MCP parity (D6): both read SignalsFeedService.list_feed."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from backend.mcp.server import _svc
from backend.mcp.server import get_signals_feed as mcp_get_signals_feed
from backend.routers.signals_feed import get_signals_feed as router_get_signals_feed
from backend.schemas.signals_feed import SignalEnvelope

_ENVELOPES = [
    SignalEnvelope(
        id="cts:1",
        source="cts",
        kind="bathroom_dwell_anomaly",
        severity="emergency",
        room_name="bathroom",
        person_id="alice",
        display_name="Alice",
        created_at=datetime(2026, 6, 3, 11, 0, tzinfo=UTC),
        resolved=False,
        detail="Bathroom dwell anomaly",
        can_acknowledge=True,
        can_delete=True,
    ),
    SignalEnvelope(
        id="rule:42",
        source="pipeline_rule",
        kind="Bathroom watch",
        severity="warning",
        room_name="bathroom",
        created_at=datetime(2026, 6, 3, 10, 0, tzinfo=UTC),
        detail="Long dwell",
    ),
]


@pytest.mark.asyncio
async def test_router_and_mcp_parity():
    stub = AsyncMock()
    stub.list_feed = AsyncMock(return_value=_ENVELOPES)

    router_result = await router_get_signals_feed(
        source=None,
        severity_min="info",
        person_id=None,
        room_name=None,
        window_hours=24,
        limit=50,
        svc=stub,
        _auth=None,
    )

    original = _svc.signals_feed
    _svc.signals_feed = stub
    try:
        mcp_result = await mcp_get_signals_feed()
    finally:
        _svc.signals_feed = original

    assert [e.id for e in router_result] == [r["id"] for r in mcp_result]
    assert [e.severity for e in router_result] == [r["severity"] for r in mcp_result]
    assert [e.source for e in router_result] == [r["source"] for r in mcp_result]
    # MCP rows carry the cross-source fields the UI needs.
    assert mcp_result[0]["room_name"] == "bathroom"
    assert mcp_result[0]["created_at"] == "2026-06-03T11:00:00+00:00"
