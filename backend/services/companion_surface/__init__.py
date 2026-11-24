"""Companion surface registry service package."""

from __future__ import annotations

from backend.services.companion_surface.service import (
    CompanionSurfaceService,
    SurfaceDeviceState,
    SurfaceView,
)

__all__ = ["CompanionSurfaceService", "SurfaceDeviceState", "SurfaceView"]
