"""NightAnchorProvider: anchors presence to ASLEEP in bedroom at night.

This is the highest-priority provider in the standard chain.  It watches
HA light states and a bed-occupancy sensor, and when the conditions for
night-mode hold it clamps presence to ``ASLEEP`` in the configured
anchor room, regardless of the absence of camera evidence.

Release predicates (the ``sticky_until`` mini-DSL) can override this
anchor — for example, motion outside the bedroom in the last 5 minutes
causes the anchor to release so a lower-priority provider (e.g.
``CtsLocationProvider``) can answer.

v0 implementation notes
-----------------------
The bed sensor is **required** for the anchor to activate.  A
lights-only fallback (where the anchor activates after
``min_dark_minutes`` of darkness without a bed sensor) is documented
as a follow-up.
"""

from __future__ import annotations

from datetime import datetime

from backend.core.logging import get_logger
from backend.integrations.ha_state_cache import HaStateCache
from backend.services.cts.location_repository import LocationRepository
from backend.services.presence import (
    PresenceSnapshot,
    PresenceSource,
    PresenceStatus,
)
from backend.services.presence.anchor_rules import AnchorPredicate

logger = get_logger(__name__)


class NightAnchorProvider:
    """Presence provider that anchors to ASLEEP during night-mode.

    Parameters
    ----------
    cache:
        The shared ``HaStateCache`` instance.
    location_repository:
        Repository for reading the last known ``PersonLocationState``.
    light_entities:
        List of HA light entity IDs that must all be ``off`` for the
        anchor to activate.
    bed_sensor_entity:
        HA bed-occupancy entity ID.  Must be ``on`` for the anchor to
        activate.  If ``None``, the anchor never activates (v0
        requires the bed sensor).
    anchor_room_id:
        Local room ID to return when anchored.
    anchor_room_name:
        Human-readable room name to return when anchored.
    require_last_room_in:
        The anchor only activates when the person's last known room is
        in this list (e.g. ``["bedroom", "hallway"]``).
    release_predicates:
        Compiled ``AnchorPredicate`` objects.  If **any** predicate
        evaluates to ``True``, the anchor releases (returns ``None``).
    confidence:
        Confidence score for the ASLEEP snapshot (default 0.95).
    min_dark_minutes:
        Minimum minutes the lights must have been off before the
        anchor activates.  Only relevant when a bed sensor is present;
        the bed sensor state is checked against this threshold.
        Default 10.
    name:
        Provider name (used in ``PresenceSource``).
    priority:
        Provider priority (higher = preferred).  Default 90 (highest
        among the standard providers).
    """

    def __init__(
        self,
        *,
        cache: HaStateCache,
        location_repository: LocationRepository,
        light_entities: list[str],
        bed_sensor_entity: str | None,
        anchor_room_id: str,
        anchor_room_name: str,
        require_last_room_in: list[str],
        release_predicates: list[AnchorPredicate] | None = None,
        confidence: float = 0.95,
        min_dark_minutes: int = 10,
        name: str = "night_anchor",
        priority: int = 90,
    ) -> None:
        self._cache = cache
        self._repo = location_repository
        self._light_entities = light_entities
        self._bed_sensor_entity = bed_sensor_entity
        self._anchor_room_id = anchor_room_id
        self._anchor_room_name = anchor_room_name
        self._require_last_room_in = [r.lower() for r in require_last_room_in]
        self._release_predicates = release_predicates or []
        self._confidence = confidence
        self._min_dark_minutes = min_dark_minutes
        self._name = name
        self._priority = priority

    @property
    def name(self) -> str:
        return self._name

    @property
    def priority(self) -> int:
        return self._priority

    def register(self) -> None:
        """Register all entity IDs with the cache for subscription."""
        for entity_id in self._light_entities:
            self._cache.register(entity_id)
        if self._bed_sensor_entity is not None:
            self._cache.register(self._bed_sensor_entity)
        # Release predicates may reference additional entities;
        # collect and register them.
        from backend.services.presence.anchor_rules import (
            collect_predicate_entities,
        )

        for eid in collect_predicate_entities(self._release_predicates):
            self._cache.register(eid)

    async def probe(
        self,
        person_id: str,
        at: datetime,
    ) -> PresenceSnapshot | None:
        """Probe night-mode conditions for *person_id*.

        Returns an ``ASLEEP`` snapshot when all night-mode conditions
        hold, or ``None`` when the anchor is released or conditions
        are not met.
        """
        # Step 1: Check release predicates.
        for pred in self._release_predicates:
            if pred.evaluate(self._cache, at):
                logger.debug(
                    "night_anchor_released",
                    person_id=person_id,
                    predicate=str(pred.__class__.__name__),
                )
                return None

        # Step 2: All light entities must be off.
        for entity_id in self._light_entities:
            state = self._cache.get(entity_id)
            if state is None:
                # Missing light entity → cannot confirm dark; yield.
                return None
            if state.state != "off":
                logger.debug(
                    "night_anchor_light_on",
                    person_id=person_id,
                    entity_id=entity_id,
                    state=state.state,
                )
                return None

        # Step 3: Last known room must be in the require list.
        state = self._repo.get_state(person_id)
        if state is None or state.current_room_name is None:
            return None
        if state.current_room_name.lower() not in self._require_last_room_in:
            logger.debug(
                "night_anchor_wrong_room",
                person_id=person_id,
                last_room=state.current_room_name,
            )
            return None

        # Step 4: Bed sensor must be on (v0 requirement).
        if self._bed_sensor_entity is not None:
            bed_state = self._cache.get(self._bed_sensor_entity)
            if bed_state is None or bed_state.state != "on":
                logger.debug(
                    "night_anchor_bed_sensor_off",
                    person_id=person_id,
                    entity_id=self._bed_sensor_entity,
                )
                return None

        # All conditions met → ASLEEP.
        dwell_minutes: float | None = None
        if state.last_seen_at is not None:
            dwell_minutes = (
                (at - state.last_seen_at).total_seconds() / 60.0
            )

        sources_parts = [
            PresenceSource(name=self._name, confidence=self._confidence),
        ]
        if self._bed_sensor_entity is not None:
            sources_parts.append(
                PresenceSource(
                    name=self._bed_sensor_entity,
                    confidence=0.9,
                ),
            )

        return PresenceSnapshot(
            person_id=person_id,
            status=PresenceStatus.ASLEEP,
            room_id=self._anchor_room_id,
            room_name=self._anchor_room_name,
            confidence=self._confidence,
            last_seen_at=state.last_seen_at,
            dwell_minutes=dwell_minutes,
            sources=tuple(sources_parts),
            inferred_at=at,
            notes="anchored, bedroom lights off, bed sensor on",
        )
