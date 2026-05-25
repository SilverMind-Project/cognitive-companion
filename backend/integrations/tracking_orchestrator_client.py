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

    async def fit_homography(
        self,
        camera_id: str,
        points: list[dict],
    ) -> dict:
        """Compute a homography from raw pixel↔floor-metre correspondences.

        The orchestrator runs ``cv2.findHomography`` server-side and stores the
        result in its in-memory calibration state.  Returns a dict with keys
        ``matrix``, ``residuals_m``, ``max_residual_m``, and ``status``.

        Raises :class:`UpstreamError` (HTTP 400) when residuals exceed the
        0.5 m threshold, propagated as a FastAPI 400 to the UI.
        """
        r = await self._request(
            "POST",
            "/internal/calibration/homography/fit",
            json={"camera_id": camera_id, "points": points},
        )
        return r.json()

    async def auto_calibrate(
        self,
        camera_id: str,
        fov_deg: float = 70.0,
        minio_key: str | None = None,
        snapshot_bytes: str | None = None,
    ) -> dict:
        """Run depth-based automatic homography estimation on a camera frame.

        Exactly one of *minio_key* or *snapshot_bytes* (base64 JPEG) must be
        provided.  Returns a dict with keys ``matrix``, ``confidence``,
        ``inlier_count``, ``sample_count``, ``fov_deg``, ``method``, and
        optionally ``warning``.
        """
        payload: dict = {"fov_deg": fov_deg}
        if minio_key is not None:
            payload["minio_key"] = minio_key
        if snapshot_bytes is not None:
            payload["snapshot_bytes"] = snapshot_bytes
        r = await self._request(
            "POST",
            f"/internal/calibration/auto/{camera_id}",
            json=payload,
        )
        return r.json()

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

    async def manual_identity_override(
        self,
        *,
        global_track_id: str,
        new_identity_id: str | None,
        actor: str,
        reason: str = "manual",
        display_name: str | None = None,
        evidence: dict | None = None,
    ) -> dict:
        """Apply a caregiver-authored identity override for ``global_track_id``.

        Thin typed wrapper over :meth:`post_manual_correction`. The orchestrator
        synthesizes an ``IdentityRevision`` from the override and publishes it
        on the ``tracking.revisions`` stream; the CC subscriber picks it up
        and rewrites the local history.
        """
        body: dict = {
            "global_track_id": global_track_id,
            "new_identity_id": new_identity_id,
            "actor": actor,
            "reason": reason,
            "evidence": evidence or {},
        }
        if display_name is not None:
            body["display_name"] = display_name
        return await self.post_manual_correction(body)

    async def get_identities(self, *, active_only: bool = True) -> list[dict]:
        """Fetch all named identities from the ReID gallery."""
        r = await self._request(
            "GET",
            "/internal/identities",
            params={"active_only": str(active_only).lower()},
        )
        return r.json().get("identities", [])

    async def get_global_tracks(
        self,
        *,
        open_only: bool = True,
        since: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        camera_id: str | None = None,
        identity_id: str | None = None,
        status: str | None = None,
        search: str | None = None,
        min_duration_s: float | None = None,
    ) -> dict:
        params: dict[str, str] = {"open_only": str(open_only).lower()}
        if since:
            params["since"] = since
        if limit is not None:
            params["limit"] = str(limit)
        if offset is not None:
            params["offset"] = str(offset)
        if camera_id:
            params["camera_id"] = camera_id
        if identity_id:
            params["identity_id"] = identity_id
        if status:
            params["status"] = status
        if search:
            params["search"] = search
        if min_duration_s is not None:
            params["min_duration_s"] = str(min_duration_s)
        r = await self._request("GET", "/internal/global_tracks", params=params)
        data = r.json()
        tracks = data.get("tracks", [])
        return {
            "tracks": tracks,
            "count": int(data.get("count", len(tracks))),
            "limit": data.get("limit"),
            "offset": data.get("offset"),
        }

    async def get_global_track(self, track_id: str) -> dict:
        r = await self._request("GET", f"/internal/global_tracks/{track_id}")
        return r.json()

    async def get_health(self) -> dict:
        r = await self._request("GET", "/internal/health")
        return r.json()

    async def get_feature_flags(self) -> dict:
        r = await self._request("GET", "/internal/features")
        return r.json()

    async def get_homography(self, camera_id: str) -> dict:
        """Return the stored homography matrix + points for a camera."""
        r = await self._request("GET", f"/internal/calibration/homography/{camera_id}")
        return r.json()

    async def list_recent_trajectory(
        self,
        *,
        identity_id: str | None = None,
        global_track_id: str | None = None,
        since: str | None = None,
        limit: int = 200,
    ) -> dict:
        params: dict = {"limit": limit}
        if identity_id:
            params["identity_id"] = identity_id
        if global_track_id:
            params["global_track_id"] = global_track_id
        if since:
            params["since"] = since
        r = await self._request("GET", "/internal/trajectory/recent", params=params)
        return r.json()

    async def calibration_status(self) -> dict:
        r = await self._request("GET", "/internal/calibration/status")
        return r.json()

    # -- Keyframe methods (M8) -----------------------------------------------

    async def enroll_from_tracklet(
        self,
        *,
        identity_id: str,
        tracklet_id: str,
        display_name: str | None = None,
    ) -> dict:
        """Enroll a tracklet's embeddings under a named identity in the ReID gallery.

        Proxies ``POST /internal/gallery/enroll`` on the orchestrator.  Returns
        the enrollment response dict (``identity_id``, ``enrolled_count``,
        ``enrolled_at``).

        Raises :class:`UpstreamError` (propagated as HTTP 502) when the
        orchestrator returns an error (e.g., 404 when the tracklet has no
        gallery embeddings yet).
        """
        body: dict = {
            "identity_id": identity_id,
            "tracklet_id": tracklet_id,
        }
        if display_name is not None:
            body["display_name"] = display_name
        r = await self._request("POST", "/internal/gallery/enroll", json=body)
        return r.json()

    async def list_keyframes(
        self,
        person_id: str | None = None,
        signal_type: str | None = None,
        after: str | None = None,
        limit: int = 100,
        global_track_id: str | None = None,
        strategy: str | None = None,
    ) -> list[dict]:
        """List tagged keyframes, optionally filtered by person, signal, or track."""
        params: dict[str, str] = {"limit": str(limit)}
        if person_id:
            params["person_id"] = person_id
        if signal_type:
            params["signal_type"] = signal_type
        if after:
            params["after"] = after
        if global_track_id:
            params["global_track_id"] = global_track_id
        if strategy:
            params["strategy"] = strategy
        r = await self._request("GET", "/internal/keyframes", params=params)
        return r.json().get("keyframes", [])

    async def get_keyframe(self, sample_id: str) -> dict:
        """Get a single tagged keyframe by sample ID."""
        r = await self._request("GET", f"/internal/keyframes/{sample_id}")
        return r.json()

    async def retain_keyframe(self, sample_id: str) -> dict:
        """Retain a keyframe past the normal retention window."""
        r = await self._request("POST", f"/internal/keyframes/{sample_id}/retain")
        return r.json()

    async def unmerge_tracklet(
        self,
        *,
        tracklet_id: str,
        requested_by: str = "caregiver",
    ) -> dict:
        """Detach a tracklet from its current global track.

        Proxies ``POST /internal/corrections/unmerge_tracklet`` on the
        orchestrator.  Returns a dict with ``tracklet_id``,
        ``original_global_track_id``, and ``new_global_track_id``.
        """
        r = await self._request(
            "POST",
            "/internal/corrections/unmerge_tracklet",
            json={"tracklet_id": tracklet_id, "requested_by": requested_by},
        )
        return r.json()

    async def merge_global_tracks(
        self,
        *,
        source_id: str,
        target_id: str,
        merged_by: str,
    ) -> dict:
        """Merge source global track into target.

        Proxies ``POST /internal/corrections/merge_global_tracks`` on the
        orchestrator.  Returns a dict with ``source_id``, ``target_id``,
        and ``merged_at``.
        """
        r = await self._request(
            "POST",
            "/internal/corrections/merge_global_tracks",
            json={
                "source_id": source_id,
                "target_id": target_id,
                "merged_by": merged_by,
            },
            timeout=30.0,
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

    # -- Bbox annotation methods -----------------------------------------------

    async def get_keyframe_bboxes(self, keyframe_id: str) -> list[dict]:
        """Return YOLO bounding-box annotations for a tagged keyframe."""
        r = await self._request("GET", f"/internal/keyframes/{keyframe_id}/bboxes")
        return r.json().get("bboxes", [])

    async def override_bbox(
        self,
        *,
        annotation_id: str,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        override_by: str,
    ) -> dict:
        """Persist a user-drawn bounding-box override."""
        r = await self._request(
            "PUT",
            f"/internal/bboxes/{annotation_id}/override",
            json={
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "override_by": override_by,
            },
        )
        return r.json()
