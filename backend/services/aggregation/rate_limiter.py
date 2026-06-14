"""Per-camera token-bucket rate limiting for image eligibility."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class PerCameraRateLimiter:
    """Per-camera token-bucket limiter for image-eligible frames.

    A rate of zero or less disables limiting. The clock is injectable for
    deterministic tests; production uses ``time.monotonic``.
    """

    def __init__(
        self,
        default_rate_per_second: float = 0.0,
        default_burst: float | None = None,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._default_rate = default_rate_per_second
        self._default_burst = default_burst
        self._time = time_fn
        self._rates: dict[str, float] = {}
        self._bursts: dict[str, float] = {}
        self._buckets: dict[str, _Bucket] = {}

    def set_camera_rate(
        self,
        camera_id: str,
        rate_per_second: float,
        burst: float | None = None,
    ) -> None:
        """Override the rate and optional burst capacity for one camera."""
        self._rates[camera_id] = rate_per_second
        if burst is not None:
            self._bursts[camera_id] = burst
        self._buckets.pop(camera_id, None)

    def rate_for(self, camera_id: str) -> float:
        """Return the configured rate for a camera."""
        return self._rates.get(camera_id, self._default_rate)

    def tokens_available(self, camera_id: str) -> float | None:
        """Return current tokens, or None when limiting is disabled."""
        if self.rate_for(camera_id) <= 0:
            return None
        self._refill(camera_id)
        bucket = self._buckets.get(camera_id)
        return bucket.tokens if bucket else self._burst_for(camera_id)

    def allow(self, camera_id: str) -> bool:
        """Consume one token and allow a frame when capacity is available."""
        rate = self.rate_for(camera_id)
        if rate <= 0:
            return True
        self._refill(camera_id)
        bucket = self._buckets[camera_id]
        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return True
        return False

    def _burst_for(self, camera_id: str) -> float:
        burst = self._bursts.get(camera_id, self._default_burst)
        if burst is not None:
            return max(1.0, burst)
        return max(1.0, self.rate_for(camera_id))

    def _refill(self, camera_id: str) -> None:
        now = self._time()
        rate = self.rate_for(camera_id)
        burst = self._burst_for(camera_id)
        bucket = self._buckets.get(camera_id)
        if bucket is None:
            self._buckets[camera_id] = _Bucket(tokens=burst, last_refill=now)
            return
        elapsed = max(0.0, now - bucket.last_refill)
        bucket.tokens = min(burst, bucket.tokens + elapsed * rate)
        bucket.last_refill = now
