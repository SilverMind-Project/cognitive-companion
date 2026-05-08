"""Shared HTTP base for LAN-local JSON/multipart integrations.

Not for CTS upstreams (those use ``_upstream_base.UpstreamClient`` with
mTLS + Ed25519 JWT); this is a lighter tool for cooperative services on
the same trusted network.

All private HTTP methods:

- Return ``None`` on ANY error (network, non-2xx, JSON-decode).
- Log via ``logger.exception("upstream_<event>", service=..., path=..., status=...)``.
- Honour ``configured`` and short-circuit when ``False``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


class HttpUpstreamClient:
    """Base class for LAN-local JSON/multipart HTTP integrations.

    Subclasses declare :attr:`SETTINGS_PREFIX` (e.g. ``"semantic_memory"``
    or ``"scene_analysis"``) which is used to build the default
    ``base_url``, ``timeout``, and ``enabled`` values from
    ``settings.yaml``.

    Maintains a lazy-initialised shared :class:`httpx.AsyncClient` with
    connection-pooling for the lifetime of the instance.  Call
    :meth:`close` during shutdown to release connections.
    """

    SETTINGS_PREFIX: str = ""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._base_url: str = (
            base_url
            if base_url is not None
            else settings.get_required(f"{self.SETTINGS_PREFIX}.url")
        ).rstrip("/")
        self._timeout: float = float(
            timeout
            if timeout is not None
            else settings.get_required(f"{self.SETTINGS_PREFIX}.timeout")
        )
        self.enabled: bool = (
            bool(enabled)
            if enabled is not None
            else bool(settings.get_required(f"{self.SETTINGS_PREFIX}.enabled"))
        )
        self._client: httpx.AsyncClient | None = None
        self._client_lock: asyncio.Lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        """Whether the client has a valid base URL and is enabled."""
        return bool(self._base_url) and self.enabled

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Return the shared :class:`httpx.AsyncClient`, creating it lazily."""
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is None:
                self._client = httpx.AsyncClient(
                    timeout=self._timeout,
                    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
                )
        return self._client

    async def close(self) -> None:
        """Release the shared HTTP client and its connection pool."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── private HTTP helpers ──────────────────────────────────────────

    async def _get_json(
        self, path: str, *, params: dict | None = None, headers: dict | None = None
    ) -> Any | None:
        """GET a JSON response. Returns None on any error."""
        if not self.configured:
            return None
        url = f"{self._base_url}{path}"
        try:
            client = await self._ensure_client()
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.exception(
                "upstream_get_error",
                service=self.SETTINGS_PREFIX,
                path=path,
            )
            return None

    async def _post_json(
        self, path: str, *, json: dict, headers: dict | None = None
    ) -> Any | None:
        """POST a JSON body. Returns None on any error."""
        if not self.configured:
            return None
        url = f"{self._base_url}{path}"
        try:
            client = await self._ensure_client()
            resp = await client.post(url, json=json, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.exception(
                "upstream_post_error",
                service=self.SETTINGS_PREFIX,
                path=path,
            )
            return None

    async def _post_multipart(
        self,
        path: str,
        *,
        files: dict,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> Any | None:
        """POST multipart/form-data. Returns None on any error."""
        if not self.configured:
            return None
        url = f"{self._base_url}{path}"
        try:
            client = await self._ensure_client()
            resp = await client.post(url, files=files, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.exception(
                "upstream_post_multipart_error",
                service=self.SETTINGS_PREFIX,
                path=path,
            )
            return None

    async def _delete_json(
        self, path: str, *, params: dict | None = None, headers: dict | None = None
    ) -> Any | None:
        """DELETE with optional query params. Returns None on any error."""
        if not self.configured:
            return None
        url = f"{self._base_url}{path}"
        try:
            client = await self._ensure_client()
            resp = await client.delete(url, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.exception(
                "upstream_delete_error",
                service=self.SETTINGS_PREFIX,
                path=path,
            )
            return None
