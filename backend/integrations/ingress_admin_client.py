"""Gateway client for the rtsp-ingress internal admin API.

All CC modules that need to reach rtsp-ingress MUST go through this class.
No other module may import ``httpx`` for upstream calls.
"""

from __future__ import annotations

from backend.integrations._upstream_base import UpstreamClient


class IngressAdminClient(UpstreamClient):
    """BFF client for the rtsp-ingress service."""

    SERVICE_NAME = "rtsp_ingress"
    AUDIENCE = "rtsp-ingress"

    async def list_streams(self) -> list[dict]:
        r = await self._request("GET", "/internal/streams")
        return r.json().get("streams", [])

    async def test_connection(self, *, rtsp_url: str) -> dict:
        r = await self._request("POST", "/internal/test-connection", json={"rtsp_url": rtsp_url})
        return r.json()

    async def reload_camera(self, *, camera_id: str) -> None:
        await self._request("POST", f"/internal/streams/{camera_id}/reload")

    async def stream_health(self, *, camera_id: str) -> dict:
        r = await self._request("GET", f"/internal/streams/{camera_id}/health")
        return r.json()

    async def snapshot(self, *, camera_id: str) -> bytes:
        r = await self._request("GET", f"/internal/streams/{camera_id}/snapshot")
        return r.content
