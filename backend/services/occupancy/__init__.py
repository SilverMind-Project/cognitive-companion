"""Unified room-occupancy read-model.

A single in-memory live store of which hypotheses (identified or not) are in
which room, fed by the world tracker and merged-at-read with Home Assistant
presence-sensor rows. Replaces the legacy ``LocationWriter`` occupancy sync as
the source for ``GET /api/v1/occupancy``.
"""

from backend.services.occupancy.read_model import OccupancyReadModel

__all__ = ["OccupancyReadModel"]
