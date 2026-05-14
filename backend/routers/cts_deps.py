"""Shared dependencies for CTS router modules.

Replaces the verbatim-duplicated ``_cts_enabled`` function present in all
8 CTS router files.  Lives alongside the router package (no core import)
so routers can import it directly.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from backend.core.config import settings

__all__ = ["cts_enabled", "inject_image_urls", "presigned_image_url"]

_DEFAULT_IMAGE_TTL = 3600  # 1 hour; sized for a caregiver review session


def cts_enabled() -> None:
    """Raise 404 if CTS is not enabled.

    Every CTS router calls this as its first statement so the feature
    flag is a hard gating boundary: zero CTS code executes when
    ``cts.enabled`` is ``False``.
    """
    if not settings.get("cts.enabled", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "cts.disabled",
                "message": "CTS is not enabled on this instance.",
            },
        )


def presigned_image_url(
    request: Request,
    minio_key: str | None,
    *,
    ttl: int = _DEFAULT_IMAGE_TTL,
) -> str | None:
    """Generate a presigned MinIO URL for a CTS frame, or None if unavailable."""
    if not minio_key:
        return None
    minio = getattr(request.app.state, "minio_client", None)
    if minio is None:
        return None
    return minio.generate_presigned_url(minio_key, expiration=ttl)  # type: ignore[no-any-return]


def inject_image_urls(
    items: list[dict],
    request: Request,
    *,
    key_field: str = "minio_key",
    url_field: str = "image_url",
    ttl: int = _DEFAULT_IMAGE_TTL,
) -> list[dict]:
    """Return a new list of dicts with ``url_field`` added where ``key_field`` exists.

    Non-mutating: each original dict is left unchanged.
    Items without ``key_field`` (or where MinIO is unconfigured) are returned as-is.
    """
    result: list[dict] = []
    for item in items:
        url = presigned_image_url(request, item.get(key_field), ttl=ttl)
        result.append({**item, url_field: url} if url is not None else item)
    return result
