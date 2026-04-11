"""
ASGI middleware for MCP endpoint authentication.

Validates API key from the X-API-Key header (or Authorization: Bearer <key>)
before forwarding requests to the mounted MCP ASGI app.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs

from backend.core.logging import get_logger

logger = get_logger(__name__)


class MCPAuthMiddleware:
    """Wraps an ASGI app with API key authentication."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        api_key = self._extract_api_key(scope)
        if not api_key:
            await self._send_error(send, 401, "API key required")
            return

        try:
            from backend.core.auth import _resolve_key

            auth = _resolve_key(api_key)
            if not any(p in ("admin", "mcp_readonly") for p in auth.permissions):
                await self._send_error(send, 403, "Insufficient permissions")
                return
        except Exception:
            await self._send_error(send, 401, "Invalid API key")
            return

        await self.app(scope, receive, send)

    @staticmethod
    def _extract_api_key(scope) -> str | None:
        """Extract API key from headers or query string."""
        headers = dict(scope.get("headers", []))

        # Check X-API-Key header
        api_key = headers.get(b"x-api-key", b"").decode()
        if api_key:
            return api_key

        # Check Authorization: Bearer <key>
        auth_header = headers.get(b"authorization", b"").decode()
        if auth_header.startswith("Bearer "):
            return auth_header[7:]

        # Check query string (?api_key=...)
        qs = scope.get("query_string", b"").decode()
        if qs:
            params = parse_qs(qs)
            keys = params.get("api_key", [])
            if keys:
                return keys[0]

        return None

    @staticmethod
    async def _send_error(send, status: int, message: str) -> None:
        """Send a JSON error response."""
        body = json.dumps({"error": message}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"content-length", str(len(body)).encode()],
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body,
            }
        )
