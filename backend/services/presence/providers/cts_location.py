"""CtsLocationProvider: reads person location from CTS location repository.

This provider is the first provider in the fusion chain for Block 1.
It reads ``PersonLocationState`` from the ``LocationRepository`` and
returns a ``PresenceSnapshot`` with ``PRESENT_ROOM`` or ``STALE`` status
depending on the TTL.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.core.logging import get_logger
from backend.services.cts.location_repository import LocationRepository
from backend.services.presence import PresenceSnapshot, PresenceSource, PresenceStatus

logger = get_logger(__name__)


def _compute_dwell(
    repo: LocationRepository,
    person_id: str,
    room_name: str,
    at: datetime,
) -> float | None:
    """Compute dwell minutes in the current room.

    Returns the number of minutes since the person entered the current
    room, or ``None`` if no open history row exists.
    """
    row = repo.get_open_history_row(person_id, room_name)
    if row is None or row.entered_at is None:
        return None

    entered = row.entered_at
    if entered.tzinfo is None:
        entered = entered.replace(tzinfo=UTC)
    delta = at - entered
    return round(delta.total_seconds() / 60.0, 2)


class CtsLocationProvider:
    """Reads location state from the CTS location repository.

    Parameters
    ----------
    location_repository:
        Repository abstraction over ``PersonLocationState`` /
        ``PersonLocationHistory``.
    ttl_seconds:
        Seconds after which ``last_seen_at`` is considered stale.
    name:
        Provider name (used in ``PresenceSource``).
    priority:
        Provider priority (higher = preferred).
    """

    def __init__(
        self,
        *,
        location_repository: LocationRepository,
        ttl_seconds: int = 120,
        name: str = "cts_location",
        priority: int = 50,
    ) -> None:
        self._repo = location_repository
        self._ttl_seconds = ttl_seconds
        self._name = name
        self._priority = priority

    @property
    def name(self) -> str:
        return self._name

    @property
    def priority(self) -> int:
        return self._priority

    async def probe(
        self,
        person_id: str,
        at: datetime,
    ) -> PresenceSnapshot | None:
        """Probe the location repository for *person_id*."""
        state = self._repo.get_state(person_id)
        if state is None:
            return None

        if state.current_room_name is None:
            # No room known; yield to next provider.
            return None

        if state.last_seen_at is None:
            # last_seen_at is None → treat as stale.
            return PresenceSnapshot(
                person_id=person_id,
                status=PresenceStatus.STALE,
                room_id=str(state.current_room_id) if state.current_room_id is not None else None,
                room_name=state.current_room_name,
                confidence=state.confidence,
                last_seen_at=None,
                dwell_minutes=None,
                sources=(PresenceSource(name=self._name, confidence=state.confidence),),
                inferred_at=at,
                notes="last_seen_at is None",
            )

        elapsed = at - state.last_seen_at
        if elapsed > timedelta(seconds=self._ttl_seconds):
            return PresenceSnapshot(
                person_id=person_id,
                status=PresenceStatus.STALE,
                room_id=str(state.current_room_id) if state.current_room_id is not None else None,
                room_name=state.current_room_name,
                confidence=state.confidence,
                last_seen_at=state.last_seen_at,
                dwell_minutes=None,
                sources=(PresenceSource(name=self._name, confidence=state.confidence),),
                inferred_at=at,
                notes=f"last_seen {elapsed.total_seconds():.0f}s ago (TTL={self._ttl_seconds}s)",
            )

        dwell_minutes = _compute_dwell(
            self._repo,
            person_id,
            state.current_room_name,
            at,
        )

        return PresenceSnapshot(
            person_id=person_id,
            status=PresenceStatus.PRESENT_ROOM,
            room_id=str(state.current_room_id) if state.current_room_id is not None else None,
            room_name=state.current_room_name,
            confidence=state.confidence,
            last_seen_at=state.last_seen_at,
            dwell_minutes=dwell_minutes,
            sources=(PresenceSource(name=self._name, confidence=state.confidence),),
            inferred_at=at,
        )
