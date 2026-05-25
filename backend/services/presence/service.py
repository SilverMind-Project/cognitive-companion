"""PresenceService: fused presence query over multiple providers.

Iterates providers sorted by priority descending.  The first
non-None snapshot whose confidence meets the configured floor wins.
Tie-break is by ``last_seen_at`` descending when two providers have
the same priority.

The winning snapshot's ``sources`` tuple is rebuilt to include the
winner's source first, followed by any non-None lower-priority
snapshots' sources.  This gives the UI the "all providers that had
something to say" view.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from backend.core.logging import get_logger
from backend.services.presence.config import FusionConfig, PresenceConfig
from backend.services.presence.types import (
    PresenceProvider,
    PresenceSnapshot,
    PresenceStatus,
)

logger = get_logger(__name__)


async def _fuse_highest_priority_above_floor(
    providers: list[PresenceProvider],
    confidence_floor: float,
    person_id: str,
    at: datetime,
) -> PresenceSnapshot:
    """Fusion rule: first non-None snapshot above the confidence floor wins.

    Parameters
    ----------
    providers:
        Provider instances sorted by priority descending.
    confidence_floor:
        Minimum confidence for a snapshot to qualify.
    person_id:
        The person to query.
    at:
        The point in time for the snapshot.

    Returns
    -------
    PresenceSnapshot
        The fused snapshot, or a sentinel UNKNOWN snapshot.
    """
    candidates: list[tuple[PresenceProvider, PresenceSnapshot]] = []

    for provider in providers:
        snapshot = await provider.probe(person_id, at)
        if snapshot is None:
            continue
        if snapshot.confidence >= confidence_floor:
            candidates.append((provider, snapshot))

    if not candidates:
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

    # Sort candidates: primary key is priority (desc), tie-break is
    # last_seen_at (desc, treating None as earliest).
    candidates.sort(
        key=lambda c: (
            c[0].priority,
            c[1].last_seen_at or datetime.min.replace(tzinfo=UTC),
        ),
        reverse=True,
    )

    _winner_provider, winner = candidates[0]

    # Rebuild sources: winner's source first, then any non-None
    # lower-priority snapshots' sources.
    all_sources = list(winner.sources)
    for _provider, snapshot in candidates[1:]:
        all_sources.extend(snapshot.sources)

    return replace(
        winner,
        inferred_at=at,
        sources=tuple(all_sources),
    )


# Map from FusionConfig.rule to the fusion function.
_FUSION_RULES: dict[str, Any] = {
    "highest_priority_above_floor": _fuse_highest_priority_above_floor,
}


class PresenceService:
    """Orchestrates presence providers and fuses their results."""

    def __init__(
        self,
        providers: list[PresenceProvider],
        *,
        fusion_config: FusionConfig | None = None,
        confidence_floor: float | None = None,
    ) -> None:
        """Initialise the service.

        Parameters
        ----------
        providers:
            Provider instances.
        fusion_config:
            Fusion rule configuration.  When provided, *confidence_floor*
            is ignored.
        confidence_floor:
            Deprecated.  When provided without *fusion_config*, a
            ``FusionConfig`` is created with this value.  Kept for
            backward compatibility with existing callers.
        """
        self._providers = sorted(providers, key=lambda p: p.priority, reverse=True)
        if fusion_config is not None:
            self._fusion_config = fusion_config
        elif confidence_floor is not None:
            self._fusion_config = FusionConfig(
                confidence_floor=confidence_floor,
            )
        else:
            self._fusion_config = FusionConfig()

    @property
    def providers(self) -> list[PresenceProvider]:
        """Read-only access to the sorted provider list."""
        return self._providers

    @property
    def fusion_rule(self) -> str:
        """The active fusion rule name."""
        return self._fusion_config.rule

    @property
    def confidence_floor(self) -> float:
        """The active confidence floor."""
        return self._fusion_config.confidence_floor

    def reload(
        self,
        new_config: FusionConfig | PresenceConfig,
        *,
        providers: list[PresenceProvider],
    ) -> None:
        """Atomically swap the provider chain and fusion config.

        Used by the ``/presence-config/reload`` endpoint to hot-reload
        without restarting the process.

        Parameters
        ----------
        new_config:
            A ``FusionConfig`` (or ``PresenceConfig`` with a ``.fusion``
            attribute) describing the new fusion settings.
        providers:
            New provider instances.
        """
        self._providers = sorted(providers, key=lambda p: p.priority, reverse=True)
        # Accept either a FusionConfig directly or a PresenceConfig with a
        # .fusion attribute (the reload endpoint passes the latter).
        if hasattr(new_config, "fusion"):
            self._fusion_config = new_config.fusion
        else:
            self._fusion_config = new_config

    async def get(
        self,
        person_id: str,
        at: datetime | None = None,
    ) -> PresenceSnapshot:
        """Return the fused presence snapshot for *person_id*.

        Iterates providers sorted by priority descending.  The first
        non-None snapshot whose confidence meets the configured floor
        wins.  If none qualifies, returns a sentinel UNKNOWN snapshot.
        """
        if at is None:
            at = datetime.now(UTC)

        rule_fn = _FUSION_RULES.get(self._fusion_config.rule)
        if rule_fn is None:
            raise ValueError(
                f"Unknown fusion rule {self._fusion_config.rule!r}. Known: {sorted(_FUSION_RULES)}"
            )

        return await rule_fn(
            self._providers,
            self._fusion_config.confidence_floor,
            person_id,
            at,
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
