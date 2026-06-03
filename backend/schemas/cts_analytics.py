"""Pydantic schemas for CTS analytics endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HeatmapBin(BaseModel):
    model_config = {"extra": "forbid"}

    x_m: float
    y_m: float
    weight: int = Field(ge=0)


class HeatmapEnvelope(BaseModel):
    model_config = {"extra": "forbid"}

    person_id: str
    bins: list[HeatmapBin]
