"""
API key authentication and permission checking.

Keys are resolved from (in order):
  1. X-API-Key header
  2. ?api_key= query parameter
  3. JSON body field "device_key" (for device endpoints)

Device keys are 8-char uppercase alphanumeric strings.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field

from fastapi import Depends, Query, Request
from fastapi.security import APIKeyHeader

from backend.core.config import settings
from backend.core.exceptions import AuthenticationError, PermissionDeniedError

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass
class AuthContext:
    """Resolved authentication context for a request."""

    key: str
    name: str
    permissions: list[str] = field(default_factory=list)
    device_type: str | None = None
    sensor_id: str | None = None


def _build_lookup() -> tuple[dict[str, dict], dict[str, dict]]:
    """Build lookup dicts from auth config. Called once per config reload."""
    auth_cfg = settings.get("auth", {})

    api_keys: dict[str, dict] = {}
    for entry in auth_cfg.get("api_keys", []):
        api_keys[entry["key"]] = entry

    device_keys: dict[str, dict] = {}
    for entry in auth_cfg.get("device_keys", []):
        device_keys[entry["key"]] = entry

    return api_keys, device_keys


def _resolve_key(raw_key: str) -> AuthContext:
    """Look up a raw key string in the config and return an AuthContext."""
    api_keys, device_keys = _build_lookup()

    # Check device keys first (8-char uppercase)
    if raw_key in device_keys:
        entry = device_keys[raw_key]
        return AuthContext(
            key=raw_key,
            name=entry.get("name", f"Device {raw_key}"),
            permissions=entry.get("permissions", []),
            device_type=entry.get("device_type"),
            sensor_id=entry.get("sensor_id"),
        )

    # Then standard API keys
    if raw_key in api_keys:
        entry = api_keys[raw_key]
        return AuthContext(
            key=raw_key,
            name=entry.get("name", "API Key"),
            permissions=entry.get("permissions", []),
        )

    raise AuthenticationError()


def _expand_permissions(permissions: list[str]) -> list[str]:
    """Expand abstract permission names to endpoint patterns using permission_map."""
    perm_map = settings.get("auth.permission_map", {})
    expanded: list[str] = []
    for perm in permissions:
        if perm in perm_map:
            expanded.extend(perm_map[perm])
        else:
            # Treat as a literal endpoint pattern
            expanded.append(perm)
    return expanded


def has_permission(auth: AuthContext, method: str, path: str) -> bool:
    """Check if auth context is allowed to access the given method + path."""
    expanded = _expand_permissions(auth.permissions)
    target = f"{method.upper()} {path}"

    for pattern in expanded:
        if pattern == "*":
            return True
        if fnmatch.fnmatch(target, pattern):
            return True
    return False


async def get_auth_context(
    request: Request,
    header_key: str | None = Depends(_api_key_header),
    query_key: str | None = Query(None, alias="api_key"),
) -> AuthContext:
    """
    FastAPI dependency – resolve the API key from header, query, or body.
    """
    raw_key = header_key or query_key

    # For device endpoints, also check JSON body
    if not raw_key and request.method in ("POST", "PUT"):
        try:
            body = await request.json()
            raw_key = body.get("device_key") or body.get("api_key")
        except Exception:
            pass

    if not raw_key:
        raise AuthenticationError()

    return _resolve_key(raw_key)


def require_permission(*permissions: str):
    """
    FastAPI dependency factory that checks AuthContext against endpoint permissions.

    Usage:
        @router.get("/rooms", dependencies=[Depends(require_permission("rooms:read"))])
    """

    async def _checker(
        request: Request,
        auth: AuthContext = Depends(get_auth_context),
    ) -> AuthContext:
        method = request.method
        path = request.url.path

        # Check explicit endpoint-level permission
        if not has_permission(auth, method, path):
            raise PermissionDeniedError()

        return auth

    return _checker
