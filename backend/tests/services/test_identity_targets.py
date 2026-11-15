"""Tests for the identity targets service.

The authoritative target list is the active household roster. It must survive an
empty or unavailable ReID gallery, and surface upstream gallery errors instead of
dropping targets.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.core.exceptions import ValidationError
from backend.integrations.person_id_client import PersonIDUpstreamError
from backend.services.identity_targets import IdentityTargetsService, list_identity_targets


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

    result = await list_identity_targets(db, orchestrator)

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

    result = await list_identity_targets(db, orchestrator)

    assert result.gallery_available is True
    assert [t.identity_id for t in result.targets] == ["alice"]
    assert result.targets[0].gallery_entry_count is None


@pytest.mark.asyncio
async def test_upstream_gallery_error_is_visible_but_targets_survive() -> None:
    db = _db_returning([_member("alice", "Alice"), _member("bob", "Bob")])
    orchestrator = AsyncMock()
    orchestrator.get_identities.side_effect = RuntimeError("orchestrator down")

    result = await list_identity_targets(db, orchestrator)

    assert result.gallery_available is False
    assert result.gallery_error is not None
    assert [t.identity_id for t in result.targets] == ["alice", "bob"]
    assert all(t.gallery_entry_count is None for t in result.targets)


@pytest.mark.asyncio
async def test_no_orchestrator_client_still_returns_targets() -> None:
    db = _db_returning([_member("alice", "Alice")])
    result = await list_identity_targets(db, None)
    assert result.gallery_available is True
    assert [t.identity_id for t in result.targets] == ["alice"]


def _person_id(*enrolled: tuple[str, int], error: Exception | None = None) -> AsyncMock:
    client = AsyncMock()
    if error is not None:
        client.list_members.side_effect = error
    else:
        client.list_members.return_value = [
            SimpleNamespace(person_id=pid, embedding_count=count) for pid, count in enrolled
        ]
    return client


@pytest.mark.asyncio
async def test_face_enrolled_marks_members_with_enrolled_photos() -> None:
    db = _db_returning([_member("alice", "Alice"), _member("bob", "Bob"), _member("cy", "Cy")])

    result = await list_identity_targets(db, None, _person_id(("alice", 7), ("bob", 0)))

    assert result.enrollment_available is True
    assert [(t.identity_id, t.face_enrolled) for t in result.targets] == [
        ("alice", True),
        ("bob", False),
        ("cy", False),
    ]


@pytest.mark.asyncio
async def test_person_id_down_keeps_every_member_with_enrollment_unknown() -> None:
    db = _db_returning([_member("alice", "Alice")])

    result = await list_identity_targets(
        db, None, _person_id(error=PersonIDUpstreamError(502, "unreachable"))
    )

    assert result.enrollment_available is False
    assert [(t.identity_id, t.face_enrolled) for t in result.targets] == [("alice", None)]


def _service(members: list, person_id: AsyncMock) -> IdentityTargetsService:
    return IdentityTargetsService(
        session_factory=lambda: _db_returning(members), person_id=person_id, orchestrator=None
    )


@pytest.mark.asyncio
async def test_require_enrolled_member_returns_an_eligible_member() -> None:
    svc = _service([_member("alice", "Alice")], _person_id(("alice", 5)))
    target = await svc.require_enrolled_member("alice")
    assert target.display_name == "Alice"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("identity_id", "message"),
    [("nobody", "not an active household member"), ("bob", "no enrolled face photos")],
)
async def test_require_enrolled_member_rejects_ineligible_targets(
    identity_id: str, message: str
) -> None:
    svc = _service([_member("bob", "Bob")], _person_id(("bob", 0)))
    with pytest.raises(ValidationError, match=message):
        await svc.require_enrolled_member(identity_id)
