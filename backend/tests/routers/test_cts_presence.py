"""Tests for the CTS presence smoke router."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.core.exceptions import register_exception_handlers
from backend.services.presence import (
    PresenceService,
    PresenceSnapshot,
    PresenceSource,
    PresenceStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_snapshot(
    *,
    status: PresenceStatus = PresenceStatus.PRESENT_ROOM,
    room_name: str = "bedroom",
    confidence: float = 0.85,
) -> PresenceSnapshot:
    at = datetime.now(UTC)
    return PresenceSnapshot(
        person_id="mom",
        status=status,
        room_id=1,
        room_name=room_name,
        confidence=confidence,
        last_seen_at=at,
        dwell_minutes=15.0,
        sources=(PresenceSource(name="cts_location", confidence=confidence),),
        inferred_at=at,
    )


@pytest.fixture
def presence_service() -> PresenceService:
    mock_provider = MagicMock()
    mock_provider.name = "cts_location"
    mock_provider.priority = 50
    mock_provider.probe = AsyncMock(return_value=_make_snapshot())

    return PresenceService(providers=[mock_provider], confidence_floor=0.0)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cts_disabled_returns_404():
    """When cts.enabled=False, return 404 with cts.disabled code."""
    mock_settings = MagicMock()
    mock_settings.get = MagicMock(side_effect=lambda key, default=None: {
        "cts.enabled": False,
    }.get(key, default))

    app = FastAPI()
    register_exception_handlers(app)

    from backend.routers.cts_presence import router

    app.include_router(router, prefix="/api/v1")
    app.state.presence = None

    with patch("backend.routers.cts_presence.settings", mock_settings):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/cts/presence/mom")

    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["code"] == "cts.disabled"


@pytest.mark.asyncio
async def test_person_not_in_repo_returns_unknown(presence_service: PresenceService):
    """When no provider returns a snapshot, return UNKNOWN."""
    # Override the provider to return None
    mock_provider = MagicMock()
    mock_provider.name = "cts_location"
    mock_provider.priority = 50
    mock_provider.probe = AsyncMock(return_value=None)

    presence_service._providers = [mock_provider]

    mock_settings = MagicMock()
    mock_settings.get = MagicMock(side_effect=lambda key, default=None: {
        "cts.enabled": True,
    }.get(key, default))

    app = FastAPI()
    register_exception_handlers(app)

    from backend.routers.cts_presence import router

    app.include_router(router, prefix="/api/v1")
    app.state.presence = presence_service

    with patch("backend.routers.cts_presence.settings", mock_settings):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/cts/presence/mom")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == PresenceStatus.UNKNOWN
    assert body["sources"] == []


@pytest.mark.asyncio
async def test_person_in_repo_returns_present_room(presence_service: PresenceService):
    """When a provider returns a snapshot, return it with correct fields."""
    mock_settings = MagicMock()
    mock_settings.get = MagicMock(side_effect=lambda key, default=None: {
        "cts.enabled": True,
    }.get(key, default))

    app = FastAPI()
    register_exception_handlers(app)

    from backend.routers.cts_presence import router

    app.include_router(router, prefix="/api/v1")
    app.state.presence = presence_service

    with patch("backend.routers.cts_presence.settings", mock_settings):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/cts/presence/mom")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == PresenceStatus.PRESENT_ROOM
    assert body["room_name"] == "bedroom"
    assert body["confidence"] == 0.85
    assert body["person_id"] == "mom"
    assert len(body["sources"]) == 1
    assert body["sources"][0]["name"] == "cts_location"
