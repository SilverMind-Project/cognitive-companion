"""
Admin endpoints for health checks and configuration management.
"""

from __future__ import annotations

import copy
import re

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
    result = {}
    for key, value in obj.items():
        if _SENSITIVE_PATTERN.search(key):
            result[key] = "********"
        elif isinstance(value, dict):
            result[key] = _sanitize(value)
        elif isinstance(value, list):
            result[key] = [
                _sanitize(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


@router.get("/health")
async def health():
    """Health check endpoint (no auth required)."""
    return {"status": "ok", "version": "2.0.0"}


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
