"""SQLAlchemy model for CTS-managed cameras.

Separate from the generic ``Sensor`` model: CTS cameras carry RTSP URLs,
floor-plan references, homography matrices, and privacy-zone configs that
have no analogue in the sensor model.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base
from backend.core.time import UTCDateTime


class CtsCamera(Base):
    __tablename__ = "cts_cameras"

    # Operator-assigned stable ID (e.g. "kitchen-cam-1").
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    rtsp_url: Mapped[str] = mapped_column(String(1024), default="")
    room_name: Mapped[str] = mapped_column(String(256), default="")
    room_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Clockwise rotation applied by rtsp-ingress at ingest time.
    # One of 0, 90, 180, 270.  Changing this value invalidates any existing
    # homography calibration — recalibrate after rotation changes.
    rotation_degrees: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Face identification: set to false for top-down cameras where faces
    # are never visible.  min_confidence overrides the orchestrator default.
    face_id_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    face_id_min_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Camera role: face_capable (has usable face angles), surveillance
    # (top-down or overview), or mixed (partial face visibility).
    role: Mapped[str] = mapped_column(String(32), default="surveillance")

    # Physical camera parameters — all optional.
    # horizontal_fov_deg: horizontal field of view in degrees (20-180).
    #   Used by depth-based auto-calibration to estimate focal length.
    # mounting_height_m: camera lens height above the floor in metres.
    #   Reserved for M7 depth-based footpoint correction.
    # tilt_deg: downward pitch angle. 0 = horizontal, -90 = pointing straight down.
    horizontal_fov_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    mounting_height_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    tilt_deg: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Native pixel dimensions of the frame used during the last homography calibration.
    snapshot_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snapshot_height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # MinIO object key for the floor-plan image (optional).
    floor_plan_key: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # 3x3 homography matrix stored as JSON [[r0c0,...], ...].
    # Null until calibration is performed.
    homography: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Per-point reprojection error from the last homography fit (meters).
    homography_residuals: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # M2: calibration health columns
    homography_matrix: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    homography_residual_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    homography_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    homography_set_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    frame_natural_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frame_natural_height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Normalised [0,1] visibility polygon derived from the homography matrix.
    # Each element is [x_norm, y_norm] where x=0 is the left edge of the floor plan
    # and x=1 is the right edge.  Populated automatically when homography is saved.
    visibility_polygon: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # List of privacy-zone dicts [{zone_id, name, polygon, policy, enabled}].
    privacy_zones: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Latest health snapshot from rtsp-ingress (filled by camera-health poll).
    health_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now()
    )
