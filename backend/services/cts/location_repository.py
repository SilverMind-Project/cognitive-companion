"""LocationRepository: abstraction layer for person location persistence.

Both the CTS ``LocationWriter`` (continuous tracking events) and the legacy
``PersonTrackingService`` (camera + HA sensor polling) write to the same
``PersonLocationState`` and ``PersonLocationHistory`` tables.  This module
provides a shared protocol so both writers use consistent transaction
semantics and tests can inject an in-memory implementation.

Phase-0 §0.28 mandates this abstraction under the name ``LocationRepository``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from backend.core.logging import get_logger
from backend.models.person import HouseholdMember, PersonLocationHistory, PersonLocationState

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class LocationRepository(Protocol):
    """Repository protocol for person-location persistence.

    Callers use these methods instead of direct ORM queries so the
    implementation can be swapped for testing or migrated to a different
    storage backend without touching service code.
    """

    def get_state(self, person_id: str) -> PersonLocationState | None:
        """Return the current location state for *person_id*, or ``None``."""
        ...

    def upsert_state(
        self,
        *,
        person_id: str,
        room_name: str | None,
        room_id: int | None = None,
        sensor_id: str,
        confidence: float,
        status: str = "home",
        event_time: datetime | None = None,
    ) -> PersonLocationState:
        """Create or update the location state row for *person_id*.

        Returns the (possibly newly created) state row.
        """
        ...

    def close_open_history(
        self,
        person_id: str,
        exited_at: datetime,
        *,
        require_no_superseded: bool = False,
    ) -> int:
        """Close the most recent open history row for *person_id*.

        Sets ``exited_at`` on the latest row where ``exited_at IS NULL``.

        Parameters
        ----------
        require_no_superseded:
            If ``True``, also filter ``superseded_by_revision_id IS NULL``.
            Used by the CTS writer to avoid closing rows that have already
            been rewritten by the identity rewriter.

        Returns
        -------
        int
            Number of rows closed (0 or 1).
        """
        ...

    def append_history(
        self,
        *,
        person_id: str,
        room_id: int | None = None,
        room_name: str | None,
        entered_at: datetime,
        source: str,
        global_track_id: str | None = None,
        direction_semantic: str | None = None,
        from_room_id: int | None = None,
        from_room_name: str | None = None,
    ) -> PersonLocationHistory:
        """Insert a new history row.

        Returns the inserted row.
        """
        ...

    def current_room_for(self, person_id: str) -> str | None:
        """Return the current room name for *person_id*, or ``None``."""
        ...

    def get_open_history_row(
        self,
        person_id: str,
        room_name: str | None = None,
    ) -> PersonLocationHistory | None:
        """Return the most recent open history row for *person_id*.

        An "open" row is one where ``exited_at IS NULL`` and
        ``superseded_by_revision_id IS NULL``.  When *room_name* is
        provided, also filter to that room.
        """
        ...

    def commit(self) -> None:
        """Commit the current transaction."""
        ...

    def rollback(self) -> None:
        """Roll back the current transaction."""
        ...

    def close(self) -> None:
        """Close the underlying session/connection."""
        ...


# ---------------------------------------------------------------------------
# SQLAlchemy implementation
# ---------------------------------------------------------------------------


class SqlAlchemyLocationRepository:
    """SQLAlchemy-backed implementation of :class:`LocationRepository`.

    Wraps a ``Session`` object and translates repository method calls
    into ORM queries.  The caller is responsible for calling
    :meth:`commit`, :meth:`rollback`, and :meth:`close` at the
    appropriate lifecycle points.
    """

    def __init__(self, session) -> None:
        self._db = session

    def get_state(self, person_id: str) -> PersonLocationState | None:
        return (
            self._db.query(PersonLocationState)
            .filter(PersonLocationState.person_id == person_id)
            .first()
        )

    def upsert_state(
        self,
        *,
        person_id: str,
        room_name: str | None,
        room_id: int | None = None,
        sensor_id: str,
        confidence: float,
        status: str = "home",
        event_time: datetime | None = None,
    ) -> PersonLocationState:
        now = event_time or datetime.now(UTC)

        # Auto-create a HouseholdMember row for CTS-discovered identities so
        # the FK constraint on PersonLocationState is satisfied and the
        # identity appears on the dashboard without manual provisioning.
        member = self._db.query(HouseholdMember).filter(HouseholdMember.id == person_id).first()
        if member is None:
            is_guest = person_id == "unknown" or person_id.startswith("unknown_")
            member = HouseholdMember(
                id=person_id,
                name="Guest" if is_guest else person_id,
                is_guest=is_guest,
            )
            self._db.add(member)
            self._db.flush()

        state = self.get_state(person_id)
        if state is None:
            state = PersonLocationState(
                person_id=person_id,
                current_room_id=room_id,
                current_room_name=room_name,
                last_seen_at=now,
                last_sensor_id=sensor_id,
                status=status,
                confidence=confidence,
                updated_at=now,
            )
            self._db.add(state)
        else:
            if room_name is not None:
                state.current_room_name = room_name
            if room_id is not None:
                state.current_room_id = room_id
            state.last_seen_at = now
            state.last_sensor_id = sensor_id
            state.status = status
            state.confidence = confidence
            state.updated_at = now
        return state

    def close_open_history(
        self,
        person_id: str,
        exited_at: datetime,
        *,
        require_no_superseded: bool = False,
    ) -> int:
        query = self._db.query(PersonLocationHistory).filter(
            PersonLocationHistory.person_id == person_id,
            PersonLocationHistory.exited_at.is_(None),
        )
        if require_no_superseded:
            query = query.filter(
                PersonLocationHistory.superseded_by_revision_id.is_(None),
            )
        row = query.order_by(PersonLocationHistory.entered_at.desc()).first()
        if row is None:
            return 0
        row.exited_at = exited_at
        return 1

    def append_history(
        self,
        *,
        person_id: str,
        room_id: int | None = None,
        room_name: str | None,
        entered_at: datetime,
        source: str,
        global_track_id: str | None = None,
        direction_semantic: str | None = None,
        from_room_id: int | None = None,
        from_room_name: str | None = None,
    ) -> PersonLocationHistory:
        row = PersonLocationHistory(
            person_id=person_id,
            room_id=room_id,
            room_name=room_name,
            entered_at=entered_at,
            source=source,
            global_track_id=global_track_id,
            direction_semantic=direction_semantic,
            from_room_id=from_room_id,
            from_room_name=from_room_name,
        )
        self._db.add(row)
        return row

    def current_room_for(self, person_id: str) -> str | None:
        state = self.get_state(person_id)
        return state.current_room_name if state is not None else None

    def get_open_history_row(
        self,
        person_id: str,
        room_name: str | None = None,
    ) -> PersonLocationHistory | None:
        query = self._db.query(PersonLocationHistory).filter(
            PersonLocationHistory.person_id == person_id,
            PersonLocationHistory.exited_at.is_(None),
            PersonLocationHistory.superseded_by_revision_id.is_(None),
        )
        if room_name is not None:
            query = query.filter(
                PersonLocationHistory.room_name == room_name,
            )
        return query.order_by(PersonLocationHistory.entered_at.desc()).first()

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()

    def close(self) -> None:
        self._db.close()


# ---------------------------------------------------------------------------
# In-memory implementation (for tests)
# ---------------------------------------------------------------------------


@dataclass
class _InMemoryState:
    person_id: str
    current_room_id: int | None = None
    current_room_name: str | None = None
    last_seen_at: datetime | None = None
    last_sensor_id: str | None = None
    status: str = "unknown"
    confidence: float = 0.0
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class _InMemoryHistory:
    id: int
    person_id: str
    room_id: int | None = None
    room_name: str | None = None
    entered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    exited_at: datetime | None = None
    source: str = "inferred"
    global_track_id: str | None = None
    direction_semantic: str | None = None
    from_room_id: int | None = None
    from_room_name: str | None = None
    superseded_by_revision_id: str | None = None


class InMemoryLocationRepository:
    """In-memory implementation for unit tests.

    Stores state and history in plain Python dicts/lists.  Commit/rollback
    are no-ops.
    """

    def __init__(self) -> None:
        self._states: dict[str, _InMemoryState] = {}
        self._history: list[_InMemoryHistory] = []
        self._next_id = 1

    def get_state(self, person_id: str) -> PersonLocationState | None:
        s = self._states.get(person_id)
        if s is None:
            return None
        # Return a duck-typed object that matches the ORM model interface
        # used by callers.
        state = PersonLocationState(
            person_id=s.person_id,
            current_room_id=s.current_room_id,
            current_room_name=s.current_room_name,
            last_seen_at=s.last_seen_at,
            last_sensor_id=s.last_sensor_id,
            status=s.status,
            confidence=s.confidence,
            updated_at=s.updated_at,
        )
        return state

    def upsert_state(
        self,
        *,
        person_id: str,
        room_name: str | None,
        room_id: int | None = None,
        sensor_id: str,
        confidence: float,
        status: str = "home",
        event_time: datetime | None = None,
    ) -> PersonLocationState:
        now = event_time or datetime.now(UTC)
        existing = self._states.get(person_id)
        if existing is None:
            self._states[person_id] = _InMemoryState(
                person_id=person_id,
                current_room_id=room_id,
                current_room_name=room_name,
                last_seen_at=now,
                last_sensor_id=sensor_id,
                status=status,
                confidence=confidence,
                updated_at=now,
            )
        else:
            if room_name is not None:
                existing.current_room_name = room_name
            if room_id is not None:
                existing.current_room_id = room_id
            existing.last_seen_at = now
            existing.last_sensor_id = sensor_id
            existing.status = status
            existing.confidence = confidence
            existing.updated_at = now

        result = self.get_state(person_id)
        assert result is not None, "upsert_state must always produce state"
        return result

    def close_open_history(
        self,
        person_id: str,
        exited_at: datetime,
        *,
        require_no_superseded: bool = False,
    ) -> int:
        candidates = [
            h for h in reversed(self._history) if h.person_id == person_id and h.exited_at is None
        ]
        if require_no_superseded:
            candidates = [h for h in candidates if h.superseded_by_revision_id is None]
        if not candidates:
            return 0
        candidates[0].exited_at = exited_at
        return 1

    def append_history(
        self,
        *,
        person_id: str,
        room_id: int | None = None,
        room_name: str | None,
        entered_at: datetime,
        source: str,
        global_track_id: str | None = None,
        direction_semantic: str | None = None,
        from_room_id: int | None = None,
        from_room_name: str | None = None,
    ) -> PersonLocationHistory:
        row = _InMemoryHistory(
            id=self._next_id,
            person_id=person_id,
            room_id=room_id,
            room_name=room_name,
            entered_at=entered_at,
            source=source,
            global_track_id=global_track_id,
            direction_semantic=direction_semantic,
            from_room_id=from_room_id,
            from_room_name=from_room_name,
        )
        self._next_id += 1
        self._history.append(row)
        # Return a mock-compatible object
        return PersonLocationHistory(
            person_id=person_id,
            room_id=room_id,
            room_name=room_name,
            entered_at=entered_at,
            source=source,
            global_track_id=global_track_id,
            direction_semantic=direction_semantic,
            from_room_id=from_room_id,
            from_room_name=from_room_name,
        )

    def current_room_for(self, person_id: str) -> str | None:
        s = self._states.get(person_id)
        return s.current_room_name if s is not None else None

    def get_open_history_row(
        self,
        person_id: str,
        room_name: str | None = None,
    ) -> PersonLocationHistory | None:
        candidates = [
            h
            for h in reversed(self._history)
            if h.person_id == person_id
            and h.exited_at is None
            and h.superseded_by_revision_id is None
        ]
        if room_name is not None:
            candidates = [h for h in candidates if h.room_name == room_name]
        if not candidates:
            return None
        row = candidates[0]
        return PersonLocationHistory(
            person_id=row.person_id,
            room_id=row.room_id,
            room_name=row.room_name,
            entered_at=row.entered_at,
            exited_at=row.exited_at,
            source=row.source,
            global_track_id=row.global_track_id,
            direction_semantic=row.direction_semantic,
            from_room_id=row.from_room_id,
            from_room_name=row.from_room_name,
            superseded_by_revision_id=row.superseded_by_revision_id,
        )

    def commit(self) -> None:
        pass  # no-op for in-memory

    def rollback(self) -> None:
        pass  # no-op for in-memory

    def close(self) -> None:
        pass  # no-op for in-memory
