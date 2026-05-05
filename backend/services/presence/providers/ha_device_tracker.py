"""HaDeviceTrackerProvider: reads HA device_tracker state.

Returns ``PRESENT_HOME``, ``AWAY``, or ``PRESENT_HOME`` (named zone)
based on the device tracker state.
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


class HaDeviceTrackerProvider:
    """Presence provider backed by an HA device_tracker entity.

    Parameters
    ----------
    cache:
        The shared ``HaStateCache`` instance.
    entity_id_template:
        Python f-string template for the entity ID, e.g.
        ``"device_tracker.{person_id}_phone"``.
    person_id_map:
        Optional mapping from person_id to the entity-name portion.
        When provided, the template uses ``map[person_id]`` instead
        of ``person_id`` directly.
    confidence:
        Confidence score for home/away snapshots (default 0.8).
    name:
        Provider name (used in ``PresenceSource``).
    priority:
        Provider priority (higher = preferred).
    """

    def __init__(
        self,
        *,
        cache: HaStateCache,
        entity_id_template: str,
        confidence: float = 0.8,
        person_id_map: dict[str, str] | None = None,
        name: str = "ha_device_tracker",
        priority: int = 30,
    ) -> None:
        self._cache = cache
        self._entity_id_template = entity_id_template
        self._confidence = confidence
        self._person_id_map = person_id_map or {}
        self._name = name
        self._priority = priority
        self._registered: set[str] = set()

    @property
    def name(self) -> str:
        return self._name

    @property
    def priority(self) -> int:
        return self._priority

    def register_for_person(self, person_id: str) -> None:
        """Register the entity ID for *person_id* with the cache."""
        entity_id = self._resolve_entity_id(person_id)
        self._cache.register(entity_id)
        self._registered.add(entity_id)

    def _resolve_entity_id(self, person_id: str) -> str:
        """Resolve the HA entity ID for *person_id*."""
        key = self._person_id_map.get(person_id, person_id)
        return self._entity_id_template.format(person_id=key)

    async def probe(
        self,
        person_id: str,
        at: datetime,
    ) -> PresenceSnapshot | None:
        """Probe the device tracker for *person_id*."""
        entity_id = self._resolve_entity_id(person_id)
        state = self._cache.get(entity_id)
        if state is None:
            return None

        status: PresenceStatus
        room_id: str | None = None
        room_name: str | None = None
        notes: str | None = None

        if state.state == "home":
            status = PresenceStatus.PRESENT_HOME
        elif state.state in ("not_home", "away"):
            status = PresenceStatus.AWAY
        else:
            # Named zone (e.g. "work", "gym") → PRESENT_HOME with notes.
            status = PresenceStatus.PRESENT_HOME
            notes = f"zone={state.state}"

        return PresenceSnapshot(
            person_id=person_id,
            status=status,
            room_id=room_id,
            room_name=room_name,
            confidence=self._confidence,
            last_seen_at=state.last_changed,
            dwell_minutes=None,
            sources=(
                PresenceSource(
                    name=self._name,
                    confidence=self._confidence,
                ),
            ),
            inferred_at=at,
            notes=notes,
        )
