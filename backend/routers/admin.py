"""
Admin endpoints for health checks and configuration management.
"""

from __future__ import annotations

import asyncio
import copy
import re

import httpx
from fastapi import APIRouter, Depends, Request

from backend._version import __version__
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
    return {"status": "ok", "version": __version__}


@router.get("/app-info")
async def app_info():
    """Return public application metadata consumed by the frontend.

    No authentication required: this endpoint exposes only non-sensitive
    configuration values (name, version, timezone).  The frontend uses the
    timezone field to format all displayed timestamps in the operator-configured
    local timezone rather than the browser's timezone.

    Includes service status information for the admin dashboard tiles.
    """
    return {
        "name": settings.get("app.name", "Cognitive Companion"),
        "version": settings.get("app.version", __version__),
        "timezone": settings.get("app.timezone", "UTC"),
        "services": {
            "person_id": {
                "enabled": bool(settings.get("person_id.url")),
                "health_url": "/admin/health/person-id",
            },
            "scene_analysis": {
                "enabled": bool(settings.get("scene_analysis.url")),
                "health_url": "/admin/health/scene-analysis",
            },
            "semantic_memory": {
                "enabled": bool(settings.get("semantic_memory.url")),
                "health_url": "/admin/health/semantic-memory",
            },
            "tts": {
                "enabled": bool(settings.get("tts.url")),
                "health_url": "/admin/health/tts",
            },
            "tracking_orchestrator": {
                "enabled": bool(settings.get("tracking_orchestrator.url")),
                "health_url": "/admin/health/tracking-orchestrator",
            },
            "triton": {
                "enabled": bool(settings.get("embedding.triton_url")),
                "health_url": "/admin/health/triton",
            },
        },
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


async def _proxy_health(url: str, timeout: float = 5.0) -> dict:
    """Fetch /health from *url* and return a normalised response dict."""
    if not url:
        return {"configured": False, "status": "not_configured"}
    base = url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{base}/health")
            resp.raise_for_status()
            data = resp.json()
            return {"configured": True, **data}
    except Exception:
        return {"configured": True, "status": "unreachable"}


@router.get("/health/tracking-orchestrator")
async def tracking_orchestrator_health():
    """Proxy health check to the Tracking Orchestrator service."""
    url = settings.get("tracking_orchestrator.url") or ""
    timeout = float(settings.get("tracking_orchestrator.timeout") or 5)
    return await _proxy_health(url, timeout)


@router.get("/health/scene-analysis")
async def scene_analysis_health():
    """Proxy health check to the Scene Analysis service."""
    url = settings.get("scene_analysis.url") or ""
    timeout = float(settings.get("scene_analysis.timeout") or 5)
    return await _proxy_health(url, timeout)


@router.get("/health/semantic-memory")
async def semantic_memory_health():
    """Proxy health check to the Semantic Memory service."""
    url = settings.get("semantic_memory.url") or ""
    timeout = float(settings.get("semantic_memory.timeout") or 5)
    return await _proxy_health(url, timeout)


@router.get("/health/triton")
async def triton_health():
    """Health check for Triton Inference Server.

    Converts the configured gRPC URL (port 8701) to an HTTP URL (port 8700)
    and hits Triton's built-in /v2/health/ready endpoint.
    """
    triton_url: str = settings.get("embedding.triton_url") or ""
    if not triton_url:
        return {"configured": False, "status": "not_configured"}
    # Derive HTTP health URL: replace gRPC port 8701 with HTTP port 8700.
    # URL may be bare host:port (no scheme) so we prepend http://.
    http_url = triton_url.replace(":8701", ":8700")
    if "://" not in http_url:
        http_url = f"http://{http_url}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{http_url}/v2/health/ready")
            resp.raise_for_status()
            return {"configured": True, "status": "ready"}
    except Exception:
        return {"configured": True, "status": "unreachable"}


@router.get("/health/llm-models")
async def llm_models_health() -> list[dict]:
    """Concurrently check the health of all configured LLM models."""
    models: list[dict] = settings.get("llm.models") or []

    async def check_model(model: dict) -> dict:
        model_id = model.get("id", "")
        name = model.get("name", "")
        base_url = (model.get("base_url") or "").rstrip("/")
        configured_model = model.get("model", "")

        base: dict = {"id": model_id, "name": name, "configured_model": configured_model}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{base_url}/v1/models")
                resp.raise_for_status()
                data = resp.json()
                available_ids = [entry.get("id") for entry in data.get("data", [])]
                if configured_model in available_ids:
                    return {**base, "status": "success"}
                else:
                    return {
                        **base,
                        "status": "warning",
                        "detail": f"configured: {configured_model}, available: {available_ids}",
                    }
        except httpx.TimeoutException:
            return {**base, "status": "error", "detail": "Request timed out"}
        except Exception as exc:
            return {**base, "status": "error", "detail": str(exc)}

    results = await asyncio.gather(*(check_model(m) for m in models))
    return list(results)


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


@router.get("/notification-channels/audit")
async def channel_audit(
    request: Request,
    _auth: AuthContext = Depends(require_permission("admin")),
):
    """Audit pipeline steps for unknown notification channel names.

    Scans every PipelineStep.config_json for a ``channels`` array
    and reports entries not in the current ChannelRegistry.
    """
    from backend.channels import ChannelRegistry
    from backend.models.pipeline import PipelineStep

    db = request.app.state.db_factory()
    try:
        registered = {m.channel_name for m in ChannelRegistry.all_metadata()}
        rows = db.query(PipelineStep).all()
        issues: list[dict] = []

        for row in rows:
            config = row.config_json or {}
            step_channels = config.get("channels") or []
            if isinstance(step_channels, str):
                step_channels = [step_channels]
            unknown = [ch for ch in step_channels if ch not in registered]
            if unknown:
                issues.append({
                    "step_id": row.id,
                    "step_type": row.step_type,
                    "rule_id": row.rule_id,
                    "unknown_channels": unknown,
                })

        return {
            "registered_channels": sorted(registered),
            "issues": issues,
            "issue_count": len(issues),
        }
    finally:
        db.close()
