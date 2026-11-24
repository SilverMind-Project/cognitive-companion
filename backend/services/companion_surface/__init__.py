"""Companion surface registry service package."""

from __future__ import annotations

from backend.services.companion_surface.service import (
    SURFACE_TEST_LEASE_SECONDS,
    CompanionSurfaceService,
    SurfaceDeviceState,
    SurfaceTestResult,
    SurfaceView,
)

__all__ = [
    "SURFACE_TEST_LEASE_SECONDS",
    "CompanionSurfaceService",
    "SurfaceDeviceState",
    "SurfaceTestResult",
    "SurfaceView",
]
