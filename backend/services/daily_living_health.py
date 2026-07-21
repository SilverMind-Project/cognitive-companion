"""Daily Living memory + ledger health snapshot (DL-M01).

Surfaces whether semantic memory and the activity ledger are actually being
written to, which the platform's own steps degrade silently by design
(`semantic_memory_query` / `semantic_memory_write` return quiet zero-values
when the upstream is unconfigured). This service makes that state visible
on the admin dashboard instead of only in structured logs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.core.time import UTC
from backend.integrations.semantic_memory_client import (
    ObservationsByDay,
    SemanticMemoryClient,
)
from backend.models.person import ActivitySession

logger = get_logger(__name__)

DBSessionFactory = Callable[[], Session]
TimeFn = Callable[[], datetime]


def _default_time_fn() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ActivityTypeHealth:
    """Write recency for one activity type over the lookback window."""

    activity_type: str
    count: int
    last_opened_at: datetime | None


@dataclass(frozen=True)
class ActivityLedgerHealth:
    """Activity ledger population snapshot."""

    by_type: list[ActivityTypeHealth] = field(default_factory=list)
    stale: bool = True


@dataclass(frozen=True)
class SemanticMemoryHealth:
    """Semantic-memory write-recency snapshot."""

    reachable: bool
    last_observation_at: datetime | None
    last_movement_at: datetime | None
    observations_by_day: list[ObservationsByDay] = field(default_factory=list)
    total_observations: int = 0
    total_movements: int = 0
    stale: bool = True


@dataclass(frozen=True)
class DailyLivingHealthSnapshot:
    """Combined memory + ledger health snapshot for the admin dashboard."""

    semantic_memory: SemanticMemoryHealth
    activity_ledger: ActivityLedgerHealth


class DailyLivingHealthService:
    """Reports write recency for semantic memory and the activity ledger.

    Read-only; never mutates data. Each half degrades independently: an
    unconfigured or unreachable semantic-memory client yields
    ``reachable=False`` and ``stale=True`` rather than raising.
    """

    def __init__(
        self,
        db_session_factory: DBSessionFactory,
        semantic_memory_client: SemanticMemoryClient | None,
        *,
        memory_stale_hours: float = 24.0,
        ledger_stale_hours: float = 48.0,
        lookback_days: int = 14,
        time_fn: TimeFn = _default_time_fn,
    ) -> None:
        self._db_session_factory = db_session_factory
        self._semantic_memory = semantic_memory_client
        self._memory_stale_hours = memory_stale_hours
        self._ledger_stale_hours = ledger_stale_hours
        self._lookback_days = lookback_days
        self._time_fn = time_fn

    async def snapshot(self) -> DailyLivingHealthSnapshot:
        """Return the combined health snapshot."""
        return DailyLivingHealthSnapshot(
            semantic_memory=await self._semantic_memory_health(),
            activity_ledger=self._activity_ledger_health(),
        )

    async def _semantic_memory_health(self) -> SemanticMemoryHealth:
        if self._semantic_memory is None:
            logger.warning("daily_living_health_semantic_memory_unconfigured")
            return SemanticMemoryHealth(
                reachable=False,
                last_observation_at=None,
                last_movement_at=None,
                stale=True,
            )

        result = await self._semantic_memory.get_write_health(days=self._lookback_days)
        if result is None:
            logger.warning("daily_living_health_semantic_memory_unreachable")
            return SemanticMemoryHealth(
                reachable=False,
                last_observation_at=None,
                last_movement_at=None,
                stale=True,
            )

        return SemanticMemoryHealth(
            reachable=True,
            last_observation_at=result.last_observation_at,
            last_movement_at=result.last_movement_at,
            observations_by_day=result.observations_by_day,
            total_observations=result.total_observations,
            total_movements=result.total_movements,
            stale=self._is_stale(result.last_observation_at, self._memory_stale_hours),
        )

    def _activity_ledger_health(self) -> ActivityLedgerHealth:
        db = self._db_session_factory()
        try:
            since = self._time_fn() - timedelta(days=self._lookback_days)
            rows = (
                db.query(
                    ActivitySession.activity_type,
                    func.count(ActivitySession.id),
                    func.max(ActivitySession.opened_at),
                )
                .filter(ActivitySession.opened_at >= since)
                .group_by(ActivitySession.activity_type)
                .order_by(func.max(ActivitySession.opened_at).desc())
                .all()
            )
        finally:
            db.close()

        by_type = [
            ActivityTypeHealth(
                activity_type=activity_type,
                count=count,
                last_opened_at=last_opened_at,
            )
            for activity_type, count, last_opened_at in rows
        ]
        latest = max(
            (row.last_opened_at for row in by_type if row.last_opened_at is not None),
            default=None,
        )
        return ActivityLedgerHealth(
            by_type=by_type,
            stale=self._is_stale(latest, self._ledger_stale_hours),
        )

    def _is_stale(self, last_at: datetime | None, stale_hours: float) -> bool:
        if last_at is None:
            return True
        return (self._time_fn() - last_at) > timedelta(hours=stale_hours)
