"""
Adapter that bridges MCP tools to Gemini Live function calling.

Reads tool definitions from the FastMCP server, converts them to Gemini
FunctionDeclaration format, and executes tools directly when Gemini
issues function calls during a voice session.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


class GeminiToolAdapter:
    """Bridges MCP tools to Gemini Live function calling."""

    def __init__(
        self,
        tool_handlers: dict[str, Callable],
        tool_schemas: list[dict[str, Any]],
    ) -> None:
        self._handlers = tool_handlers
        self._schemas = tool_schemas

    def get_declarations(self) -> list[dict[str, Any]]:
        """Convert MCP tool schemas to Gemini FunctionDeclaration dicts.

        Filters to only the tools listed in ``mcp.gemini_tools`` settings.
        Returns plain dicts accepted by the google-genai SDK as
        ``FunctionDeclarationDict`` within ``Tool(function_declarations=[...])``.
        """
        allowed = settings.get("mcp.gemini_tools", [])
        declarations: list[dict[str, Any]] = []

        for schema in self._schemas:
            name = schema.get("name", "")
            if allowed and name not in allowed:
                continue
            if name not in self._handlers:
                continue

            decl: dict[str, Any] = {
                "name": name,
                "description": schema.get("description", ""),
            }

            # MCP inputSchema uses JSON Schema (type/properties/required).
            # Gemini parameters uses the same structure (OpenAPI 3.0 subset).
            params = schema.get("inputSchema")
            if params and params.get("properties"):
                # Strip keys unsupported by Gemini (e.g. $ref, oneOf)
                decl["parameters"] = {
                    "type": params.get("type", "object"),
                    "properties": params["properties"],
                }
                if "required" in params:
                    decl["parameters"]["required"] = params["required"]

            declarations.append(decl)

        logger.info("gemini_tool_declarations_built", count=len(declarations))
        return declarations

    async def execute_tool(
        self, name: str, args: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a tool by name and return the result as a dict.

        Returns ``{"result": ...}`` on success or ``{"error": ...}`` on failure.
        """
        handler = self._handlers.get(name)
        if handler is None:
            logger.warning("gemini_tool_not_found", tool=name)
            return {"error": f"Unknown tool: {name}"}

        try:
            result = await handler(**(args or {}))
            logger.info("gemini_tool_executed", tool=name)
            return {"result": result}
        except Exception as exc:
            logger.exception("gemini_tool_error", tool=name)
            return {"error": str(exc)}
