"""PresenceService: fused presence query over multiple providers.

For Block 1 the fusion rule is simple: iterate providers sorted by
priority descending, return the first non-None snapshot whose confidence
meets the floor.  Block 3 will replace this with the configurable engine.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from backend.core.logging import get_logger
from backend.services.presence.types import (
    PresenceProvider,
    PresenceSnapshot,
    PresenceStatus,
)

logger = get_logger(__name__)


class PresenceService:
    """Orchestrates presence providers and fuses their results."""

    def __init__(
        self,
        providers: list[PresenceProvider],
        *,
        confidence_floor: float = 0.0,
    ) -> None:
        self._providers = sorted(providers, key=lambda p: p.priority, reverse=True)
        self._confidence_floor = confidence_floor

    async def get(
        self,
        person_id: str,
        at: datetime | None = None,
    ) -> PresenceSnapshot:
        """Return the fused presence snapshot for *person_id*.

        Iterates providers sorted by priority descending.  The first
        non-None snapshot whose ``confidence >= confidence_floor`` wins.
        If none qualifies, returns a sentinel ``UNKNOWN`` snapshot.
        """
        if at is None:
            at = datetime.now(UTC)

        for provider in self._providers:
            snapshot = await provider.probe(person_id, at)
            if snapshot is None:
                continue
            if snapshot.confidence >= self._confidence_floor:
                return replace(snapshot, inferred_at=at)

        return PresenceSnapshot(
            person_id=person_id,
            status=PresenceStatus.UNKNOWN,
            room_id=None,
            room_name=None,
            confidence=0.0,
            last_seen_at=None,
            dwell_minutes=None,
            sources=(),
            inferred_at=at,
            notes="no provider matched",
        )

    async def history(
        self,
        person_id: str,
        since: datetime,
    ) -> list[PresenceSnapshot]:
        """Return historical snapshots for *person_id* since *since*.

        Block 9 territory.
        """
        raise NotImplementedError("history is block 9 territory")

    async def for_room(self, room_id: str) -> list[PresenceSnapshot]:
        """Return snapshots of all persons in *room_id*.

        Block 9 territory.
        """
        raise NotImplementedError("for_room is block 9 territory")
