"""The caregiver-only channel boundary for guided-task escalations."""

from __future__ import annotations

from backend.channels import ChannelRegistry
from backend.services.guided_task.escalation.channels import (
    CAREGIVER_ESCALATION_CHANNELS,
    caregiver_channels,
)


def test_resident_facing_channels_are_dropped_in_order() -> None:
    configured = ["pwa_popup_text", "webhook", "ha_speaker_tts", "telegram", "eink", "webhook"]
    assert caregiver_channels(configured, session_id=1) == ["webhook", "telegram"]


def test_never_returns_an_empty_list() -> None:
    assert caregiver_channels([], session_id=1) == ["telegram"]
    assert caregiver_channels(["pwa_tts_announcement", "pwa_realtime_ai"], session_id=1) == [
        "telegram"
    ]


def test_allowlist_names_registered_channels() -> None:
    ChannelRegistry.discover()
    registered = set(ChannelRegistry.all_names())
    assert registered >= CAREGIVER_ESCALATION_CHANNELS
