"""Shared floor-plan scale and normalized-to-metre coordinate conversion helpers.

Every consumer that converts normalized ``[0, 1]`` floor-plan coordinates into
household floor-plan metres (room polygons, RF node site-config, anchor survey
checks, homography visibility) uses the exact formula mirrored in CTS
``cc_config_sync._floor_plan_scale_m``:

    width_m  = floor_plan_width * floor_meters_per_pixel
    height_m = floor_plan_height * floor_meters_per_pixel
    x_m      = x_norm * width_m
    y_m      = y_norm * height_m
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from backend.models.household_settings import HouseholdSettings

SURVEY_DISCREPANCY_WARN_M = 0.2

WallEdge = Literal["left", "right", "top", "bottom"]


@dataclass(frozen=True)
class FloorPlanScale:
    """Validated floor-plan dimensions in metres."""

    floor_plan_id: str
    width_m: float
    height_m: float


@dataclass(frozen=True)
class SurveyCheckItem:
    """Comparison of one tape-measured distance against the clicked floor-plan position."""

    reference_kind: Literal["wall", "node"]
    reference_id: str
    measured_m: float
    expected_m: float
    discrepancy_m: float
    exceeds_tolerance: bool


def shared_floor_plan_id(settings: HouseholdSettings | None) -> str:
    """Return the canonical shared floor-plan identifier for the household."""
    if settings is not None and settings.floor_plan_key:
        return settings.floor_plan_key
    return "household:1"


def floor_plan_scale(settings: HouseholdSettings | None) -> FloorPlanScale | None:
    """Return validated floor-plan dimensions in metres, or ``None`` if incomplete."""
    if settings is None:
        return None
    if not settings.floor_plan_key:
        return None
    w = settings.floor_plan_width
    h = settings.floor_plan_height
    mpp = settings.floor_meters_per_pixel
    if not w or not h or not mpp or w <= 0 or h <= 0 or mpp <= 0.0:
        return None
    return FloorPlanScale(
        floor_plan_id=shared_floor_plan_id(settings),
        width_m=float(w) * float(mpp),
        height_m=float(h) * float(mpp),
    )


def norm_to_floor_m(x_norm: float, y_norm: float, scale: FloorPlanScale) -> tuple[float, float]:
    """Convert normalized floor-plan coordinates ``[0, 1]`` into metres ``(x_m, y_m)``."""
    return (float(x_norm) * scale.width_m, float(y_norm) * scale.height_m)


def wall_distance_m(x_m: float, y_m: float, wall: WallEdge, scale: FloorPlanScale) -> float:
    """Return perpendicular distance in metres from ``(x_m, y_m)`` to a floor-plan edge."""
    if wall == "left":
        return x_m
    if wall == "right":
        return scale.width_m - x_m
    if wall == "top":
        return y_m
    if wall == "bottom":
        return scale.height_m - y_m
    raise ValueError(f"Unsupported wall edge: {wall!r}")


def evaluate_survey_distance(
    *,
    x_m: float,
    y_m: float,
    z_m: float,
    reference_kind: Literal["wall", "node"],
    reference_id: str,
    measured_m: float,
    scale: FloorPlanScale,
    other_node_xyz_m: tuple[float, float, float] | None = None,
    tolerance_m: float = SURVEY_DISCREPANCY_WARN_M,
) -> SurveyCheckItem:
    """Compare one tape measurement against the placed coordinate."""
    if reference_kind == "wall":
        if reference_id not in ("left", "right", "top", "bottom"):
            raise ValueError(f"Invalid wall reference {reference_id!r}")
        expected_m = wall_distance_m(x_m, y_m, reference_id, scale)  # type: ignore[arg-type]
    else:
        if other_node_xyz_m is None:
            raise ValueError(f"Reference node {reference_id!r} coordinates are required")
        ox, oy, oz = other_node_xyz_m
        expected_m = math.sqrt((x_m - ox) ** 2 + (y_m - oy) ** 2 + (z_m - oz) ** 2)

    discrepancy_m = abs(expected_m - measured_m)
    return SurveyCheckItem(
        reference_kind=reference_kind,
        reference_id=reference_id,
        measured_m=measured_m,
        expected_m=round(expected_m, 4),
        discrepancy_m=round(discrepancy_m, 4),
        exceeds_tolerance=discrepancy_m > tolerance_m,
    )
