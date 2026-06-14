"""Unit tests for shared cooldown tracking."""

from __future__ import annotations

from backend.services.aggregation import CooldownTracker


class _Clock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_active_true_before_deadline() -> None:
    clock = _Clock()
    tracker = CooldownTracker(time_fn=clock)

    tracker.arm("camera-1", 10.0)

    assert tracker.active("camera-1") is True


def test_active_false_after_deadline() -> None:
    clock = _Clock()
    tracker = CooldownTracker(time_fn=clock)
    tracker.arm("camera-1", 10.0)

    clock.now = 10.0

    assert tracker.active("camera-1") is False


def test_remaining_none_when_unset() -> None:
    tracker = CooldownTracker()

    assert tracker.remaining("camera-1") is None


def test_remaining_positive_then_none_after_expiry() -> None:
    clock = _Clock(now=5.0)
    tracker = CooldownTracker(time_fn=clock)
    tracker.arm("camera-1", 10.0)

    assert tracker.remaining("camera-1") == 10.0

    clock.now = 15.0

    assert tracker.remaining("camera-1") is None
