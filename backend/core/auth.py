"""
API key authentication and permission checking.

Keys are resolved from the ``X-API-Key`` header. Endpoints serving hardware
that cannot set headers opt into :func:`get_auth_context_device`, which also
accepts a ``?api_key=`` query parameter and a JSON body ``device_key`` /
``api_key`` field. Query-string and body keys leak into access logs and
browser history, so they stay confined to that device surface: never wire
the device resolver into a browser-facing endpoint.

Device keys are 8-character uppercase alphanumeric strings.

Architecture
------------
The :class:`KeyStore` class is a pure lookup/permission checker: it takes
raw mappings of API keys, device keys, and a permission map, and exposes
:meth:`KeyStore.resolve` and :meth:`KeyStore.has_permission`. It has no
dependency on FastAPI or the module-level :mod:`backend.core.config`
singleton, so tests can construct it directly with hand-crafted data.

The module-level functions (:func:`get_auth_context`,
:func:`require_permission`, :func:`invalidate_lookup_cache`, and the
private ``_resolve_key`` used by the MCP middleware) are a thin facade
over a lazily-built default :class:`KeyStore` sourced from
:data:`backend.core.config.settings`.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, Query, Request
from fastapi.security import APIKeyHeader
from prometheus_client import Counter

from backend.core.config import Settings, settings
from backend.core.exceptions import AuthenticationError, PermissionDeniedError
from backend.core.logging import get_logger
from backend.core.permission_migration import (
    ALLOWED_ACTIONS,
    D4_TO_LEGACY_REQUIRE_TOKEN,
    D4_TOKEN_RE,
    is_valid_d4_token,
)

__all__ = [
    "ALLOWED_ACTIONS",
    "D4_TOKEN_RE",
    "AuthContext",
    "KeyStore",
    "actor_from_auth",
    "assert_declared_tokens_known",
    "cc_auth_shadow_mismatch_total",
    "declare_internal_tokens",
    "declare_tokens",
    "evaluate_ws_inverse_shadow",
    "get_auth_context",
    "get_auth_context_device",
    "has_role_token",
    "has_token",
    "invalidate_lookup_cache",
    "is_valid_d4_token",
    "require_permission",
    "require_token",
]

logger = get_logger(__name__)

# EG-M14 PR 3 inverse-shadow mismatch counter.
# Labels are bounded: token name, sorted role names (never key material), and
# decision ("legacy_would_allow" or "legacy_would_deny").
cc_auth_shadow_mismatch_total = Counter(
    "cc_auth_shadow_mismatch_total",
    "Disagreements between live EG-M14 D4 token auth and legacy path-glob shadow",
    ["token", "role", "decision"],
)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass
class AuthContext:
    """Resolved authentication context for a request."""

    key: str
    name: str
    permissions: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    # Direct token grants used only by synthetic unit tests; KeyStore.resolve()
    # never populates this field from config/auth.yaml.
    tokens: frozenset[str] = field(default_factory=frozenset)
    device_type: str | None = None
    sensor_id: str | None = None


def actor_from_auth(auth: AuthContext | None) -> str:
    """The name an audit record stores for whoever made this request: the API key's name.

    Pass the ``AuthContext`` a route received from ``require_permission`` or ``require_token``.
    A review or correction must never be recorded as made by nobody, so a missing context or a
    nameless key raises instead of falling back to a placeholder such as "system".
    """
    if auth is None or not auth.name:
        raise AuthenticationError()
    return auth.name


class KeyStore:
    """Immutable lookup table for API + device keys plus a permission map.

    :class:`KeyStore` is intentionally decoupled from
    :mod:`backend.core.config`: construct it directly in tests, or use
    :meth:`from_settings` to load from the live YAML config.
    """

    def __init__(
        self,
        api_keys: list[Mapping[str, Any]] | None = None,
        device_keys: list[Mapping[str, Any]] | None = None,
        permission_map: Mapping[str, list[str]] | None = None,
        roles: Mapping[str, list[str]] | None = None,
    ) -> None:
        self._api_keys: dict[str, Mapping[str, Any]] = {
            entry["key"]: entry for entry in (api_keys or [])
        }
        self._device_keys: dict[str, Mapping[str, Any]] = {
            entry["key"]: entry for entry in (device_keys or [])
        }
        self._permission_map: dict[str, list[str]] = dict(permission_map or {})
        self._roles: dict[str, list[str]] = dict(roles or {})

    # -- construction --------------------------------------------------------

    @classmethod
    def from_settings(cls, s: Settings) -> KeyStore:
        """Build a KeyStore from an application :class:`Settings` instance."""
        auth_cfg = s.get("auth", {}) or {}
        return cls(
            api_keys=auth_cfg.get("api_keys", []),
            device_keys=auth_cfg.get("device_keys", []),
            permission_map=s.get("auth.permission_map", {}) or {},
            roles=s.get("auth.roles", {}) or {},
        )

    # -- resolution ----------------------------------------------------------

    def resolve(self, raw_key: str) -> AuthContext:
        """Look up *raw_key* and return an :class:`AuthContext`.

        Raises :class:`AuthenticationError` if the key is unknown.
        """
        # Check device keys first (8-char uppercase)
        entry = self._device_keys.get(raw_key)
        if entry is not None:
            return AuthContext(
                key=raw_key,
                name=entry.get("name", f"Device {raw_key}"),
                permissions=list(entry.get("permissions", [])),
                roles=list(entry.get("roles", [])),
                device_type=entry.get("device_type"),
                sensor_id=entry.get("sensor_id"),
            )

        # Then standard API keys
        entry = self._api_keys.get(raw_key)
        if entry is not None:
            return AuthContext(
                key=raw_key,
                name=entry.get("name", "API Key"),
                permissions=list(entry.get("permissions", [])),
                roles=list(entry.get("roles", [])),
            )

        raise AuthenticationError()

    # -- permissions ---------------------------------------------------------

    @property
    def permission_map(self) -> dict[str, list[str]]:
        """Read-only view of the configured legacy role/permission definitions."""
        return dict(self._permission_map)

    @property
    def roles(self) -> dict[str, list[str]]:
        """Read-only view of the EG-M14 ``roles:`` token sets."""
        return dict(self._roles)

    @property
    def has_roles_config(self) -> bool:
        """Return True when the EG-M14 ``roles:`` mapping is loaded."""
        return bool(self._roles)

    @property
    def has_legacy_permission_map(self) -> bool:
        """Return True when the legacy ``permission_map:`` mapping is loaded."""
        return bool(self._permission_map)

    def expand_role_tokens(self, roles: list[str]) -> set[str]:
        """Expand EG-M14 role names into their union of D4 tokens (pure membership)."""
        granted: set[str] = set()
        for role in roles:
            granted.update(self._roles.get(role, ()))
        return granted

    def has_role_token(self, auth: AuthContext, *tokens: str) -> bool:
        """Return True if *auth*'s EG-M14 roles (or direct test tokens) carry one of *tokens*."""
        granted = self.expand_role_tokens(auth.roles) | auth.tokens
        if "*" in granted:
            return True
        return any(token in granted for token in tokens)

    def known_role_tokens(self) -> set[str]:
        """Return every explicit D4 token listed in ``roles:`` (excluding ``*``)."""
        return {tok for toks in self._roles.values() for tok in toks if tok != "*"}

    def known_tokens(self) -> set[str]:
        """Return every token known to ``roles:`` (when configured) or legacy ``permission_map``."""
        if self._roles:
            return self.known_role_tokens()
        return set(self._permission_map) | {
            perm for perms in self._permission_map.values() for perm in perms
        }

    def expand_permissions(self, permissions: list[str]) -> list[str]:
        """Expand abstract permission names to endpoint patterns via the map."""
        expanded: list[str] = []
        for perm in permissions:
            mapped = self._permission_map.get(perm)
            if mapped is not None:
                expanded.extend(mapped)
            else:
                # Treat as a literal endpoint pattern
                expanded.append(perm)
        return expanded

    def has_permission(self, auth: AuthContext, method: str, path: str) -> bool:
        """Return True if *auth* may access ``METHOD /path``."""
        target = f"{method.upper()} {path}"
        for pattern in self.expand_permissions(auth.permissions):
            if pattern == "*":
                return True
            if fnmatch.fnmatch(target, pattern):
                return True
        return False

    def has_token(self, auth: AuthContext, *tokens: str) -> bool:
        """Return True if *auth* explicitly carries one of *tokens* (or ``*``).

        Unlike :meth:`has_permission`, this ignores method/path glob grants such
        as ``GET /api/v1/*``. It is a strict token-membership check used to gate
        a surface that broad role globs must not unlock (M09 gallery review).
        """
        granted = set(self.expand_permissions(auth.permissions))
        if "*" in granted:
            return True
        return any(token in granted for token in tokens)


# ─── Module-level facade ─────────────────────────────────────────────────────
#
# A process-wide KeyStore is built lazily from the application settings on
# first use and invalidated by :func:`invalidate_lookup_cache` whenever the
# config is reloaded, so rotated keys take effect without a server restart.

_default_keystore: KeyStore | None = None


def _ensure_keystore() -> KeyStore:
    global _default_keystore
    if _default_keystore is None:
        _default_keystore = KeyStore.from_settings(settings)
    return _default_keystore


def invalidate_lookup_cache() -> None:
    """Force a cache rebuild on the next authentication attempt.

    Call this after :meth:`Settings.reload` so that newly added or rotated
    keys take effect immediately without restarting the server.
    """
    global _default_keystore
    _default_keystore = None


def _resolve_key(raw_key: str) -> AuthContext:
    """Module-level resolver kept for ``backend.mcp.middleware`` compatibility."""
    return _ensure_keystore().resolve(raw_key)


def has_permission(auth: AuthContext, method: str, path: str) -> bool:
    """Check if *auth* is allowed to access ``METHOD /path``."""
    return _ensure_keystore().has_permission(auth, method, path)


def has_token(auth: AuthContext, *tokens: str) -> bool:
    """Check if *auth* explicitly carries one of *tokens* (legacy ``permission_map`` check)."""
    return _ensure_keystore().has_token(auth, *tokens)


def has_role_token(auth: AuthContext, *tokens: str) -> bool:
    """Check if *auth*'s EG-M14 roles (or direct test tokens) carry one of *tokens*."""
    return _ensure_keystore().has_role_token(auth, *tokens)


def _deny(request: Request, reason: str) -> None:
    """Log a structured denial. Never logs key material."""
    logger.info(
        "auth_denied",
        method=request.method,
        path=request.url.path,
        reason=reason,
    )


async def get_auth_context(
    request: Request,
    header_key: str | None = Depends(_api_key_header),
) -> AuthContext:
    """FastAPI dependency: resolve the API key from the ``X-API-Key`` header.

    This is the default resolver for every browser-facing endpoint. Use
    :func:`get_auth_context_device` for hardware that cannot set headers.
    """
    if not header_key:
        _deny(request, "missing_key")
        raise AuthenticationError()

    try:
        return _ensure_keystore().resolve(header_key)
    except AuthenticationError:
        _deny(request, "unknown_key")
        raise


async def get_auth_context_device(
    request: Request,
    header_key: str | None = Depends(_api_key_header),
    query_key: str | None = Query(None, alias="api_key"),
) -> AuthContext:
    """Permissive resolver for the device surface: header, query, then body.

    reCamera-class hardware cannot set request headers, so the key arrives as
    ``?api_key=`` or in the JSON body. Only device endpoints may depend on
    this; see the module docstring.
    """
    raw_key = header_key or query_key

    if not raw_key and request.method in ("POST", "PUT"):
        try:
            body = await request.json()
            raw_key = body.get("device_key") or body.get("api_key")
        except Exception:  # noqa: BLE001
            pass

    if not raw_key:
        _deny(request, "missing_key")
        raise AuthenticationError()

    try:
        return _ensure_keystore().resolve(raw_key)
    except AuthenticationError:
        _deny(request, "unknown_key")
        raise


# Every token name passed to require_permission/require_token, or declared by a
# non-route surface through declare_tokens (MCP tools), collected at import time
# so the lifespan can verify each one is defined by auth.yaml.
# See assert_declared_tokens_known.
_DECLARED_TOKENS: set[str] = set()

# Tokens only an in-process principal carries (the voice companion's resident
# tools). No API key may be granted one, so they are exempt from the "defined in
# auth.yaml" check and, conversely, must not appear there.
_INTERNAL_TOKENS: set[str] = set()


def declare_tokens(*tokens: str) -> None:
    """Register tokens enforced outside ``require_permission`` for the startup check."""
    _DECLARED_TOKENS.update(tokens)


def declare_internal_tokens(*tokens: str) -> None:
    """Register tokens that only in-process principals hold; auth.yaml must never grant them."""
    _INTERNAL_TOKENS.update(tokens)


def assert_declared_tokens_known(keystore: KeyStore | None = None) -> None:
    """Verify every declared permission token is valid and listed in ``config/auth.yaml``.

    When ``roles:`` is loaded (EG-M14 PR 3+), every declared non-internal token
    must conform to the closed D4 grammar and appear in at least one role in
    ``config/auth.yaml`` (excluding ``*``), and no internal-only token may appear
    in any role. Every key's configured role names must also exist under ``roles:``.
    """
    ks = keystore or _ensure_keystore()
    if ks.has_roles_config:
        declared_names = _DECLARED_TOKENS - _INTERNAL_TOKENS
        invalid = sorted(t for t in declared_names if not is_valid_d4_token(t))
        if invalid:
            logger.error("auth_declared_tokens_invalid_d4", tokens=invalid)
            raise RuntimeError(
                "Permission tokens declared at call sites fail EG-M14 D4 grammar: "
                f"{', '.join(invalid)}"
            )
        known = ks.known_role_tokens()
        unknown = sorted(declared_names - known)
        if unknown:
            logger.error("auth_declared_tokens_unknown", tokens=unknown)
            raise RuntimeError(
                "Permission tokens declared at call sites but absent from "
                f"config/auth.yaml roles: {', '.join(unknown)}"
            )
        granted_internal = sorted(_INTERNAL_TOKENS & known)
        if granted_internal:
            logger.error("auth_internal_tokens_granted", tokens=granted_internal)
            raise RuntimeError(
                "Internal-only tokens must not appear in config/auth.yaml: "
                f"{', '.join(granted_internal)}"
            )
        for entry in list(ks._api_keys.values()) + list(ks._device_keys.values()):
            for role_name in entry.get("roles", []):
                if role_name not in ks._roles:
                    logger.error("auth_key_unknown_role", role=role_name)
                    raise RuntimeError(
                        f"Key {entry.get('name', '?')!r} references undefined role {role_name!r}"
                    )
        return

    declared_names = {t for t in _DECLARED_TOKENS if " " not in t} - _INTERNAL_TOKENS
    known = ks.known_tokens()
    unknown = sorted(declared_names - known)
    if unknown:
        logger.error("auth_declared_tokens_unknown", tokens=unknown)
        raise RuntimeError(
            "Permission tokens declared at call sites but absent from "
            f"config/auth.yaml permission_map: {', '.join(unknown)}"
        )
    granted_internal = sorted(_INTERNAL_TOKENS & known)
    if granted_internal:
        logger.error("auth_internal_tokens_granted", tokens=granted_internal)
        raise RuntimeError(
            "Internal-only tokens must not appear in config/auth.yaml: "
            f"{', '.join(granted_internal)}"
        )


def _mark_checker(
    checker: Callable[..., Awaitable[AuthContext]],
    tokens: tuple[str, ...],
    kind: str,
) -> None:
    """Tag a dependency so the route-auth coverage test can recognize it.

    A deliberate marker rather than ``__qualname__`` matching: FastAPI wraps
    dependencies, and a name-based probe would rot on the next refactor.
    """
    checker.__cc_auth_checker__ = True  # type: ignore[attr-defined]
    checker.__cc_auth_tokens__ = tokens  # type: ignore[attr-defined]
    checker.__cc_auth_kind__ = kind  # type: ignore[attr-defined]


def _role_label(auth: AuthContext) -> str:
    """Bounded role label for shadow metrics/logs. Never includes key material."""
    return ",".join(sorted(auth.roles)) if auth.roles else "none"


def _record_inverse_shadow_mismatch(
    token: str,
    auth: AuthContext,
    method: str,
    route: str,
    *,
    live_allowed: bool,
    legacy_allowed: bool,
) -> None:
    """Record a disagreement between live D4 token enforcement and legacy glob shadow."""
    decision = "legacy_would_allow" if legacy_allowed else "legacy_would_deny"
    role = _role_label(auth)
    cc_auth_shadow_mismatch_total.labels(token=token, role=role, decision=decision).inc()
    logger.warning(
        "auth_shadow_mismatch",
        method=method,
        route=route,
        token=token,
        role=role,
        decision=decision,
        live_allowed=live_allowed,
        legacy_allowed=legacy_allowed,
    )


def _evaluate_http_inverse_shadow(
    ks: KeyStore,
    request: Request,
    auth: AuthContext,
    declared_tokens: tuple[str, ...],
    *,
    kind: str,
    live_allowed: bool,
) -> None:
    """Evaluate legacy path-glob / require_token auth in shadow mode after PR 3 switch."""
    if not ks.has_legacy_permission_map or not auth.permissions or not declared_tokens:
        return
    if kind == "token":
        legacy_tokens = tuple(D4_TO_LEGACY_REQUIRE_TOKEN.get(t, t) for t in declared_tokens)
        legacy_allowed = ks.has_token(auth, *legacy_tokens)
    else:
        legacy_allowed = ks.has_permission(auth, request.method, request.url.path)
    if legacy_allowed != live_allowed:
        route_obj = request.scope.get("route")
        route_template = str(getattr(route_obj, "path", request.url.path))
        _record_inverse_shadow_mismatch(
            declared_tokens[0],
            auth,
            request.method,
            route_template,
            live_allowed=live_allowed,
            legacy_allowed=legacy_allowed,
        )


def evaluate_ws_inverse_shadow(
    auth: AuthContext,
    path: str,
    token: str,
    *,
    live_allowed: bool,
    keystore: KeyStore | None = None,
) -> None:
    """Evaluate legacy WebSocket path-glob auth in inverse shadow mode after PR 3 switch."""
    ks = keystore or _ensure_keystore()
    if not ks.has_legacy_permission_map or not auth.permissions:
        return
    legacy_allowed = ks.has_permission(auth, "GET", path)
    if legacy_allowed != live_allowed:
        _record_inverse_shadow_mismatch(
            token,
            auth,
            "WS",
            path,
            live_allowed=live_allowed,
            legacy_allowed=legacy_allowed,
        )


def require_permission(
    *permissions: str,
    resolver: Callable[..., Awaitable[AuthContext]] = get_auth_context,
) -> Callable[..., Awaitable[AuthContext]]:
    """FastAPI dependency factory enforcing EG-M14 D4 token membership.

    Each route declares one ``<resource>:<action>`` token. Enforcement checks
    :meth:`KeyStore.has_role_token` against the caller's roles defined in
    ``config/auth.yaml``. During PR 3, legacy path-glob evaluation runs as an
    inverse shadow and records disagreements without affecting enforcement.

    Pass ``resolver=get_auth_context_device`` on device endpoints only.

    Usage::

        @router.get("/rooms", dependencies=[Depends(require_permission("rooms:read"))])
    """
    _DECLARED_TOKENS.update(permissions)

    async def _checker(
        request: Request,
        auth: AuthContext = Depends(resolver),
    ) -> AuthContext:
        ks = _ensure_keystore()
        live_allowed = ks.has_role_token(auth, *permissions)
        _evaluate_http_inverse_shadow(
            ks, request, auth, permissions, kind="permission", live_allowed=live_allowed
        )
        if not live_allowed:
            _deny(request, "permission")
            raise PermissionDeniedError()
        return auth

    _mark_checker(_checker, permissions, "permission")
    return _checker


def require_token(
    *tokens: str,
    resolver: Callable[..., Awaitable[AuthContext]] = get_auth_context,
) -> Callable[..., Awaitable[AuthContext]]:
    """Dependency factory enforcing EG-M14 D4 token membership.

    Retained during PR 3 so inverse-shadow telemetry can still distinguish
    legacy ``require_token`` routes from legacy ``require_permission`` globs;
    unified into :func:`require_permission` in PR 4.
    """
    _DECLARED_TOKENS.update(tokens)

    async def _checker(
        request: Request,
        auth: AuthContext = Depends(resolver),
    ) -> AuthContext:
        ks = _ensure_keystore()
        live_allowed = ks.has_role_token(auth, *tokens)
        _evaluate_http_inverse_shadow(
            ks, request, auth, tokens, kind="token", live_allowed=live_allowed
        )
        if not live_allowed:
            _deny(request, "permission")
            raise PermissionDeniedError()
        return auth

    _mark_checker(_checker, tokens, "token")
    return _checker
