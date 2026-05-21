"""Service layer for bounding-box annotations — proxies to the
tracking-orchestrator internal API rather than querying the CTS database
directly (CC and CTS use separate databases).
"""

from __future__ import annotations

from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.schemas.cts_bbox import BboxAnnotationResponse, BboxOverrideRequest


class BboxAnnotationService:
    def __init__(self, client: OrchestratorClient) -> None:
        self._client = client

    async def get_for_keyframe(self, keyframe_id: str) -> list[BboxAnnotationResponse]:
        bboxes = await self._client.get_keyframe_bboxes(keyframe_id)
        return [_dict_to_response(b) for b in bboxes]

    async def save_override(
        self,
        annotation_id: str,
        body: BboxOverrideRequest,
        override_by: str,
    ) -> BboxAnnotationResponse:
        """Persist a user-drawn bbox override via the orchestrator.

        The orchestrator returns the full updated annotation on success.
        Raises ``UpstreamError`` (HTTP 502) when the orchestrator returns
        an error (e.g., 404 when the annotation does not exist).
        """
        result = await self._client.override_bbox(
            annotation_id=annotation_id,
            x1=body.x1,
            y1=body.y1,
            x2=body.x2,
            y2=body.y2,
            override_by=override_by,
        )
        return _dict_to_response(result)


def _dict_to_response(d: dict) -> BboxAnnotationResponse:
    return BboxAnnotationResponse(
        id=d["id"],
        keyframe_id=d["keyframe_id"],
        tracklet_id=d["tracklet_id"],
        camera_id=d["camera_id"],
        x1=float(d["x1"]),
        y1=float(d["y1"]),
        x2=float(d["x2"]),
        y2=float(d["y2"]),
        detection_confidence=float(d["detection_confidence"]),
        frame_width=int(d["frame_width"]),
        frame_height=int(d["frame_height"]),
        identity_id=d.get("identity_id"),
        created_at=d["created_at"],
        override_x1=d.get("override_x1"),
        override_y1=d.get("override_y1"),
        override_x2=d.get("override_x2"),
        override_y2=d.get("override_y2"),
        override_by=d.get("override_by"),
        override_at=d.get("override_at"),
    )
