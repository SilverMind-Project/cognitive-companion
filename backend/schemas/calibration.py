"""Shared schema mixin for M2 calibration validation results."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CalibrationValidation(BaseModel):
    """Sanity-check result for a stored homography."""

    ok: bool
    severity: str = Field(..., pattern="^(ok|warning|error)$")
    issues: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)


class CalibrationDiagnosticsEntry(BaseModel):
    """Per-camera calibration health for the diagnostics endpoint."""

    camera_id: str
    room_id: str | None = None
    room_name: str = ""
    has_homography: bool = False
    homography_set_at: str | None = None
    homography_method: str | None = None
    validation: CalibrationValidation | None = None


class CalibrationDiagnosticsResponse(BaseModel):
    """Response for GET /cts/diagnostics/calibration."""

    cameras: list[CalibrationDiagnosticsEntry]
