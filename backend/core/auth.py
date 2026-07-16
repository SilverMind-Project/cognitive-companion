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

from backend.core.config import Settings, settings
from backend.core.exceptions import AuthenticationError, PermissionDeniedError
from backend.core.logging import get_logger

__all__ = [
    "AuthContext",
    "KeyStore",
    "assert_declared_tokens_known",
    "get_auth_context",
    "get_auth_context_device",
    "invalidate_lookup_cache",
    "require_permission",
    "require_token",
]

logger = get_logger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass
class AuthContext:
    """Resolved authentication context for a request."""

    key: str
    name: str
    permissions: list[str] = field(default_factory=list)
    device_type: str | None = None
    sensor_id: str | None = None


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
    ) -> None:
        self._api_keys: dict[str, Mapping[str, Any]] = {
            entry["key"]: entry for entry in (api_keys or [])
        }
        self._device_keys: dict[str, Mapping[str, Any]] = {
            entry["key"]: entry for entry in (device_keys or [])
        }
        self._permission_map: dict[str, list[str]] = dict(permission_map or {})

    # -- construction --------------------------------------------------------

    @classmethod
    def from_settings(cls, s: Settings) -> KeyStore:
        """Build a KeyStore from an application :class:`Settings` instance."""
        auth_cfg = s.get("auth", {}) or {}
        return cls(
            api_keys=auth_cfg.get("api_keys", []),
            device_keys=auth_cfg.get("device_keys", []),
            permission_map=s.get("auth.permission_map", {}) or {},
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
            )

        raise AuthenticationError()

    # -- permissions ---------------------------------------------------------

    @property
    def permission_map(self) -> dict[str, list[str]]:
        """Read-only view of the configured role/permission definitions."""
        return dict(self._permission_map)

    def known_tokens(self) -> set[str]:
        """Return every token the permission map gives meaning to.

        Two shapes count, because ``auth.yaml`` uses both: a *key* defines a
        token as a set of patterns (``rooms:read``), and a *value* is a token a
        role carries directly (``cts.view``, checked by :meth:`has_token`).
        A name in neither is one no caller can ever hold.
        """
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


# Every token name passed to require_permission/require_token, collected at
# import time so the lifespan can verify each one is defined by auth.yaml.
# See assert_declared_tokens_known.
_DECLARED_TOKENS: set[str] = set()


def assert_declared_tokens_known(keystore: KeyStore | None = None) -> None:
    """Verify every declared permission token exists in the permission map.

    ``require_permission("rooms:read")`` reads as if the named token were
    enforced; the check is actually method+path against the caller's expanded
    patterns. This turns the names into a checked contract: a token that no
    role can ever grant is a typo or a missing ``auth.yaml`` entry.
    """
    ks = keystore or _ensure_keystore()
    # A declared name containing a space is a literal "METHOD /path" pattern,
    # which expand_permissions passes through by design; only symbolic names
    # need a definition.
    declared_names = {t for t in _DECLARED_TOKENS if " " not in t}
    unknown = sorted(declared_names - ks.known_tokens())
    if unknown:
        logger.error("auth_declared_tokens_unknown", tokens=unknown)
        raise RuntimeError(
            "Permission tokens declared at call sites but absent from "
            f"config/auth.yaml permission_map: {', '.join(unknown)}"
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


def require_permission(
    *permissions: str,
    resolver: Callable[..., Awaitable[AuthContext]] = get_auth_context,
) -> Callable[..., Awaitable[AuthContext]]:
    """
    FastAPI dependency factory that checks AuthContext against endpoint permissions.

    The check is performed against the resolved request method/path: permission
    strings in config are endpoint patterns as well as role names. The
    ``*permissions`` names are call-site documentation, but not decorative --
    each is registered in ``_DECLARED_TOKENS`` and must be defined by
    ``auth.yaml`` or startup fails (:func:`assert_declared_tokens_known`).

    Pass ``resolver=get_auth_context_device`` on device endpoints only.

    Usage::

        @router.get("/rooms", dependencies=[Depends(require_permission("rooms:read"))])
    """
    _DECLARED_TOKENS.update(permissions)

    async def _checker(
        request: Request,
        auth: AuthContext = Depends(resolver),
    ) -> AuthContext:
        if not _ensure_keystore().has_permission(auth, request.method, request.url.path):
            _deny(request, "permission")
            raise PermissionDeniedError()
        return auth

    _mark_checker(_checker, permissions, "permission")
    return _checker


def require_token(
    *tokens: str,
    resolver: Callable[..., Awaitable[AuthContext]] = get_auth_context,
) -> Callable[..., Awaitable[AuthContext]]:
    """Dependency factory enforcing strict token membership, not path globs.

    Use for a surface that must stay separate from broad role grants: a caller
    holding only ``GET /api/v1/*`` or ``cts.identity.correct`` is rejected unless
    it also carries one of *tokens* (or the ``*`` superuser grant). This is the
    enforcement seam for the M09 ``cts.identity.gallery_review`` permission.
    """
    _DECLARED_TOKENS.update(tokens)

    async def _checker(
        request: Request,
        auth: AuthContext = Depends(resolver),
    ) -> AuthContext:
        if not _ensure_keystore().has_token(auth, *tokens):
            _deny(request, "permission")
            raise PermissionDeniedError()
        return auth

    _mark_checker(_checker, tokens, "token")
    return _checker
