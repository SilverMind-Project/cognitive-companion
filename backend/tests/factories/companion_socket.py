"""The surface-routing half of ``ConnectionManager`` for recording test fakes.

A fake companion socket records ``broadcast`` calls; mixing this in gives it the
routing methods services call, modelled on a one-screen home where no registered
surface is connected. Every surface-targeted message therefore lands on the fake's
``broadcast`` (the real fallback), and a hardware command is recorded but reaches
nothing (the real no-fallback rule). Tests of routing itself use the real
``ConnectionManager``.
"""

from __future__ import annotations

from typing import Any

from backend.schemas.companion_surface_ws import SurfaceHardwareCommand


class CompanionSocketRouting:
    async def broadcast(self, payload: dict[str, Any]) -> None:
        raise NotImplementedError

    async def send_to_surface(self, surface_id: str | None, payload: dict[str, Any]) -> int:
        await self.broadcast(payload)
        return 1

    def is_surface_connected(self, surface_id: str) -> bool:
        return False

    def reaches_surface(self, surface_id: str | None) -> bool:
        has_connections = getattr(self, "has_connections", False)
        return bool(has_connections() if callable(has_connections) else has_connections)

    def conversation_session_id(self, surface_id: str | None = None) -> int | None:
        return getattr(self, "current_conversation_session_id", None)

    async def send_hardware_command(self, command: SurfaceHardwareCommand) -> int:
        self.__dict__.setdefault("hardware_commands", []).append(command)
        return 0
