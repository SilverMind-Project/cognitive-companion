"""WTR7/R2: RoomFilter tests with PersonLocationService SSOT."""

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

    mock_svc.where_is.return_value = None
    result = await flt.evaluate(
        {"person_id": "alice-123", "room_id": "1"},
        sensor=None,
        now=datetime.now(UTC),
        services=services,
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
        sensor=None,
        now=datetime.now(UTC),
        services=services,
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
        sensor=None,
        now=datetime.now(UTC),
        services=services,
    )
    assert result is True


@pytest.mark.asyncio
async def test_fail_closed_no_person_location():
    """R2: when services.person_location is None, filter fails closed."""
    flt = RoomFilter()
    services = MagicMock()
    services.person_location = None
    result = await flt.evaluate(
        {"person_id": "alice", "room_id": "1"},
        sensor=None,
        now=datetime.now(UTC),
        services=services,
    )
    assert result is False


@pytest.mark.asyncio
async def test_fail_closed_no_services():
    """R2: when services is None, filter fails closed (no sensor fallback)."""
    flt = RoomFilter()
    result = await flt.evaluate(
        {"person_id": "alice", "room_id": "1"},
        sensor=None,
        now=datetime.now(UTC),
        services=None,
    )
    assert result is False


@pytest.mark.asyncio
async def test_no_person_id_returns_false():
    """When no person_id in config, returns False immediately."""
    flt = RoomFilter()
    result = await flt.evaluate(
        {"room_name": "Kitchen"},
        sensor=None,
        now=datetime.now(UTC),
        services=None,
    )
    assert result is False


@pytest.mark.asyncio
async def test_no_uuid_coercion():
    """UUID coercion must not be present -- person_id is a string."""
    flt = RoomFilter()
    result = await flt.evaluate(
        {"person_id": "simple-name", "room_id": "1"},
        sensor=None,
        now=datetime.now(UTC),
        services=None,
    )
    assert result is False  # no services, fails closed
