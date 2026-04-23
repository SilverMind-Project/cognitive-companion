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

    # -- Keyframe methods (M8) -----------------------------------------------

    async def list_keyframes(
        self,
        person_id: str | None = None,
        signal_type: str | None = None,
        after: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """List tagged keyframes, optionally filtered by person or signal."""
        params: dict[str, str] = {"limit": str(limit)}
        if person_id:
            params["person_id"] = person_id
        if signal_type:
            params["signal_type"] = signal_type
        if after:
            params["after"] = after
        r = await self._request("GET", "/internal/keyframes", params=params)
        return r.json().get("keyframes", [])

    async def get_keyframe(self, sample_id: str) -> dict:
        """Get a single tagged keyframe by sample ID."""
        r = await self._request("GET", f"/internal/keyframes/{sample_id}")
        return r.json()

    async def retain_keyframe(self, sample_id: str) -> dict:
        """Retain a keyframe past the normal retention window."""
        r = await self._request(
            "POST", f"/internal/keyframes/{sample_id}/retain"
        )
        return r.json()

    # -- Dashboard methods (M8) ----------------------------------------------

    async def get_dashboard_signals(
        self,
        person_id: str | None = None,
        window_hours: int = 24,
        signal_kind: str | None = None,
        limit: int = 200,
    ) -> dict:
        """Fetch recent dementia signals from the orchestrator dashboard."""
        params: dict[str, str] = {
            "window_hours": str(window_hours),
            "limit": str(limit),
        }
        if person_id:
            params["person_id"] = person_id
        if signal_kind:
            params["signal_kind"] = signal_kind
        r = await self._request("GET", "/internal/dashboard/signals", params=params)
        return r.json()

    async def get_dashboard_trajectory(
        self,
        person_id: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 500,
    ) -> dict:
        """Fetch trajectory points for floor-plan overlay."""
        params: dict[str, str] = {"person_id": person_id, "limit": str(limit)}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        r = await self._request("GET", "/internal/dashboard/trajectory", params=params)
        return r.json()

    async def get_dashboard_dwell_summary(
        self,
        person_id: str,
        date: str | None = None,
    ) -> dict:
        """Fetch room dwell aggregation for one day."""
        params: dict[str, str] = {"person_id": person_id}
        if date:
            params["date"] = date
        r = await self._request("GET", "/internal/dashboard/dwell_summary", params=params)
        return r.json()
