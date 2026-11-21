"""HTTP client for the Person Identification Service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

import httpx

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)

VisitorClusterStatus = Literal["candidate", "surfaced", "named", "dismissed", "attributed"]
VisitorReviewVerdict = Literal["attribute", "dismiss"]


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
    bbox: list[float]
    # Rich face evidence: three-valued recognition state from person-identification-service.
    # "recognized" (strong positive), "candidate" (grey zone), "unrecognized".
    recognition_state: str = "recognized"
    # Rich face evidence: nearest centroid person_id, set even when similarity is below threshold.
    best_candidate_id: str | None = None
    # Rich face evidence: raw ArcFace cosine similarity to the best candidate centroid. This is the
    # face's only match score; the service's legacy "confidence" field is not read.
    raw_similarity: float = 0.0
    # Rich face evidence: head pose yaw in degrees (primary frontality axis).
    yaw_deg: float = 0.0
    # Rich face evidence: head pose pitch in degrees.
    pitch_deg: float = 0.0
    # Rich face evidence: head pose roll in degrees.
    roll_deg: float = 0.0
    # Rich face evidence: SCRFD face detection confidence score.
    det_score: float = 0.0
    # ArcFace calibration fields, forwarded so CC-side identification
    # (reCamera face sighting) can carry the same fail-closed calibration
    # contract as CTS's own face client. None/degraded means "not trustworthy",
    # never a raw-similarity fallback.
    calibrated_confidence: float | None = None
    calibration_status: str = "degraded_missing"
    calibration_artifact_version: str | None = None
    # Top-2 margin and gallery representation metadata.
    second_best_candidate_id: str | None = None
    second_best_similarity: float | None = None
    margin: float | None = None
    gallery_representation: str = "centroid"
    recognizer_version: str = ""


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
    gallery_revision: int = 1
    prototype_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class PrototypeInfo:
    prototype_id: str
    person_id: str
    pose_bin: str
    member_count: int
    source: str
    quality_score: float | None
    quality_version: str | None
    crop_object_key: str | None
    approved_by: str | None
    approved_at: datetime | None
    created_at: datetime | None


@dataclass(frozen=True)
class MemberPrototypesInfo:
    person_id: str
    gallery_revision: int
    prototypes: list[PrototypeInfo]
    counts_by_bin: dict[str, int]


@dataclass(frozen=True)
class PromoteCandidateResult:
    candidate_id: str
    person_id: str
    pose_bin: str
    embedding_id: int
    gallery_revision: int
    prototype_count: int
    counts_by_bin: dict[str, int]


@dataclass(frozen=True)
class RebuildPrototypesResult:
    person_id: str
    prototype_count: int
    counts_by_bin: dict[str, int]


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


CalibrationLabelState = Literal["unlabeled", "labeled", "rejected", "attested"]
CalibrationLabelKind = Literal["member", "not_enrolled", "not_a_face"]
AttestationAuditVerdict = Literal["correct", "wrong", "not_a_face"]
AttestationGrade = Literal["room", "trajectory"]


@dataclass
class CalibrationCandidateInfo:
    """A face capture awaiting or carrying an operator label (no embedding ever reaches CC)."""

    candidate_id: str
    captured_at: datetime
    camera_id: str
    crop_object_key: str
    quality_score: float
    quality_version: str
    interocular_px: float | None
    yaw_deg: float
    pitch_deg: float
    nearest_person_id: str | None
    nearest_similarity: float
    label_state: CalibrationLabelState
    label_kind: CalibrationLabelKind | None
    label_identity_id: str | None
    labeled_by: str | None
    labeled_at: datetime | None
    pose_bin: str = "frontal"
    promoted: bool = False
    promotion_eligible: bool = False
    promotion_ineligible_reason: str | None = None
    # Wearable attestation provenance and its audit; set only on attested captures.
    attestation_association_id: str | None = None
    attestation_grade: AttestationGrade | None = None
    audit_verdict: AttestationAuditVerdict | None = None
    audited_by: str | None = None
    audited_at: datetime | None = None


@dataclass(frozen=True)
class AttestationAuditSummaryInfo:
    """Audit of wearable-attested face labels; counts and the precision bound only."""

    attested: int
    audited: int
    correct: int
    wrong: int
    not_a_face: int
    precision_lower_bound: float | None
    min_audited: int
    min_precision_lower_bound: float
    meets_bar: bool


@dataclass
class CalibrationCandidatePage:
    candidates: list[CalibrationCandidateInfo]
    next_cursor: str | None


@dataclass
class CalibrationIdentityProgress:
    identity_id: str
    labeled_faces: int
    episodes: int
    target_labeled_faces: int


@dataclass
class CalibrationSummaryInfo:
    by_state: dict[str, int]
    by_label_kind: dict[str, int]
    by_quality_decile: dict[str, int]
    by_camera: dict[str, int]
    identities: list[CalibrationIdentityProgress]
    not_enrolled_episodes: int
    capture_enabled: bool
    promotable_by_identity_pose: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass
class CalibrationHealthInfo:
    """Calibration artifact state from person-id ``/health``; no crop, embedding, or score."""

    status: str
    # Identities the single-frame artifact was fitted for; None when no artifact is loaded.
    covered_identities: list[str] | None
    template_status: str
    recognizer_version: str = ""
    active_profile: str = ""
    licence: str = ""


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
    # Set for an attributed cluster: the enrolled member these faces belong to (never enrolled).
    attributed_person_id: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None


@dataclass
class VisitorClusterDetail(VisitorClusterSummary):
    recent_sightings: list[VisitorSightingInfo] = field(default_factory=list)


@dataclass(frozen=True)
class VisitorReviewItem:
    cluster_id: str
    ok: bool
    error_code: str | None


@dataclass(frozen=True)
class CalibrationLabelItem:
    candidate_id: str
    ok: bool
    error_code: str | None


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


def _raw_similarity(face: dict[str, Any]) -> float:
    """A face's raw cosine similarity; an older service sends only the "similarity" alias."""
    return float(face.get("raw_similarity", face.get("similarity", 0.0)))


def _recognizer_version(face: dict[str, Any]) -> str:
    """Decode recognizer_version with a one-release fallback to arcface_model_version."""
    return str(face.get("recognizer_version") or face.get("arcface_model_version") or "")


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
                bbox=f["bbox"],
                recognition_state=f.get("recognition_state", "recognized"),
                best_candidate_id=f.get("best_candidate_id"),
                raw_similarity=_raw_similarity(f),
                yaw_deg=f.get("yaw_deg", 0.0),
                pitch_deg=f.get("pitch_deg", 0.0),
                roll_deg=f.get("roll_deg", 0.0),
                det_score=f.get("det_score", 0.0),
                calibrated_confidence=f.get("calibrated_confidence"),
                calibration_status=f.get("calibration_status", "degraded_missing"),
                calibration_artifact_version=f.get("calibration_artifact_version"),
                second_best_candidate_id=f.get("second_best_candidate_id"),
                second_best_similarity=(
                    float(f["second_best_similarity"])
                    if f.get("second_best_similarity") is not None
                    else None
                ),
                margin=float(f["margin"]) if f.get("margin") is not None else None,
                gallery_representation=str(f.get("gallery_representation", "centroid")),
                recognizer_version=_recognizer_version(f),
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
        """Fetch all enrolled members; an empty list when the service is unavailable.

        For callers that must tell "nobody enrolled" from "service down", use
        :meth:`list_members`, which raises instead.
        """
        try:
            return await self.list_members()
        except PersonIDUpstreamError:
            logger.exception("person_id_get_members_failed")
            return []

    async def list_members(self) -> list[MemberInfo]:
        """Fetch all enrolled members, raising ``PersonIDUpstreamError`` on any failure."""
        data = await self._request_or_raise("GET", "/api/v1/members")
        try:
            return [
                MemberInfo(
                    person_id=m["person_id"],
                    name=m["name"],
                    embedding_count=m["embedding_count"],
                    created_at=datetime.fromisoformat(m["created_at"]),
                    gallery_revision=int(m.get("gallery_revision", 1)),
                    prototype_counts={
                        str(k): int(v) for k, v in (m.get("prototype_counts") or {}).items()
                    },
                )
                for m in data["members"]
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise PersonIDUpstreamError(502, f"malformed member list envelope: {exc}") from exc

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
            gallery_revision=int(data.get("gallery_revision", 1)),
            prototype_counts={
                str(k): int(v) for k, v in (data.get("prototype_counts") or {}).items()
            },
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

    # -- Visitors --------------------------------
    #
    # Unlike the rest of this client, these methods raise PersonIDUpstreamError
    # on failure instead of returning None. The visitor admin surface is a
    # caregiver-facing mutation surface (naming, dismissing, merging a visitor
    # cluster): the BFF must distinguish "cluster not found" (404) from
    # "clustering disabled" (409) from a transport failure (502/504), which a
    # blanket None return would collapse into one generic error.

    async def list_visitor_clusters(self, status: str | None = None) -> VisitorClusterListResult:
        params = {"status": status} if status else None
        data = await self._request_or_raise("GET", "/api/v1/visitors/clusters", params=params)
        try:
            return VisitorClusterListResult(
                clusters=[self._parse_cluster_summary(c) for c in data["clusters"]],
                total=data["total"],
            )
        except (KeyError, TypeError) as exc:
            raise PersonIDUpstreamError(502, f"malformed cluster list envelope: {exc}") from exc

    async def get_visitor_cluster(self, cluster_id: str) -> VisitorClusterDetail:
        data = await self._request_or_raise("GET", f"/api/v1/visitors/clusters/{cluster_id}")
        try:
            return self._parse_cluster_detail(data)
        except (KeyError, TypeError) as exc:
            raise PersonIDUpstreamError(502, f"malformed cluster detail envelope: {exc}") from exc

    async def name_visitor_cluster(
        self, cluster_id: str, person_id: str, name: str
    ) -> VisitorNameResult:
        data = await self._request_or_raise(
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

    async def review_visitor_clusters(
        self,
        cluster_ids: list[str],
        verdict: VisitorReviewVerdict,
        *,
        actor: str,
        person_id: str | None = None,
    ) -> list[VisitorReviewItem]:
        """Attribute clusters to an enrolled member, or dismiss them. Never enrolls anything."""
        body: dict[str, Any] = {"cluster_ids": cluster_ids, "verdict": verdict, "actor": actor}
        if person_id is not None:
            body["person_id"] = person_id
        data = await self._request_or_raise("POST", "/api/v1/visitors/clusters/review", json=body)
        try:
            return [
                VisitorReviewItem(
                    cluster_id=str(r["cluster_id"]), ok=bool(r["ok"]), error_code=r["error_code"]
                )
                for r in data["results"]
            ]
        except (KeyError, TypeError) as exc:
            raise PersonIDUpstreamError(502, f"malformed review response envelope: {exc}") from exc

    async def merge_visitor_clusters(self, cluster_a: str, cluster_b: str) -> VisitorClusterSummary:
        data = await self._request_or_raise(
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
            "attributed_person_id": data.get("attributed_person_id"),
            "reviewed_by": data.get("reviewed_by"),
            "reviewed_at": (
                datetime.fromisoformat(data["reviewed_at"]) if data.get("reviewed_at") else None
            ),
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

    # -- Calibration capture review -------------------------------------------

    async def list_calibration_candidates(
        self, *, state: str | None, limit: int, cursor: str | None
    ) -> CalibrationCandidatePage:
        params = {"limit": str(limit)}
        if state:
            params["state"] = state
        if cursor:
            params["cursor"] = cursor
        data = await self._request_or_raise("GET", "/api/v1/calibration/candidates", params=params)
        try:
            return CalibrationCandidatePage(
                candidates=[self._parse_calibration_candidate(c) for c in data["candidates"]],
                next_cursor=data["next_cursor"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PersonIDUpstreamError(
                502, f"malformed calibration candidate page: {exc}"
            ) from exc

    async def label_calibration_candidate(
        self,
        candidate_id: str,
        *,
        label_kind: str,
        label_identity_id: str | None,
        labeled_by: str,
    ) -> CalibrationCandidateInfo:
        data = await self._request_or_raise(
            "POST",
            f"/api/v1/calibration/candidates/{candidate_id}/label",
            json={
                "label_kind": label_kind,
                "label_identity_id": label_identity_id,
                "labeled_by": labeled_by,
            },
        )
        return self._calibration_candidate_or_502(data)

    async def label_calibration_candidates(
        self, candidate_ids: list[str], *, label_kind: str, labeled_by: str
    ) -> list[CalibrationLabelItem]:
        """Label several captures ``not_enrolled`` or ``not_a_face``; one result each."""
        data = await self._request_or_raise(
            "POST",
            "/api/v1/calibration/candidates/label-batch",
            json={
                "candidate_ids": candidate_ids,
                "label_kind": label_kind,
                "labeled_by": labeled_by,
            },
        )
        try:
            return [
                CalibrationLabelItem(
                    candidate_id=str(r["candidate_id"]),
                    ok=bool(r["ok"]),
                    error_code=r["error_code"],
                )
                for r in data["results"]
            ]
        except (KeyError, TypeError) as exc:
            raise PersonIDUpstreamError(502, f"malformed label batch envelope: {exc}") from exc

    async def reject_calibration_candidate(self, candidate_id: str) -> CalibrationCandidateInfo:
        data = await self._request_or_raise(
            "POST", f"/api/v1/calibration/candidates/{candidate_id}/reject"
        )
        return self._calibration_candidate_or_502(data)

    async def delete_calibration_candidate(self, candidate_id: str) -> None:
        await self._request_or_raise("DELETE", f"/api/v1/calibration/candidates/{candidate_id}")

    async def promote_calibration_candidate(
        self,
        candidate_id: str,
        *,
        approved_by: str,
        person_id: str | None = None,
    ) -> PromoteCandidateResult:
        """Promote a labeled calibration capture into that member's prototypes."""
        body: dict[str, Any] = {"approved_by": approved_by}
        if person_id is not None:
            body["person_id"] = person_id
        data = await self._request_or_raise(
            "POST",
            f"/api/v1/calibration/candidates/{candidate_id}/promote",
            json=body,
        )
        try:
            return PromoteCandidateResult(
                candidate_id=str(data["candidate_id"]),
                person_id=str(data["person_id"]),
                pose_bin=str(data["pose_bin"]),
                embedding_id=int(data["embedding_id"]),
                gallery_revision=int(data["gallery_revision"]),
                prototype_count=int(data["prototype_count"]),
                counts_by_bin={str(k): int(v) for k, v in data["counts_by_bin"].items()},
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise PersonIDUpstreamError(502, f"malformed promote response: {exc}") from exc

    async def list_member_prototypes(self, person_id: str) -> MemberPrototypesInfo:
        """Fetch pose-binned prototypes for one enrolled member."""
        data = await self._request_or_raise("GET", f"/api/v1/members/{person_id}/prototypes")
        try:
            prototypes = [
                PrototypeInfo(
                    prototype_id=str(p["prototype_id"]),
                    person_id=str(p["person_id"]),
                    pose_bin=str(p["pose_bin"]),
                    member_count=int(p["member_count"]),
                    source=str(p["source"]),
                    quality_score=(
                        None if p.get("quality_score") is None else float(p["quality_score"])
                    ),
                    quality_version=p.get("quality_version"),
                    crop_object_key=p.get("crop_object_key"),
                    approved_by=p.get("approved_by"),
                    approved_at=(
                        None
                        if p.get("approved_at") is None
                        else datetime.fromisoformat(p["approved_at"])
                    ),
                    created_at=(
                        None
                        if p.get("created_at") is None
                        else datetime.fromisoformat(p["created_at"])
                    ),
                )
                for p in data["prototypes"]
            ]
            return MemberPrototypesInfo(
                person_id=str(data["person_id"]),
                gallery_revision=int(data["gallery_revision"]),
                prototypes=prototypes,
                counts_by_bin={str(k): int(v) for k, v in data["counts_by_bin"].items()},
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise PersonIDUpstreamError(502, f"malformed prototypes envelope: {exc}") from exc

    async def rebuild_member_prototypes(self, person_id: str) -> RebuildPrototypesResult:
        """Rebuild pose-binned prototypes for one enrolled member."""
        data = await self._request_or_raise(
            "POST", f"/api/v1/members/{person_id}/prototypes/rebuild"
        )
        try:
            return RebuildPrototypesResult(
                person_id=str(data["person_id"]),
                prototype_count=int(data["prototype_count"]),
                counts_by_bin={str(k): int(v) for k, v in data["counts_by_bin"].items()},
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise PersonIDUpstreamError(502, f"malformed rebuild response: {exc}") from exc

    async def delete_member_prototype(self, person_id: str, prototype_id: str) -> None:
        """Remove one prototype (and its underlying embedding(s)) for a member."""
        await self._request_or_raise(
            "DELETE", f"/api/v1/members/{person_id}/prototypes/{prototype_id}"
        )

    async def get_calibration_summary(self) -> CalibrationSummaryInfo:
        data = await self._request_or_raise("GET", "/api/v1/calibration/summary")
        try:
            return CalibrationSummaryInfo(
                by_state={str(k): int(v) for k, v in data["by_state"].items()},
                by_label_kind={str(k): int(v) for k, v in data["by_label_kind"].items()},
                by_quality_decile={str(k): int(v) for k, v in data["by_quality_decile"].items()},
                by_camera={str(k): int(v) for k, v in data["by_camera"].items()},
                identities=[
                    CalibrationIdentityProgress(
                        identity_id=i["identity_id"],
                        labeled_faces=int(i["labeled_faces"]),
                        episodes=int(i["episodes"]),
                        target_labeled_faces=int(i["target_labeled_faces"]),
                    )
                    for i in data["identities"]
                ],
                not_enrolled_episodes=int(data["not_enrolled_episodes"]),
                capture_enabled=bool(data["capture_enabled"]),
                promotable_by_identity_pose={
                    str(pid): {str(b): int(cnt) for b, cnt in bins.items()}
                    for pid, bins in (data.get("promotable_by_identity_pose") or {}).items()
                },
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise PersonIDUpstreamError(502, f"malformed calibration summary: {exc}") from exc

    async def get_calibration_health(self) -> CalibrationHealthInfo:
        """Calibration artifact status; raises instead of guessing when ``/health`` fails."""
        data = await self._request_or_raise("GET", "/health")
        try:
            calibration = data["calibration"]
            covered = calibration["covered_identities"]
            return CalibrationHealthInfo(
                status=str(calibration["status"]),
                covered_identities=None if covered is None else [str(i) for i in covered],
                template_status=str(data["template_calibration"]["status"]),
                recognizer_version=str(
                    data.get("recognizer_version")
                    or calibration.get("recognizer_version")
                    or data.get("model")
                    or ""
                ),
                active_profile=str(data.get("active_profile") or ""),
                licence=str(data.get("licence") or ""),
            )
        except (KeyError, TypeError) as exc:
            raise PersonIDUpstreamError(502, f"malformed health response: {exc}") from exc

    async def list_attested_faces(
        self, *, identity_id: str | None, audited: bool | None, limit: int
    ) -> list[CalibrationCandidateInfo]:
        """Wearable-attested captures, best quality first (the exemplar grid)."""
        params = {"limit": str(limit)}
        if identity_id:
            params["identity_id"] = identity_id
        if audited is not None:
            params["audited"] = "true" if audited else "false"
        data = await self._request_or_raise(
            "GET", "/api/v1/calibration/attestations", params=params
        )
        return self._calibration_candidates_or_502(data)

    async def get_attestation_audit_sample(self, n: int) -> list[CalibrationCandidateInfo]:
        """A uniform random sample of unaudited attested captures, drawn by person-id."""
        data = await self._request_or_raise(
            "GET", "/api/v1/calibration/attestations/audit-sample", params={"n": str(n)}
        )
        return self._calibration_candidates_or_502(data)

    async def audit_attested_face(
        self, candidate_id: str, *, verdict: str, audited_by: str
    ) -> CalibrationCandidateInfo:
        data = await self._request_or_raise(
            "POST",
            f"/api/v1/calibration/attestations/{candidate_id}/audit",
            json={"verdict": verdict, "audited_by": audited_by},
        )
        return self._calibration_candidate_or_502(data)

    async def get_attestation_audit_summary(self) -> AttestationAuditSummaryInfo:
        data = await self._request_or_raise("GET", "/api/v1/calibration/attestations/audit-summary")
        try:
            bound = data["precision_lower_bound"]
            return AttestationAuditSummaryInfo(
                attested=int(data["attested"]),
                audited=int(data["audited"]),
                correct=int(data["correct"]),
                wrong=int(data["wrong"]),
                not_a_face=int(data["not_a_face"]),
                precision_lower_bound=None if bound is None else float(bound),
                min_audited=int(data["min_audited"]),
                min_precision_lower_bound=float(data["min_precision_lower_bound"]),
                meets_bar=bool(data["meets_bar"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PersonIDUpstreamError(502, f"malformed attestation audit summary: {exc}") from exc

    def _calibration_candidates_or_502(self, data: Any) -> list[CalibrationCandidateInfo]:
        try:
            return [self._parse_calibration_candidate(c) for c in data["candidates"]]
        except (KeyError, TypeError, ValueError) as exc:
            raise PersonIDUpstreamError(502, f"malformed attested face list: {exc}") from exc

    def _calibration_candidate_or_502(self, data: Any) -> CalibrationCandidateInfo:
        try:
            return self._parse_calibration_candidate(data)
        except (KeyError, TypeError, ValueError) as exc:
            raise PersonIDUpstreamError(502, f"malformed calibration candidate: {exc}") from exc

    @staticmethod
    def _parse_calibration_candidate(c: dict[str, Any]) -> CalibrationCandidateInfo:
        labeled_at = c["labeled_at"]
        return CalibrationCandidateInfo(
            candidate_id=c["candidate_id"],
            captured_at=datetime.fromisoformat(c["captured_at"]),
            camera_id=c["camera_id"],
            crop_object_key=c["crop_object_key"],
            quality_score=float(c["quality_score"]),
            quality_version=c["quality_version"],
            interocular_px=None if c["interocular_px"] is None else float(c["interocular_px"]),
            yaw_deg=float(c["yaw_deg"]),
            pitch_deg=float(c["pitch_deg"]),
            nearest_person_id=c["nearest_person_id"],
            nearest_similarity=float(c["nearest_similarity"]),
            label_state=c["label_state"],
            label_kind=c["label_kind"],
            label_identity_id=c["label_identity_id"],
            labeled_by=c["labeled_by"],
            labeled_at=None if labeled_at is None else datetime.fromisoformat(labeled_at),
            pose_bin=str(c.get("pose_bin", "frontal")),
            promoted=bool(c.get("promoted", False)),
            promotion_eligible=bool(c.get("promotion_eligible", False)),
            promotion_ineligible_reason=c.get("promotion_ineligible_reason"),
            attestation_association_id=c.get("attestation_association_id"),
            attestation_grade=c.get("attestation_grade"),
            audit_verdict=c.get("audit_verdict"),
            audited_by=c.get("audited_by"),
            audited_at=(
                None if c.get("audited_at") is None else datetime.fromisoformat(c["audited_at"])
            ),
        )

    async def _request_or_raise(
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
                "person_id_request_failed",
                method=method,
                path=path,
                status=exc.response.status_code,
                detail=detail,
            )
            raise PersonIDUpstreamError(exc.response.status_code, detail) from exc
        except httpx.TimeoutException as exc:
            logger.warning("person_id_request_timeout", method=method, path=path)
            raise PersonIDUpstreamError(504, "Person identification service timed out") from exc
        except httpx.HTTPError as exc:
            logger.exception("person_id_request_error", method=method, path=path)
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
                    bbox=f["bbox"],
                    recognition_state=f.get("recognition_state", "recognized"),
                    best_candidate_id=f.get("best_candidate_id"),
                    raw_similarity=_raw_similarity(f),
                    yaw_deg=f.get("yaw_deg", 0.0),
                    pitch_deg=f.get("pitch_deg", 0.0),
                    roll_deg=f.get("roll_deg", 0.0),
                    det_score=f.get("det_score", 0.0),
                    calibrated_confidence=f.get("calibrated_confidence"),
                    calibration_status=f.get("calibration_status", "degraded_missing"),
                    calibration_artifact_version=f.get("calibration_artifact_version"),
                    second_best_candidate_id=f.get("second_best_candidate_id"),
                    second_best_similarity=f.get("second_best_similarity"),
                    margin=f.get("margin"),
                    gallery_representation=f.get("gallery_representation", "centroid"),
                    recognizer_version=_recognizer_version(f),
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
