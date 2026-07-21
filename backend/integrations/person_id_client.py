"""HTTP client for the Person Identification Service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

import httpx

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)

VisitorClusterStatus = Literal["candidate", "surfaced", "named", "dismissed"]


class PersonIDUpstreamError(Exception):
    """The person-identification service rejected or failed a visitor request.

    Unlike the rest of this client (which returns ``None``/``[]`` on any
    failure -- an acceptable degrade for optional face-recognition reads), the
    visitor admin surface (identity-continuity M07) needs to distinguish a
    genuine 404/409/400 domain response (cluster not found, clustering
    disabled, bad slug) from a transport failure, so the BFF can render each
    distinctly instead of collapsing everything to one generic error. Callers
    map this to a BFF-facing status: upstream 5xx and transport failures
    become 502/504, upstream 4xx statuses pass through unchanged.
    """

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(f"{status}: {message}")


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class FaceResult:
    person_id: str
    name: str
    confidence: float
    bbox: list[float]
    # Rich face evidence: three-valued recognition state from person-identification-service.
    # "recognized" (strong positive), "candidate" (grey zone), "unrecognized".
    recognition_state: str = "recognized"
    # Rich face evidence: nearest centroid person_id, set even when similarity is below threshold.
    best_candidate_id: str | None = None
    # Rich face evidence: raw cosine similarity to the best candidate centroid.
    similarity: float = 0.0
    # Rich face evidence: head pose yaw in degrees (primary frontality axis).
    yaw_deg: float = 0.0
    # Rich face evidence: head pose pitch in degrees.
    pitch_deg: float = 0.0
    # Rich face evidence: head pose roll in degrees.
    roll_deg: float = 0.0
    # Rich face evidence: SCRFD face detection confidence score.
    det_score: float = 0.0


@dataclass
class MotionResult:
    person_id: str
    name: str
    direction: str
    confidence: float


@dataclass
class BatchIdentifyResult:
    frames: list[list[FaceResult]]  # per-frame face detections
    motion: list[MotionResult]
    annotated_images: list[str] | None = None  # base64-encoded annotated frames


@dataclass
class IdentifyResult:
    faces: list[FaceResult]
    annotated_image: str | None = None


@dataclass
class EnrollResult:
    person_id: str
    name: str
    embedding_count: int
    status: str  # "enrolled" | "updated"
    failed_images: list[int] = field(default_factory=list)


@dataclass
class MemberInfo:
    person_id: str
    name: str
    embedding_count: int
    created_at: datetime


@dataclass
class TrajectoryPoint:
    cx: float
    cy: float
    width: float
    height: float


@dataclass
class PersonTrack:
    track_id: int
    person_id: str
    name: str
    direction: str
    confidence: float
    trajectory: list[TrajectoryPoint]


@dataclass
class MotionDetectionResult:
    persons: list[PersonTrack]


@dataclass
class VisitorSightingInfo:
    seen_at: datetime
    quality: float
    crop_object: str | None = None


@dataclass
class VisitorClusterSummary:
    cluster_id: str
    status: VisitorClusterStatus
    display_hint: str | None
    named_person_id: str | None
    sighting_count: int
    distinct_days: int
    first_seen_at: datetime
    last_seen_at: datetime
    recent_crop_keys: list[str] = field(default_factory=list)


@dataclass
class VisitorClusterDetail(VisitorClusterSummary):
    recent_sightings: list[VisitorSightingInfo] = field(default_factory=list)


@dataclass
class VisitorClusterListResult:
    clusters: list[VisitorClusterSummary]
    total: int


@dataclass
class VisitorNameResult:
    cluster_id: str
    status: VisitorClusterStatus
    named_person_id: str
    member_name: str
    embedding_count: int


def _extract_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:500] or f"HTTP {response.status_code}"
    detail = body.get("detail") if isinstance(body, dict) else None
    return str(detail) if detail else (response.text[:500] or f"HTTP {response.status_code}")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class PersonIDClient:
    """Async HTTP client for the standalone Person Identification Service."""

    def __init__(self) -> None:
        self.base_url: str = settings.as_str("person_id.url").rstrip("/")
        self.timeout: int = settings.as_int("person_id.timeout")
        self.enabled: bool = settings.as_bool("person_id.enabled")

    # -- Health ---------------------------------------------------------------

    async def health_check(self) -> dict | None:
        if not self.enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.base_url}/health")
                resp.raise_for_status()
                return resp.json()
        except Exception:
            logger.warning("person_id_health_check_failed")
            return None

    # -- Identification -------------------------------------------------------

    async def identify_batch(
        self,
        images: list[str],
        include_motion: bool = True,
        include_annotated_image: bool = False,
        save_guest_images: bool = False,
    ) -> BatchIdentifyResult | None:
        """Send a batch of base64 images to the person-id service.

        Args:
            images: List of base64-encoded images.
            include_motion: Whether to compute motion direction.
            include_annotated_image: Return annotated images with bounding boxes.
            save_guest_images: Save frames when unidentified guests are detected.

        Returns:
            BatchIdentifyResult or None if the service is unavailable.
        """
        if not self.enabled:
            return None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/api/v1/identify-batch",
                    json={
                        "images": images,
                        "include_motion": include_motion,
                        "include_annotated_image": include_annotated_image,
                        "save_guest_images": save_guest_images,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            logger.exception("person_id_identify_batch_failed")
            return None

        return self._parse_batch_result(data)

    async def identify_single(
        self,
        image: str,
        include_annotated_image: bool = False,
        save_guest_images: bool = False,
    ) -> IdentifyResult | None:
        """Identify faces in a single image.

        Args:
            image: Base64-encoded image.
            include_annotated_image: Return image with bounding boxes and labels.
            save_guest_images: Save image when unidentified guests are detected.

        Returns:
            IdentifyResult or None if the service is unavailable.
        """
        if not self.enabled:
            return None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/api/v1/identify",
                    json={
                        "image": image,
                        "include_annotated_image": include_annotated_image,
                        "save_guest_images": save_guest_images,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            logger.exception("person_id_identify_single_failed")
            return None

        faces = [
            FaceResult(
                person_id=f["person_id"],
                name=f["name"],
                confidence=f["confidence"],
                bbox=f["bbox"],
                recognition_state=f.get("recognition_state", "recognized"),
                best_candidate_id=f.get("best_candidate_id"),
                similarity=f.get("similarity", 0.0),
                yaw_deg=f.get("yaw_deg", 0.0),
                pitch_deg=f.get("pitch_deg", 0.0),
                roll_deg=f.get("roll_deg", 0.0),
                det_score=f.get("det_score", 0.0),
            )
            for f in data.get("faces", [])
        ]
        return IdentifyResult(
            faces=faces,
            annotated_image=data.get("annotated_image"),
        )

    # -- Enrollment -----------------------------------------------------------

    async def enroll(
        self,
        person_id: str,
        name: str,
        images: list[str],
    ) -> EnrollResult | None:
        """Enroll a household member with base64-encoded face images.

        Args:
            person_id: Unique identifier for the person.
            name: Display name.
            images: List of base64-encoded face images.

        Returns:
            EnrollResult or None if the service is unavailable.
        """
        if not self.enabled:
            return None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/api/v1/enroll",
                    json={
                        "person_id": person_id,
                        "name": name,
                        "images": images,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            logger.exception("person_id_enroll_failed")
            return None

        return EnrollResult(
            person_id=data["person_id"],
            name=data["name"],
            embedding_count=data["embedding_count"],
            status=data["status"],
            failed_images=data.get("failed_images", []),
        )

    # -- Members --------------------------------------------------------------

    async def get_members(self) -> list[MemberInfo]:
        """Fetch all enrolled members from the person-id service."""
        if not self.enabled:
            return []

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.base_url}/api/v1/members")
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            logger.exception("person_id_get_members_failed")
            return []

        return [
            MemberInfo(
                person_id=m["person_id"],
                name=m["name"],
                embedding_count=m["embedding_count"],
                created_at=datetime.fromisoformat(m["created_at"]),
            )
            for m in data.get("members", [])
        ]

    async def get_member(self, person_id: str) -> MemberInfo | None:
        """Fetch details of a specific enrolled member.

        Returns:
            MemberInfo or None if the member is not found or the service is unavailable.
        """
        if not self.enabled:
            return None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.base_url}/api/v1/members/{person_id}")
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            logger.exception("person_id_get_member_failed")
            return None
        except Exception:
            logger.exception("person_id_get_member_failed")
            return None

        return MemberInfo(
            person_id=data["person_id"],
            name=data["name"],
            embedding_count=data["embedding_count"],
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    async def delete_member(self, person_id: str) -> bool:
        """Remove an enrolled member and all their embeddings.

        Returns:
            True if deleted, False if not found or service unavailable.
        """
        if not self.enabled:
            return False

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.delete(f"{self.base_url}/api/v1/members/{person_id}")
                resp.raise_for_status()
                return resp.json().get("deleted", False)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return False
            logger.exception("person_id_delete_member_failed")
            return False
        except Exception:
            logger.exception("person_id_delete_member_failed")
            return False

    # -- Motion ---------------------------------------------------------------

    async def detect_motion(self, images: list[str]) -> MotionDetectionResult | None:
        """Standalone motion direction detection across a frame sequence.

        Args:
            images: Ordered list of base64-encoded images (minimum 2).

        Returns:
            MotionDetectionResult or None if the service is unavailable.
        """
        if not self.enabled:
            return None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/api/v1/detect-motion",
                    json={"images": images},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            logger.exception("person_id_detect_motion_failed")
            return None

        persons = [
            PersonTrack(
                track_id=p["track_id"],
                person_id=p["person_id"],
                name=p["name"],
                direction=p["direction"],
                confidence=p["confidence"],
                trajectory=[
                    TrajectoryPoint(cx=t["cx"], cy=t["cy"], width=t["width"], height=t["height"])
                    for t in p.get("trajectory", [])
                ],
            )
            for p in data.get("persons", [])
        ]
        return MotionDetectionResult(persons=persons)

    # -- Visitors (identity-continuity M06/M07) --------------------------------
    #
    # Unlike the rest of this client, these methods raise PersonIDUpstreamError
    # on failure instead of returning None. The visitor admin surface is a
    # caregiver-facing mutation surface (naming, dismissing, merging a visitor
    # cluster): the BFF must distinguish "cluster not found" (404) from
    # "clustering disabled" (409) from a transport failure (502/504), which a
    # blanket None return would collapse into one generic error.

    async def list_visitor_clusters(self, status: str | None = None) -> VisitorClusterListResult:
        params = {"status": status} if status else None
        data = await self._visitor_request("GET", "/api/v1/visitors/clusters", params=params)
        try:
            return VisitorClusterListResult(
                clusters=[self._parse_cluster_summary(c) for c in data["clusters"]],
                total=data["total"],
            )
        except (KeyError, TypeError) as exc:
            raise PersonIDUpstreamError(502, f"malformed cluster list envelope: {exc}") from exc

    async def get_visitor_cluster(self, cluster_id: str) -> VisitorClusterDetail:
        data = await self._visitor_request("GET", f"/api/v1/visitors/clusters/{cluster_id}")
        try:
            return self._parse_cluster_detail(data)
        except (KeyError, TypeError) as exc:
            raise PersonIDUpstreamError(502, f"malformed cluster detail envelope: {exc}") from exc

    async def name_visitor_cluster(
        self, cluster_id: str, person_id: str, name: str
    ) -> VisitorNameResult:
        data = await self._visitor_request(
            "POST",
            f"/api/v1/visitors/clusters/{cluster_id}/name",
            json={"person_id": person_id, "name": name},
        )
        try:
            return VisitorNameResult(
                cluster_id=data["cluster_id"],
                status=data["status"],
                named_person_id=data["named_person_id"],
                member_name=data["member_name"],
                embedding_count=data["embedding_count"],
            )
        except (KeyError, TypeError) as exc:
            raise PersonIDUpstreamError(502, f"malformed name response envelope: {exc}") from exc

    async def dismiss_visitor_cluster(self, cluster_id: str) -> None:
        await self._visitor_request("POST", f"/api/v1/visitors/clusters/{cluster_id}/dismiss")

    async def merge_visitor_clusters(
        self, cluster_a: str, cluster_b: str
    ) -> VisitorClusterSummary:
        data = await self._visitor_request(
            "POST", f"/api/v1/visitors/clusters/{cluster_a}/merge/{cluster_b}"
        )
        try:
            return self._parse_cluster_summary(data)
        except (KeyError, TypeError) as exc:
            raise PersonIDUpstreamError(502, f"malformed merge response envelope: {exc}") from exc

    @staticmethod
    def _cluster_fields(data: dict[str, Any]) -> dict[str, Any]:
        return {
            "cluster_id": data["cluster_id"],
            "status": data["status"],
            "display_hint": data.get("display_hint"),
            "named_person_id": data.get("named_person_id"),
            "sighting_count": data["sighting_count"],
            "distinct_days": data["distinct_days"],
            "first_seen_at": datetime.fromisoformat(data["first_seen_at"]),
            "last_seen_at": datetime.fromisoformat(data["last_seen_at"]),
            "recent_crop_keys": data.get("recent_crop_keys", []),
        }

    @classmethod
    def _parse_cluster_summary(cls, data: dict[str, Any]) -> VisitorClusterSummary:
        return VisitorClusterSummary(**cls._cluster_fields(data))

    @classmethod
    def _parse_cluster_detail(cls, data: dict[str, Any]) -> VisitorClusterDetail:
        return VisitorClusterDetail(
            **cls._cluster_fields(data),
            recent_sightings=[
                VisitorSightingInfo(
                    seen_at=datetime.fromisoformat(s["seen_at"]),
                    quality=s["quality"],
                    crop_object=s.get("crop_object"),
                )
                for s in data.get("recent_sightings", [])
            ],
        )

    async def _visitor_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        if not self.enabled:
            raise PersonIDUpstreamError(503, "Person identification service is disabled")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.request(
                    method, f"{self.base_url}{path}", params=params, json=json
                )
                resp.raise_for_status()
                return resp.json() if resp.content else None
        except httpx.HTTPStatusError as exc:
            detail = _extract_detail(exc.response)
            logger.warning(
                "person_id_visitor_request_failed",
                method=method,
                path=path,
                status=exc.response.status_code,
                detail=detail,
            )
            raise PersonIDUpstreamError(exc.response.status_code, detail) from exc
        except httpx.TimeoutException as exc:
            logger.warning("person_id_visitor_request_timeout", method=method, path=path)
            raise PersonIDUpstreamError(504, "Person identification service timed out") from exc
        except httpx.HTTPError as exc:
            logger.exception("person_id_visitor_request_error", method=method, path=path)
            raise PersonIDUpstreamError(
                502, "Person identification service is unreachable"
            ) from exc

    # -- Internal helpers -----------------------------------------------------

    def _parse_batch_result(self, data: dict) -> BatchIdentifyResult:
        frames: list[list[FaceResult]] = []
        for frame in data.get("frames", []):
            faces = [
                FaceResult(
                    person_id=f["person_id"],
                    name=f["name"],
                    confidence=f["confidence"],
                    bbox=f["bbox"],
                    recognition_state=f.get("recognition_state", "recognized"),
                    best_candidate_id=f.get("best_candidate_id"),
                    similarity=f.get("similarity", 0.0),
                    yaw_deg=f.get("yaw_deg", 0.0),
                    pitch_deg=f.get("pitch_deg", 0.0),
                    roll_deg=f.get("roll_deg", 0.0),
                    det_score=f.get("det_score", 0.0),
                )
                for f in frame.get("faces", [])
            ]
            frames.append(faces)

        motion = [
            MotionResult(
                person_id=m["person_id"],
                name=m["name"],
                direction=m["direction"],
                confidence=m["confidence"],
            )
            for m in data.get("motion", [])
        ]

        annotated_images = data.get("annotated_images")
        return BatchIdentifyResult(frames=frames, motion=motion, annotated_images=annotated_images)
