"""Unit tests for uniform aggregator state contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.services.aggregation import CameraBufferState


def test_camera_buffer_state_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        CameraBufferState(
            camera_id="camera-1",
            origin="cts",
            buffer_depth=1,
            unexpected=True,
        )


def test_camera_buffer_state_optional_fields_default_none() -> None:
    state = CameraBufferState(
        camera_id="camera-1",
        origin="recamera",
        buffer_depth=0,
    )

    assert state.buffer_capacity is None
    assert state.pending_flush is None
    assert state.cooldown_remaining_seconds is None
    assert state.rate_per_second is None
    assert state.tokens_available is None
    assert state.last_event_at is None
