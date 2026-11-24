"""Caregiver-only channel boundary for guided-task escalations.

An escalation message is a caregiver diagnostic: routine name, failure reason,
recent transcript, and the takeover link. Read aloud on an in-home speaker or
shown on the resident's tablet it startles and disorients a person living with
dementia, so escalations go only to channels that reach a caregiver.

This is an allowlist rather than a list of resident-facing channels to remove,
so a channel added later cannot reach the resident until someone decides it is
caregiver-only.
"""

from __future__ import annotations

from collections.abc import Iterable

from backend.core.logging import get_logger

logger = get_logger(__name__)

CAREGIVER_ESCALATION_CHANNELS: frozenset[str] = frozenset({"telegram", "webhook"})

# The notification dispatcher treats an empty channel list as "use the
# alert level's defaults", and those defaults include the tablet popup, e-ink,
# and speaker channels. An escalation must never fall through to them, and must
# never be dropped silently either, so an empty result falls back here.
_FALLBACK_CHANNELS: tuple[str, ...] = ("telegram",)


def caregiver_channels(configured: Iterable[str], *, session_id: int) -> list[str]:
    """Return the configured channels that reach a caregiver, never an empty list.

    Order is preserved and duplicates are dropped. Every channel removed is
    logged so a misconfigured routine override is visible.
    """
    kept: list[str] = []
    for channel in configured:
        if channel in CAREGIVER_ESCALATION_CHANNELS:
            if channel not in kept:
                kept.append(channel)
        else:
            logger.warning(
                "guided_escalation_resident_channel_skipped",
                session_id=session_id,
                channel=channel,
            )
    if not kept:
        logger.warning(
            "guided_escalation_channel_fallback",
            session_id=session_id,
            channels=list(_FALLBACK_CHANNELS),
        )
        return list(_FALLBACK_CHANNELS)
    return kept
