"""HaBedSensorProvider: reads HA bed-occupancy sensor state.

Returns ``PRESENT_ROOM`` when the configured bed sensor is ``on``,
otherwise ``None``.
"""

from __future__ import annotations

from datetime import datetime

from backend.core.logging import get_logger
from backend.integrations.ha_state_cache import HaStateCache
from backend.services.presence import (
    PresenceSnapshot,
    PresenceSource,
    PresenceStatus,
)

logger = get_logger(__name__)


class HaBedSensorProvider:
    """Presence provider backed by a single HA bed-occupancy sensor.

    Parameters
    ----------
    cache:
        The shared ``HaStateCache`` instance.
    entity_id:
        HA entity ID of the bed sensor (e.g.
        ``binary_sensor.master_bedroom_bed_occupancy``).
    person_id:
        The household member this sensor tracks.
    room_id:
        Local room ID to return when the sensor is on.
    room_name:
        Human-readable room name.
    confidence:
        Confidence score for the snapshot (default 0.95).
    name:
        Provider name (used in ``PresenceSource``).
    priority:
        Provider priority (higher = preferred).
    """

    def __init__(
        self,
        *,
        cache: HaStateCache,
        entity_id: str,
        person_id: str,
        room_id: str,
        room_name: str,
        confidence: float = 0.95,
        name: str = "ha_bed_sensor",
        priority: int = 70,
    ) -> None:
        self._cache = cache
        self._entity_id = entity_id
        self._person_id = person_id
        self._room_id = room_id
        self._room_name = room_name
        self._confidence = confidence
        self._name = name
        self._priority = priority

    @property
    def name(self) -> str:
        return self._name

    @property
    def priority(self) -> int:
        return self._priority

    def register(self) -> None:
        """Register the entity ID with the cache for subscription."""
        self._cache.register(self._entity_id)

    async def probe(
        self,
        person_id: str,
        at: datetime,
    ) -> PresenceSnapshot | None:
        """Probe the bed sensor for *person_id*."""
        if person_id != self._person_id:
            return None

        state = self._cache.get(self._entity_id)
        if state is None or state.state != "on":
            return None

        dwell_minutes = (at - state.last_changed).total_seconds() / 60.0

        return PresenceSnapshot(
            person_id=person_id,
            status=PresenceStatus.PRESENT_ROOM,
            room_id=self._room_id,
            room_name=self._room_name,
            confidence=self._confidence,
            last_seen_at=state.last_changed,
            dwell_minutes=dwell_minutes,
            sources=(
                PresenceSource(
                    name=self._name,
                    confidence=self._confidence,
                ),
            ),
            inferred_at=at,
            notes=f"bed sensor {self._entity_id} on",
        )
