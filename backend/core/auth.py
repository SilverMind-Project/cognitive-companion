"""API key authentication and named D4 permission-token authorization.

Keys are resolved from the ``X-API-Key`` header. Endpoints serving hardware
that cannot set headers opt into :func:`get_auth_context_device`, which also
accepts a ``?api_key=`` query parameter and a JSON body ``device_key`` /
``api_key`` field. Query-string and body keys leak into access logs and
browser history, so they stay confined to that device surface: never wire
the device resolver into a browser-facing endpoint.

Device keys are 8-character uppercase alphanumeric strings.

Architecture
------------
Authorization uses named D4 ``<resource>:<action>`` permission tokens (EG-M14):

- every guarded HTTP route, WebSocket endpoint, and MCP tool declares exactly
  one D4 token;
- roles are token sets defined only under ``roles:`` in ``config/auth.yaml``;
- every check is pure token membership via :meth:`KeyStore.has_token`.

The :class:`KeyStore` class has no dependency on FastAPI or the module-level
:mod:`backend.core.config` singleton, so tests can construct it directly with
hand-crafted data.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, Query, Request, WebSocket
from fastapi.security import APIKeyHeader

from backend.core.config import Settings, settings
from backend.core.exceptions import AuthenticationError, PermissionDeniedError
from backend.core.logging import get_logger

__all__ = [
    "ALLOWED_ACTIONS",
    "D4_TOKEN_RE",
    "WS_ROUTE_TOKENS",
    "AuthContext",
    "KeyStore",
    "WebSocketAuth",
    "actor_from_auth",
    "assert_declared_tokens_known",
    "authenticate_websocket",
    "declare_internal_tokens",
    "declare_tokens",
    "get_auth_context",
    "get_auth_context_device",
    "has_token",
    "invalidate_lookup_cache",
    "is_valid_d4_token",
    "require_permission",
]

logger = get_logger(__name__)

# Closed D4 action vocabulary (EG-M14). Adding an action is a reviewed edit here.
ALLOWED_ACTIONS: frozenset[str] = frozenset(
    {
        "read",
        "write",
        "delete",
        "execute",
        "import",
        "acknowledge",
        "propose",
        "correct",
        "calibrate",
        "review",
        "takeover",
        "act",
        "ingest",
        "heartbeat",
    }
)

D4_TOKEN_RE: re.Pattern[str] = re.compile(
    r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*:(" + "|".join(sorted(ALLOWED_ACTIONS)) + r")$"
)

# Authenticated WebSocket routes and their required D4 tokens.
WS_ROUTE_TOKENS: dict[str, str] = {
    "/ws/audio": "companion.audio:act",
    "/ws/cts": "cts.live:read",
    "/ws/pipeline": "pipeline.events:read",
}

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def is_valid_d4_token(token: str) -> bool:
    """Return True iff *token* conforms to the closed D4 ``<resource>:<action>`` grammar."""
    return bool(D4_TOKEN_RE.match(token))


@dataclass
class AuthContext:
    """Resolved authentication context for a request."""

    key: str
    name: str
    roles: list[str] = field(default_factory=list)
    # Direct token grants used only by synthetic unit tests; KeyStore.resolve()
    # never populates this field from config/auth.yaml.
    tokens: frozenset[str] = field(default_factory=frozenset)
    device_type: str | None = None
    sensor_id: str | None = None


def actor_from_auth(auth: AuthContext | None) -> str:
    """The name an audit record stores for whoever made this request: the API key's name.

    Pass the ``AuthContext`` a route received from ``require_permission``.
    A review or correction must never be recorded as made by nobody, so a missing context or a
    nameless key raises instead of falling back to a placeholder such as "system".
    """
    if auth is None or not auth.name:
        raise AuthenticationError()
    return auth.name


class KeyStore:
    """Immutable lookup table for API + device keys and ``roles:`` token sets.

    :class:`KeyStore` is intentionally decoupled from
    :mod:`backend.core.config`: construct it directly in tests, or use
    :meth:`from_settings` to load from the live YAML config.
    """

    def __init__(
        self,
        api_keys: list[Mapping[str, Any]] | None = None,
        device_keys: list[Mapping[str, Any]] | None = None,
        roles: Mapping[str, list[str]] | None = None,
    ) -> None:
        self._api_keys: dict[str, Mapping[str, Any]] = {
            entry["key"]: entry for entry in (api_keys or [])
        }
        self._device_keys: dict[str, Mapping[str, Any]] = {
            entry["key"]: entry for entry in (device_keys or [])
        }
        self._roles: dict[str, list[str]] = dict(roles or {})

    # -- construction --------------------------------------------------------

    @classmethod
    def from_settings(cls, s: Settings) -> KeyStore:
        """Build a KeyStore from an application :class:`Settings` instance."""
        auth_cfg = s.get("auth", {}) or {}
        return cls(
            api_keys=auth_cfg.get("api_keys", []),
            device_keys=auth_cfg.get("device_keys", []),
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
                roles=list(entry.get("roles", [])),
            )

        raise AuthenticationError()

    # -- permissions ---------------------------------------------------------

    @property
    def roles(self) -> dict[str, list[str]]:
        """Read-only view of the configured ``roles:`` token sets."""
        return dict(self._roles)

    def expand_role_tokens(self, roles: list[str]) -> set[str]:
        """Expand role names into their union of D4 tokens (pure membership)."""
        granted: set[str] = set()
        for role in roles:
            granted.update(self._roles.get(role, ()))
        return granted

    def has_token(self, auth: AuthContext, *tokens: str) -> bool:
        """Return True if *auth*'s roles (or direct test tokens) carry one of *tokens* or ``*``."""
        granted = self.expand_role_tokens(auth.roles) | auth.tokens
        if "*" in granted:
            return True
        return any(token in granted for token in tokens)

    def known_tokens(self) -> set[str]:
        """Return every explicit D4 token listed in ``roles:`` (excluding ``*``)."""
        return {tok for toks in self._roles.values() for tok in toks if tok != "*"}


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
    """Module-level resolver kept for ``backend.mcp.middleware`` and WebSocket handlers."""
    return _ensure_keystore().resolve(raw_key)


def has_token(auth: AuthContext, *tokens: str) -> bool:
    """Check if *auth*'s roles carry one of *tokens* (see :meth:`KeyStore.has_token`)."""
    return _ensure_keystore().has_token(auth, *tokens)


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


# Every token name passed to require_permission, or declared by a non-route
# surface through declare_tokens (MCP tools, WebSockets), collected at import
# time so the lifespan can verify each one conforms to D4 and exists in roles:.
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
    """Verify every declared token is D4-valid and present in ``config/auth.yaml`` ``roles:``.

    Also verifies that no internal-only token appears in ``roles:``, that every
    non-``*`` token configured in ``roles:`` conforms to D4, and that every role
    referenced by an API or device key is defined under ``roles:``.
    """
    ks = keystore or _ensure_keystore()
    declared_names = _DECLARED_TOKENS - _INTERNAL_TOKENS

    invalid_declared = sorted(t for t in declared_names if not is_valid_d4_token(t))
    if invalid_declared:
        logger.error("auth_declared_tokens_invalid_d4", tokens=invalid_declared)
        raise RuntimeError(
            "Permission tokens declared at call sites fail D4 grammar: "
            f"{', '.join(invalid_declared)}"
        )

    known = ks.known_tokens()
    invalid_configured = sorted(t for t in known if not is_valid_d4_token(t))
    if invalid_configured:
        logger.error("auth_configured_tokens_invalid_d4", tokens=invalid_configured)
        raise RuntimeError(
            "Permission tokens in config/auth.yaml roles fail D4 grammar: "
            f"{', '.join(invalid_configured)}"
        )

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


def _mark_checker(
    checker: Callable[..., Awaitable[AuthContext]],
    tokens: tuple[str, ...],
) -> None:
    """Tag a dependency so the route-auth coverage test can recognize it.

    A deliberate marker rather than ``__qualname__`` matching: FastAPI wraps
    dependencies, and a name-based probe would rot on the next refactor.
    """
    checker.__cc_auth_checker__ = True  # type: ignore[attr-defined]
    checker.__cc_auth_tokens__ = tokens  # type: ignore[attr-defined]


def require_permission(
    *permissions: str,
    resolver: Callable[..., Awaitable[AuthContext]] = get_auth_context,
) -> Callable[..., Awaitable[AuthContext]]:
    """FastAPI dependency factory enforcing D4 named-token membership.

    Each route declares exactly one ``<resource>:<action>`` token. Enforcement
    checks :meth:`KeyStore.has_token` against the caller's roles defined in
    ``config/auth.yaml``. Every declared token is registered in
    ``_DECLARED_TOKENS`` and verified by :func:`assert_declared_tokens_known`
    at startup.

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
        if not ks.has_token(auth, *permissions):
            _deny(request, "permission")
            raise PermissionDeniedError()
        return auth

    _mark_checker(_checker, permissions)
    return _checker


@dataclass(frozen=True)
class WebSocketAuth:
    """An authenticated WebSocket upgrade.

    ``subprotocol`` must be passed to ``websocket.accept(subprotocol=...)``: a browser
    that offered the key as its ``Sec-WebSocket-Protocol`` drops the connection
    (close 1006) unless the server selects that subprotocol in its handshake.
    """

    auth: AuthContext
    subprotocol: str | None


async def authenticate_websocket(
    websocket: WebSocket, token: str, *, channel: str
) -> WebSocketAuth | None:
    """Authenticate a WebSocket upgrade against one D4 ``token``.

    The key comes from the ``x-api-key`` header (non-browser clients) or the
    ``Sec-WebSocket-Protocol`` header (browsers, which cannot set headers on a
    WebSocket and must not put a key in the URL). On failure the socket is closed
    with 1008 and a reason (``auth_required``, ``auth_failed``,
    ``permission_denied``), a ``ws_rejected_*`` event naming ``channel`` is
    logged, and None is returned. Never logs key material.
    """
    client_ip = websocket.client.host if websocket.client else "unknown"
    header_key = websocket.headers.get("x-api-key")
    protocol_key = websocket.headers.get("sec-websocket-protocol", "").strip()
    raw_key = header_key or protocol_key
    if not raw_key:
        logger.warning("ws_rejected_no_key", channel=channel, client=client_ip)
        await websocket.close(code=1008, reason="auth_required")
        return None
    try:
        auth = _resolve_key(raw_key)
    except AuthenticationError:
        logger.warning("ws_rejected_auth_failed", channel=channel, client=client_ip)
        await websocket.close(code=1008, reason="auth_failed")
        return None
    if not has_token(auth, token):
        logger.warning(
            "ws_rejected_permission_denied", channel=channel, client=client_ip, name=auth.name
        )
        await websocket.close(code=1008, reason="permission_denied")
        return None
    return WebSocketAuth(auth=auth, subprotocol=None if header_key else protocol_key)
