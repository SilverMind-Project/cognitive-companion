"""MCP server module for AI agent integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.mcp.server import get_tool_registry, init_services, mcp_server

__all__ = ["get_tool_registry", "init_services", "mcp_server"]


def __getattr__(name: str):
    """Lazy import to avoid circular import issues."""
    if name in __all__:
        from backend.mcp import server

        return getattr(server, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
