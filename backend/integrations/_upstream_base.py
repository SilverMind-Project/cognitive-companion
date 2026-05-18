"""Shared mTLS + JWT httpx base for BFF gateway calls.

Only :mod:`backend.integrations.ingress_admin_client` and
:mod:`backend.integrations.tracking_orchestrator_client` may subclass this.
All other CC modules that need HTTP must go through one of those clients.

mTLS degrades gracefully: when ``ca_file`` is absent from the service config
the client uses plain HTTPS with no client certificate.  This enables local
development without certificates while keeping the JWT in place for request
attribution.
"""

from __future__ import annotations

import ssl
import time
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.core.service_jwt import mint_service_jwt
from backend.core.upstream_errors import UpstreamError, UpstreamTimeout, UpstreamUnavailable

logger = get_logger(__name__)


class UpstreamClient:
    """Base class for all BFF gateway clients.

    Subclasses declare :attr:`SERVICE_NAME` (matches ``cts.upstream.<name>``
    in settings) and :attr:`AUDIENCE` (the ``aud`` claim the upstream expects).
    """

    SERVICE_NAME: str = ""
    AUDIENCE: str = ""

    def __init__(self) -> None:
        cfg: dict[str, Any] = settings.get(f"cts.upstream.{self.SERVICE_NAME}") or {}
        self._base: str = cfg.get("url", "").rstrip("/")
        self._timeout: float = float(cfg.get("timeout_s", 5.0))
        self._ssl_ctx: ssl.SSLContext | bool = self._build_ssl(cfg)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_ssl(cfg: dict[str, Any]) -> ssl.SSLContext | bool:
        ca_file: str | None = cfg.get("ca_file")
        client_cert: str | None = cfg.get("client_cert")
        client_key: str | None = cfg.get("client_key")

        if not ca_file:
            # Dev mode: no mTLS; still validate server cert with default CAs.
            return True

        ctx = ssl.create_default_context(cafile=ca_file)
        if client_cert and client_key:
            ctx.load_cert_chain(certfile=client_cert, keyfile=client_key)
        return ctx

    async def _request(
        self,
        method: str,
        path: str,
        *,
        request_id: str = "",
        **kw: Any,
    ) -> httpx.Response:
        headers: dict[str, str] = kw.pop("headers", {}) or {}
        token = mint_service_jwt(aud=self.AUDIENCE)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if request_id:
            headers["X-Request-ID"] = request_id
        kw["headers"] = headers

        if not self._base:
            raise UpstreamUnavailable(
                self.SERVICE_NAME, 503
            )

        @retry(
            retry=retry_if_exception_type((UpstreamTimeout, UpstreamUnavailable)),
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=0.1, max=1.5),
            reraise=True,
        )
        async def _do() -> httpx.Response:
            started = time.perf_counter()
            try:
                async with httpx.AsyncClient(
                    verify=self._ssl_ctx,
                    timeout=self._timeout,
                ) as c:
                    r = await c.request(method, f"{self._base}{path}", **kw)
                    elapsed_ms = (time.perf_counter() - started) * 1000
                    logger.info(
                        "upstream_request",
                        service=self.SERVICE_NAME,
                        path=path,
                        method=method,
                        status=r.status_code,
                        ms=round(elapsed_ms, 2),
                    )
                    if r.status_code >= 500:
                        raise UpstreamUnavailable(self.SERVICE_NAME, r.status_code, r.text)
                    if r.status_code >= 400:
                        raise UpstreamError(self.SERVICE_NAME, r.status_code, r.text)
                    return r
            except httpx.TimeoutException as exc:
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.warning(
                    "upstream_timeout",
                    service=self.SERVICE_NAME,
                    path=path,
                    ms=round(elapsed_ms, 2),
                )
                raise UpstreamTimeout(self.SERVICE_NAME, str(exc)) from exc

        return await _do()
