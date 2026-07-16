"""Route-to-auth coverage gate (M16).

Two independent properties, checked against the real app and the real
``config/auth.yaml``:

1. every HTTP route carries a ``require_permission``/``require_token`` checker,
   or is in the justified allowlist below;
2. every guarded route is reachable by at least one configured role -- a route
   no role can reach is either dead or misconfigured.

The matching in (2) reuses :class:`KeyStore` rather than re-implementing glob
expansion, so this test cannot drift from production semantics.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

import pytest
import yaml
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute
from starlette.routing import Mount, Route

from backend.core.auth import AuthContext, KeyStore, require_permission

# ─── Allowlist ────────────────────────────────────────────────────────────
#
# Every entry needs a justification. Adding a line here is a security
# decision: prefer a dependency.

ALLOWLISTED_ROUTES: dict[str, str] = {
    # Liveness probes: no data, must answer before auth config is trusted.
    "GET /api/v1/health": "liveness probe, static payload",
    "GET /api/v1/admin/health": "liveness probe, static payload",
    # Public bootstrap metadata the SPA reads before it holds a key (api.js).
    "GET /api/v1/admin/app-info": "public bootstrap metadata, no household data",
    # Deprecated tombstone: returns 410 unconditionally, touches no data.
    "GET /api/v1/persons/cts/person-location": "410 Gone tombstone, no handler body",
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


def _app() -> FastAPI:
    import backend.main

    return backend.main.app


def _method(route: APIRoute) -> str:
    return sorted(route.methods - {"HEAD", "OPTIONS"})[0]


def _key(route: APIRoute) -> str:
    return f"{_method(route)} {route.path}"


def _auth_checkers(route: APIRoute) -> list:
    """Return every marked auth checker in the route's dependency tree."""
    found = []
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        if getattr(dep.call, "__cc_auth_checker__", False):
            found.append(dep.call)
        stack.extend(dep.dependencies)
    return found


def _api_routes() -> list[APIRoute]:
    return [r for r in _app().routes if isinstance(r, APIRoute)]


def _keystore() -> KeyStore:
    data = yaml.safe_load(Path("config/auth.yaml").read_text())
    return KeyStore(permission_map=data.get("permission_map", {}))


# ─── 1. Every route is guarded ────────────────────────────────────────────


def test_every_route_is_guarded_or_allowlisted() -> None:
    unguarded = [
        _key(r) for r in _api_routes() if not _auth_checkers(r) and _key(r) not in ALLOWLISTED_ROUTES
    ]
    assert not unguarded, (
        "Routes with no require_permission/require_token dependency:\n  "
        + "\n  ".join(sorted(unguarded))
        + "\nAdd a dependency, or allowlist with a justification in this file."
    )


def test_allowlist_has_no_stale_entries() -> None:
    """An allowlisted route that no longer exists (or is now guarded) must go."""
    live = {_key(r) for r in _api_routes() if not _auth_checkers(r)}
    stale = sorted(set(ALLOWLISTED_ROUTES) - live)
    assert not stale, f"Allowlist entries no longer needed (route gone or now guarded): {stale}"


def test_websocket_routes_are_known() -> None:
    from starlette.routing import WebSocketRoute

    for route in _app().routes:
        if isinstance(route, WebSocketRoute):
            module = route.endpoint.__module__
            assert module in ALLOWLISTED_WS_MODULES, (
                f"WebSocket {route.path} lives in unreviewed module {module}; "
                "subprotocol auth must be verified by hand before allowlisting."
            )


def test_non_api_routes_are_framework_or_mounts() -> None:
    from starlette.routing import WebSocketRoute

    for route in _app().routes:
        if isinstance(route, APIRoute | WebSocketRoute):
            continue
        if isinstance(route, Mount):
            assert route.path in ALLOWLISTED_MOUNT_PATHS, f"Unreviewed mount: {route.path}"
        elif isinstance(route, Route):
            assert route.path in FRAMEWORK_PATHS, f"Unreviewed bare route: {route.path}"


def test_webhook_trigger_requires_secret_header() -> None:
    """The one allowlisted data-mutating route must still authenticate."""
    route = next(r for r in _api_routes() if _key(r) == "POST /api/v1/webhooks/{rule_id}")
    names = {p.name for p in route.dependant.header_params}
    assert "x_webhook_secret" in names, (
        "webhook trigger no longer reads X-Webhook-Secret; it is allowlisted from "
        "API-key auth on the assumption that it verifies an HMAC secret instead."
    )


# ─── 2. Every guarded route is reachable by some role ─────────────────────


def _roles_reaching(ks: KeyStore, method: str, path: str, *, superuser: bool) -> list[str]:
    """Roles whose patterns reach ``METHOD path``.

    With ``superuser=False`` the bare ``*`` grant is dropped before matching,
    which is what makes this check meaningful: ``admin`` holds ``*``, and
    ``has_permission`` short-circuits True on it for every conceivable path,
    so a plain "is anyone able to reach this?" question is always yes.
    """
    hits = []
    for role in sorted(ks.known_tokens()):
        patterns = ks.expand_permissions([role])
        if not superuser:
            patterns = [p for p in patterns if p != "*"]
        target = f"{method.upper()} {path}"
        if any(fnmatch.fnmatch(target, p) for p in patterns):
            hits.append(role)
    return hits


def test_every_guarded_route_is_reachable_by_a_role() -> None:
    """No route is unreachable even counting the superuser grant.

    Weak by construction (``admin: "*"`` reaches everything), so it only
    catches a route no key could ever hold. The load-bearing audit is
    test_routes_reachable_only_by_superuser below.
    """
    ks = _keystore()
    unreachable = [
        _key(r)
        for r in _api_routes()
        if _auth_checkers(r)
        and _key(r) not in ALLOWLISTED_ROUTES
        and not _roles_reaching(ks, _method(r), r.path, superuser=True)
    ]
    assert not unreachable, (
        "Routes no configured role in config/auth.yaml can reach (dead or "
        "misconfigured):\n  " + "\n  ".join(sorted(unreachable))
    )


def test_reachability_check_is_not_vacuous() -> None:
    """Guard the guard: a path no pattern matches must read as unreachable.

    Without dropping the ``*`` grant this assertion fails, which is exactly
    how the first version of this test could never go red.
    """
    ks = _keystore()
    assert not _roles_reaching(ks, "GET", "/zzz/definitely-not-a-route", superuser=False)
    assert _roles_reaching(ks, "GET", "/zzz/definitely-not-a-route", superuser=True) == [
        "*",
        "admin",
        "operator",
    ]


def test_routes_reachable_only_by_superuser() -> None:
    """Report-only: routes no *named* role can reach (M16 task 5 audit).

    51 of ~308 guarded routes land here. Reported rather than failed because
    the admin key (`*`) is what the SPA itself carries, so a hard gate would
    fail on every new admin route and would encode "admin-only is wrong",
    which is not this product's posture.

    Not all 51 are intentional, though. `caregiver_admin` is provisioned with
    `cts.cameras.write` / `cts.calibrate` / `cts.bboxes.write`, and every one
    is inert: `require_permission` matches METHOD+path and a bare token
    matches no path, so the config reads as if caregiver_admin manages
    cameras and calibration while only admin/operator actually can. Only
    `require_token` consults token membership. See the M16 dated corrections;
    wiring it means granting real access, a product decision.
    """
    ks = _keystore()
    only_star = sorted(
        _key(r)
        for r in _api_routes()
        if _auth_checkers(r)
        and _key(r) not in ALLOWLISTED_ROUTES
        and not _roles_reaching(ks, _method(r), r.path, superuser=False)
    )
    if only_star:
        pytest.skip(f"reachable only via the '*' grant ({len(only_star)}): {only_star}")


def test_permission_map_patterns_match_a_live_route() -> None:
    """Report-only: patterns matching nothing are stale auth.yaml entries.

    Kept as a warning rather than a failure: a pattern may legitimately
    describe a route served by another component behind the same key.
    """
    from starlette.routing import WebSocketRoute

    live = {_key(r) for r in _api_routes()}
    # WebSocket and mounted sub-apps are grantable targets too, and auth.yaml
    # addresses them with the same "METHOD path" syntax.
    for route in _app().routes:
        if isinstance(route, WebSocketRoute):
            live.add(f"GET {route.path}")
        elif isinstance(route, Mount):
            live.update({f"GET {route.path}", f"POST {route.path}"})
    patterns = {p for perms in _keystore().permission_map.values() for p in perms if " " in p}
    stale = sorted(p for p in patterns if not any(fnmatch.fnmatch(t, p) for t in live))
    if stale:
        pytest.skip(f"auth.yaml patterns matching no live route (report-only): {stale}")


# ─── 3. The permissive resolver stays confined to the device surface ──────

# Routes allowed to accept a key via query string / JSON body. Hardware that
# cannot set HTTP headers only. Adding to this set is a security decision.
DEVICE_RESOLVER_ROUTES = {
    # reCamera pushes YOLO payloads; key arrives as ?api_key= or in the body.
    "POST /api/v1/device/recamera",
    # reTerminal e-ink displays poll for their active image; "image:read" is
    # held only by device keys and no browser client calls this route.
    "GET /api/v1/image/active",
}


def _uses_device_resolver(route: APIRoute) -> bool:
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


# ─── 4. Self-test: the gate actually catches an unguarded route ───────────


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
    """Every token named on a real route resolves in config/auth.yaml.

    This is the same contract the lifespan enforces via
    ``assert_declared_tokens_known``, but scoped to tokens reachable from the
    app's own routes rather than the process-global ``_DECLARED_TOKENS`` --
    which any other test module can add to.
    """
    known = _keystore().known_tokens()
    declared: set[str] = set()
    for route in _api_routes():
        for checker in _auth_checkers(route):
            declared.update(getattr(checker, "__cc_auth_tokens__", ()))
    # Names containing a space are literal "METHOD /path" patterns, which
    # expand_permissions passes through by design.
    unknown = sorted({t for t in declared if " " not in t} - known)
    assert not unknown, (
        f"Tokens named at route call sites but absent from config/auth.yaml: {unknown}"
    )
