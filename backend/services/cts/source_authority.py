"""SourceAuthority: decides which source may overwrite PersonLocationState.

Without an explicit arbiter, two signal paths can race on the same identity:

1. **CTS** (tracking-orchestrator events) - highest-confidence when available
   because it merges face + body ReID + camera topology.
2. **Home Assistant** presence sensors - polled every 30s; authoritative
   when cameras are offline or during low-light hours, but laggier and
   less granular than CTS.
3. **scene-analysis** fallback - identifies people from a single frame when
   tracking is unavailable (low-traffic rooms, guest cameras).

The default policy:

- CTS events supersede any non-CTS last_sensor_id.
- CTS events also supersede a stale CTS state (>60s old) so a fresh camera
  always wins over a stale one.
- Sensor-inferred state is never allowed to overwrite a CTS write newer
  than the configured ``cts_lock_s`` window.

The policy is codified here so the callers (:class:`LocationWriter` and
:class:`PersonTrackingService`) share one implementation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


class SourceAuthority:
    """Conflict-resolution policy between CTS and non-CTS location writers.

    The policy is intentionally simple: a new CTS event is accepted unless
    an even newer CTS event wrote within ``cts_lock_s`` seconds.  The lock
    prevents out-of-order replay from walking state backwards.
    """

    CTS_LAST_SENSOR_PREFIX = "cts:"

    def __init__(
        self,
        *,
        cts_lock_s: float = 60.0,
        cts_source_names: tuple[str, ...] = ("cts", "tracking-orchestrator"),
    ) -> None:
        self._cts_lock = timedelta(seconds=cts_lock_s)
        self._cts_source_names = cts_source_names

    def cts_supersedes(
        self,
        *,
        current_source: str,
        current_updated_at: datetime | None,
        event_time: datetime,
    ) -> bool:
        """Return ``True`` if a CTS event at ``event_time`` should write.

        - If there is no current state or no timestamp, CTS writes.
        - If the current row was written by a non-CTS source, CTS writes
          unconditionally (CTS is the higher-fidelity signal when present).
        - If the current row was written by CTS, CTS writes only when the
          event is strictly newer than the current timestamp AND the current
          row is older than ``cts_lock_s``.  This prevents out-of-order
          replay from walking the state backwards.
        """
        if current_updated_at is None:
            return True

        now_aware = _ensure_aware(current_updated_at)
        evt_aware = _ensure_aware(event_time)

        if not self._is_cts_source(current_source):
            return True

        if evt_aware <= now_aware:
            return False

        # The current CTS row is recent; accept only fresh events.
        if now_aware + self._cts_lock > evt_aware:
            return evt_aware > now_aware
        return True

    def _is_cts_source(self, source: str) -> bool:
        if not source:
            return False
        if source.startswith(self.CTS_LAST_SENSOR_PREFIX):
            return True
        return source in self._cts_source_names


def _ensure_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
