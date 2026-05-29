"""Configuration for the unified person location service."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PersonLocationConfig:
    inferred_dwell_max_s: float = 14400.0  # 4 hours
    revision_horizon_s: float = 600.0  # 10 minutes
    ph_anchor_match_distance_m: float = 1.5
    ph_anchor_match_window_s: float = 3.0
    presence_grace_s: float = 30.0  # "away" after 30s of no segment
