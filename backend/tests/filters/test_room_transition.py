"""Unit tests for :class:`~backend.filters.builtin.room_transition.RoomTransitionFilter`.

Uses the in-memory SQLite engine from conftest so the filter's DB queries run
against real schema / data with no mocking required.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.filters import FilterRegistry
from backend.filters.builtin.room_transition import RoomTransitionFilter
from backend.models.person import HouseholdMember, PersonLocationHistory

# Ensure the filter is registered (in CI the FilterRegistry may not have been
# populated yet because main.py's lifespan has not run).
FilterRegistry.discover()

_NOW = datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def room_filter() -> RoomTransitionFilter:
    instance = FilterRegistry.get("room_transition")
    assert instance is not None, "RoomTransitionFilter not registered"
    return instance  # type: ignore[return-value]


@pytest.fixture
def person_fixture(db_session):
    member = HouseholdMember(id="alice", name="Alice", is_active=True)
    db_session.add(member)
    db_session.flush()
    return member


def _add_history(
    db, person_id, room_name, entered_at, direction_semantic=None, from_room_name=None
):
    row = PersonLocationHistory(
        person_id=person_id,
        room_name=room_name,
        entered_at=entered_at,
        source="inferred",
        direction_semantic=direction_semantic,
        from_room_name=from_room_name,
    )
    db.add(row)
    db.flush()
    return row


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
# Guard-rail: no DB / no person_id
# ---------------------------------------------------------------------------


class TestGuards:
    def test_returns_false_without_db(self, room_filter):
        assert room_filter.evaluate({"person_id": "alice"}, None, _NOW, db=None) is False

    def test_returns_false_without_person_id(self, room_filter, db_session):
        assert room_filter.evaluate({}, None, _NOW, db=db_session) is False

    def test_returns_false_with_empty_person_id(self, room_filter, db_session):
        assert room_filter.evaluate({"person_id": ""}, None, _NOW, db=db_session) is False


# ---------------------------------------------------------------------------
# Core matching behaviour
# ---------------------------------------------------------------------------


class TestCoreMatching:
    def test_matches_within_window(self, room_filter, db_session, person_fixture):
        _add_history(
            db_session,
            "alice",
            "Kitchen",
            _NOW - timedelta(minutes=2),
            direction_semantic="entering",
        )
        result = room_filter.evaluate(
            {"person_id": "alice", "within_minutes": 5},
            None,
            _NOW,
            db=db_session,
        )
        assert result is True

    def test_no_match_outside_window(self, room_filter, db_session, person_fixture):
        _add_history(
            db_session,
            "alice",
            "Kitchen",
            _NOW - timedelta(minutes=10),
            direction_semantic="entering",
        )
        result = room_filter.evaluate(
            {"person_id": "alice", "within_minutes": 5},
            None,
            _NOW,
            db=db_session,
        )
        assert result is False

    def test_no_match_when_direction_semantic_is_null(self, room_filter, db_session, person_fixture):
        """Legacy rows with no direction_semantic must not match."""
        _add_history(
            db_session,
            "alice",
            "Kitchen",
            _NOW - timedelta(minutes=1),
            direction_semantic=None,
        )
        result = room_filter.evaluate(
            {"person_id": "alice", "within_minutes": 5},
            None,
            _NOW,
            db=db_session,
        )
        assert result is False

    def test_no_match_for_different_person(self, room_filter, db_session, person_fixture):
        _add_history(
            db_session,
            "alice",
            "Kitchen",
            _NOW - timedelta(minutes=1),
            direction_semantic="entering",
        )
        result = room_filter.evaluate(
            {"person_id": "bob"},
            None,
            _NOW,
            db=db_session,
        )
        assert result is False


# ---------------------------------------------------------------------------
# Semantic filter
# ---------------------------------------------------------------------------


class TestSemanticFilter:
    def test_matches_correct_semantic(self, room_filter, db_session, person_fixture):
        _add_history(
            db_session,
            "alice",
            "Kitchen",
            _NOW - timedelta(minutes=1),
            direction_semantic="entering",
        )
        assert (
            room_filter.evaluate(
                {"person_id": "alice", "semantic": "entering"},
                None,
                _NOW,
                db=db_session,
            )
            is True
        )

    def test_no_match_wrong_semantic(self, room_filter, db_session, person_fixture):
        _add_history(
            db_session,
            "alice",
            "Kitchen",
            _NOW - timedelta(minutes=1),
            direction_semantic="entering",
        )
        assert (
            room_filter.evaluate(
                {"person_id": "alice", "semantic": "exiting"},
                None,
                _NOW,
                db=db_session,
            )
            is False
        )


# ---------------------------------------------------------------------------
# to_room_name filter
# ---------------------------------------------------------------------------


class TestToRoomFilter:
    def test_matches_correct_room(self, room_filter, db_session, person_fixture):
        _add_history(
            db_session,
            "alice",
            "Kitchen",
            _NOW - timedelta(minutes=1),
            direction_semantic="entering",
        )
        assert (
            room_filter.evaluate(
                {"person_id": "alice", "to_room_name": "Kitchen"},
                None,
                _NOW,
                db=db_session,
            )
            is True
        )

    def test_case_insensitive_room_match(self, room_filter, db_session, person_fixture):
        _add_history(
            db_session,
            "alice",
            "Kitchen",
            _NOW - timedelta(minutes=1),
            direction_semantic="entering",
        )
        assert (
            room_filter.evaluate(
                {"person_id": "alice", "to_room_name": "kitchen"},
                None,
                _NOW,
                db=db_session,
            )
            is True
        )

    def test_no_match_wrong_room(self, room_filter, db_session, person_fixture):
        _add_history(
            db_session,
            "alice",
            "Kitchen",
            _NOW - timedelta(minutes=1),
            direction_semantic="entering",
        )
        assert (
            room_filter.evaluate(
                {"person_id": "alice", "to_room_name": "Bedroom"},
                None,
                _NOW,
                db=db_session,
            )
            is False
        )


# ---------------------------------------------------------------------------
# from_room_name filter
# ---------------------------------------------------------------------------


class TestFromRoomFilter:
    def test_matches_correct_from_room(self, room_filter, db_session, person_fixture):
        _add_history(
            db_session,
            "alice",
            "Kitchen",
            _NOW - timedelta(minutes=1),
            direction_semantic="entering",
            from_room_name="Hallway",
        )
        assert (
            room_filter.evaluate(
                {"person_id": "alice", "from_room_name": "Hallway"},
                None,
                _NOW,
                db=db_session,
            )
            is True
        )

    def test_case_insensitive_from_room(self, room_filter, db_session, person_fixture):
        _add_history(
            db_session,
            "alice",
            "Kitchen",
            _NOW - timedelta(minutes=1),
            direction_semantic="entering",
            from_room_name="Hallway",
        )
        assert (
            room_filter.evaluate(
                {"person_id": "alice", "from_room_name": "hallway"},
                None,
                _NOW,
                db=db_session,
            )
            is True
        )

    def test_no_match_wrong_from_room(self, room_filter, db_session, person_fixture):
        _add_history(
            db_session,
            "alice",
            "Kitchen",
            _NOW - timedelta(minutes=1),
            direction_semantic="entering",
            from_room_name="Hallway",
        )
        assert (
            room_filter.evaluate(
                {"person_id": "alice", "from_room_name": "Garage"},
                None,
                _NOW,
                db=db_session,
            )
            is False
        )


# ---------------------------------------------------------------------------
# Combined constraints
# ---------------------------------------------------------------------------


class TestCombinedConstraints:
    def test_all_constraints_pass(self, room_filter, db_session, person_fixture):
        _add_history(
            db_session,
            "alice",
            "Kitchen",
            _NOW - timedelta(minutes=1),
            direction_semantic="entering",
            from_room_name="Hallway",
        )
        assert (
            room_filter.evaluate(
                {
                    "person_id": "alice",
                    "semantic": "entering",
                    "to_room_name": "Kitchen",
                    "from_room_name": "Hallway",
                    "within_minutes": 5,
                },
                None,
                _NOW,
                db=db_session,
            )
            is True
        )

    def test_one_failing_constraint_rejects(self, room_filter, db_session, person_fixture):
        _add_history(
            db_session,
            "alice",
            "Kitchen",
            _NOW - timedelta(minutes=1),
            direction_semantic="entering",
            from_room_name="Hallway",
        )
        # Everything matches except from_room_name
        assert (
            room_filter.evaluate(
                {
                    "person_id": "alice",
                    "semantic": "entering",
                    "to_room_name": "Kitchen",
                    "from_room_name": "Garage",  # <-- wrong
                },
                None,
                _NOW,
                db=db_session,
            )
            is False
        )

    def test_most_recent_row_selected_over_older(self, room_filter, db_session, person_fixture):
        """The filter should find the recent row even when an older row exists."""
        _add_history(
            db_session,
            "alice",
            "Bedroom",
            _NOW - timedelta(minutes=20),
            direction_semantic="entering",
        )
        _add_history(
            db_session,
            "alice",
            "Kitchen",
            _NOW - timedelta(minutes=1),
            direction_semantic="entering",
        )
        assert (
            room_filter.evaluate(
                {"person_id": "alice", "to_room_name": "Kitchen", "within_minutes": 5},
                None,
                _NOW,
                db=db_session,
            )
            is True
        )
