"""Whether each configured LLM model is actually served by its inference server.

``llm.models`` names a ``model`` per entry; the server behind ``base_url`` decides which
models exist. A configured id the server does not serve passes every config check and
then fails on each call, so both the admin health page and startup ask the server.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from typing import Any

import httpx

from backend.core.logging import get_logger

logger = get_logger(__name__)

_PROBE_TIMEOUT_S = 10.0


async def check_served_models(models: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Probe ``{base_url}/v1/models`` for every configured model, concurrently.

    Each result has ``id``, ``name``, ``configured_model``, and ``status``: ``success``
    when the server lists the model, ``warning`` (with ``detail``) when it answers without
    it, ``error`` (with ``detail``) when it cannot be reached.
    """

    async def check(model: Mapping[str, Any]) -> dict[str, Any]:
        base_url = (model.get("base_url") or "").rstrip("/")
        configured_model = model.get("model", "")
        base: dict[str, Any] = {
            "id": model.get("id", ""),
            "name": model.get("name", ""),
            "configured_model": configured_model,
        }
        try:
            async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_S) as client:
                resp = await client.get(f"{base_url}/v1/models")
                resp.raise_for_status()
                available = [entry.get("id") for entry in resp.json().get("data", [])]
        except httpx.TimeoutException:
            return {**base, "status": "error", "detail": "Request timed out"}
        except Exception as exc:  # noqa: BLE001 - any probe failure is reported, never raised
            return {**base, "status": "error", "detail": str(exc)}
        if configured_model in available:
            return {**base, "status": "success"}
        return {
            **base,
            "status": "warning",
            "detail": f"configured: {configured_model}, available: {available}",
        }

    return list(await asyncio.gather(*(check(m) for m in models)))


async def log_unserved_models(
    models: Iterable[Mapping[str, Any]], *, required_ids: Mapping[str, str]
) -> list[dict[str, Any]]:
    """Log every configured model its server does not serve; return the probe results.

    ``required_ids`` maps a setting key to the model id a feature depends on (for example
    ``knowledge.answer_model``). A required model that is not served is an error, since that
    feature fails on every call; any other unserved entry is a warning.
    """
    results = await check_served_models(models)
    required_by_id: dict[str, list[str]] = {}
    for key, model_id in required_ids.items():
        required_by_id.setdefault(model_id, []).append(key)
    for result in results:
        if result["status"] == "success":
            continue
        keys = required_by_id.get(result["id"], [])
        log = logger.error if keys else logger.warning
        log(
            "llm_model_not_served",
            model_id=result["id"],
            configured_model=result["configured_model"],
            status=result["status"],
            detail=result.get("detail", ""),
            required_by=keys,
        )
    return results
