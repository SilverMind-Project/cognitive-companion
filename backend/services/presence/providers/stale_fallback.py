"""StaleFallbackProvider: emits STALE when location data is old.

This provider reads ``PersonLocationState`` from the
``LocationRepository`` and returns a ``PresenceSnapshot`` with
``STALE`` status when ``last_seen_at`` exists but is older than
the configured ``ttl_seconds``.  When no state row exists or the
data is fresh, it returns ``None`` so a higher-priority provider
can answer.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from backend.core.logging import get_logger
from backend.services.cts.location_repository import LocationRepository
from backend.services.presence import (
    PresenceSnapshot,
    PresenceSource,
    PresenceStatus,
)

logger = get_logger(__name__)


class StaleFallbackProvider:
    """Presence provider that emits STALE for expired location data.

    This is a fallback provider (low priority) that only answers when
    the CTS location data exists but is older than *ttl_seconds*.
    It never competes with real-time providers.

    Parameters
    ----------
    location_repository_factory:
        Callable returning a fresh ``LocationRepository`` for each probe.
        The provider creates and closes a repo per call so long-lived
        SQLAlchemy sessions are never held across requests.
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
        location_repository_factory: Callable[[], LocationRepository],
        ttl_seconds: int = 3600,
        name: str = "stale_fallback",
        priority: int = 10,
    ) -> None:
        self._repo_factory = location_repository_factory
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
        """Probe the location repository for stale data.

        Returns a ``STALE`` snapshot when ``last_seen_at`` exists
        but is older than ``ttl_seconds``.  Returns ``None`` when
        no state row exists (yield to lower-priority providers) or
        when the data is fresh (yield to higher-priority providers).
        """
        repo = self._repo_factory()
        try:
            state = repo.get_state(person_id)
        finally:
            repo.close()

        if state is None:
            # No state at all; yield to UnknownProvider.
            return None

        if state.last_seen_at is None:
            # last_seen_at is None; yield to UnknownProvider.
            return None

        elapsed = at - state.last_seen_at
        if elapsed <= timedelta(seconds=self._ttl_seconds):
            # Data is fresh; yield to higher-priority providers.
            return None

        return PresenceSnapshot(
            person_id=person_id,
            status=PresenceStatus.STALE,
            room_id=str(state.current_room_id) if state.current_room_id is not None else None,
            room_name=state.current_room_name,
            confidence=state.confidence,
            last_seen_at=state.last_seen_at,
            dwell_minutes=None,
            sources=(
                PresenceSource(
                    name=self._name,
                    confidence=state.confidence,
                ),
            ),
            inferred_at=at,
            notes=f"last_seen {elapsed.total_seconds():.0f}s ago (TTL={self._ttl_seconds}s)",
        )
