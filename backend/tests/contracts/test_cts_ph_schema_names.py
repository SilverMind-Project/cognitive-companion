"""WTR1: CC contract name tests — PH-native field names.

Asserts that CC BFF schemas and presence timeline schemas expose PH-native
names. No CC schema may expose ``global_track_id`` or ``tracklet_id``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# -- Forbidden field names in public Pydantic schemas ------------------------
_FORBIDDEN_FIELDS: set[str] = {"global_track_id", "tracklet_id"}

# -- Directories to scan for Pydantic schemas ---------------------------------
_SCHEMA_DIRS: list[str] = ["backend/schemas"]


def _find_schema_files() -> list[Path]:
    root = Path(__file__).resolve().parents[2]
    files: list[Path] = []
    for schema_dir in _SCHEMA_DIRS:
        target = root / schema_dir
        if target.exists():
            files.extend(target.rglob("*.py"))
    return files


def _extract_pydantic_field_names(file_path: Path) -> dict[str, list[str]]:
    try:
        tree = ast.parse(file_path.read_text())
    except SyntaxError:
        return {}

    models: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        is_pydantic = False
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == "BaseModel":
                is_pydantic = True
                break
            if isinstance(base, ast.Attribute) and base.attr == "BaseModel":
                is_pydantic = True
                break
        if not is_pydantic:
            continue

        field_names: list[str] = []
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                field_names.append(item.target.id)
        models[node.name] = field_names

    return models


@pytest.mark.parametrize(
    "file_path", _find_schema_files(), ids=lambda p: str(p.relative_to(p.parents[2]))
)
def test_cc_schemas_use_ph_native_names(file_path: Path):
    """No CC Pydantic schema may expose global_track_id or tracklet_id."""
    models = _extract_pydantic_field_names(file_path)
    violations: list[str] = []
    for class_name, field_names in models.items():
        for forbidden in _FORBIDDEN_FIELDS:
            if forbidden in field_names:
                violations.append(f"  {class_name}.{forbidden}")

    assert not violations, (
        f"{file_path.name}: CC schemas must not expose legacy field names. "
        f"Violations:\n" + "\n".join(violations)
    )


def test_ph_summary_response_uses_ph_id():
    """PHSummaryResponse must expose ph_id, not global_track_id."""
    from backend.schemas.cts_ph import PHSummaryResponse

    assert "ph_id" in PHSummaryResponse.model_fields
    assert "global_track_id" not in PHSummaryResponse.model_fields
    assert "tracklet_id" not in PHSummaryResponse.model_fields


def test_ph_detail_response_uses_ph_id():
    """PHDetailResponse must expose ph_id, not global_track_id."""
    from backend.schemas.cts_ph import PHDetailResponse

    assert "ph_id" in PHDetailResponse.model_fields
    assert "global_track_id" not in PHDetailResponse.model_fields
    assert "tracklet_id" not in PHDetailResponse.model_fields


def test_ph_ws_events_use_ph_id():
    """PHUpdateEvent and PHCorrectionEvent must use ph_id."""
    from backend.schemas.cts_ph_ws import PHCorrectionEvent, PHUpdateEvent

    assert "ph_id" in PHUpdateEvent.model_fields
    assert "global_track_id" not in PHUpdateEvent.model_fields
    assert "tracklet_id" not in PHUpdateEvent.model_fields

    assert "ph_id" in PHCorrectionEvent.model_fields
    assert "global_track_id" not in PHCorrectionEvent.model_fields
    assert "tracklet_id" not in PHCorrectionEvent.model_fields


def test_presence_timeline_uses_person_id():
    """Presence timeline schemas use person_id, not ph_id (WTR1 §6)."""
    from backend.schemas.presence_timeline import (
        CurrentInEntry,
        PresenceSegmentOut,
        TimelineResponse,
    )

    assert "person_id" in PresenceSegmentOut.model_fields
    assert "person_id" in TimelineResponse.model_fields
    assert "person_id" in CurrentInEntry.model_fields
    assert "global_track_id" not in PresenceSegmentOut.model_fields
    assert "tracklet_id" not in PresenceSegmentOut.model_fields


def test_ph_schema_parity_accepts_orchestrator_payloads():
    """CC PH schemas parse representative orchestrator response dictionaries."""
    from backend.schemas.cts_ph import (
        PHCoPresentResponse,
        PHDetailResponse,
        PHKeyframesResponse,
        PHObservationsResponse,
        PHTrailResponse,
        RevisionsFeedResponse,
    )

    PHDetailResponse(
        ph_id="ph-1",
        current_identity_id="alice",
        metadata={"posterior_entropy": 0.12},
        state_mean=[1.0, 2.0, 0.0, 0.0],
    )
    PHObservationsResponse(
        ph_id="ph-1",
        items=[
            {
                "observation_id": "obs-1",
                "camera_id": "cam-1",
                "frame_index": 12,
                "floor_x_m": 1.5,
                "floor_y_m": 2.5,
                "detection_confidence": 0.91,
            }
        ],
        count=1,
    )
    PHKeyframesResponse(
        ph_id="ph-1",
        items=[
            {
                "observation_id": "obs-1",
                "camera_id": "cam-1",
                "minio_key": "cts/keyframes/obs-1.jpg",
                "reid_confidence": 0.8,
            }
        ],
        count=1,
    )
    PHTrailResponse(
        ph_id="ph-1",
        points=[
            {"camera_id": "cam-1", "floor_x_m": 1.0, "floor_y_m": 2.0},
            {"camera_id": "cam-2", "floor_x_m": 2.0, "floor_y_m": 3.0},
        ],
        count=2,
    )
    PHCoPresentResponse(
        ph_id="ph-1",
        co_present=[
            {
                "ph_id": "ph-2",
                "current_identity_id": "bob",
                "last_seen_camera": "cam-2",
            }
        ],
        radius_m=5.0,
    )
    RevisionsFeedResponse(
        items=[
            {
                "revision_id": "rev-1",
                "ph_id": "ph-1",
                "previous_identity_id": None,
                "new_identity_id": "alice",
                "kind": "manual_correct",
            }
        ],
        has_more=False,
    )
