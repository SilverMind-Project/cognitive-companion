"""Sticky-rule evaluator for NightAnchorProvider.

Parses the ``sticky_until`` / ``release_predicates`` mini-DSL into
callables that can evaluate against a ``HaStateCache``.

Supported expression grammar (v0)
=================================

1. ``entity_id == value`` — equality on ``cache.get(entity_id).state``.
2. ``entity_id != value`` — negation of equality.
3. ``motion outside <room> in last <N>m`` — true if any cached entity
   matching ``binary_sensor.<area>_motion`` (where *area* is NOT in the
   configured room mapping) has ``last_changed`` within the last N minutes.

Each predicate captures the entity IDs it depends on so the wiring
layer can register them with ``HaStateCache``.

Security
========

No ``eval()`` is used.  The parser is a small recursive-descent grammar
that rejects anything it does not recognise with a clear ``ValueError``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from backend.core.logging import get_logger
from backend.integrations.ha_state_cache import HaStateCache

logger = get_logger(__name__)

# -- Public types ------------------------------------------------------------


@dataclass(frozen=True)
class AnchorPredicate:
    """A compiled predicate that evaluates to True or False.

    Attributes
    ----------
    entity_ids:
        HA entity IDs this predicate reads from the cache.  The wiring
        layer uses this set to register entities with ``HaStateCache``.
    """

    entity_ids: tuple[str, ...]

    def evaluate(self, cache: HaStateCache, at: datetime) -> bool:
        """Evaluate the predicate against *cache* at time *at*."""
        raise NotImplementedError


# -- Predicate implementations -----------------------------------------------


class _EqualityPredicate(AnchorPredicate):
    """entity_id == value."""

    def __init__(
        self,
        entity_id: str,
        expected_value: str,
        negated: bool = False,
    ) -> None:
        super().__init__(entity_ids=(entity_id,))
        self._entity_id = entity_id
        self._expected = expected_value
        self._negated = negated

    def evaluate(self, cache: HaStateCache, at: datetime) -> bool:
        state = cache.get(self._entity_id)
        if state is None:
            # Missing entity → treat as not matching.
            return self._negated
        matches = state.state == self._expected
        return not matches if self._negated else matches


class _MotionPredicate(AnchorPredicate):
    """motion outside <room> in last <N>m."""

    # Regex: motion outside <room> in last <N>m
    _PATTERN = re.compile(
        r"^\s*motion\s+outside\s+(\S+)\s+in\s+last\s+(\d+)\s*m\s*$",
        re.IGNORECASE,
    )

    def __init__(self, room: str, minutes: int) -> None:
        # We don't know the exact entity IDs until we inspect the cache,
        # so we collect them lazily at evaluation time.
        super().__init__(entity_ids=())
        self._room = room.lower()
        self._minutes = minutes

    def evaluate(self, cache: HaStateCache, at: datetime) -> bool:
        cutoff = at - timedelta(minutes=self._minutes)
        # Look for any binary_sensor.*_motion entity whose room area is
        # NOT the anchor room and whose last_changed is within the window.
        for entity_id, state in cache._states.items():
            if not entity_id.startswith("binary_sensor."):
                continue
            if "_motion" not in entity_id:
                continue
            if state.last_changed < cutoff:
                continue
            # Extract the area from the entity_id.
            # Convention: binary_sensor.<area>_motion or binary_sensor.<area>_motion_sensor
            suffix = entity_id[len("binary_sensor.") :]
            area = suffix.replace("_motion", "").replace("_motion_sensor", "")
            if area.lower() != self._room:
                # Outside the anchor room — motion detected.
                return True
        return False


# -- Parser ------------------------------------------------------------------


def compile_predicate(expr: str) -> AnchorPredicate:
    """Parse a single predicate expression into a callable.

    Parameters
    ----------
    expr:
        A single predicate expression (see module docstring).

    Returns
    -------
    AnchorPredicate
        A compiled predicate object.

    Raises
    ------
    ValueError
        When the expression does not match any supported grammar.
    """
    stripped = expr.strip()
    if not stripped:
        raise ValueError("empty predicate expression")

    # --- Pattern 3: motion outside <room> in last <N>m ---
    m = _MotionPredicate._PATTERN.match(stripped)
    if m:
        room = m.group(1)
        minutes = int(m.group(2))
        return _MotionPredicate(room=room, minutes=minutes)

    # --- Patterns 1 & 2: entity_id == value / entity_id != value ---
    # Split on == or != (but not === or !==).
    eq_match = re.match(
        r"^\s*(\S+)\s*(!=|==)\s*(\S+)\s*$",
        stripped,
    )
    if eq_match:
        entity_id = eq_match.group(1)
        op = eq_match.group(2)
        value = eq_match.group(3)
        negated = op == "!="
        return _EqualityPredicate(
            entity_id=entity_id,
            expected_value=value,
            negated=negated,
        )

    raise ValueError(
        f"unrecognised predicate expression {expr!r}. "
        f"Supported: '<entity_id> == <value>', "
        f"'<entity_id> != <value>', "
        f"'motion outside <room> in last <N>m'"
    )


def collect_predicate_entities(predicates: list[AnchorPredicate]) -> set[str]:
    """Collect all entity IDs referenced by *predicates*.

    Returns a set of entity IDs that the wiring layer should register
    with ``HaStateCache``.  For motion predicates (which do not declare
    specific entity IDs upfront), this returns an empty set; callers
    should handle motion-predicate entity discovery separately.
    """
    entities: set[str] = set()
    for pred in predicates:
        entities.update(pred.entity_ids)
    return entities
