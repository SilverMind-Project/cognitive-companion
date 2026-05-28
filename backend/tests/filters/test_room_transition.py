"""Unit tests for :class:`~backend.filters.builtin.room_transition.RoomTransitionFilter` (R2: PersonLocationService SSOT).

Uses mock PersonLocationService with presence_history() instead of
direct PersonLocationHistory table queries.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from backend.filters import FilterRegistry
from backend.filters.builtin.room_transition import RoomTransitionFilter
from backend.services.camera_topology import (
    SEMANTIC_ENTERING,
    SEMANTIC_EXITING,
)
from backend.services.person_location.types import (
    EntrySource,
    ExitSource,
    PresenceSegment,
)

# Ensure the filter is registered.
FilterRegistry.discover()

_NOW = datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC)


def _seg(
    room_id: int = 1,
    room_name: str = "Kitchen",
    entered_at: datetime | None = None,
    exited_at: datetime | None = None,
    entry_source: EntrySource = "observed",
    exit_source: ExitSource | None = None,
) -> PresenceSegment:
    """Create a PresenceSegment fixture."""
    return PresenceSegment(
        id=uuid4(),
        person_id="alice",
        room_id=room_id,
        entered_at=entered_at or (_NOW - timedelta(minutes=5)),
        exited_at=exited_at,
        entry_source=entry_source,
        exit_source=exit_source,
        confidence=0.9,
        last_observed_at=entered_at or _NOW,
        metadata={"room_name": room_name},
    )


def _services(*segments: PresenceSegment):
    """Build a mock services container with presence_history()."""
    svc = MagicMock()
    svc.presence_history = AsyncMock(return_value=list(segments))
    services = MagicMock()
    services.person_location = svc
    return services


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def room_filter() -> RoomTransitionFilter:
    instance = FilterRegistry.get("room_transition")
    assert instance is not None, "RoomTransitionFilter not registered"
    return instance  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestMetadata:
    def test_filter_type(self, room_filter):
        assert room_filter.metadata().filter_type == "room_transition"

    def test_display_name(self, room_filter):
        assert "Room Transition" in room_filter.metadata().display_name

    def test_config_schema_requires_person_id(self, room_filter):
        assert "person_id" in room_filter.metadata().config_schema.get("required", [])


# ---------------------------------------------------------------------------
# Guard-rail: no services / no person_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGuards:
    async def test_returns_false_without_services(self, room_filter):
        result = await room_filter.evaluate(
            {"person_id": "alice"}, None, _NOW, services=None,
        )
        assert result is False

    async def test_returns_false_without_person_id(self, room_filter):
        svc = _services()
        result = await room_filter.evaluate(
            {}, None, _NOW, services=svc,
        )
        assert result is False

    async def test_returns_false_with_empty_person_id(self, room_filter):
        svc = _services()
        result = await room_filter.evaluate(
            {"person_id": ""}, None, _NOW, services=svc,
        )
        assert result is False

    async def test_fail_closed_when_person_location_none(self, room_filter):
        """When services.person_location is None, filter fails closed."""
        services = MagicMock()
        services.person_location = None
        result = await room_filter.evaluate(
            {"person_id": "alice"}, None, _NOW, services=services,
        )
        assert result is False


# ---------------------------------------------------------------------------
# Core matching behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCoreMatching:
    async def test_matches_within_window(self, room_filter):
        s1 = _seg(room_id=1, room_name="Kitchen",
                   entered_at=_NOW - timedelta(minutes=3),
                   entry_source="observed")
        s2 = _seg(room_id=2, room_name="Hallway",
                   entered_at=_NOW - timedelta(minutes=1),
                   entry_source="observed")
        svc = _services(s1, s2)
        result = await room_filter.evaluate(
            {"person_id": "alice", "within_minutes": 5},
            None, _NOW, services=svc,
        )
        assert result is True

    async def test_no_match_single_segment(self, room_filter):
        """Need at least 2 active segments for a transition."""
        s1 = _seg(room_id=1, entered_at=_NOW - timedelta(minutes=2))
        svc = _services(s1)
        result = await room_filter.evaluate(
            {"person_id": "alice", "within_minutes": 5},
            None, _NOW, services=svc,
        )
        assert result is False

    async def test_no_match_same_room(self, room_filter):
        """Adjacent segments in the same room should not count as transition."""
        s1 = _seg(room_id=1, room_name="Kitchen",
                   entered_at=_NOW - timedelta(minutes=3))
        s2 = _seg(room_id=1, room_name="Kitchen",
                   entered_at=_NOW - timedelta(minutes=1))
        svc = _services(s1, s2)
        result = await room_filter.evaluate(
            {"person_id": "alice", "within_minutes": 5},
            None, _NOW, services=svc,
        )
        assert result is False

    async def test_no_match_single_segment_inside_window(self, room_filter):
        """A single segment (no transition) returns False even inside the window."""
        s1 = _seg(room_id=1, entered_at=_NOW - timedelta(minutes=2))
        svc = _services(s1)
        result = await room_filter.evaluate(
            {"person_id": "alice", "within_minutes": 5},
            None, _NOW, services=svc,
        )
        assert result is False

    async def test_no_match_for_different_person(self, room_filter):
        """Segments exist for alice, but config asks for bob."""
        seg = PresenceSegment(
            id=uuid4(),
            person_id="bob",
            room_id=1,
            entered_at=_NOW - timedelta(minutes=1),
            entry_source="observed",
            confidence=0.9,
            last_observed_at=_NOW,
        )
        svc = _services(seg)
        result = await room_filter.evaluate(
            {"person_id": "bob", "within_minutes": 5},
            None, _NOW, services=svc,
        )
        assert result is False  # only one segment


# ---------------------------------------------------------------------------
# to_room_name / from_room_name filters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestToRoomFilter:
    async def test_matches_correct_room(self, room_filter):
        s1 = _seg(room_id=1, room_name="Hallway",
                   entered_at=_NOW - timedelta(minutes=3))
        s2 = _seg(room_id=2, room_name="Kitchen",
                   entered_at=_NOW - timedelta(minutes=1))
        svc = _services(s1, s2)
        result = await room_filter.evaluate(
            {"person_id": "alice", "to_room_name": "Kitchen"},
            None, _NOW, services=svc,
        )
        assert result is True

    async def test_case_insensitive_room_match(self, room_filter):
        s1 = _seg(room_id=1, room_name="Hallway",
                   entered_at=_NOW - timedelta(minutes=3))
        s2 = _seg(room_id=2, room_name="Kitchen",
                   entered_at=_NOW - timedelta(minutes=1))
        svc = _services(s1, s2)
        result = await room_filter.evaluate(
            {"person_id": "alice", "to_room_name": "kitchen"},
            None, _NOW, services=svc,
        )
        assert result is True

    async def test_no_match_wrong_room(self, room_filter):
        s1 = _seg(room_id=1, room_name="Hallway",
                   entered_at=_NOW - timedelta(minutes=3))
        s2 = _seg(room_id=2, room_name="Kitchen",
                   entered_at=_NOW - timedelta(minutes=1))
        svc = _services(s1, s2)
        result = await room_filter.evaluate(
            {"person_id": "alice", "to_room_name": "Bedroom"},
            None, _NOW, services=svc,
        )
        assert result is False


@pytest.mark.asyncio
class TestFromRoomFilter:
    async def test_matches_correct_from_room(self, room_filter):
        s1 = _seg(room_id=1, room_name="Hallway",
                   entered_at=_NOW - timedelta(minutes=3))
        s2 = _seg(room_id=2, room_name="Kitchen",
                   entered_at=_NOW - timedelta(minutes=1))
        svc = _services(s1, s2)
        result = await room_filter.evaluate(
            {"person_id": "alice", "from_room_name": "Hallway"},
            None, _NOW, services=svc,
        )
        assert result is True

    async def test_case_insensitive_from_room(self, room_filter):
        s1 = _seg(room_id=1, room_name="Hallway",
                   entered_at=_NOW - timedelta(minutes=3))
        s2 = _seg(room_id=2, room_name="Kitchen",
                   entered_at=_NOW - timedelta(minutes=1))
        svc = _services(s1, s2)
        result = await room_filter.evaluate(
            {"person_id": "alice", "from_room_name": "hallway"},
            None, _NOW, services=svc,
        )
        assert result is True

    async def test_no_match_wrong_from_room(self, room_filter):
        s1 = _seg(room_id=1, room_name="Hallway",
                   entered_at=_NOW - timedelta(minutes=3))
        s2 = _seg(room_id=2, room_name="Kitchen",
                   entered_at=_NOW - timedelta(minutes=1))
        svc = _services(s1, s2)
        result = await room_filter.evaluate(
            {"person_id": "alice", "from_room_name": "Garage"},
            None, _NOW, services=svc,
        )
        assert result is False


# ---------------------------------------------------------------------------
# Semantic filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSemanticFilter:
    async def test_matches_entering_semantic(self, room_filter):
        s1 = _seg(room_id=1, room_name="Hallway",
                   entered_at=_NOW - timedelta(minutes=3),
                   entry_source="observed")
        s2 = _seg(room_id=2, room_name="Kitchen",
                   entered_at=_NOW - timedelta(minutes=1),
                   entry_source="observed")
        svc = _services(s1, s2)
        result = await room_filter.evaluate(
            {"person_id": "alice", "semantic": SEMANTIC_ENTERING},
            None, _NOW, services=svc,
        )
        assert result is True

    async def test_no_match_wrong_semantic(self, room_filter):
        s1 = _seg(room_id=1, room_name="Hallway",
                   entered_at=_NOW - timedelta(minutes=3),
                   entry_source="observed")
        s2 = _seg(room_id=2, room_name="Kitchen",
                   entered_at=_NOW - timedelta(minutes=1),
                   entry_source="observed")
        svc = _services(s1, s2)
        result = await room_filter.evaluate(
            {"person_id": "alice", "semantic": SEMANTIC_EXITING},
            None, _NOW, services=svc,
        )
        assert result is False

    async def test_matches_exiting_semantic(self, room_filter):
        s1 = _seg(room_id=1, room_name="Kitchen",
                   entered_at=_NOW - timedelta(minutes=3),
                   entry_source="observed",
                   exit_source="observed")
        s2 = _seg(room_id=2, room_name="Hallway",
                   entered_at=_NOW - timedelta(minutes=1),
                   entry_source="observed",
                   exit_source="observed")
        svc = _services(s1, s2)
        result = await room_filter.evaluate(
            {"person_id": "alice", "semantic": SEMANTIC_EXITING},
            None, _NOW, services=svc,
        )
        assert result is True


# ---------------------------------------------------------------------------
# Combined constraints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCombinedConstraints:
    async def test_all_constraints_pass(self, room_filter):
        s1 = _seg(room_id=1, room_name="Hallway",
                   entered_at=_NOW - timedelta(minutes=3),
                   entry_source="observed")
        s2 = _seg(room_id=2, room_name="Kitchen",
                   entered_at=_NOW - timedelta(minutes=1),
                   entry_source="observed")
        svc = _services(s1, s2)
        result = await room_filter.evaluate(
            {
                "person_id": "alice",
                "semantic": SEMANTIC_ENTERING,
                "to_room_name": "Kitchen",
                "from_room_name": "Hallway",
                "within_minutes": 5,
            },
            None, _NOW, services=svc,
        )
        assert result is True

    async def test_one_failing_constraint_rejects(self, room_filter):
        s1 = _seg(room_id=1, room_name="Hallway",
                   entered_at=_NOW - timedelta(minutes=3),
                   entry_source="observed")
        s2 = _seg(room_id=2, room_name="Kitchen",
                   entered_at=_NOW - timedelta(minutes=1),
                   entry_source="observed")
        svc = _services(s1, s2)
        result = await room_filter.evaluate(
            {
                "person_id": "alice",
                "semantic": SEMANTIC_ENTERING,
                "to_room_name": "Kitchen",
                "from_room_name": "Garage",  # wrong
            },
            None, _NOW, services=svc,
        )
        assert result is False

    async def test_most_recent_segments_considered(self, room_filter):
        s1 = _seg(room_id=3, room_name="Bedroom",
                   entered_at=_NOW - timedelta(minutes=10),
                   entry_source="observed")
        s2 = _seg(room_id=1, room_name="Hallway",
                   entered_at=_NOW - timedelta(minutes=5),
                   entry_source="observed")
        s3 = _seg(room_id=2, room_name="Kitchen",
                   entered_at=_NOW - timedelta(minutes=1),
                   entry_source="observed")
        svc = _services(s1, s2, s3)
        result = await room_filter.evaluate(
            {"person_id": "alice", "to_room_name": "Kitchen", "within_minutes": 5},
            None, _NOW, services=svc,
        )
        assert result is True
