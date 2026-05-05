"""UnknownProvider: sentinel that always returns UNKNOWN.

This provider has priority 0 (lowest) and always returns a
``PresenceSnapshot`` with ``UNKNOWN`` status.  It serves as the
final fallback when no other provider can answer.
"""

from __future__ import annotations

from datetime import datetime

from backend.services.presence import (
    PresenceSnapshot,
    PresenceSource,
    PresenceStatus,
)


class UnknownProvider:
    """Lowest-priority sentinel provider that always returns UNKNOWN.

    Parameters
    ----------
    name:
        Provider name (used in ``PresenceSource``).
    """

    def __init__(
        self,
        *,
        name: str = "unknown_sentinel",
    ) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def priority(self) -> int:
        return 0

    async def probe(
        self,
        person_id: str,
        at: datetime,
    ) -> PresenceSnapshot:
        """Always return an UNKNOWN snapshot."""
        return PresenceSnapshot(
            person_id=person_id,
            status=PresenceStatus.UNKNOWN,
            room_id=None,
            room_name=None,
            confidence=0.0,
            last_seen_at=None,
            dwell_minutes=None,
            sources=(
                PresenceSource(
                    name=self._name,
                    confidence=0.0,
                ),
            ),
            inferred_at=at,
            notes="no provider matched",
        )
