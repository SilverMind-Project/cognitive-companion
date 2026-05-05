"""Tests for the sticky-rule evaluator (anchor_rules.py)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.integrations.ha_state_cache import HaState
from backend.services.presence.anchor_rules import (
    collect_predicate_entities,
    compile_predicate,
)

# ---------------------------------------------------------------------------
# Stub HaStateCache for tests
# ---------------------------------------------------------------------------


class _StubCache:
    """Minimal stub of HaStateCache backed by a dict."""

    def __init__(self, states: dict[str, HaState] | None = None) -> None:
        self._states: dict[str, HaState] = states or {}

    def get(self, entity_id: str) -> HaState | None:
        return self._states.get(entity_id)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def now():
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Pattern 1: entity_id == value
# ---------------------------------------------------------------------------


def test_equality_true(now):
    cache = _StubCache({
        "light.bedroom": HaState(
            entity_id="light.bedroom",
            state="off",
            attributes={},
            last_changed=now,
        ),
    })
    pred = compile_predicate("light.bedroom == off")
    assert pred.evaluate(cache, now) is True
    assert pred.entity_ids == ("light.bedroom",)


def test_equality_false(now):
    cache = _StubCache({
        "light.bedroom": HaState(
            entity_id="light.bedroom",
            state="on",
            attributes={},
            last_changed=now,
        ),
    })
    pred = compile_predicate("light.bedroom == off")
    assert pred.evaluate(cache, now) is False


def test_equality_missing_entity(now):
    cache = _StubCache()
    pred = compile_predicate("light.bedroom == off")
    # Missing entity → treated as not matching.
    assert pred.evaluate(cache, now) is False


# ---------------------------------------------------------------------------
# Pattern 2: entity_id != value
# ---------------------------------------------------------------------------


def test_negation_true(now):
    cache = _StubCache({
        "light.bedroom": HaState(
            entity_id="light.bedroom",
            state="on",
            attributes={},
            last_changed=now,
        ),
    })
    pred = compile_predicate("light.bedroom != off")
    assert pred.evaluate(cache, now) is True


def test_negation_false(now):
    cache = _StubCache({
        "light.bedroom": HaState(
            entity_id="light.bedroom",
            state="off",
            attributes={},
            last_changed=now,
        ),
    })
    pred = compile_predicate("light.bedroom != off")
    assert pred.evaluate(cache, now) is False


# ---------------------------------------------------------------------------
# Pattern 3: motion outside <room> in last <N>m
# ---------------------------------------------------------------------------


def test_motion_outside_detected(now):
    cache = _StubCache({
        "binary_sensor.hallway_motion": HaState(
            entity_id="binary_sensor.hallway_motion",
            state="on",
            attributes={},
            last_changed=now - timedelta(minutes=2),
        ),
    })
    pred = compile_predicate("motion outside bedroom in last 5m")
    assert pred.evaluate(cache, now) is True


def test_motion_inside_not_detected(now):
    cache = _StubCache({
        "binary_sensor.bedroom_motion": HaState(
            entity_id="binary_sensor.bedroom_motion",
            state="on",
            attributes={},
            last_changed=now - timedelta(minutes=2),
        ),
    })
    pred = compile_predicate("motion outside bedroom in last 5m")
    assert pred.evaluate(cache, now) is False


def test_motion_too_old_not_detected(now):
    cache = _StubCache({
        "binary_sensor.hallway_motion": HaState(
            entity_id="binary_sensor.hallway_motion",
            state="on",
            attributes={},
            last_changed=now - timedelta(minutes=10),
        ),
    })
    pred = compile_predicate("motion outside bedroom in last 5m")
    assert pred.evaluate(cache, now) is False


# ---------------------------------------------------------------------------
# Parse errors
# ---------------------------------------------------------------------------


def test_empty_expression_raises():
    with pytest.raises(ValueError, match="empty"):
        compile_predicate("")


def test_random_string_raises():
    with pytest.raises(ValueError, match="unrecognised"):
        compile_predicate("eval('rm -rf /')")


def test_incomplete_expression_raises():
    with pytest.raises(ValueError, match="unrecognised"):
        compile_predicate("light.bedroom ==")


# ---------------------------------------------------------------------------
# collect_predicate_entities
# ---------------------------------------------------------------------------


def test_collect_equality_entities():
    eq_pred = compile_predicate("light.bedroom == off")
    assert collect_predicate_entities([eq_pred]) == {"light.bedroom"}


def test_collect_motion_entities_empty():
    motion_pred = compile_predicate("motion outside bedroom in last 5m")
    assert collect_predicate_entities([motion_pred]) == set()


def test_collect_mixed_entities():
    preds = [
        compile_predicate("light.bedroom == off"),
        compile_predicate("motion outside bedroom in last 5m"),
        compile_predicate("light.hallway != on"),
    ]
    entities = collect_predicate_entities(preds)
    assert entities == {"light.bedroom", "light.hallway"}
