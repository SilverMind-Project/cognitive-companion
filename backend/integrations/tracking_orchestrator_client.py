"""Gateway client for the tracking-orchestrator internal API.

All CC modules that need to reach tracking-orchestrator MUST go through this
class.  No other module may import ``httpx`` for upstream calls.
"""

from __future__ import annotations

from backend.integrations._upstream_base import UpstreamClient


class OrchestratorClient(UpstreamClient):
    """BFF client for the tracking-orchestrator service."""

    SERVICE_NAME = "tracking_orchestrator"
    AUDIENCE = "tracking-orchestrator"

    async def post_homography(
        self,
        camera_id: str,
        matrix: list[list[float]],
        points: list[dict],
        meta: dict | None = None,
    ) -> dict:
        r = await self._request(
            "POST",
            "/internal/calibration/homography",
            json={
                "camera_id": camera_id,
                "matrix": matrix,
                "points": points,
                "meta": meta or {},
            },
        )
        return r.json() if r.content else {}

    async def post_privacy_zones(self, camera_id: str, zones: list[dict]) -> None:
        await self._request(
            "POST",
            "/internal/calibration/privacy_zones",
            json={"camera_id": camera_id, "zones": zones},
        )

    async def post_adjacency(self, edges: list[dict]) -> None:
        await self._request(
            "POST",
            "/internal/calibration/camera_adjacency",
            json={"edges": edges},
        )

    async def post_reload(self) -> None:
        await self._request("POST", "/internal/calibration/reload")

    async def post_manual_correction(self, body: dict) -> dict:
        r = await self._request("POST", "/internal/corrections", json=body)
        return r.json()

    async def get_global_tracks(self, *, open_only: bool = True) -> list[dict]:
        r = await self._request(
            "GET",
            "/internal/global_tracks",
            params={"open_only": str(open_only).lower()},
        )
        return r.json().get("tracks", [])

    async def get_global_track(self, track_id: str) -> dict:
        r = await self._request("GET", f"/internal/global_tracks/{track_id}")
        return r.json()

    async def get_health(self) -> dict:
        r = await self._request("GET", "/internal/health")
        return r.json()

    async def get_feature_flags(self) -> dict:
        r = await self._request("GET", "/internal/features")
        return r.json()

    async def calibration_status(self) -> dict:
        r = await self._request("GET", "/internal/calibration/status")
        return r.json()
