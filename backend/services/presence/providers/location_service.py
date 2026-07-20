"""LocationServiceProvider: reads person location from PersonLocationService.

Reads the current open segment (room) and the latest observation
(freshness) from ``PersonLocationService`` and returns a
``PresenceSnapshot`` with ``PRESENT_ROOM`` or ``STALE`` status depending
on the per-source TTL.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from backend.core.logging import get_logger
from backend.services.person_location.service import PersonLocationService
from backend.services.person_location.types import SourceTag
from backend.services.presence import PresenceSnapshot, PresenceSource, PresenceStatus

logger = get_logger(__name__)

_DEFAULT_TTLS: dict[SourceTag, int] = {
    "world_tracker": 120,
    "face_sighting": 2700,
    "sensor": 1800,
    "manual": 86400,
}


class LocationServiceProvider:
    """Reads location state from ``PersonLocationService``.

    Parameters
    ----------
    location_service:
        The shared ``PersonLocationService`` instance.
    ttl_seconds_by_source:
        Per-source mapping of seconds after which the latest observation is considered stale.
    name:
        Provider name (used in ``PresenceSource``).
    priority:
        Provider priority (higher = preferred).
    """

    def __init__(
        self,
        *,
        location_service: PersonLocationService,
        ttl_seconds_by_source: dict[SourceTag, int] | None = None,
        name: str = "location_service",
        priority: int = 50,
    ) -> None:
        self._location = location_service
        self._ttl_seconds_by_source = dict(ttl_seconds_by_source or _DEFAULT_TTLS)
        self._name = name
        self._priority = priority
        self._unknown_sources_logged: set[str] = set()

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
        """Probe ``PersonLocationService`` for *person_id*."""
        loc = await self._location.where_is(person_id, at)
        if loc is None:
            # No open segment; yield to next provider.
            return None

        room_id = str(loc.room_id)

        obs = await self._location.latest_observation(person_id)
        last_seen_at = obs.observed_at if obs is not None else None

        if last_seen_at is None:
            return PresenceSnapshot(
                person_id=person_id,
                status=PresenceStatus.STALE,
                room_id=room_id,
                room_name=loc.room_name,
                confidence=loc.confidence,
                last_seen_at=None,
                dwell_minutes=None,
                sources=(PresenceSource(name=self._name, confidence=loc.confidence),),
                inferred_at=at,
                notes="last_seen_at is None",
            )

        source = obs.source if obs is not None else None
        if source in self._ttl_seconds_by_source:
            ttl_seconds = self._ttl_seconds_by_source[source]
        else:
            # Unknown source uses most conservative configured value (min)
            ttl_seconds = min(self._ttl_seconds_by_source.values()) if self._ttl_seconds_by_source else 120
            if source and source not in self._unknown_sources_logged:
                self._unknown_sources_logged.add(source)
                logger.warning(
                    "location_service_unknown_source",
                    source=source,
                    fallback_ttl_seconds=ttl_seconds,
                )

        elapsed = at - last_seen_at
        if elapsed > timedelta(seconds=ttl_seconds):
            return PresenceSnapshot(
                person_id=person_id,
                status=PresenceStatus.STALE,
                room_id=room_id,
                room_name=loc.room_name,
                confidence=loc.confidence,
                last_seen_at=last_seen_at,
                dwell_minutes=None,
                sources=(PresenceSource(name=self._name, confidence=loc.confidence),),
                inferred_at=at,
                notes=f"last_seen {elapsed.total_seconds():.0f}s ago (TTL={ttl_seconds}s, source={source})",
            )

        dwell_minutes = round((at - loc.since).total_seconds() / 60.0, 2)

        return PresenceSnapshot(
            person_id=person_id,
            status=PresenceStatus.PRESENT_ROOM,
            room_id=room_id,
            room_name=loc.room_name,
            confidence=loc.confidence,
            last_seen_at=last_seen_at,
            dwell_minutes=dwell_minutes,
            sources=(PresenceSource(name=self._name, confidence=loc.confidence),),
            inferred_at=at,
        )
