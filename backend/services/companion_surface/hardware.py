"""Wake the resident's companion surface and lease its capture hardware.

Every delivery that speaks to her (a guided step, a quiz, an info card, an
interactive prompt) calls :func:`engage_surface` before it speaks and
:func:`release_surface` when it ends, both under its own ``owner`` key, so the
device can hold several deliveries' leases at once and ending one never closes
another's microphone. Both are no-ops without a target surface:
waking a screen or opening a microphone is only ever done in the room she is in,
so there is no house-wide fallback (``ConnectionManager.send_hardware_command``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from backend.core.config import Settings
from backend.core.config import settings as default_settings
from backend.core.logging import get_logger
from backend.schemas.companion_surface_ws import MAX_LEASE_SECONDS, SurfaceHardwareCommand

if TYPE_CHECKING:
    from backend.websocket.connection_manager import ConnectionManager

logger = get_logger(__name__)


# Mirrors config/settings.yaml; used when a settings object (a test's, or an older
# deployment's) does not carry the key.
_DEFAULT_LEASE_MARGIN_S = 30


def capture_lease_seconds(turn_seconds: float, *, settings: Settings = default_settings) -> int:
    """A lease that outlives a turn of ``turn_seconds`` by the configured margin."""
    margin = int(settings.get("companion_surface.lease_margin_s", _DEFAULT_LEASE_MARGIN_S))
    return max(1, min(MAX_LEASE_SECONDS, int(turn_seconds) + margin))


async def engage_surface(
    ws_manager: ConnectionManager | None,
    surface_id: str | None,
    *,
    owner: str,
    reason: str,
    lease_seconds: int,
    microphone: bool = True,
    camera: bool = False,
    settings: Settings = default_settings,
    now: datetime | None = None,
) -> int:
    """Wake ``surface_id`` and lease it for ``owner``: the screen always, the
    microphone and camera as asked (``microphone=False`` is a screen-only lease).

    Sending again renews the lease. Returns how many connections it reached
    (0 with no surface, no socket manager, or the surface offline).
    """
    if ws_manager is None or surface_id is None:
        return 0
    command = SurfaceHardwareCommand(
        surface_id=surface_id,
        lease_owner=owner,
        reason=reason,
        wake_screen=True,
        enable_microphone=microphone,
        enable_camera=camera,
        volume_min_pct=settings.get("companion_surface.volume_min_pct", None),
        attention_chime=settings.get("companion_surface.attention_chime", None),
        lease_seconds=min(MAX_LEASE_SECONDS, max(0, lease_seconds)),
        server_timestamp=now or datetime.now(UTC),
    )
    return await ws_manager.send_hardware_command(command)


async def release_surface(
    ws_manager: ConnectionManager | None,
    surface_id: str | None,
    *,
    owner: str,
    reason: str,
    now: datetime | None = None,
) -> int:
    """End ``owner``'s lease on ``surface_id``.

    The device closes the microphone and camera and lets the screen rest only when
    no other delivery's lease still holds them. Best-effort and safe to repeat; the
    device's own lease timer is the backstop when this never arrives.
    """
    if ws_manager is None or surface_id is None:
        return 0
    command = SurfaceHardwareCommand(
        surface_id=surface_id,
        lease_owner=owner,
        reason=reason,
        server_timestamp=now or datetime.now(UTC),
    )
    try:
        return await ws_manager.send_hardware_command(command)
    except Exception:
        logger.exception("surface_release_failed", surface_id=surface_id, reason=reason)
        return 0
