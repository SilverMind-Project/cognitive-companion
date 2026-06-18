"""Routine CRUD and step-management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.core.auth import AuthContext, require_permission
from backend.routers.dependencies import get_guided_task_service
from backend.schemas.guided_task import (
    GuidedSessionOut,
    RoutineCreate,
    RoutineDetailOut,
    RoutineListOut,
    RoutineOut,
    RoutineStepsReplaceIn,
    RoutineTestRunIn,
    RoutineUpdate,
)
from backend.services.guided_task.service import GuidedTaskService

router = APIRouter(prefix="/routines", tags=["routines"])


@router.get("", response_model=RoutineListOut)
def list_routines(
    person_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    svc: GuidedTaskService = Depends(get_guided_task_service),
    _auth: AuthContext = Depends(require_permission("routines:read")),
) -> RoutineListOut:
    return svc.list_routines(person_id=person_id, limit=limit, offset=offset)


@router.get("/{routine_id}", response_model=RoutineDetailOut)
def get_routine(
    routine_id: int,
    svc: GuidedTaskService = Depends(get_guided_task_service),
    _auth: AuthContext = Depends(require_permission("routines:read")),
) -> RoutineDetailOut:
    return svc.get_routine_detail(routine_id)


@router.post("", response_model=RoutineOut, status_code=201)
def create_routine(
    payload: RoutineCreate,
    svc: GuidedTaskService = Depends(get_guided_task_service),
    _auth: AuthContext = Depends(require_permission("routines:write")),
) -> RoutineOut:
    return svc.create_routine(payload)


@router.patch("/{routine_id}", response_model=RoutineOut)
def update_routine(
    routine_id: int,
    payload: RoutineUpdate,
    svc: GuidedTaskService = Depends(get_guided_task_service),
    _auth: AuthContext = Depends(require_permission("routines:write")),
) -> RoutineOut:
    return svc.update_routine(routine_id, payload)


@router.delete("/{routine_id}", status_code=204)
def delete_routine(
    routine_id: int,
    svc: GuidedTaskService = Depends(get_guided_task_service),
    _auth: AuthContext = Depends(require_permission("routines:write")),
) -> None:
    svc.delete_routine(routine_id)


@router.put("/{routine_id}/steps", response_model=RoutineDetailOut)
def replace_routine_steps(
    routine_id: int,
    payload: RoutineStepsReplaceIn,
    svc: GuidedTaskService = Depends(get_guided_task_service),
    _auth: AuthContext = Depends(require_permission("routines:write")),
) -> RoutineDetailOut:
    return svc.replace_steps(routine_id, [s.model_dump() for s in payload.steps])


@router.post("/{routine_id}/test-run", response_model=GuidedSessionOut, status_code=201)
async def start_routine_test_run(
    routine_id: int,
    payload: RoutineTestRunIn,
    svc: GuidedTaskService = Depends(get_guided_task_service),
    _auth: AuthContext = Depends(require_permission("routines:write")),
) -> GuidedSessionOut:
    return await svc.test_run(routine_id, surface_id=payload.surface_id)
