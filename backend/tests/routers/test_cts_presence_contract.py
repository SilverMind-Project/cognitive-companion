"""Contract tests for the CTS presence BFF endpoint shape (Block 9).

These tests assert that the JSON response from ``GET /api/v1/cts/presence/{id}``
matches the ``PresenceSnapshotOut`` Pydantic model exactly.  Any change
to response keys or types is a breaking API change.

Verification: ``make check``.
"""

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
    room_id: int = 1,
    confidence: float = 0.85,
    person_id: str = "mom",
    notes: str | None = "anchored, bedroom lights off, bed sensor on",
) -> PresenceSnapshot:
    now = datetime.now(UTC)
    return PresenceSnapshot(
        person_id=person_id,
        status=status,
        room_id=room_id,
        room_name=room_name,
        confidence=confidence,
        last_seen_at=now,
        dwell_minutes=15.0,
        sources=(PresenceSource(name="cts_location", confidence=confidence),),
        inferred_at=now,
        notes=notes,
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
async def test_response_keys_match_contract(presence_service: PresenceService):
    """Assert every expected key is present in the JSON response."""
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
            resp = await client.get("/api/v1/cts/mom")

    assert resp.status_code == 200
    body = resp.json()

    # All expected top-level keys must be present.
    expected_keys = {
        "person_id",
        "status",
        "room_id",
        "room_name",
        "confidence",
        "last_seen_at",
        "dwell_minutes",
        "sources",
        "inferred_at",
        "notes",
    }
    assert set(body.keys()) == expected_keys, (
        f"Response keys {set(body.keys())} != expected {expected_keys}"
    )


@pytest.mark.asyncio
async def test_response_types(presence_service: PresenceService):
    """Assert every field has the correct JSON type."""
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
            resp = await client.get("/api/v1/cts/mom")

    body = resp.json()

    assert isinstance(body["person_id"], str)
    assert isinstance(body["status"], str)
    assert isinstance(body["room_id"], str)
    assert isinstance(body["room_name"], str)
    assert isinstance(body["confidence"], (int, float))
    assert isinstance(body["last_seen_at"], str)
    assert isinstance(body["dwell_minutes"], (int, float))
    assert isinstance(body["sources"], list)
    assert isinstance(body["inferred_at"], str)
    assert isinstance(body["notes"], str)

    # Each source has name + confidence.
    for source in body["sources"]:
        assert set(source.keys()) == {"name", "confidence"}
        assert isinstance(source["name"], str)
        assert isinstance(source["confidence"], (int, float))


@pytest.mark.asyncio
async def test_unknown_snapshot_empty_sources(presence_service: PresenceService):
    """When no provider matches, sources must be an empty list (not null)."""
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
            resp = await client.get("/api/v1/cts/mom")

    body = resp.json()
    assert body["status"] == PresenceStatus.UNKNOWN
    assert body["sources"] == []
    assert body["room_id"] is None
    assert body["room_name"] is None
    assert body["confidence"] == 0.0
    assert body["last_seen_at"] is None
    assert body["dwell_minutes"] is None
