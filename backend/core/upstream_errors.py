"""Upstream error taxonomy for BFF gateway calls.

All errors raised by ``IngressAdminClient`` and ``OrchestratorClient``
inherit from :class:`UpstreamError`.  Routers catch these and render them
as a uniform JSON shape so the frontend can display a stable toast:

    {"error": {"code": "upstream.timeout", "service": "rtsp_ingress",
               "message": "...", "request_id": "..."}}
"""

from __future__ import annotations

from enum import StrEnum


class UpstreamCode(StrEnum):
    TIMEOUT = "upstream.timeout"
    UNAVAILABLE = "upstream.unavailable"
    BAD_REQUEST = "upstream.bad_request"
    FORBIDDEN = "upstream.forbidden"
    NOT_FOUND = "upstream.not_found"
    CONFLICT = "upstream.conflict"
    UNKNOWN = "upstream.unknown"


class UpstreamError(Exception):
    """Base class for all upstream gateway errors."""

    def __init__(self, service: str, status: int, body: str = "") -> None:
        self.service = service
        self.status = status
        self.body = body[:512]
        self.code: UpstreamCode = {
            400: UpstreamCode.BAD_REQUEST,
            403: UpstreamCode.FORBIDDEN,
            404: UpstreamCode.NOT_FOUND,
            409: UpstreamCode.CONFLICT,
        }.get(status, UpstreamCode.UNKNOWN)
        super().__init__(f"{self.code}: {self.service} returned HTTP {status}")


class UpstreamTimeout(UpstreamError):
    def __init__(self, service: str, detail: str = "") -> None:
        super().__init__(service, 504, detail)
        self.code = UpstreamCode.TIMEOUT


class UpstreamUnavailable(UpstreamError):
    def __init__(self, service: str, status: int = 503) -> None:
        super().__init__(service, status)
        self.code = UpstreamCode.UNAVAILABLE
