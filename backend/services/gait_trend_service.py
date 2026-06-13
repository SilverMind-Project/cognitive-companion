"""GaitTrendService: fetch and classify gait daily aggregates from CTS.

Calls CTS /internal/gait/daily, applies the same data-quality gates used by
the gait_slowing signal detector (>= 3 bouts AND >= 60 s walking per day),
computes a baseline median over the older half of the window, and classifies
the trend so the frontend never re-implements gate or classification logic.
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime, timedelta

from backend.core.logging import get_logger
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.schemas.gait import GaitDayPoint, GaitTrendEnvelope

logger = get_logger(__name__)

# A day is "sufficient" when it meets the same quality gates the signal uses.
_MIN_BOUTS = 3
_MIN_WALKING_S = 60.0

# Minimum qualifying days required in each half-window before we can classify.
_MIN_QUALIFYING_DAYS = 10

# Decline thresholds matching the signal detector (dementia_signals.py).
_DECLINE_PCT_FLOOR = 0.10  # 10 % of baseline
_DECLINE_ABS_FLOOR = 0.08  # 0.08 m/s absolute minimum


def _weighted_median(values: list[float], weights: list[float]) -> float:
    """Duration-weighted median: sort by value, accumulate weight until midpoint."""
    if not values:
        raise ValueError("empty values")
    pairs = sorted(zip(values, weights, strict=True), key=lambda p: p[0])
    total = sum(weights)
    half = total / 2.0
    cumulative = 0.0
    for val, w in pairs:
        cumulative += w
        if cumulative >= half:
            return val
    return pairs[-1][0]


def _modified_z(value: float, samples: list[float]) -> float | None:
    """Modified z-score using MAD; returns None when MAD is zero."""
    if len(samples) < 3:
        return None
    med = statistics.median(samples)
    mad = statistics.median([abs(x - med) for x in samples])
    if mad == 0:
        return None
    return 0.6745 * (value - med) / mad


class GaitTrendService:
    def __init__(self, client: OrchestratorClient) -> None:
        self._client = client

    async def get_gait_trend(
        self,
        person_id: str,
        days: int = 56,
    ) -> GaitTrendEnvelope:
        """Return a GaitTrendEnvelope for *person_id* covering the last *days* days.

        The window is split at the midpoint: the older half is the baseline;
        the recent half is evaluated for decline.
        """
        today = datetime.now(UTC).date()
        since = (today - timedelta(days=days)).isoformat()
        until = (today - timedelta(days=1)).isoformat()

        rows = await self._client.list_gait_daily(
            identity_id=person_id,
            since=since,
            until=until,
        )

        if not isinstance(rows, list):
            logger.error(
                "gait_daily_contract_violation",
                person_id=person_id,
                received_type=type(rows).__name__,
            )
            return GaitTrendEnvelope(
                person_id=person_id,
                days=[],
                baseline_median_m_s=None,
                trend="insufficient",
            )

        half = days // 2
        recent_cutoff = today - timedelta(days=half)

        day_points: list[GaitDayPoint] = []
        baseline_sufficient: list[tuple[float, float]] = []  # (speed, walking_s)
        recent_sufficient: list[tuple[float, float]] = []

        for row in rows:
            bout_count = int(row["bout_count"])
            total_walking_s = float(row["total_walking_s"])
            median_speed = float(row["median_speed_m_s"])
            sufficient = bout_count >= _MIN_BOUTS and total_walking_s >= _MIN_WALKING_S

            from datetime import date as _date

            local_date = _date.fromisoformat(row["local_date"])
            day_points.append(
                GaitDayPoint(
                    date=row["local_date"],
                    median_speed_m_s=median_speed if sufficient else None,
                    bout_count=bout_count,
                    total_walking_s=total_walking_s,
                    sufficient=sufficient,
                )
            )

            if sufficient:
                if local_date < recent_cutoff:
                    baseline_sufficient.append((median_speed, total_walking_s))
                else:
                    recent_sufficient.append((median_speed, total_walking_s))

        # Classify trend.
        if len(baseline_sufficient) < _MIN_QUALIFYING_DAYS or len(recent_sufficient) < _MIN_QUALIFYING_DAYS:
            return GaitTrendEnvelope(
                person_id=person_id,
                days=day_points,
                baseline_median_m_s=None,
                trend="insufficient",
            )

        b_speeds, b_weights = zip(*baseline_sufficient, strict=True)
        r_speeds, r_weights = zip(*recent_sufficient, strict=True)
        baseline_median = _weighted_median(list(b_speeds), list(b_weights))
        recent_median = _weighted_median(list(r_speeds), list(r_weights))

        decline_floor = max(_DECLINE_ABS_FLOOR, _DECLINE_PCT_FLOOR * baseline_median)
        mz = _modified_z(recent_median, list(b_speeds))

        is_declining = (
            recent_median <= baseline_median - decline_floor
            and (mz is None or mz <= -2.0)
        )

        return GaitTrendEnvelope(
            person_id=person_id,
            days=day_points,
            baseline_median_m_s=round(baseline_median, 3),
            trend="declining" if is_declining else "stable",
        )
