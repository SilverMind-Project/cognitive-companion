"""Built-in presence providers."""

from __future__ import annotations

from backend.services.presence.providers.cts_location import (
    CtsLocationProvider,
)
from backend.services.presence.providers.ha_bed_sensor import (
    HaBedSensorProvider,
)
from backend.services.presence.providers.ha_device_tracker import (
    HaDeviceTrackerProvider,
)

__all__ = [
    "CtsLocationProvider",
    "HaBedSensorProvider",
    "HaDeviceTrackerProvider",
]
