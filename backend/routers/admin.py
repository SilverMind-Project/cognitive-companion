"""
Admin endpoints for health checks and configuration management.
"""

from __future__ import annotations

import copy
import re

import httpx
from fastapi import APIRouter, Depends

from backend.core.auth import AuthContext, require_permission
from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

# Pattern for sensitive config keys
_SENSITIVE_PATTERN = re.compile(r"(api_key|token|secret|password|credential)", re.IGNORECASE)


def _sanitize(obj: dict) -> dict:
    """Recursively mask sensitive values in a config dictionary."""
    result: dict = {}
    for key, value in obj.items():
        if _SENSITIVE_PATTERN.search(key):
            result[key] = "********"
        elif isinstance(value, dict):
            result[key] = _sanitize(value)
        elif isinstance(value, list):
            result[key] = [_sanitize(item) if isinstance(item, dict) else item for item in value]
        else:
            result[key] = value
    return result


@router.get("/health")
async def health():
    """Health check endpoint (no auth required)."""
    return {"status": "ok", "version": "2.0.0"}


@router.get("/app-info")
async def app_info():
    """Return public application metadata consumed by the frontend.

    No authentication required: this endpoint exposes only non-sensitive
    configuration values (name, version, timezone).  The frontend uses the
    timezone field to format all displayed timestamps in the operator-configured
    local timezone rather than the browser's timezone.
    """
    return {
        "name": settings.get("app.name", "Cognitive Companion"),
        "version": settings.get("app.version", "2.0.0"),
        "timezone": settings.get("app.timezone", "UTC"),
    }


@router.get("/health/person-id")
async def person_id_health():
    """Proxy health check to the Person Identification service."""
    from backend.integrations.person_id_client import PersonIDClient

    client = PersonIDClient()
    if not client.enabled:
        return {"configured": False, "status": "not_configured"}
    data = await client.health_check()
    if data is None:
        return {"configured": True, "status": "unreachable"}
    return {"configured": True, **data}


@router.get("/health/tts")
async def tts_health():
    """Proxy health check to the TTS service."""
    tts_url = settings.get("tts.url") or ""
    if not tts_url:
        return {"configured": False, "status": "not_configured"}
    base = tts_url.rstrip("/")
    # Strip /v1 suffix if present: health lives at root /health
    if base.endswith("/v1"):
        base = base[:-3]
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base}/health")
            resp.raise_for_status()
            data = resp.json()
            return {"configured": True, **data}
    except Exception:
        return {"configured": True, "status": "unreachable"}


@router.post("/config/reload")
def reload_config(
    _auth: AuthContext = Depends(require_permission("admin")),
):
    """Reload YAML configuration files."""
    settings.reload()
    logger.info("Configuration reloaded via admin endpoint")
    return {"status": "reloaded"}


@router.get("/config/current")
def current_config(
    _auth: AuthContext = Depends(require_permission("admin")),
):
    """Return the current configuration with sensitive values masked."""
    raw = copy.deepcopy(settings.raw())
    return _sanitize(raw)


@router.get("/telegram/trigger-defaults")
def telegram_trigger_defaults(
    _auth: AuthContext = Depends(require_permission("admin")),
):
    """Return the system-configured default whitelist for Telegram trigger rules.

    The frontend uses this to pre-populate the ``allowed_chat_ids`` field when
    creating or editing a telegram-type rule that has no explicit whitelist.
    Empty strings (produced by unset env vars) are excluded so the caller
    always receives a clean list of real chat IDs.
    """
    raw_ids: list = settings.get("notifications.telegram.trigger_allowed_chat_ids") or []
    return {
        "allowed_chat_ids": [str(c) for c in raw_ids if c],
    }
