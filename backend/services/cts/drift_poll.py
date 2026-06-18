"""Periodic drift-detection poll for CTS cameras (M11).

Runs on a configurable interval (default: 3600 s / hourly).  For each
enabled camera that has a committed calibration reference frame, it:

  1. Retrieves a recent keyframe for that camera from the orchestrator.
  2. Calls the CTS drift endpoint (POST /internal/calibration/drift/{id}).
  3. If drifted: sets ``needs_recalibration=True`` and logs a warning so
     operators can investigate.
  4. Always updates ``drift_checked_at`` to record the last check time.

Human-in-the-loop: this service ONLY sets a database flag.  It never
mutates any homography or triggers an automatic recalibration.  The
operator must initiate recalibration via the admin UI CTA.

Frequency: drift is rare; polling every minute would be wasteful.
The default hourly cadence is configurable via ``cts.drift_poll_interval_s``.
False positives annoy operators, so when ORB returns insufficient_features
(textureless scene / dark frame) the result is not flagged as drift.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from backend.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from backend.integrations.tracking_orchestrator_client import OrchestratorClient

logger = get_logger(__name__)


async def poll_camera_drift(
    *,
    db_factory: object,
    orchestrator: OrchestratorClient,
) -> None:
    """Check all calibrated cameras for drift.

    Called by the APScheduler ``IntervalTrigger`` job wired in ``main.py``.
    Uses the DB session factory (same pattern as other CC periodic tasks) so
    each invocation gets a fresh session that is closed on completion.
    """
    from sqlalchemy import select

    from backend.models.cts_camera import CtsCamera

    session_factory = db_factory  # type: ignore[assignment]
    # db_factory is a callable that returns a context-managed session.
    db: Session = session_factory()
    try:
        cameras = db.execute(
            select(CtsCamera).where(
                CtsCamera.enabled.is_(True),
                CtsCamera.calibration_ref_key.isnot(None),
            )
        ).scalars().all()

        for cam in cameras:
            await _check_one_camera(cam=cam, db=db, orchestrator=orchestrator)
    finally:
        db.close()


async def _check_one_camera(
    *,
    cam: object,
    db: Session,
    orchestrator: OrchestratorClient,
) -> None:
    """Run drift detection for a single camera and persist the result."""
    from backend.core.upstream_errors import UpstreamError, UpstreamTimeout, UpstreamUnavailable
    from backend.models.cts_camera import CtsCamera

    camera_id: str = cam.id  # type: ignore[attr-defined]
    ref_key: str = cam.calibration_ref_key  # type: ignore[attr-defined]

    # Fetch a recent keyframe for this camera from the orchestrator.
    current_key: str | None = await _recent_keyframe_key(
        orchestrator=orchestrator,
        camera_id=camera_id,
    )
    if current_key is None:
        logger.info(
            "drift_poll_no_recent_frame",
            camera_id=camera_id,
        )
        return

    try:
        result = await orchestrator.check_drift(
            camera_id=camera_id,
            reference_key=ref_key,
            current_key=current_key,
        )
    except (UpstreamError, UpstreamTimeout, UpstreamUnavailable) as exc:
        logger.warning(
            "drift_poll_upstream_error",
            camera_id=camera_id,
            error=str(exc),
        )
        return
    except Exception as exc:
        logger.warning(
            "drift_poll_unexpected_error",
            camera_id=camera_id,
            error=str(exc),
        )
        return

    drifted: bool = result.get("drifted", False)
    reason: str = result.get("reason", "unknown")

    # Reload the row inside the same session to apply the update.
    cam_row = db.get(CtsCamera, camera_id)
    if cam_row is None:
        return

    cam_row.drift_checked_at = datetime.now(UTC)

    if drifted:
        cam_row.needs_recalibration = True
        cam_row.drift_reason = reason
        db.commit()
        logger.warning(
            "camera_drift_detected",
            camera_id=camera_id,
            inlier_ratio=round(result.get("inlier_ratio", 0.0), 4),
            ssim=round(result.get("ssim", 0.0), 4),
            reason=reason,
        )
    else:
        db.commit()
        logger.info(
            "camera_drift_ok",
            camera_id=camera_id,
            inlier_ratio=round(result.get("inlier_ratio", 0.0), 4),
            reason=reason,
        )


async def _recent_keyframe_key(
    *,
    orchestrator: OrchestratorClient,
    camera_id: str,
) -> str | None:
    """Return the MinIO key of a recent keyframe for *camera_id*, or None."""
    try:
        keyframes = await orchestrator.list_keyframes(limit=50)
    except Exception as exc:
        logger.warning(
            "drift_poll_keyframe_fetch_failed",
            camera_id=camera_id,
            error=str(exc),
        )
        return None

    # list_keyframes returns dicts with a "camera_id" field.  Filter to
    # this camera's most recent frame (keyframes are ordered newest-first).
    for kf in keyframes:
        if kf.get("camera_id") == camera_id:
            minio_key: str | None = kf.get("minio_key")
            if minio_key:
                return minio_key
    return None
