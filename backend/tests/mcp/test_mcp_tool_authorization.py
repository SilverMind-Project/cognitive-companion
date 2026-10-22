"""MCP tool authorization: every tool declares a token, and the token is enforced per call.

The MCP endpoint once admitted any key holding ``admin`` or ``mcp_readonly`` to every tool,
including the twelve that change state, so the "read-only" agent key could trigger rules and
acknowledge signals. These tests pin the per-tool registry, the HTTP middleware that enforces
it, the in-process voice principal, and the startup token contract.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from starlette.testclient import TestClient

import backend.core.auth as auth_module
from backend.core.auth import KeyStore, assert_declared_tokens_known
from backend.core.config import settings
from backend.mcp import server as mcp_module
from backend.mcp.gemini_adapter import GeminiToolAdapter
from backend.mcp.middleware import MAX_BODY_BYTES, MCPAuthMiddleware

# Static expectations, written out rather than derived from the registry, so an empty or
# mis-tokened registry fails here instead of agreeing with itself.
_MUTATING_TOOL_TOKENS = {
    "trigger_rule": "rules:execute",
    "import_rule_bundle": "rules:import",
    "acknowledge_dementia_signal": "cts.signals:acknowledge",
    "propose_identity_correction": "cts.identity:propose",
    "submit_user_response": "resident_session:act",
    "submit_quiz_answer": "resident_session:act",
    "complete_quiz_session": "resident_session:act",
    "mark_guided_step_complete": "resident_session:act",
    "repeat_guided_step": "resident_session:act",
    "report_step_blocked": "resident_session:act",
    "request_caregiver_help": "resident_session:act",
    "record_resident_preference": "resident_session:act",
}
_READ_TOOL_COUNT = 49

_READ_KEY = "read-key"
_AGENT_KEY = "agent-key"
_ADMIN_KEY = "admin-key"
_CAREGIVER_KEY = "caregiver-key"


@pytest.fixture
def keystore(monkeypatch: pytest.MonkeyPatch) -> KeyStore:
    """Test keys over the real config/auth.yaml permission map, so real grants are tested."""
    ks = KeyStore(
        api_keys=[
            {"key": _READ_KEY, "name": "Read", "permissions": ["mcp_readonly"]},
            {
                "key": _AGENT_KEY,
                "name": "Agent",
                "permissions": ["mcp_readonly", "rules:write_via_mcp"],
            },
            {"key": _ADMIN_KEY, "name": "Admin", "permissions": ["admin"]},
            {"key": _CAREGIVER_KEY, "name": "Caregiver", "permissions": ["caregiver"]},
        ],
        permission_map=settings.get("auth.permission_map", {}),
    )
    monkeypatch.setattr(auth_module, "_default_keystore", ks)
    return ks


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_every_tool_declares_the_expected_token() -> None:
    tokens = mcp_module._tool_tokens

    assert set(tokens) == set(mcp_module._tool_handlers)
    for name, token in _MUTATING_TOOL_TOKENS.items():
        assert tokens[name] == token, name
    read_tools = {name for name, token in tokens.items() if token == mcp_module.TOOLS_READ}
    assert len(read_tools) == _READ_TOOL_COUNT
    assert not read_tools & set(_MUTATING_TOOL_TOKENS)


def test_registration_without_a_token_is_a_type_error() -> None:
    async def tool() -> dict[str, Any]:
        return {}

    with pytest.raises(TypeError):
        mcp_module._register(tool)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# HTTP middleware
# ---------------------------------------------------------------------------


class _InnerApp:
    """Stub MCP app recording whether a request reached it and the body it received."""

    def __init__(self) -> None:
        self.calls = 0
        self.body = b""

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self.calls += 1
        message = await receive()
        self.body = message.get("body", b"")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})


def _call(name: str, call_id: int = 1) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": call_id, "method": "tools/call", "params": {"name": name}}


async def _request(
    middleware: MCPAuthMiddleware,
    *,
    body: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
    query: bytes = b"",
    method: str = "POST",
) -> tuple[int, dict[str, Any]]:
    sent: list[dict[str, Any]] = []
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "method": method,
        "path": "/",
        "headers": headers or [],
        "query_string": query,
    }
    await middleware(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    payload = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, json.loads(payload or b"{}")


def _key(value: str) -> list[tuple[bytes, bytes]]:
    return [(b"x-api-key", value.encode())]


@pytest.mark.usefixtures("keystore")
class TestMiddleware:
    async def test_read_key_calls_a_read_tool(self) -> None:
        inner = _InnerApp()
        body = json.dumps(_call("get_rooms")).encode()

        status, _ = await _request(MCPAuthMiddleware(inner), body=body, headers=_key(_READ_KEY))

        assert status == 200
        assert inner.calls == 1
        assert inner.body == body, "the buffered body must reach the MCP app unchanged"

    @pytest.mark.parametrize(
        "tool",
        [
            "trigger_rule",
            "import_rule_bundle",
            "acknowledge_dementia_signal",
            "propose_identity_correction",
            "mark_guided_step_complete",
        ],
    )
    async def test_read_key_cannot_call_a_mutating_tool(self, tool: str) -> None:
        inner = _InnerApp()

        status, payload = await _request(
            MCPAuthMiddleware(inner),
            body=json.dumps(_call(tool)).encode(),
            headers=_key(_READ_KEY),
        )

        assert status == 403
        assert payload["error"]["message"].endswith(tool)
        assert inner.calls == 0

    async def test_agent_key_may_import_rule_bundles(self) -> None:
        inner = _InnerApp()

        status, _ = await _request(
            MCPAuthMiddleware(inner),
            body=json.dumps(_call("import_rule_bundle")).encode(),
            headers=_key(_AGENT_KEY),
        )

        assert status == 200
        assert inner.calls == 1

    @pytest.mark.parametrize(
        "tool", ["trigger_rule", "acknowledge_dementia_signal", "propose_identity_correction"]
    )
    async def test_agent_key_cannot_call_admin_only_mutations(self, tool: str) -> None:
        inner = _InnerApp()

        status, _ = await _request(
            MCPAuthMiddleware(inner),
            body=json.dumps(_call(tool)).encode(),
            headers=_key(_AGENT_KEY),
        )

        assert status == 403
        assert inner.calls == 0

    async def test_admin_key_may_call_agent_facing_mutations(self) -> None:
        inner = _InnerApp()

        status, _ = await _request(
            MCPAuthMiddleware(inner),
            body=json.dumps(_call("acknowledge_dementia_signal")).encode(),
            headers=_key(_ADMIN_KEY),
        )

        assert status == 200

    async def test_no_http_key_may_call_resident_tools(self) -> None:
        """Only the in-process voice principal carries resident_session:act."""
        inner = _InnerApp()

        status, _ = await _request(
            MCPAuthMiddleware(inner),
            body=json.dumps(_call("submit_quiz_answer")).encode(),
            headers=_key(_AGENT_KEY),
        )

        assert status == 403
        assert inner.calls == 0

    async def test_a_batch_with_one_denied_call_is_denied_whole(self) -> None:
        inner = _InnerApp()
        batch = [_call("get_rooms", 1), _call("trigger_rule", 2)]

        status, _ = await _request(
            MCPAuthMiddleware(inner), body=json.dumps(batch).encode(), headers=_key(_READ_KEY)
        )

        assert status == 403
        assert inner.calls == 0

    async def test_an_unknown_tool_is_denied(self) -> None:
        inner = _InnerApp()

        status, _ = await _request(
            MCPAuthMiddleware(inner),
            body=json.dumps(_call("no_such_tool")).encode(),
            headers=_key(_ADMIN_KEY),
        )

        assert status == 404
        assert inner.calls == 0

    async def test_a_key_in_the_query_string_is_not_accepted(self) -> None:
        inner = _InnerApp()

        status, _ = await _request(
            MCPAuthMiddleware(inner),
            body=json.dumps(_call("get_rooms")).encode(),
            query=f"api_key={_READ_KEY}".encode(),
        )

        assert status == 401
        assert inner.calls == 0

    async def test_bearer_header_is_accepted(self) -> None:
        inner = _InnerApp()

        status, _ = await _request(
            MCPAuthMiddleware(inner),
            body=json.dumps(_call("get_rooms")).encode(),
            headers=[(b"authorization", f"Bearer {_READ_KEY}".encode())],
        )

        assert status == 200

    async def test_a_key_without_the_read_token_cannot_reach_the_endpoint(self) -> None:
        inner = _InnerApp()

        status, _ = await _request(
            MCPAuthMiddleware(inner),
            body=json.dumps(_call("get_rooms")).encode(),
            headers=_key(_CAREGIVER_KEY),
        )

        assert status == 403
        assert inner.calls == 0

    async def test_an_unknown_key_is_rejected(self) -> None:
        status, _ = await _request(MCPAuthMiddleware(_InnerApp()), headers=_key("nope"))

        assert status == 401

    async def test_an_oversized_body_is_refused(self) -> None:
        inner = _InnerApp()

        status, _ = await _request(
            MCPAuthMiddleware(inner),
            body=b"x" * (MAX_BODY_BYTES + 1),
            headers=_key(_ADMIN_KEY),
        )

        assert status == 413
        assert inner.calls == 0

    async def test_a_get_stream_request_passes_without_a_body(self) -> None:
        inner = _InnerApp()

        status, _ = await _request(MCPAuthMiddleware(inner), method="GET", headers=_key(_READ_KEY))

        assert status == 200
        assert inner.calls == 1

    async def test_a_non_auth_error_during_resolution_is_not_reported_as_a_bad_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(_key: str) -> None:
            raise RuntimeError("keystore failed")

        monkeypatch.setattr("backend.mcp.middleware._resolve_key", broken)

        with pytest.raises(RuntimeError, match="keystore failed"):
            await _request(MCPAuthMiddleware(_InnerApp()), headers=_key(_READ_KEY))


def test_mounted_mcp_app_denies_a_mutation_but_admits_a_read_handshake(
    keystore: KeyStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end through the real FastMCP streamable-HTTP app and the real tool registry."""
    # FastMCP keeps one session manager per server and a manager runs only once; give this
    # test its own so the app built later by create_app() can still start.
    monkeypatch.setattr(mcp_module.mcp_server, "_session_manager", None)
    monkeypatch.setattr(mcp_module.mcp_server.settings, "streamable_http_path", "/")
    app = MCPAuthMiddleware(mcp_module.mcp_server.streamable_http_app())
    accept = {"accept": "application/json, text/event-stream"}

    with TestClient(app, base_url="http://localhost:8000") as client:
        denied = client.post(
            "/",
            headers={"x-api-key": _READ_KEY, **accept},
            json=_call("acknowledge_dementia_signal"),
        )
        initialize = client.post(
            "/",
            headers={"x-api-key": _READ_KEY, **accept},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )

    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == -32003
    assert initialize.status_code == 200, "a read key still reaches the MCP app for non-tool calls"


# ---------------------------------------------------------------------------
# Voice principal
# ---------------------------------------------------------------------------


class _Settings:
    def __init__(self, tools: list[str]) -> None:
        self._tools = tools

    def as_list(self, key: str) -> list[str]:
        assert key == "mcp.gemini_tools"
        return list(self._tools)


def _adapter(called: list[str]) -> GeminiToolAdapter:
    def handler(name: str) -> Callable[..., Awaitable[dict[str, Any]]]:
        async def run(**_: Any) -> dict[str, Any]:
            called.append(name)
            return {"ok": True}

        return run

    names = ["get_rooms", "trigger_rule", "submit_quiz_answer"]
    return GeminiToolAdapter(
        {name: handler(name) for name in names},
        [{"name": name, "description": name} for name in names],
    )


def test_voice_declarations_follow_the_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.mcp.gemini_adapter.settings", _Settings(["get_rooms", "submit_quiz_answer"])
    )

    declared = {d["name"] for d in _adapter([]).get_declarations()}

    assert declared == {"get_rooms", "submit_quiz_answer"}


def test_an_empty_voice_allowlist_declares_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.mcp.gemini_adapter.settings", _Settings([]))

    assert _adapter([]).get_declarations() == []


async def test_voice_dispatch_refuses_a_tool_outside_the_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.mcp.gemini_adapter.settings", _Settings(["get_rooms"]))
    called: list[str] = []

    result = await _adapter(called).execute_tool("trigger_rule")

    assert result == {"error": "Tool not allowed: trigger_rule"}
    assert called == []


def test_the_configured_voice_allowlist_has_no_agent_facing_mutation() -> None:
    allowed = set(settings.as_list("mcp.gemini_tools"))

    assert allowed, "mcp.gemini_tools must not be empty: the voice agent would have no tools"
    agent_mutations = {"trigger_rule", "import_rule_bundle", "acknowledge_dementia_signal"}
    assert not allowed & (agent_mutations | {"propose_identity_correction"})


# ---------------------------------------------------------------------------
# Startup token contract and dead config
# ---------------------------------------------------------------------------


def test_every_tool_token_is_known_to_the_configured_keystore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Only the tool tokens: other tests register throwaway route tokens in the same global set.
    monkeypatch.setattr(auth_module, "_DECLARED_TOKENS", set(mcp_module._tool_tokens.values()))

    assert_declared_tokens_known(KeyStore.from_settings(settings))


def test_an_internal_token_granted_in_auth_yaml_fails_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_module, "_DECLARED_TOKENS", set())
    ks = KeyStore(permission_map={"caregiver": ["resident_session:act"]})

    with pytest.raises(RuntimeError, match="resident_session:act"):
        assert_declared_tokens_known(ks)


def test_an_undefined_tool_token_fails_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_module, "_DECLARED_TOKENS", set(mcp_module._tool_tokens.values()) | {"rules:explode"}
    )

    with pytest.raises(RuntimeError, match="rules:explode"):
        assert_declared_tokens_known(KeyStore.from_settings(settings))


def test_the_dead_mcp_tools_setting_stays_removed() -> None:
    assert settings.get("mcp.tools") is None
