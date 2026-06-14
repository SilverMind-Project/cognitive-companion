"""Unit tests for per-camera token-bucket rate limiting."""

from __future__ import annotations

from backend.services.aggregation import PerCameraRateLimiter


class _Clock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_allow_passes_through_when_rate_zero() -> None:
    limiter = PerCameraRateLimiter(default_rate_per_second=0.0)

    assert limiter.allow("camera-1") is True
    assert limiter.allow("camera-1") is True


def test_allow_consumes_tokens_and_blocks_when_empty() -> None:
    clock = _Clock()
    limiter = PerCameraRateLimiter(
        default_rate_per_second=1.0,
        default_burst=1.0,
        time_fn=clock,
    )

    assert limiter.allow("camera-1") is True
    assert limiter.allow("camera-1") is False


def test_refill_restores_tokens_over_time() -> None:
    clock = _Clock()
    limiter = PerCameraRateLimiter(
        default_rate_per_second=1.0,
        default_burst=1.0,
        time_fn=clock,
    )
    assert limiter.allow("camera-1") is True

    clock.now = 1.0

    assert limiter.allow("camera-1") is True


def test_set_camera_rate_overrides_default() -> None:
    limiter = PerCameraRateLimiter(
        default_rate_per_second=1.0,
        default_burst=1.0,
    )

    limiter.set_camera_rate("camera-1", rate_per_second=2.0, burst=2.0)

    assert limiter.rate_for("camera-1") == 2.0
    assert limiter.allow("camera-1") is True
    assert limiter.allow("camera-1") is True
    assert limiter.allow("camera-1") is False


def test_tokens_available_none_when_disabled() -> None:
    limiter = PerCameraRateLimiter(default_rate_per_second=0.0)

    assert limiter.tokens_available("camera-1") is None


def test_burst_caps_token_accumulation() -> None:
    clock = _Clock()
    limiter = PerCameraRateLimiter(
        default_rate_per_second=2.0,
        default_burst=3.0,
        time_fn=clock,
    )
    assert limiter.allow("camera-1") is True

    clock.now = 100.0

    assert limiter.tokens_available("camera-1") == 3.0
