"""Gait trend BFF envelope: per-day speed records and aggregate trend signal."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GaitDayPoint(BaseModel):
    date: str = Field(description="ISO-8601 date (YYYY-MM-DD)")
    median_speed_m_s: float | None = Field(
        description="Median walking speed that day in m/s, or null if insufficient"
    )
    bout_count: int
    total_walking_s: float
    sufficient: bool = Field(
        description="True when the day meets data quality gates (>=3 bouts, >=60 s walking)"
    )


class GaitTrendEnvelope(BaseModel):
    person_id: str
    days: list[GaitDayPoint]
    baseline_median_m_s: float | None = Field(
        description="Duration-weighted median speed over days 28-56 in the window; null when insufficient baseline"
    )
    trend: Literal["stable", "declining", "insufficient"] = Field(
        description="stable: no significant decline; declining: robust decline detected; insufficient: not enough data"
    )
