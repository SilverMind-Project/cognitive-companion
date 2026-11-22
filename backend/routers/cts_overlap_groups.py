"""CTS camera overlap groups: declare which cameras see the same floor area at the same time.

An overlap group is a set of cameras, not a directed edge, and carries no transit time: walk
times between cameras are learned by CTS (see ``cts_topology``). The tracking orchestrator reads
the groups on every CC config sync and uses them to merge one person seen by several
uncalibrated cameras of a group by appearance, to link co-present tracks, and to keep ReID
embeddings on for those cameras. Suggestions come from calibrated cameras' floor coverage.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.models.cts_camera import CtsCamera
from backend.routers.cts_deps import cts_enabled
from backend.services.cts_overlap_suggestions import suggest_overlap_groups

router = APIRouter(prefix="/cts/overlap_groups", tags=["cts-overlap-groups"])


class OverlapGroupIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    camera_ids: list[str] = Field(..., min_length=2)

    @field_validator("camera_ids")
    @classmethod
    def _distinct_cameras(cls, camera_ids: list[str]) -> list[str]:
        if len(set(camera_ids)) != len(camera_ids):
            raise ValueError("camera_ids must be distinct")
        return camera_ids


class OverlapGroupOut(BaseModel):
    id: int
    name: str
    camera_ids: list[str]
    created_at: str | None = None


class SuggestedOverlapGroupOut(BaseModel):
    camera_ids: list[str]
    iou: float
    # True when a declared group already contains every camera of the suggestion.
    declared: bool


class OverlapGroupSuggestionsOut(BaseModel):
    groups: list[SuggestedOverlapGroupOut]
    # Enabled cameras without a calibration (no visibility polygon): never suggested.
    uncalibrated_camera_ids: list[str]


@router.get("/suggested", response_model=OverlapGroupSuggestionsOut)
def suggested_groups(
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.cameras:read")),
) -> OverlapGroupSuggestionsOut:
    """Suggest groups from calibrated cameras whose floor coverage overlaps (nothing is saved)."""
    cts_enabled()
    cameras = db.scalars(select(CtsCamera).where(CtsCamera.enabled.is_(True))).all()
    suggestions = suggest_overlap_groups(
        [{"id": c.id, "visibility_polygon": c.visibility_polygon} for c in cameras]
    )
    declared = [
        set(r.camera_ids or [])
        for r in db.execute(text("SELECT camera_ids FROM cts_camera_overlap_groups")).fetchall()
    ]
    return OverlapGroupSuggestionsOut(
        groups=[
            SuggestedOverlapGroupOut(
                camera_ids=g.camera_ids,
                iou=g.iou,
                declared=any(set(g.camera_ids) <= group for group in declared),
            )
            for g in suggestions.groups
        ],
        uncalibrated_camera_ids=sorted(suggestions.skipped_camera_ids),
    )


@router.get("", response_model=list[OverlapGroupOut])
def list_groups(
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.cameras.roster:read")),
) -> list[dict]:
    cts_enabled()
    rows = db.execute(
        text("SELECT id, name, camera_ids, created_at FROM cts_camera_overlap_groups ORDER BY id")
    ).fetchall()
    return [
        {
            "id": r.id,
            "name": r.name,
            "camera_ids": r.camera_ids or [],
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("", response_model=OverlapGroupOut, status_code=status.HTTP_201_CREATED)
def create_group(
    body: OverlapGroupIn,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.cameras:write")),
) -> dict:
    cts_enabled()
    # A group naming a camera that does not exist is inert in tracking and would hide the typo.
    known = set(db.scalars(select(CtsCamera.id).where(CtsCamera.id.in_(body.camera_ids))).all())
    unknown = sorted(set(body.camera_ids) - known)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "overlap_group.unknown_camera", "camera_ids": unknown},
        )
    result = db.execute(
        text(
            "INSERT INTO cts_camera_overlap_groups (name, camera_ids) "
            "VALUES (:name, :camera_ids) RETURNING id, created_at"
        ),
        {"name": body.name, "camera_ids": body.camera_ids},
    )
    row = result.fetchone()
    db.commit()
    return {
        "id": row.id,
        "name": body.name,
        "camera_ids": body.camera_ids,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.cameras:write")),
) -> None:
    cts_enabled()
    result = db.execute(
        text("DELETE FROM cts_camera_overlap_groups WHERE id = :id"),
        {"id": group_id},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail={"code": "overlap_group.not_found"})
    db.commit()
