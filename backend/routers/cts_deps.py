"""Shared dependencies for CTS router modules.

Replaces the verbatim-duplicated ``_cts_enabled`` function present in all
8 CTS router files.  Lives alongside the router package (no core import)
so routers can import it directly.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from backend.core.config import settings

__all__ = ["cts_enabled"]


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
