"""Camera placement optics calculator and CTS observed-stream-size sync.

All pinhole math and interocular pixel band thresholds come exclusively from
``cts_contracts.optics`` so there is a single source of truth across CTS, CC, and the UI.
"""

from __future__ import annotations

from typing import Any, Final

from cts_contracts.optics import (
    INTEROCULAR_BANDS_PX,
    INTEROCULAR_GOOD_MIN_PX,
    classify_interocular_px,
    distance_for_interocular_m,
    expected_interocular_px,
    focal_length_px,
)
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.models.cts_camera import CtsCamera
from backend.schemas.cts_camera import (
    CameraOpticsOut,
    OpticsBandThreshold,
    OpticsDistanceRow,
)

logger = get_logger(__name__)

# Standard distances (metres) shown in the camera placement calculator panel.
PREVIEW_DISTANCES_M: Final[tuple[float, ...]] = (1.0, 2.0, 3.0, 4.0, 5.0)


def _band_thresholds() -> list[OpticsBandThreshold]:
    return [
        OpticsBandThreshold(band=spec.band, min_px=spec.min_px, max_px=spec.max_px)
        for spec in INTEROCULAR_BANDS_PX
    ]


def compute_camera_optics(
    *,
    camera_id: str | None = None,
    horizontal_fov_deg: float | None,
    frame_natural_width: int | None,
    frame_natural_height: int | None = None,
    observed_stream_width: int | None = None,
    observed_stream_height: int | None = None,
    stream_size_mismatch: bool = False,
) -> CameraOpticsOut:
    """Compute pinhole focal length and expected interocular pixels from ``cts_contracts.optics``."""
    effective_width = frame_natural_width or observed_stream_width
    effective_height = frame_natural_height or observed_stream_height

    missing: list[str] = []
    if horizontal_fov_deg is None:
        missing.append("horizontal_fov_deg")
    if effective_width is None:
        missing.append("frame_natural_width")

    bands = _band_thresholds()
    if missing or horizontal_fov_deg is None or effective_width is None:
        return CameraOpticsOut(
            camera_id=camera_id,
            horizontal_fov_deg=horizontal_fov_deg,
            frame_natural_width=frame_natural_width,
            frame_natural_height=frame_natural_height,
            observed_stream_width=observed_stream_width,
            observed_stream_height=observed_stream_height,
            stream_size_mismatch=stream_size_mismatch,
            focal_length_px=None,
            distance_for_24px_m=None,
            distances=[],
            bands=bands,
            missing_inputs=missing,
        )

    focal = focal_length_px(effective_width, horizontal_fov_deg)
    dist_24 = distance_for_interocular_m(focal, INTEROCULAR_GOOD_MIN_PX)
    rows = [
        OpticsDistanceRow(
            distance_m=distance_m,
            interocular_px=(iod := expected_interocular_px(focal, distance_m)),
            band=classify_interocular_px(iod),
        )
        for distance_m in PREVIEW_DISTANCES_M
    ]

    return CameraOpticsOut(
        camera_id=camera_id,
        horizontal_fov_deg=horizontal_fov_deg,
        frame_natural_width=effective_width,
        frame_natural_height=effective_height,
        observed_stream_width=observed_stream_width,
        observed_stream_height=observed_stream_height,
        stream_size_mismatch=stream_size_mismatch,
        focal_length_px=focal,
        distance_for_24px_m=dist_24,
        distances=rows,
        bands=bands,
        missing_inputs=[],
    )


def _extract_stream_size(raw: Any) -> tuple[int, int] | None:
    if not isinstance(raw, dict):
        return None
    w = raw.get("width_px")
    h = raw.get("height_px")
    if (
        isinstance(w, int)
        and not isinstance(w, bool)
        and isinstance(h, int)
        and not isinstance(h, bool)
        and w > 0
        and h > 0
    ):
        return w, h
    return None


def apply_observed_stream_sizes(
    cameras: list[CtsCamera],
    calibration_status: dict[str, Any],
    db: Session,
) -> dict[str, tuple[int, int, bool]]:
    """Sync CTS-reported stream dimensions into ``cts_cameras`` without breaking calibration.

    For cameras with unset ``frame_natural_width``/``frame_natural_height`` (or without a
    committed homography), stores the observed dimensions from CTS. For calibrated cameras
    whose live stream dimensions differ from their calibration snapshot, preserves the
    stored calibration dimensions and flags ``stream_size_mismatch=True``.
    """
    raw_map = calibration_status.get("observed_stream_sizes")
    if not isinstance(raw_map, dict):
        return {}

    dirty = False
    result: dict[str, tuple[int, int, bool]] = {}
    for cam in cameras:
        dims = _extract_stream_size(raw_map.get(cam.id))
        if dims is None:
            continue
        obs_w, obs_h = dims
        has_homography = bool(cam.homography_matrix)
        mismatch = False
        if cam.frame_natural_width is None or cam.frame_natural_height is None:
            cam.frame_natural_width = obs_w
            cam.frame_natural_height = obs_h
            dirty = True
        elif cam.frame_natural_width != obs_w or cam.frame_natural_height != obs_h:
            if not has_homography:
                cam.frame_natural_width = obs_w
                cam.frame_natural_height = obs_h
                dirty = True
            else:
                mismatch = True
        result[cam.id] = (obs_w, obs_h, mismatch)

    if dirty:
        db.commit()
    return result


async def sync_camera_observed_stream_size(
    cam: CtsCamera,
    db: Session,
    orchestrator: OrchestratorClient | None,
) -> tuple[int | None, int | None, bool]:
    """Fetch observed stream size from CTS ``/internal/calibration/status`` if reachable."""
    if orchestrator is None:
        return None, None, False
    try:
        status = await orchestrator.calibration_status()
    except Exception as exc:  # noqa: BLE001 - optional live enrichment; optics still works offline
        logger.debug("cts_camera_optics_status_unavailable", camera_id=cam.id, error=str(exc))
        return None, None, False
    if not isinstance(status, dict):
        return None, None, False
    synced = apply_observed_stream_sizes([cam], status, db)
    entry = synced.get(cam.id)
    if entry is None:
        return None, None, False
    return entry
