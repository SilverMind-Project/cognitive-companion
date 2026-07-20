"""Built-in presence providers."""

from __future__ import annotations

from backend.services.presence.providers.ha_bed_sensor import (
    HaBedSensorProvider,
)
from backend.services.presence.providers.ha_device_tracker import (
    HaDeviceTrackerProvider,
)
from backend.services.presence.providers.location_service import (
    LocationServiceProvider,
)
from backend.services.presence.providers.night_anchor import (
    NightAnchorProvider,
)
from backend.services.presence.providers.stale_fallback import (
    StaleFallbackProvider,
)
from backend.services.presence.providers.unknown import (
    UnknownProvider,
)

__all__ = [
    "HaBedSensorProvider",
    "HaDeviceTrackerProvider",
    "LocationServiceProvider",
    "NightAnchorProvider",
    "StaleFallbackProvider",
    "UnknownProvider",
]
