"""Route-to-auth coverage and D4 token gate.

Three independent properties, checked against the real app and the real
``config/auth.yaml``:

1. every HTTP route carries exactly one ``require_permission`` checker declaring
   exactly one D4 ``<resource>:<action>`` token, or is in the justified allowlist;
2. every guarded route's D4 token is explicitly listed on at least one role in
   ``config/auth.yaml`` (excluding ``*``), so no route is unreachable or typo'd;
3. the permissive device key resolver stays confined to hardware device routes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute, RouteContext
from starlette.routing import Mount, Route

from backend.core.auth import (
    WS_ROUTE_TOKENS,
    AuthContext,
    KeyStore,
    is_valid_d4_token,
    require_permission,
)
from backend.tests.routers._route_inventory import (
    api_route_contexts,
    primary_method,
    route_contexts,
    route_key,
)

# ─── Allowlist ────────────────────────────────────────────────────────────
#
# Every entry needs a justification. Adding a line here is a security
# decision: prefer a dependency.

ALLOWLISTED_ROUTES: dict[str, str] = {
    # Liveness probes: no data, must answer before auth config is trusted.
    "GET /api/v1/health": "liveness probe, static payload",
    "GET /api/v1/admin/health": "liveness probe, static payload",
    # Public bootstrap metadata the SPA reads before it holds a key.
    "GET /api/v1/admin/app-info": "public bootstrap metadata, no household data",
    # Authenticated by X-Webhook-Secret (per-rule HMAC), asserted below.
    "POST /api/v1/webhooks/{rule_id}": "X-Webhook-Secret HMAC auth, see test_webhook_trigger_*",
    # Prometheus scrape surface; network-restricted at the deployment layer.
    "GET /metrics": "Prometheus scrape endpoint, no household data",
}

# WebSocket routes authenticate inside the handler via the
# Sec-WebSocket-Protocol subprotocol; they cannot carry a header dependency.
ALLOWLISTED_WS_MODULES = {
    "backend.routers.ws",
    "backend.routers.cts_live",
}

# Non-APIRoute mounts with their own middleware / framework-owned paths.
ALLOWLISTED_MOUNT_PATHS = {"/mcp"}
FRAMEWORK_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


_method = primary_method
_key = route_key


def _auth_checkers(route: APIRoute | RouteContext) -> list:
    """Return every marked auth checker in the route's dependency tree."""
    found = []
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        if getattr(dep.call, "__cc_auth_checker__", False):
            found.append(dep.call)
        stack.extend(dep.dependencies)
    return found


_api_routes = api_route_contexts


def _keystore() -> KeyStore:
    data = yaml.safe_load(Path("config/auth.yaml").read_text())
    return KeyStore(
        api_keys=data.get("api_keys", []),
        device_keys=data.get("device_keys", []),
        roles=data.get("roles", {}),
    )


# ─── 1. Every route is guarded with exactly one D4 token ──────────────────


def test_every_route_is_guarded_or_allowlisted() -> None:
    unguarded = [
        _key(r)
        for r in _api_routes()
        if not _auth_checkers(r) and _key(r) not in ALLOWLISTED_ROUTES
    ]
    assert not unguarded, (
        "Routes with no require_permission dependency:\n  "
        + "\n  ".join(sorted(unguarded))
        + "\nAdd a dependency, or allowlist with a justification in this file."
    )


def test_every_guarded_route_declares_exactly_one_d4_token() -> None:
    """Every guarded route carries one auth checker with one D4 ``<resource>:<action>`` token."""
    bad_count: list[str] = []
    bad_d4: list[str] = []
    checked = 0
    for r in _api_routes():
        checkers = _auth_checkers(r)
        if not checkers:
            continue
        checked += 1
        tokens = tuple(t for c in checkers for t in getattr(c, "__cc_auth_tokens__", ()))
        if len(checkers) != 1 or len(tokens) != 1:
            bad_count.append(f"{_key(r)}: checkers={len(checkers)}, tokens={tokens!r}")
            continue
        if not is_valid_d4_token(tokens[0]):
            bad_d4.append(f"{_key(r)}: {tokens[0]!r}")

    assert checked >= 300, f"Non-vacuity canary: expected >= 300 guarded routes, got {checked}"
    assert not bad_count, "Routes must declare exactly one token:\n  " + "\n  ".join(bad_count)
    assert not bad_d4, "Routes declaring non-D4 tokens:\n  " + "\n  ".join(bad_d4)


def test_allowlist_has_no_stale_entries() -> None:
    """An allowlisted route that no longer exists (or is now guarded) must go."""
    live = {_key(r) for r in _api_routes() if not _auth_checkers(r)}
    stale = sorted(set(ALLOWLISTED_ROUTES) - live)
    assert not stale, f"Allowlist entries no longer needed (route gone or now guarded): {stale}"


def test_webhook_trigger_requires_secret_header() -> None:
    """The one allowlisted data-mutating route must still authenticate."""
    route = next(r for r in _api_routes() if _key(r) == "POST /api/v1/webhooks/{rule_id}")
    names = {p.name for p in route.dependant.header_params}
    assert "x_webhook_secret" in names, (
        "webhook trigger no longer reads X-Webhook-Secret; it is allowlisted from "
        "API-key auth on the assumption that it verifies an HMAC secret instead."
    )


def test_websocket_routes_are_known() -> None:
    from starlette.routing import WebSocketRoute

    for ctx in route_contexts():
        route = ctx.original_route
        if isinstance(route, WebSocketRoute):
            module = route.endpoint.__module__
            assert module in ALLOWLISTED_WS_MODULES, (
                f"WebSocket {route.path} lives in unreviewed module {module}; "
                "subprotocol auth must be verified by hand before allowlisting."
            )


def test_non_api_routes_are_framework_or_mounts() -> None:
    from starlette.routing import WebSocketRoute

    for ctx in route_contexts():
        route = ctx.original_route
        if isinstance(route, APIRoute | WebSocketRoute):
            continue
        if isinstance(route, Mount):
            assert route.path in ALLOWLISTED_MOUNT_PATHS, f"Unreviewed mount: {route.path}"
        elif isinstance(route, Route):
            assert route.path in FRAMEWORK_PATHS, f"Unreviewed bare route: {route.path}"


# ─── 2. Every guarded route is reachable by a configured role ─────────────


def _roles_reaching_token(ks: KeyStore, token: str, *, superuser: bool) -> list[str]:
    """Roles in ``config/auth.yaml`` ``roles:`` carrying *token*.

    With ``superuser=False``, bare ``*`` grants are dropped before matching so
    a typo or unlisted token reads as unreachable.
    """
    hits = []
    for role, toks in sorted(ks.roles.items()):
        effective = [t for t in toks if superuser or t != "*"]
        if "*" in effective or token in effective:
            hits.append(role)
    return hits


def test_every_guarded_route_is_reachable_by_a_role() -> None:
    """Every guarded route's D4 token is explicitly listed on at least one role."""
    ks = _keystore()
    unreachable = []
    for r in _api_routes():
        checkers = _auth_checkers(r)
        if not checkers or _key(r) in ALLOWLISTED_ROUTES:
            continue
        tokens = getattr(checkers[0], "__cc_auth_tokens__", ())
        if not tokens or not any(_roles_reaching_token(ks, t, superuser=False) for t in tokens):
            unreachable.append(_key(r))
    assert not unreachable, (
        "Routes no configured role in config/auth.yaml can reach (dead or "
        "misconfigured):\n  " + "\n  ".join(sorted(unreachable))
    )


def test_reachability_check_is_not_vacuous() -> None:
    """Guard the guard: an unknown token must read as unreachable without ``*``."""
    ks = _keystore()
    assert not _roles_reaching_token(ks, "nonexistent:read", superuser=False)
    assert _roles_reaching_token(ks, "nonexistent:read", superuser=True) == [
        "admin",
        "operator",
    ]


def test_routes_reachable_only_by_superuser() -> None:
    """Report-only: routes whose token is granted only to ``admin``/``operator``."""
    ks = _keystore()
    only_super = sorted(
        _key(r)
        for r in _api_routes()
        if _auth_checkers(r)
        and _key(r) not in ALLOWLISTED_ROUTES
        and set(
            _roles_reaching_token(
                ks,
                getattr(_auth_checkers(r)[0], "__cc_auth_tokens__", ("",))[0],
                superuser=False,
            )
        )
        <= {"admin", "operator"}
    )
    if only_super:
        pytest.skip(f"reachable only by admin/operator ({len(only_super)}): {only_super}")


def test_every_configured_role_token_matches_a_live_route_ws_or_mcp_tool() -> None:
    """No stale D4 tokens linger in ``config/auth.yaml`` ``roles:``."""
    from backend.mcp import server as mcp_server

    live_tokens: set[str] = set(WS_ROUTE_TOKENS.values()) | set(mcp_server._tool_tokens.values())
    for r in _api_routes():
        for checker in _auth_checkers(r):
            live_tokens.update(getattr(checker, "__cc_auth_tokens__", ()))

    configured = _keystore().known_tokens()
    stale = sorted(configured - live_tokens)
    assert not stale, f"Tokens in config/auth.yaml roles: matching no live route/WS/tool: {stale}"


# ─── 3. The permissive resolver stays confined to the device surface ──────

# Routes allowed to accept a key via query string / JSON body. Hardware that
# cannot set HTTP headers only. Adding to this set is a security decision.
DEVICE_RESOLVER_ROUTES = {
    # reCamera pushes YOLO payloads; key arrives as ?api_key= or in the body.
    "POST /api/v1/device/recamera",
    # reTerminal e-ink displays poll for their active image.
    "GET /api/v1/image/active",
}


def _uses_device_resolver(route: APIRoute | RouteContext) -> bool:
    from backend.core.auth import get_auth_context_device

    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        if dep.call is get_auth_context_device:
            return True
        stack.extend(dep.dependencies)
    return False


def test_device_resolver_used_only_by_device_routes() -> None:
    """A query-string key on a browser-facing route would leak into access logs."""
    actual = {_key(r) for r in _api_routes() if _uses_device_resolver(r)}
    assert actual == DEVICE_RESOLVER_ROUTES, (
        f"device resolver drift: expected {DEVICE_RESOLVER_ROUTES}, found {actual}"
    )


def test_recamera_route_still_accepts_query_key() -> None:
    """reCamera hardware cannot set headers; its key arrives as ?api_key=."""
    route = next(r for r in _api_routes() if _key(r) == "POST /api/v1/device/recamera")
    assert _uses_device_resolver(route)


# ─── 4. Self-test: the gate catches unguarded and non-D4 routes ───────────


def test_gate_catches_unguarded_route() -> None:
    """A deliberately unguarded route on a throwaway app must be detected."""
    app = FastAPI()

    @app.get("/oops")
    async def oops() -> dict:
        return {}

    @app.get("/fine")
    async def fine(_a: AuthContext = Depends(require_permission("rooms:read"))) -> dict:
        return {}

    routes = {r.path: r for r in app.routes if isinstance(r, APIRoute)}
    assert not _auth_checkers(routes["/oops"]), "gate would miss an unguarded route"
    assert _auth_checkers(routes["/fine"]), "gate would miss a guarded route"


def test_declared_tokens_all_exist_in_auth_yaml() -> None:
    """Every token named on a real route is D4-valid and listed in ``config/auth.yaml``."""
    known = _keystore().known_tokens()
    declared: set[str] = set()
    for route in _api_routes():
        for checker in _auth_checkers(route):
            declared.update(getattr(checker, "__cc_auth_tokens__", ()))
    unknown = sorted(declared - known)
    assert not unknown, (
        f"Tokens named at route call sites but absent from config/auth.yaml roles: {unknown}"
    )
