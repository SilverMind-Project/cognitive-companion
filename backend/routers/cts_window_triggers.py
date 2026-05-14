"""CRUD endpoints for CtsWindowTrigger.

Registered at ``/api/v1/rules/cts-window-triggers`` under the auth
permissions ``rules:read`` and ``rules:write`` (same as cron triggers).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.exceptions import NotFoundError
from backend.models.cts_window_trigger import CtsWindowTrigger
from backend.schemas.cts_window_trigger import (
    CtsWindowTriggerCreate,
    CtsWindowTriggerOut,
    CtsWindowTriggerUpdate,
)

router = APIRouter(
    prefix="/rules/cts-window-triggers",
    tags=["cts-window-triggers"],
)


@router.get("", response_model=list[CtsWindowTriggerOut])
def list_cts_window_triggers(
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:read")),
) -> list[CtsWindowTrigger]:
    return db.query(CtsWindowTrigger).order_by(CtsWindowTrigger.name).all()


@router.post("", response_model=CtsWindowTriggerOut, status_code=201)
def create_cts_window_trigger(
    payload: CtsWindowTriggerCreate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
) -> CtsWindowTrigger:
    ct = CtsWindowTrigger(**payload.model_dump())
    db.add(ct)
    db.commit()
    db.refresh(ct)
    return ct


@router.put("/{ct_id}", response_model=CtsWindowTriggerOut)
def update_cts_window_trigger(
    ct_id: str,
    payload: CtsWindowTriggerUpdate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
) -> CtsWindowTrigger:
    ct = db.get(CtsWindowTrigger, ct_id)
    if ct is None:
        raise NotFoundError("CtsWindowTrigger", ct_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(ct, key, value)
    db.commit()
    db.refresh(ct)
    return ct


@router.delete("/{ct_id}", status_code=204)
def delete_cts_window_trigger(
    ct_id: str,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
) -> None:
    from backend.models.cts_window_trigger import RuleCtsWindowTrigger

    ct = db.get(CtsWindowTrigger, ct_id)
    if ct is None:
        raise NotFoundError("CtsWindowTrigger", ct_id)
    # Clean up join-table rows first.
    db.query(RuleCtsWindowTrigger).filter(
        RuleCtsWindowTrigger.cts_window_trigger_id == ct_id
    ).delete(synchronize_session=False)
    db.delete(ct)
    db.commit()
