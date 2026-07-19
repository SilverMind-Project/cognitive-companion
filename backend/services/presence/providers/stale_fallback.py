"""StaleFallbackProvider: emits STALE when location data is old.

This provider reads the latest observation from ``PersonLocationService``
and returns a ``PresenceSnapshot`` with ``STALE`` status when the
observation exists but is older than the configured ``ttl_seconds``. When
no observation exists or the data is fresh, it returns ``None`` so a
higher-priority provider can answer.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from backend.core.logging import get_logger
from backend.services.person_location.service import PersonLocationService
from backend.services.presence import (
    PresenceSnapshot,
    PresenceSource,
    PresenceStatus,
)

logger = get_logger(__name__)


class StaleFallbackProvider:
    """Presence provider that emits STALE for expired location data.

    This is a fallback provider (low priority) that only answers when
    the latest observation exists but is older than *ttl_seconds*.
    It never competes with real-time providers.

    Parameters
    ----------
    location_service:
        The shared ``PersonLocationService`` instance.
    ttl_seconds:
        Seconds after which the latest observation is considered stale.
    name:
        Provider name (used in ``PresenceSource``).
    priority:
        Provider priority (higher = preferred).
    """

    def __init__(
        self,
        *,
        location_service: PersonLocationService,
        ttl_seconds: int = 3600,
        name: str = "stale_fallback",
        priority: int = 10,
    ) -> None:
        self._location = location_service
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
        """Probe the latest observation for stale data.

        Returns a ``STALE`` snapshot when the latest observation exists
        but is older than ``ttl_seconds``. Returns ``None`` when no
        observation exists at all (yield to lower-priority providers) or
        when the data is fresh (yield to higher-priority providers).
        """
        obs = await self._location.latest_observation(person_id)

        if obs is None:
            # No observation at all; yield to UnknownProvider.
            return None

        elapsed = at - obs.observed_at
        if elapsed <= timedelta(seconds=self._ttl_seconds):
            # Data is fresh; yield to higher-priority providers.
            return None

        return PresenceSnapshot(
            person_id=person_id,
            status=PresenceStatus.STALE,
            room_id=str(obs.room_id) if obs.room_id is not None else None,
            room_name=obs.room_name,
            confidence=obs.confidence,
            last_seen_at=obs.observed_at,
            dwell_minutes=None,
            sources=(
                PresenceSource(
                    name=self._name,
                    confidence=obs.confidence,
                ),
            ),
            inferred_at=at,
            notes=f"last_seen {elapsed.total_seconds():.0f}s ago (TTL={self._ttl_seconds}s)",
        )
