"""SourceAuthority: decides which source may overwrite PersonLocationState.

Without an explicit arbiter, three signal paths can race on the same identity:

1. **CTS** (tracking-orchestrator events) - highest-confidence when available
   because it merges face + body ReID + camera topology.
2. **reCamera person-id** - person-identification-service with face recognition.
3. **Home Assistant** presence sensors - polled every 30s; authoritative
   when cameras are offline or during low-light hours, but laggier and
   less granular than CTS.

The policy is codified here so all callers (:class:`LocationWriter` and
:class:`PersonTrackingService`) share one implementation.  This enforces
**CR-15**: one writer policy per state row.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from backend.core.logging import get_logger
from backend.services.cts._time import ensure_aware

logger = get_logger(__name__)

# Priority ranking: higher = more authoritative.
# Only sources at or above SOURCE_PRIORITY_UNKNOWN update state.
SOURCE_PRIORITY: dict[str, int] = {
    "cts:committed": 100,  # CTS with committed identity (p >= 0.65)
    "recamera:person_id": 80,  # reCamera person-identification (confidence >= 0.5)
    "ha:correlated": 40,  # HA presence sensor in CTS-confirmed room
    "ha:uncorrelated": 10,  # HA presence sensor without CTS correlation
    "cts:unknown": 0,  # CTS with UNKNOWN identity (does not update state)
}

STALENESS_THRESHOLD_S = 30.0


class SourceAuthority:
    """Conflict-resolution policy for person-location writers.

    Priority-based: a higher-priority source always overwrites.
    A lower-priority source writes only when the current state is older
    than ``staleness_threshold_s`` or the state is empty.
    Same-priority ties are broken by recency (newer wins).

    The :meth:`should_write` method is the single gate that every writer
    must pass before calling ``upsert_state`` (CR-15).
    """

    CTS_LAST_SENSOR_PREFIX = "cts:"

    def __init__(
        self,
        *,
        cts_lock_s: float = 60.0,
        cts_source_names: tuple[str, ...] = ("cts", "tracking-orchestrator"),
        staleness_threshold_s: float = STALENESS_THRESHOLD_S,
    ) -> None:
        self._cts_lock = timedelta(seconds=cts_lock_s)
        self._cts_source_names = cts_source_names
        self._staleness_threshold = timedelta(seconds=staleness_threshold_s)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_write(
        self,
        *,
        incoming_priority: int,
        incoming_time: datetime,
        current_source: str | None = None,
        current_updated_at: datetime | None = None,
    ) -> bool:
        """Return ``True`` if an event with *incoming_priority* at
        *incoming_time* should overwrite the current state.

        - No current state or no timestamp: always write.
        - Higher priority: always write.
        - Lower priority: write only when current state is older than
          ``staleness_threshold_s``.
        - Same priority: newer timestamp wins.
        """
        if incoming_priority <= 0:
            return False  # Unknown CTS never updates state

        if current_updated_at is None:
            return True

        now_aware = ensure_aware(current_updated_at)
        evt_aware = ensure_aware(incoming_time)

        current_priority = self._resolve_priority(current_source or "")

        if incoming_priority > current_priority:
            return True

        if incoming_priority < current_priority:
            age = evt_aware - now_aware
            return age > self._staleness_threshold

        # Same priority: newer wins
        return evt_aware > now_aware

    def cts_supersedes(
        self,
        *,
        current_source: str,
        current_updated_at: datetime | None,
        event_time: datetime,
    ) -> bool:
        """Legacy convenience for CTS writers.

        CTS is always priority 100 (committed).  This method exists so
        :class:`LocationWriter` callers don't need to know about priority
        values.
        """
        incoming_priority = self._resolve_priority(f"{self.CTS_LAST_SENSOR_PREFIX}committed")
        return self.should_write(
            incoming_priority=incoming_priority,
            incoming_time=event_time,
            current_source=current_source,
            current_updated_at=current_updated_at,
        )

    def priority_for(self, source: str) -> int:
        """Return the priority for a source string."""
        return self._resolve_priority(source)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_priority(self, source: str) -> int:
        """Map a source string to a priority value."""
        if not source:
            return 0

        if source.startswith(self.CTS_LAST_SENSOR_PREFIX):
            # CTS source: check if it carries a committed identity.
            # The prefix convention is "cts:{camera_id}" for committed,
            # "cts:unknown" for UNKNOWN.
            if "unknown" in source.lower():
                return SOURCE_PRIORITY.get("cts:unknown", 0)
            return SOURCE_PRIORITY.get("cts:committed", 100)

        if source in self._cts_source_names:
            return SOURCE_PRIORITY.get("cts:committed", 100)

        # ha:correlated vs ha:uncorrelated determined by caller
        if source in SOURCE_PRIORITY:
            return SOURCE_PRIORITY[source]

        if source.startswith("ha:"):
            return SOURCE_PRIORITY.get("ha:uncorrelated", 10)

        if source.startswith("recamera:") or source in ("camera", "recamera"):
            return SOURCE_PRIORITY.get("recamera:person_id", 80)

        if source == "ha_sensor":
            return SOURCE_PRIORITY.get("ha:uncorrelated", 10)

        return 10  # Default low priority

    def _is_cts_source(self, source: str) -> bool:
        if not source:
            return False
        if source.startswith(self.CTS_LAST_SENSOR_PREFIX):
            return True
        return source in self._cts_source_names
