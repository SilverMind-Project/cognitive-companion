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
        provided. Returns a draft-only dict with keys ``draft_matrix``,
        ``suggested_points``, ``confidence``, ``inlier_count``,
        ``sample_count``, ``fov_deg``, ``method``, and optionally ``warning``.
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
        *,
        floor_plan_id: str,
        image_width: int,
        image_height: int,
        max_residual_m: float,
        mean_residual_m: float,
        quality_status: str,
        quality_point_count: int,
    ) -> dict:
        r = await self._request(
            "POST",
            "/internal/calibration/homography",
            json={
                "camera_id": camera_id,
                "matrix": matrix,
                "points": points,
                "meta": meta or {},
                "floor_plan_id": floor_plan_id,
                "image_width": image_width,
                "image_height": image_height,
                "max_residual_m": max_residual_m,
                "mean_residual_m": mean_residual_m,
                "quality_status": quality_status,
                "quality_point_count": quality_point_count,
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

    async def post_projection_ack(
        self,
        *,
        revision_id: str,
        consumer: str = "cc",
        schema_version: str = "1",
        status: str = "acked",
        counts: dict[str, int] | None = None,
    ) -> None:
        """Acknowledge that this consumer applied an identity revision.

        CTS marks the revision job complete only after every required projection
        acknowledges the same ``revision_id`` (M06). A ``failed`` status flips the
        job to ``failed`` so it can be retried idempotently.
        """
        await self._request(
            "POST",
            "/internal/projection-acks",
            json={
                "revision_id": revision_id,
                "consumer": consumer,
                "schema_version": schema_version,
                "status": status,
                "counts": counts or {},
            },
        )

    async def get_identities(self, *, active_only: bool = True) -> list[dict]:
        """Fetch all named identities from the ReID gallery."""
        r = await self._request(
            "GET",
            "/internal/identities",
            params={"active_only": str(active_only).lower()},
        )
        return r.json().get("identities", [])

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

    async def list_room_dwells(
        self,
        *,
        ph_id: str,
        start: str,
        end: str,
    ) -> dict:
        """Return one PH's room dwells within an explicit ISO-8601 UTC range.

        Backs the identity-continuity M05 backfill projector: fetches the
        CTS room-dwell history for an ``inferred_backfill`` revision's range
        so it can be projected into ``PersonLocationService`` as closed
        presence segments. Returns the raw envelope ``{"dwells": [...]}``;
        the caller validates shape before use (BFF fail-closed rule).
        """
        r = await self._request(
            "GET",
            "/internal/trajectory/dwells",
            params={"ph_id": ph_id, "start": start, "end": end},
        )
        return r.json()

    async def list_recent_trajectory(
        self,
        *,
        identity_id: str | None = None,
        ph_id: str | None = None,
        since: str | None = None,
        limit: int = 200,
    ) -> dict:
        params: dict = {"limit": limit}
        if identity_id:
            params["identity_id"] = identity_id
        if ph_id:
            params["ph_id"] = ph_id
        if since:
            params["since"] = since
        r = await self._request("GET", "/internal/trajectory/recent", params=params)
        return r.json()

    async def list_gait_daily(
        self,
        identity_id: str,
        *,
        since: str | None = None,
        until: str | None = None,
    ) -> list[dict]:
        """Return gait daily aggregate rows for one resident."""
        params: dict[str, str] = {"identity_id": identity_id}
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        r = await self._request("GET", "/internal/gait/daily", params=params)
        return r.json()

    async def check_drift(
        self,
        camera_id: str,
        reference_key: str,
        current_key: str,
    ) -> dict:
        """Run the drift score for a camera against its stored reference frame.

        Returns a dict with keys ``camera_id``, ``inlier_ratio``, ``ssim``,
        ``drifted``, and ``reason``.
        """
        r = await self._request(
            "POST",
            f"/internal/calibration/drift/{camera_id}",
            json={"reference_key": reference_key, "current_key": current_key},
        )
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
        ph_id: str | None = None,
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
        if ph_id:
            params["ph_id"] = ph_id
        if strategy:
            params["strategy"] = strategy
        r = await self._request("GET", "/internal/keyframes", params=params)
        return r.json().get("keyframes", [])

    async def list_keyframe_frames(self, params: dict[str, str]) -> dict:
        """List keyframes grouped into physical-frame cards (M07).

        Returns the orchestrator's grouped envelope ``{"frames": [...],
        "total": int, "limit": int, "offset": int}`` from
        ``/internal/keyframes/grouped``. The BFF validates this shape and
        derives the card summary; it does not re-query.
        """
        r = await self._request("GET", "/internal/keyframes/grouped", params=params)
        return r.json()

    async def get_keyframe(self, sample_id: str) -> dict:
        """Get a single tagged keyframe by sample ID."""
        r = await self._request("GET", f"/internal/keyframes/{sample_id}")
        return r.json()

    async def retain_keyframe(self, sample_id: str) -> dict:
        """Retain a keyframe past the normal retention window."""
        r = await self._request("POST", f"/internal/keyframes/{sample_id}/retain")
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

    async def tag_bbox_annotation(
        self,
        *,
        annotation_id: str,
        identity_id: str | None,
        tagged_by: str,
    ) -> dict:
        """Set or clear the identity_id on a single bbox annotation."""
        r = await self._request(
            "PUT",
            f"/internal/bboxes/{annotation_id}/tag",
            json={"identity_id": identity_id, "tagged_by": tagged_by},
        )
        return r.json()

    async def delete_bbox_annotation(self, *, annotation_id: str) -> None:
        """Delete a single bbox annotation."""
        await self._request(
            "DELETE",
            f"/internal/bboxes/{annotation_id}",
        )

    async def apply_bbox_batch(self, keyframe_id: str, operations: list[dict]) -> dict:
        """Apply a batch of bbox create/update/delete operations atomically."""
        r = await self._request(
            "POST",
            "/internal/bboxes/batch",
            json={"keyframe_id": keyframe_id, "operations": operations},
        )
        return r.json()

    # -- N2: Person Hypothesis methods ----------------------------------------

    async def list_phs(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        room_id: str | None = None,
        identity_id: str | None = None,
        state: str | None = None,
        include_transient: bool = False,
        min_duration_s: float | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        params: dict[str, str] = {"limit": str(limit), "offset": str(offset)}
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        if room_id:
            params["room_id"] = room_id
        if identity_id:
            params["identity_id"] = identity_id
        if state:
            params["state"] = state
        if include_transient:
            params["include_transient"] = "true"
        if min_duration_s is not None:
            params["min_duration_s"] = str(min_duration_s)
        if search:
            params["search"] = search
        r = await self._request("GET", "/ph", params=params)
        return r.json()

    async def get_ph(self, ph_id: str) -> dict:
        r = await self._request("GET", f"/ph/{ph_id}")
        return r.json()

    async def list_ph_observations(self, ph_id: str, *, limit: int = 200) -> dict:
        r = await self._request("GET", f"/ph/{ph_id}/observations", params={"limit": str(limit)})
        return r.json()

    async def list_ph_keyframes(self, ph_id: str, *, limit: int = 24) -> dict:
        r = await self._request("GET", f"/ph/{ph_id}/keyframes", params={"limit": str(limit)})
        return r.json()

    async def get_ph_trail(self, ph_id: str, *, since: str | None = None) -> dict:
        params: dict[str, str] = {}
        if since:
            params["since"] = since
        r = await self._request("GET", f"/ph/{ph_id}/trail", params=params)
        return r.json()

    async def get_ph_co_present(self, ph_id: str, *, radius_m: float = 5.0) -> dict:
        r = await self._request(
            "GET", f"/ph/{ph_id}/co_present", params={"radius_m": str(radius_m)}
        )
        return r.json()

    async def correct_ph_identity(
        self,
        ph_id: str,
        *,
        new_identity_id: str | None,
        reason: str = "manual",
        actor: str = "system",
        idempotency_key: str | None = None,
    ) -> dict:
        headers: dict[str, str] = {"X-Actor-Subject": actor}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        r = await self._request(
            "POST",
            f"/ph/{ph_id}/correct",
            json={"new_identity_id": new_identity_id, "reason": reason},
            headers=headers,
        )
        return r.json()

    async def merge_phs(
        self,
        *,
        source_ph_id: str,
        target_ph_id: str,
        reason: str = "manual",
        actor: str = "system",
        idempotency_key: str | None = None,
    ) -> dict:
        headers: dict[str, str] = {"X-Actor-Subject": actor}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        r = await self._request(
            "POST",
            "/ph/merge",
            json={"source_ph_id": source_ph_id, "target_ph_id": target_ph_id, "reason": reason},
            headers=headers,
        )
        return r.json()

    async def batch_merge_phs(
        self,
        *,
        source_ph_ids: list[str],
        target_ph_id: str,
        reason: str = "manual_bulk_merge",
        actor: str = "system",
        idempotency_key: str | None = None,
    ) -> dict:
        headers: dict[str, str] = {"X-Actor-Subject": actor}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        r = await self._request(
            "POST",
            "/ph/batch_merge",
            json={
                "source_ph_ids": source_ph_ids,
                "target_ph_id": target_ph_id,
                "reason": reason,
            },
            headers=headers,
        )
        return r.json()

    async def split_ph(
        self,
        ph_id: str,
        *,
        at_observation_id: str,
        reason: str = "manual",
        actor: str = "system",
        idempotency_key: str | None = None,
    ) -> dict:
        headers: dict[str, str] = {"X-Actor-Subject": actor}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        r = await self._request(
            "POST",
            f"/ph/{ph_id}/split",
            json={"at_observation_id": at_observation_id, "reason": reason},
            headers=headers,
        )
        return r.json()

    async def batch_correct_phs(
        self,
        *,
        corrections: list[dict],
        actor: str = "system",
        idempotency_key: str | None = None,
    ) -> dict:
        headers: dict[str, str] = {"X-Actor-Subject": actor}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        r = await self._request(
            "POST",
            "/ph/batch_correct",
            json={"corrections": corrections},
            headers=headers,
        )
        return r.json()

    async def batch_delete_phs(
        self,
        *,
        ph_ids: list[str],
        reason: str = "manual_delete",
        actor: str = "system",
        idempotency_key: str | None = None,
    ) -> dict:
        headers: dict[str, str] = {"X-Actor-Subject": actor}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        r = await self._request(
            "POST",
            "/ph/batch_delete",
            json={"ph_ids": ph_ids, "reason": reason},
            headers=headers,
        )
        return r.json()

    async def purge_unknown_phs(
        self,
        *,
        older_than_days: int,
        limit: int = 1000,
        actor: str = "system",
        idempotency_key: str | None = None,
    ) -> dict:
        headers: dict[str, str] = {"X-Actor-Subject": actor}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        r = await self._request(
            "POST",
            "/ph/purge_unknown",
            json={"older_than_days": older_than_days, "limit": limit},
            headers=headers,
        )
        return r.json()

    async def list_ph_revisions(
        self,
        *,
        ph_id: str | None = None,
        kind: str | None = None,
        limit: int = 50,
        before_id: str | None = None,
    ) -> dict:
        params: dict[str, str] = {"limit": str(limit)}
        if ph_id:
            params["ph_id"] = ph_id
        if kind:
            params["kind"] = kind
        if before_id:
            params["before_id"] = before_id
        r = await self._request("GET", "/ph/revisions", params=params)
        return r.json()

    # -- M08 segment correction (propose / apply / compensate / job) ----------

    async def propose_segment(
        self,
        *,
        ph_id: str,
        observation_id: str | None = None,
        at: str | None = None,
    ) -> dict:
        body: dict[str, object] = {"ph_id": ph_id}
        if observation_id is not None:
            body["observation_id"] = observation_id
        if at is not None:
            body["at"] = at
        r = await self._request("POST", "/internal/corrections/propose", json=body)
        return r.json()

    async def apply_segment_correction(self, *, payload: dict) -> dict:
        r = await self._request("POST", "/internal/corrections/apply", json=payload)
        return r.json()

    async def compensate_correction(self, *, correction_id: str, actor: str) -> dict:
        r = await self._request(
            "POST",
            f"/internal/corrections/{correction_id}/compensate",
            json={"actor": actor},
        )
        return r.json()

    async def get_correction_job(self, *, revision_id: str) -> dict:
        r = await self._request("GET", f"/internal/corrections/jobs/{revision_id}")
        return r.json()

    # -- M09 ReID review queue ------------------------------------------------

    async def list_review_candidates(self, params: dict[str, str]) -> dict:
        r = await self._request("GET", "/internal/reid-review/candidates", params=params)
        return r.json()

    async def get_review_candidate(self, candidate_id: str) -> dict:
        r = await self._request("GET", f"/internal/reid-review/candidates/{candidate_id}")
        return r.json()

    async def list_review_events(self, candidate_id: str) -> dict:
        r = await self._request("GET", f"/internal/reid-review/candidates/{candidate_id}/events")
        return r.json()

    async def get_review_counts(self) -> dict:
        r = await self._request("GET", "/internal/reid-review/counts")
        return r.json()

    async def approve_review_candidate(self, candidate_id: str, *, payload: dict) -> dict:
        r = await self._request(
            "POST",
            f"/internal/reid-review/candidates/{candidate_id}/approve",
            json=payload,
        )
        return r.json()

    async def relabel_review_candidate(self, candidate_id: str, *, payload: dict) -> dict:
        r = await self._request(
            "POST",
            f"/internal/reid-review/candidates/{candidate_id}/relabel",
            json=payload,
        )
        return r.json()

    async def reject_review_candidate(self, candidate_id: str, *, payload: dict) -> dict:
        r = await self._request(
            "POST",
            f"/internal/reid-review/candidates/{candidate_id}/reject",
            json=payload,
        )
        return r.json()

    async def demote_review_candidate(self, candidate_id: str, *, payload: dict) -> dict:
        r = await self._request(
            "POST",
            f"/internal/reid-review/candidates/{candidate_id}/demote",
            json=payload,
        )
        return r.json()

    async def reject_review_batch(self, *, payload: dict) -> dict:
        r = await self._request("POST", "/internal/reid-review/reject-batch", json=payload)
        return r.json()

    async def compensate_review_candidate(self, candidate_id: str, *, actor: str) -> dict:
        r = await self._request(
            "POST",
            f"/internal/reid-review/candidates/{candidate_id}/compensate",
            json={"actor": actor},
        )
        return r.json()

    async def add_gallery_crop(self, *, payload: dict) -> dict:
        await self._request(
            "POST",
            "/internal/gallery/add_crop",
            content=payload["crop_bytes"],
            headers={
                "X-Identity-Id": payload["identity_id"],
                "Content-Type": "image/jpeg",
            },
        )
        return {}
