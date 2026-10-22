"""
ASGI middleware for MCP endpoint authentication and per-tool authorization.

Validates the API key from the ``X-API-Key`` header (or ``Authorization: Bearer <key>``),
requires the read token to reach the endpoint at all, and authorizes every JSON-RPC
``tools/call`` against the permission token the tool was registered with
(:func:`backend.mcp.server.tool_token`) before forwarding the request to the mounted MCP
ASGI app. A read-only key therefore cannot invoke a tool that changes state. Keys in the
query string are not accepted: URLs land in access logs and proxies.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from backend.core.auth import AuthContext, _resolve_key, has_token
from backend.core.exceptions import AuthenticationError
from backend.core.logging import get_logger

logger = get_logger(__name__)

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

# JSON-RPC requests are small; a body this large is refused rather than buffered.
MAX_BODY_BYTES = 1024 * 1024

# Error codes in the JSON-RPC "server error" range.
_RPC_FORBIDDEN = -32003
_RPC_UNKNOWN_TOOL = -32004


def _default_tool_token(name: str) -> str | None:
    from backend.mcp.server import tool_token

    return tool_token(name)


class MCPAuthMiddleware:
    """Wraps the MCP ASGI app with key authentication and per-tool authorization."""

    def __init__(
        self,
        app: ASGIApp,
        tool_token: Callable[[str], str | None] = _default_tool_token,
        read_token: str = "mcp.tools:read",
    ) -> None:
        self.app = app
        self._tool_token = tool_token
        self._read_token = read_token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        api_key = self._extract_api_key(scope)
        if not api_key:
            await self._send_error(send, 401, "API key required")
            return

        try:
            auth = _resolve_key(api_key)
        except AuthenticationError:
            await self._send_error(send, 401, "Invalid API key")
            return

        if not has_token(auth, self._read_token):
            await self._send_error(send, 403, "Insufficient permissions")
            return

        if scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return

        body = await self._read_body(receive)
        if body is None:
            await self._send_error(send, 413, "Request body too large")
            return

        denial = self._authorize_calls(auth, body)
        if denial is not None:
            status, code, message, tool = denial
            logger.info("mcp_tool_denied", tool=tool, key_name=auth.name, status=status)
            await self._send_rpc_error(send, status, code, message)
            return

        await self.app(scope, self._replay(body, receive), send)

    def _authorize_calls(self, auth: AuthContext, body: bytes) -> tuple[int, int, str, str] | None:
        """Return (status, rpc code, message, tool) for the first unauthorized call, else None.

        A batch is authorized as a whole: one denied call denies the request, so a batch never
        executes partially. A body that is not JSON is left for the MCP app to reject.
        """
        try:
            payload = json.loads(body) if body else None
        except ValueError:
            return None
        messages = payload if isinstance(payload, list) else [payload]
        for message in messages:
            if not isinstance(message, dict) or message.get("method") != "tools/call":
                continue
            params = message.get("params")
            name = params.get("name") if isinstance(params, dict) else None
            token = self._tool_token(name) if isinstance(name, str) else None
            if token is None:
                return 404, _RPC_UNKNOWN_TOOL, f"Unknown tool: {name}", str(name)
            if not has_token(auth, token):
                return 403, _RPC_FORBIDDEN, f"Insufficient permissions for tool: {name}", name
        return None

    @staticmethod
    async def _read_body(receive: Receive) -> bytes | None:
        """Buffer the request body; None when it exceeds :data:`MAX_BODY_BYTES`."""
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > MAX_BODY_BYTES:
                return None
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        return b"".join(chunks)

    @staticmethod
    def _replay(body: bytes, receive: Receive) -> Receive:
        """A receive callable that yields the buffered body once, then defers to *receive*."""
        sent = False

        async def replay() -> Message:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return replay

    @staticmethod
    def _extract_api_key(scope: Scope) -> str | None:
        """Extract the API key from the X-API-Key or Authorization: Bearer header."""
        headers = dict(scope.get("headers", []))

        api_key = headers.get(b"x-api-key", b"").decode()
        if api_key:
            return api_key

        auth_header = headers.get(b"authorization", b"").decode()
        if auth_header.startswith("Bearer "):
            return auth_header[7:]

        return None

    @staticmethod
    async def _send_error(send: Send, status: int, message: str) -> None:
        """Send a JSON error response."""
        await MCPAuthMiddleware._send_json(send, status, {"error": message})

    @staticmethod
    async def _send_rpc_error(send: Send, status: int, code: int, message: str) -> None:
        """Send a JSON-RPC error object (id null: the call was rejected before dispatch)."""
        payload = {"jsonrpc": "2.0", "id": None, "error": {"code": code, "message": message}}
        await MCPAuthMiddleware._send_json(send, status, payload)

    @staticmethod
    async def _send_json(send: Send, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
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
        await send({"type": "http.response.body", "body": body})
