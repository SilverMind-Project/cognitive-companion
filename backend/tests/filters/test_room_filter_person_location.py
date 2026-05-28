"""WTR7: RoomFilter tests with PersonLocationService."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.filters.builtin.room import RoomFilter


@pytest.mark.asyncio
async def test_string_person_id_works():
    """RoomFilter must accept string person_id, not require UUID."""
    flt = RoomFilter()
    mock_svc = MagicMock()
    mock_svc.where_is = AsyncMock()
    services = MagicMock()
    services.person_location = mock_svc

    # String person_id (not UUID) must work without error.
    mock_svc.where_is.return_value = None
    result = await flt.evaluate(
        {"person_id": "alice-123", "room_id": "1"},
        sensor=None, now=datetime.now(UTC), services=services,
    )
    assert result is False
    mock_svc.where_is.assert_called_once_with("alice-123")


@pytest.mark.asyncio
async def test_room_id_matches():
    """When room_id config matches current location's room_id, filter passes."""
    flt = RoomFilter()
    mock_svc = MagicMock()
    mock_svc.where_is = AsyncMock()
    services = MagicMock()
    services.person_location = mock_svc

    mock_loc = MagicMock()
    mock_loc.room_id = 3
    mock_svc.where_is.return_value = mock_loc

    result = await flt.evaluate(
        {"person_id": "bob", "room_id": "3"},
        sensor=None, now=datetime.now(UTC), services=services,
    )
    assert result is True


@pytest.mark.asyncio
async def test_room_name_matches():
    """When room_name config matches current location's room_name, filter passes."""
    flt = RoomFilter()
    mock_svc = MagicMock()
    mock_svc.where_is = AsyncMock()
    services = MagicMock()
    services.person_location = mock_svc

    mock_loc = MagicMock()
    mock_loc.room_name = "Living Room"
    mock_svc.where_is.return_value = mock_loc

    result = await flt.evaluate(
        {"person_id": "carol", "room_name": "living room"},
        sensor=None, now=datetime.now(UTC), services=services,
    )
    assert result is True


@pytest.mark.asyncio
async def test_no_uuid_coercion():
    """UUID coercion must not be present — person_id is a string."""
    flt = RoomFilter()
    # This person_id is clearly not a UUID. It must not raise ValueError.
    result = await flt.evaluate(
        {"person_id": "simple-name", "room_id": "1"},
        sensor=None, now=datetime.now(UTC), services=None,
    )
    assert result is False  # no services, just verify no crash
