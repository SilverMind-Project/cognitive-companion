"""HTTP client for the Person Identification Service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import httpx

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class FaceResult:
    person_id: str
    name: str
    confidence: float
    bbox: list[float]


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


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class PersonIDClient:
    """Async HTTP client for the standalone Person Identification Service."""

    def __init__(self) -> None:
        self.base_url: str = (settings.get("person_id.url") or "http://localhost:8100").rstrip("/")
        self.timeout: int = settings.get("person_id.timeout", 30)
        self.enabled: bool = settings.get("person_id.enabled", False)

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
