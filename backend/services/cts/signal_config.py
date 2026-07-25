"""Per-person CTS alert configuration helpers.

Defines the canonical signal kind set, the three preset profiles, and the
``is_signal_enabled`` predicate used by both the subscriber (to gate
pipeline dispatch) and the signals router (to filter API responses).
"""

from __future__ import annotations

from typing import Any

from cts_contracts import DementiaSignalKind

WIRE_SIGNAL_KINDS: tuple[str, ...] = tuple(str(k) for k in DementiaSignalKind)
CC_LOCAL_SIGNAL_KINDS: tuple[str, ...] = ("inferred_dwell_exceeded", "tea_intent_suspected")
ALL_SIGNAL_KINDS: tuple[str, ...] = WIRE_SIGNAL_KINDS + CC_LOCAL_SIGNAL_KINDS

# Presence-only kinds that are relevant for everyone regardless of profile.
_PRESENCE_KINDS: frozenset[str] = frozenset({"absence"})
_SLEEP_REST_KINDS: frozenset[str] = frozenset({"nighttime_movement", "stillness_anomaly"})
_DEMENTIA_SPECIFIC_KINDS: frozenset[str] = frozenset(
    {"pacing", "bathroom_dwell_anomaly", "sundowning_index", "tea_intent_suspected"}
)

# Profile presets: maps a profile name to the default enabled kinds.
SIGNAL_PROFILE_KINDS: dict[str, tuple[str, ...]] = {
    "senior": ALL_SIGNAL_KINDS,
    "adult": ("absence", "nighttime_movement", "stillness_anomaly"),
    "guest": ("absence",),
}

_SEVERITY_ORDER = {"info": 0, "warning": 1, "emergency": 2}


def is_signal_enabled(
    cts_alert_config: dict[str, Any] | None,
    signal_type: str,
    severity: str,
) -> bool:
    """Return True if this signal type and severity pass the person's alert config.

    A ``None`` config means no preference has been set; the signal is enabled
    (default-permissive so that existing members without a config still receive
    all signals until an operator sets one).

    Args:
        cts_alert_config: The ``cts_alert_config`` JSON value from
            ``HouseholdMember``, or ``None``.
        signal_type: Canonical signal kind string, e.g. ``"pacing"``.
        severity: Signal severity string: ``"info"``, ``"warning"``, or
            ``"emergency"``.
    """
    if cts_alert_config is None:
        return True

    if signal_type not in ALL_SIGNAL_KINDS:
        return False

    enabled_kinds = cts_alert_config.get("enabled_kinds")
    if enabled_kinds is not None and signal_type not in enabled_kinds:
        return False

    min_severity = cts_alert_config.get("min_severity", "info")
    signal_rank = _SEVERITY_ORDER.get(severity, 0)
    min_rank = _SEVERITY_ORDER.get(min_severity, 0)
    return signal_rank >= min_rank


def default_config_for_profile(profile: str) -> dict[str, Any]:
    """Return the default ``cts_alert_config`` dict for a named profile."""
    kinds = SIGNAL_PROFILE_KINDS.get(profile, ALL_SIGNAL_KINDS)
    return {"enabled_kinds": list(kinds), "min_severity": "info"}


# Tests moved to test suite, but leaving function definitions intact.
