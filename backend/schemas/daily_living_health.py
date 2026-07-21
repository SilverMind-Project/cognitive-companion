"""Response envelopes for the Daily Living memory and ledger health surface (DL-M01)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ObservationsByDayOut(BaseModel):
    """One day/source bucket of semantic-memory observation counts."""

    model_config = ConfigDict(extra="forbid")

    day: str
    source: str
    count: int


class SemanticMemoryHealthOut(BaseModel):
    """Write-recency snapshot for the semantic-memory service."""

    model_config = ConfigDict(extra="forbid")

    reachable: bool
    last_observation_at: datetime | None
    last_movement_at: datetime | None
    observations_by_day: list[ObservationsByDayOut]
    total_observations: int
    total_movements: int
    stale: bool


class ActivityTypeHealthOut(BaseModel):
    """Write-recency snapshot for one activity type in the ledger."""

    model_config = ConfigDict(extra="forbid")

    activity_type: str
    count: int
    last_opened_at: datetime | None


class ActivityLedgerHealthOut(BaseModel):
    """Write-recency snapshot for the activity ledger."""

    model_config = ConfigDict(extra="forbid")

    by_type: list[ActivityTypeHealthOut]
    stale: bool


class DailyLivingHealthOut(BaseModel):
    """Combined memory + ledger health snapshot for the admin dashboard."""

    model_config = ConfigDict(extra="forbid")

    semantic_memory: SemanticMemoryHealthOut
    activity_ledger: ActivityLedgerHealthOut
