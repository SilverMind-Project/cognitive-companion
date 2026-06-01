"""Pydantic schemas for the CTS camera API."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from backend.schemas.common import OutSchema, UTCDatetime


class RoomRef(BaseModel):
    """Lightweight Room reference for camera output."""

    id: int
    name: str


class CtsCameraFields(BaseModel):
    """Shared editable fields for CTS camera create / output."""

    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    rtsp_url: str = Field(default="", max_length=1024)
    room_name: str = Field(default="", max_length=256)
    room_id: int | None = None
    enabled: bool = True
    floor_plan_key: str | None = None
    # Clockwise rotation applied at ingest time (0, 90, 180, 270).
    # Changing this invalidates homography calibration.
    rotation_degrees: int = Field(default=0, ge=0, le=270)

    @field_validator("rotation_degrees")
    @classmethod
    def _validate_rotation(cls, v: int) -> int:
        if v not in (0, 90, 180, 270):
            raise ValueError("rotation_degrees must be 0, 90, 180, or 270")
        return v

    # Face identification: set enabled=false for top-down cameras where
    # faces are never visible.  min_confidence overrides the orchestrator
    # default (higher = stricter matching).
    face_id_enabled: bool = True
    face_id_min_confidence: float | None = None
    role: str = Field(default="surveillance", pattern="^(face_capable|surveillance|mixed)$")

    horizontal_fov_deg: float | None = Field(
        default=None,
        ge=20.0,
        le=180.0,
        description=(
            "Horizontal field of view in degrees. "
            "Used by auto-calibration to estimate focal length. "
            "Enter HFOV, not diagonal FOV."
        ),
    )
    mounting_height_m: float | None = Field(
        default=None,
        ge=0.1,
        le=10.0,
        description="Camera mounting height above the floor in metres.",
    )
    tilt_deg: float | None = Field(
        default=None,
        ge=-90.0,
        le=0.0,
        description="Downward tilt angle in degrees. 0 = horizontal, -90 = pointing straight down.",
    )


class CtsCameraCreate(CtsCameraFields):
    model_config = {"extra": "forbid"}


class CtsCameraUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=256)
    rtsp_url: str | None = Field(default=None, max_length=1024)
    room_name: str | None = Field(default=None, max_length=256)
    room_id: int | None = None
    enabled: bool | None = None
    floor_plan_key: str | None = None
    rotation_degrees: int | None = Field(default=None, ge=0, le=270)
    face_id_enabled: bool | None = None
    face_id_min_confidence: float | None = None
    role: str | None = Field(default=None, pattern="^(face_capable|surveillance|mixed)$")
    horizontal_fov_deg: float | None = Field(default=None, ge=20.0, le=180.0)
    mounting_height_m: float | None = Field(default=None, ge=0.1, le=10.0)
    tilt_deg: float | None = Field(default=None, ge=-90.0, le=0.0)

    model_config = {"extra": "forbid"}


class CtsCameraOut(CtsCameraFields, OutSchema):
    room: RoomRef | None = None
    has_homography: bool
    homography_residuals: list[float] | None
    homography_matrix: list[list[float]] | None = None
    homography_residual_m: float | None = None
    homography_method: str | None = None
    homography_set_at: UTCDatetime | None = None
    homography_floor_plan_id: str | None = None
    frame_natural_width: int | None = None
    frame_natural_height: int | None = None
    privacy_zone_count: int
    health: dict | None
    snapshot_width: int | None = None
    snapshot_height: int | None = None
    visibility_polygon: list[list[float]] | None = None
    created_at: UTCDatetime
    updated_at: UTCDatetime


# ---------------------------------------------------------------------------
# Calibration schemas
# ---------------------------------------------------------------------------


class CalibrationPoint(BaseModel):
    pixel: list[float] = Field(..., min_length=2, max_length=2)
    floor_m: list[float] = Field(..., min_length=2, max_length=2)


class HomographyRequest(BaseModel):
    camera_id: str = Field(..., min_length=1)
    points: list[CalibrationPoint] = Field(..., min_length=4)
    image_width: int = Field(
        ..., ge=1, description="Native pixel width of the calibration snapshot."
    )
    image_height: int = Field(
        ..., ge=1, description="Native pixel height of the calibration snapshot."
    )


class HomographyResult(BaseModel):
    camera_id: str
    matrix: list[list[float]]
    residuals_m: list[float]
    max_residual_m: float
    status: str  # "ok" | "warning" | "error"
    visibility_polygon_computed: bool = False
    visibility_polygon_warning: str | None = None


class HomographyPreviewRequest(BaseModel):
    """Fit H from point pairs and return the matrix without saving."""

    points: list[CalibrationPoint] = Field(..., min_length=4)

    model_config = {"extra": "forbid"}


class HomographyPreviewResult(BaseModel):
    matrix: list[list[float]]
    residuals_m: list[float]
    max_residual_m: float
    status: str  # "ok" | "warning" | "error"


class InferredEdgeOut(BaseModel):
    from_camera: str = Field(..., alias="from")
    to_camera: str = Field(..., alias="to")
    min_transit_s: float
    max_transit_s: float
    overlap: bool
    iou: float

    model_config = {"populate_by_name": True}


class InferredOverlapGroupOut(BaseModel):
    camera_ids: list[str]
    iou: float


class InferredAdjacencyResponse(BaseModel):
    edges: list[InferredEdgeOut]
    overlap_groups: list[InferredOverlapGroupOut]
    skipped_camera_ids: list[str]


class PrivacyZoneIn(BaseModel):
    zone_id: str = Field(..., min_length=1)
    name: str = ""
    polygon: list[list[float]] = Field(..., min_length=3)
    policy: str = Field(..., pattern=r"^(drop_detections|blur_faces|mask_region)$")
    enabled: bool = True

    @field_validator("polygon")
    @classmethod
    def _normalize(cls, pts: list[list[float]]) -> list[list[float]]:
        for pt in pts:
            if len(pt) != 2:
                raise ValueError("each polygon point must be [x, y]")
            if not all(0.0 <= v <= 1.0 for v in pt):
                raise ValueError("polygon coordinates must be in [0, 1]")
        return pts


class PrivacyZonesRequest(BaseModel):
    camera_id: str = Field(..., min_length=1)
    zones: list[PrivacyZoneIn]


class CameraVisibilityPolygon(BaseModel):
    camera_id: str
    camera_name: str
    has_homography: bool
    visibility_polygon: list[list[float]] | None


class VisibilityPolygonsResponse(BaseModel):
    cameras: list[CameraVisibilityPolygon]
    floor_meters_per_pixel: float | None
    floor_plan_width_px: int | None
    floor_plan_height_px: int | None


class AdjacencyEdgeIn(BaseModel):
    from_camera: str = Field(..., alias="from", min_length=1)
    to_camera: str = Field(..., alias="to", min_length=1)
    min_transit_s: float = Field(default=0.5, ge=0.0)
    max_transit_s: float = Field(default=30.0, ge=0.0)
    overlap: bool = False

    model_config = {"populate_by_name": True}


class AdjacencyRequest(BaseModel):
    edges: list[AdjacencyEdgeIn]
