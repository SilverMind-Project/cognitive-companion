"""MemoryQueryService -- read-side wrapper around SemanticMemoryClient.

Consolidates the two public read patterns currently scattered across
``semantic_memory_query.py`` and ``object_trend_analysis.py``:

- ``room_context()`` -- observations + objects + hazards for a room.
- ``room_trends()`` -- object trends + snapshots for a room.
- ``search()`` -- free-text vector search.

When ``client`` is ``None`` (service unavailable), all methods return
empty results and never raise.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from backend.core.logging import get_logger
from backend.integrations.semantic_memory_client import (
    ObservationSearchRequest,
    SemanticMemoryClient,
)
from backend.services.memory_query.types import (
    HazardObservation,
    ObjectPresenceRecord,
    ObservationSearchHit,
    RoomContext,
    RoomTrendContext,
    TrendSnapshot,
)

logger = get_logger(__name__)

_SEVERITY_ORDER = {"ok": 0, "info": 1, "warning": 2, "critical": 3}


class _TTLCache:
    """Minimal in-memory TTL cache (no external dependencies).

    Simple dict keyed on a hashable tuple of arguments.  Entries expire
    after ``ttl_seconds``.  Evicts at most ``maxsize`` entries (FIFO
    eviction when full).
    """

    def __init__(self, ttl_seconds: int = 30, maxsize: int = 256) -> None:
        self._ttl = ttl_seconds
        self._maxsize = maxsize
        self._store: dict[tuple, tuple[datetime, object]] = {}

    def get(self, key: tuple) -> object | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if datetime.now(UTC) >= expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: tuple, value: object) -> None:
        if len(self._store) >= self._maxsize:
            # Evict oldest entry (dict insertion order).
            oldest_key = next(iter(self._store))
            del self._store[oldest_key]
        self._store[key] = (datetime.now(UTC) + timedelta(seconds=self._ttl), value)


class MemoryQueryService:
    """Read-side counterpart for semantic memory queries.

    Constructor:

    - ``client``: ``SemanticMemoryClient | None``.  When ``None``, all
      methods return empty results without calling any HTTP endpoint.
    - ``cache_enabled``: when ``True``, ``room_context()`` and
      ``room_trends()`` results are cached for ``cache_ttl_seconds``.
    - ``cache_maxsize``: maximum number of cached entries (default 256).
    """

    def __init__(
        self,
        *,
        client: SemanticMemoryClient | None,
        cache_enabled: bool = False,
        cache_ttl_seconds: int = 30,
        cache_maxsize: int = 256,
    ) -> None:
        self._client = client
        self._cache: _TTLCache | None = (
            _TTLCache(ttl_seconds=cache_ttl_seconds, maxsize=cache_maxsize)
            if cache_enabled
            else None
        )

    # ------------------------------------------------------------------
    # room_context
    # ------------------------------------------------------------------

    async def room_context(
        self,
        room_id: str,
        *,
        since_minutes: int = 60,
        objects_any: tuple[str, ...] = (),
        hazard_flags_any: tuple[str, ...] = (),
        query_text: str = "",
        limit: int = 5,
    ) -> RoomContext:
        """Query semantic memory for scene context in a single room.

        Returns a ``RoomContext`` with recent objects, hazards,
        observations, a compact summary, and observation count.
        """
        # Cache hit path.
        if self._cache is not None:
            cache_key = (
                room_id,
                since_minutes,
                objects_any,
                hazard_flags_any,
                query_text,
                limit,
            )
            hit = self._cache.get(cache_key)
            if hit is not None:
                return cast(RoomContext, hit)

        # No client → empty context.
        if self._client is None:
            result = RoomContext(
                room_id=room_id,
                summary="No memory context available.",
            )
            if self._cache is not None:
                self._cache.set(cache_key if self._cache is not None else (), result)
            return result

        # -- Search observations -------------------------------------------
        req = ObservationSearchRequest(
            room_id=room_id,
            since_minutes=since_minutes,
            objects_any=list(objects_any),
            hazard_flags_any=list(hazard_flags_any),
            query_text=query_text,
            limit=limit,
        )
        observations: list[ObservationSearchHit] = await self._client.search_observations(req)

        # -- Recent objects ------------------------------------------------
        recent_objects: list[ObjectPresenceRecord] = []
        try:
            obj_records = await self._client.get_recent_objects(
                room_id, since_minutes=since_minutes
            )
            recent_objects = list(obj_records)
        except Exception:  # noqa: BLE001
            logger.warning("recent_objects_fetch_failed", room_id=room_id)

        # -- Format hazards ------------------------------------------------
        recent_hazards: list[HazardObservation] = []
        if hazard_flags_any:
            recent_hazards = [
                HazardObservation(
                    id=o.id,
                    room_id=o.room_id,
                    observed_at=o.observed_at,
                    hazard_flags=o.hazard_flags,
                    description=o.description,
                )
                for o in observations
                if o.hazard_flags
            ]

        # -- Build summary -------------------------------------------------
        summary = self._build_context_summary(
            room_id=room_id,
            since_minutes=since_minutes,
            recent_objects=recent_objects,
            recent_hazards=recent_hazards,
            observations=observations,
        )

        result = RoomContext(
            room_id=room_id,
            recent_objects=tuple(recent_objects),
            recent_hazards=tuple(recent_hazards),
            observations=tuple(observations),
            summary=summary,
            observations_count=len(observations),
        )

        if self._cache is not None:
            self._cache.set(cache_key, result)

        return result

    # ------------------------------------------------------------------
    # room_trends
    # ------------------------------------------------------------------

    async def room_trends(
        self,
        room_id: str,
        *,
        include_snapshots_hours: int = 0,
        severity_threshold: str = "info",
    ) -> RoomTrendContext | None:
        """Query semantic memory for trend state in a single room.

        Returns ``None`` when the client is unavailable or the service
        returns no data for the room.
        """
        # Cache hit path.
        if self._cache is not None:
            cache_key = (room_id, include_snapshots_hours, severity_threshold)
            hit = self._cache.get(cache_key)
            if hit is not None:
                return cast(RoomTrendContext | None, hit)

        if self._client is None:
            return None

        try:
            result = await self._client.get_room_trends(room_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("trend_fetch_failed", room_id=room_id, error=str(exc))
            return None

        if not result:
            return None

        # Apply severity threshold filtering.
        threshold_level = _SEVERITY_ORDER.get(severity_threshold, 1)
        filtered_anomalies = [
            a
            for a in result.anomalies
            if _SEVERITY_ORDER.get(a.get("severity", "ok"), 0) >= threshold_level
        ]

        # Fetch snapshots if requested.
        snapshots: tuple[TrendSnapshot, ...] | None = None
        if include_snapshots_hours > 0:
            try:
                snap_list = await self._client.get_snapshots(
                    room_id, since_hours=include_snapshots_hours
                )
                snapshots = tuple(snap_list)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "trend_snapshots_failed",
                    room_id=room_id,
                    error=str(exc),
                )

        ctx = RoomTrendContext(
            room_id=room_id,
            clutter_score=result.clutter_score,
            trend_direction=result.trend_direction,
            overall_severity=result.overall_severity,
            persistent_objects=result.persistent_objects,
            novel_objects=result.novel_objects,
            anomalies=tuple(filtered_anomalies),
            snapshots=snapshots,
        )

        if self._cache is not None:
            self._cache.set(cache_key, ctx)

        return ctx

    # ------------------------------------------------------------------
    # search
    # ------------------------------------------------------------------

    async def search(
        self,
        *,
        query_text: str = "",
        room_id: str | None = None,
        since_minutes: int | None = 60,
        objects_any: tuple[str, ...] = (),
        kind: str | None = None,
        person_id: str | None = None,
        limit: int = 10,
    ) -> tuple[ObservationSearchHit, ...]:
        """Free-text vector search over observations, with structured filters.

        ``objects_any``/``kind``/``person_id`` are exact-match filters
        (DL-M05); when ``query_text`` is empty, results fall back to
        most-recent-first ordering, which is what a structured "last
        matching record" lookup wants. Not cached (too much variation in
        query_text and filters).
        """
        if self._client is None:
            return ()

        req = ObservationSearchRequest(
            room_id=room_id,
            since_minutes=since_minutes,
            objects_any=list(objects_any),
            query_text=query_text,
            kind=kind,
            person_id=person_id,
            limit=limit,
        )
        hits = await self._client.search_observations(req)
        return tuple(hits)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_context_summary(
        room_id: str,
        since_minutes: int,
        recent_objects: list[ObjectPresenceRecord],
        recent_hazards: list[HazardObservation],
        observations: list[ObservationSearchHit],
    ) -> str:
        """Build a compact text summary for LLM prompt injection."""
        if observations or recent_objects:
            parts: list[str] = []
            if room_id:
                parts.append(f"In the past {since_minutes} min in {room_id}:")
            if recent_objects:
                obj_strs = [f"{r.label} ({r.observation_count}x)" for r in recent_objects]
                parts.append(", ".join(obj_strs))
            if recent_hazards:
                hazard_names: set[str] = set()
                for h in recent_hazards:
                    hazard_names.update(h.hazard_flags)
                parts.append(f"{len(hazard_names)} hazard(s): {', '.join(sorted(hazard_names))}.")
            return " ".join(parts)
        return "No memory context available."
