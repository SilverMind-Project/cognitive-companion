"""Tests for the M06 correction-targets service.

The authoritative target list is the active household roster. It must survive an
empty or unavailable ReID gallery, and surface upstream gallery errors instead of
dropping targets.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.cts.correction_targets import list_correction_targets


def _member(member_id: str, name: str, *, is_active: bool = True, is_guest: bool = False):
    return SimpleNamespace(id=member_id, name=name, is_active=is_active, is_guest=is_guest)


def _db_returning(members: list) -> MagicMock:
    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = members
    return db


@pytest.mark.asyncio
async def test_targets_from_active_household_with_gallery_decoration() -> None:
    db = _db_returning([_member("alice", "Alice"), _member("bob", "Bob")])
    orchestrator = AsyncMock()
    orchestrator.get_identities.return_value = [
        {"identity_id": "alice", "gallery_entry_count": 4, "gallery_verified_count": 2},
    ]

    result = await list_correction_targets(db, orchestrator)

    assert result.gallery_available is True
    assert [t.identity_id for t in result.targets] == ["alice", "bob"]
    alice = result.targets[0]
    assert alice.gallery_entry_count == 4
    assert alice.gallery_verified_count == 2
    # Bob has no gallery entry -> decoration absent but still a valid target.
    assert result.targets[1].gallery_entry_count is None


@pytest.mark.asyncio
async def test_targets_returned_with_empty_gallery() -> None:
    db = _db_returning([_member("alice", "Alice")])
    orchestrator = AsyncMock()
    orchestrator.get_identities.return_value = []

    result = await list_correction_targets(db, orchestrator)

    assert result.gallery_available is True
    assert [t.identity_id for t in result.targets] == ["alice"]
    assert result.targets[0].gallery_entry_count is None


@pytest.mark.asyncio
async def test_upstream_gallery_error_is_visible_but_targets_survive() -> None:
    db = _db_returning([_member("alice", "Alice"), _member("bob", "Bob")])
    orchestrator = AsyncMock()
    orchestrator.get_identities.side_effect = RuntimeError("orchestrator down")

    result = await list_correction_targets(db, orchestrator)

    assert result.gallery_available is False
    assert result.gallery_error is not None
    assert [t.identity_id for t in result.targets] == ["alice", "bob"]
    assert all(t.gallery_entry_count is None for t in result.targets)


@pytest.mark.asyncio
async def test_no_orchestrator_client_still_returns_targets() -> None:
    db = _db_returning([_member("alice", "Alice")])
    result = await list_correction_targets(db, None)
    assert result.gallery_available is True
    assert [t.identity_id for t in result.targets] == ["alice"]
