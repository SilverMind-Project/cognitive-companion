"""OccupancyReadModel: in-memory, TTL-pruned room occupancy.

The world-tracker subscriber records every hypothesis it sees in a room
(identified or not) via :meth:`record_room_presence`. Reads aggregate the
live set per room: identified hypotheses surface as ``person_ids`` and the
rest as ``unknown_count``. A hypothesis that stops being observed ages out
after ``ttl_seconds`` so occupancy clears without an explicit "left" event.

This deliberately mirrors live presence (open ``presence_segments``): it is a
read-model, not a written table. It is single-process state held in
``app.state`` -- the CTS Redis consumer ownership already assumes one process.

``get_occupancy`` also merges Home Assistant presence-sensor rows
(``RoomOccupancyState`` rows whose ``source`` is not ``cts``) so HA-only rooms
are not lost. World-tracker rooms win when both sources name the same room.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.schemas.occupancy import RoomOccupancyStateEnvelope

logger = get_logger(__name__)

WORLD_TRACKER_SOURCE = "world_tracker"
FACE_SIGHTING_SOURCE = "face_sighting"
_DEFAULT_TTL_SECONDS = 120


@dataclass
class _PHPresence:
    """One hypothesis seen in a room: identity (if known) and timing."""

    identity_id: str | None
    room_name: str
    source: str
    first_seen: datetime
    last_seen: datetime


class OccupancyReadModel:
    """Live, TTL-pruned occupancy keyed on hypothesis id.

    Parameters
    ----------
    db_factory:
        Optional session factory used to merge non-CTS ``RoomOccupancyState``
        rows (Home Assistant sensors) at read time. When ``None``, only the
        live world-tracker set is returned.
    ttl_seconds:
        How long a hypothesis stays "present" after its last observation.
    """

    def __init__(
        self,
        db_factory: Callable[[], Session] | None = None,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        self._db_factory = db_factory
        self._ttl = timedelta(seconds=ttl_seconds)
        # room_id -> {ph_id: _PHPresence}
        self._rooms: dict[int, dict[str, _PHPresence]] = {}
        self._lock = threading.Lock()

    # -- write path ----------------------------------------------------------

    def record_room_presence(
        self,
        *,
        room_id: int,
        room_name: str,
        ph_id: str,
        identity_id: str | None,
        source: str = WORLD_TRACKER_SOURCE,
        observed_at: datetime | None = None,
    ) -> None:
        """Record that ``ph_id`` was seen in ``room_id`` at ``observed_at``."""
        now = observed_at or datetime.now(UTC)
        with self._lock:
            room = self._rooms.setdefault(room_id, {})
            existing = room.get(ph_id)
            if existing is None:
                room[ph_id] = _PHPresence(
                    identity_id=identity_id,
                    room_name=room_name,
                    source=source,
                    first_seen=now,
                    last_seen=now,
                )
            else:
                existing.last_seen = max(existing.last_seen, now)
                existing.identity_id = identity_id or existing.identity_id
                existing.room_name = room_name or existing.room_name
                # A hypothesis is only ever in one room; drop any stale entry
                # for it in other rooms so it doesn't double-count.
            self._evict_from_other_rooms(ph_id, keep_room_id=room_id)

    def _evict_from_other_rooms(self, ph_id: str, *, keep_room_id: int) -> None:
        for rid, phs in list(self._rooms.items()):
            if rid == keep_room_id:
                continue
            if ph_id in phs:
                del phs[ph_id]
                if not phs:
                    del self._rooms[rid]

    # -- read path -----------------------------------------------------------

    def _prune(self, now: datetime) -> None:
        cutoff = now - self._ttl
        for rid, phs in list(self._rooms.items()):
            for ph_id, pres in list(phs.items()):
                if pres.last_seen < cutoff:
                    del phs[ph_id]
            if not phs:
                del self._rooms[rid]

    async def get_occupancy(self, room_name: str | None = None) -> list[RoomOccupancyStateEnvelope]:
        """Return live occupancy, world-tracker rooms merged with HA sensors."""
        now = datetime.now(UTC)
        # Keyed by room_name so a room is never reported twice across sources.
        by_name: dict[str, RoomOccupancyStateEnvelope] = {}

        with self._lock:
            self._prune(now)
            snapshot = {rid: dict(phs) for rid, phs in self._rooms.items()}

        for room_id, phs in snapshot.items():
            if not phs:
                continue
            identified = sorted({p.identity_id for p in phs.values() if p.identity_id})
            unknown = sum(1 for p in phs.values() if not p.identity_id)
            rn = next(iter(phs.values())).room_name
            sources = {p.source for p in phs.values()}
            primary_source = (
                WORLD_TRACKER_SOURCE
                if WORLD_TRACKER_SOURCE in sources
                else next(iter(sources))
            )
            by_name[rn] = RoomOccupancyStateEnvelope(
                room_id=room_id,
                room_name=rn,
                occupied=True,
                person_ids=identified,
                unknown_count=unknown,
                source=primary_source,
                since=min(p.first_seen for p in phs.values()),
                last_updated=max(p.last_seen for p in phs.values()),
            )

        self._merge_ha_rows(by_name)

        records = list(by_name.values())
        if room_name:
            records = [r for r in records if r.room_name == room_name]
        records.sort(key=lambda r: r.room_name)
        return records

    def _merge_ha_rows(self, by_name: dict[str, RoomOccupancyStateEnvelope]) -> None:
        """Overlay non-CTS RoomOccupancyState rows (HA sensors) at read time.

        World-tracker rooms already in ``by_name`` win; this only adds rooms
        the tracker does not currently cover. Legacy ``cts``-source rows are
        ignored -- the world tracker is now the authority for camera rooms.
        """
        if self._db_factory is None:
            return
        from backend.models.occupancy import RoomOccupancyState

        db = self._db_factory()
        try:
            rows = db.query(RoomOccupancyState).filter(RoomOccupancyState.source != "cts").all()
            for row in rows:
                if row.room_name in by_name:
                    continue
                by_name[row.room_name] = RoomOccupancyStateEnvelope(
                    room_id=None,
                    room_name=row.room_name,
                    occupied=row.occupied,
                    person_ids=list(row.person_ids or []),
                    unknown_count=0,
                    source=row.source,
                    since=row.since,
                    last_updated=row.last_updated,
                )
        except Exception:
            logger.exception("occupancy_ha_merge_error")
        finally:
            db.close()
