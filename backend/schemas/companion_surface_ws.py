"""Companion-surface messages on the resident socket (``/ws/audio``).

A surface is one registered companion device (tablet, speaker, display, TV). The
server tells the surface in the resident's room to wake and open its microphone or
camera, and the surface reports back only whether someone is facing it. No image,
audio, or identity ever travels in these messages.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SURFACE_HARDWARE_COMMAND_TYPE = "surface_hardware_command"
SURFACE_ATTENTION_STATE_TYPE = "surface_attention_state"

# A capture lease is bounded so a lost release can never leave a microphone or camera
# open: the device stops capture on its own when the lease runs out unrenewed.
MAX_LEASE_SECONDS = 3600

SurfacePlatform = Literal["web", "android_tablet", "android_tv"]
AttentionChime = Literal["gentle"]


class SurfaceHardwareCommand(BaseModel):
    """Wake a surface and lease its hardware for one delivery, or end that lease.

    Leases are per ``lease_owner`` (the delivery's voice owner key, e.g. one guided
    session or one quiz): the device keeps the screen awake while any lease is live
    and the microphone (camera) open while any live lease asks for it, so one
    delivery ending never closes another's microphone. ``lease_seconds`` bounds the
    lease; its owner renews it by sending again and ends it with ``lease_seconds=0``.
    A command that wakes the screen without capture is a screen-only lease, not a
    release. ``reason`` names the delivery kind for the device log only.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["surface_hardware_command"] = "surface_hardware_command"
    surface_id: str
    lease_owner: str = Field(min_length=1, max_length=128)
    reason: str
    wake_screen: bool = False
    enable_microphone: bool = False
    enable_camera: bool = False
    volume_min_pct: int | None = Field(default=None, ge=0, le=100)
    attention_chime: AttentionChime | None = None
    lease_seconds: int = Field(default=0, ge=0, le=MAX_LEASE_SECONDS)
    server_timestamp: datetime

    @property
    def captures(self) -> bool:
        """Whether the command opens a microphone or camera."""
        return self.enable_microphone or self.enable_camera

    @property
    def ends_lease(self) -> bool:
        """Whether the command ends its owner's lease (no time left on it)."""
        return self.lease_seconds == 0


class SurfaceAttentionStateIn(BaseModel):
    """A surface's on-device attention reading, sent up the resident socket.

    Only whether a face is in front of the screen and roughly where it is looking.
    ``extra="forbid"`` rejects any attempt to send an image or embedding with it.
    The surface is the one the socket authenticated as, never a field the client
    chooses.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["surface_attention_state"]
    face_present: bool
    head_yaw_deg: float | None = Field(default=None, ge=-180, le=180)
    head_pitch_deg: float | None = Field(default=None, ge=-180, le=180)
    timestamp: datetime | None = None
