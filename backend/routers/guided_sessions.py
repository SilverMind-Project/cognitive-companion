"""Caregiver takeover endpoints for guided-task sessions."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.core.auth import AuthContext, require_permission
from backend.routers.dependencies import get_guided_task_service
from backend.schemas.guided_task import (
    GuidedSessionAdvanceOut,
    GuidedSessionDetailOut,
    GuidedSessionOut,
    GuidedSessionSayIn,
)
from backend.services.guided_task.service import GuidedTaskService

router = APIRouter(prefix="/guided-sessions", tags=["guided-sessions"])


@router.get("/{session_id}/detail", response_model=GuidedSessionDetailOut)
async def get_guided_session_detail(
    session_id: int,
    svc: GuidedTaskService = Depends(get_guided_task_service),
    _auth: AuthContext = Depends(require_permission("guided_sessions:read")),
) -> GuidedSessionDetailOut:
    return await svc.get_detail(session_id)


@router.post("/{session_id}/takeover", response_model=GuidedSessionOut)
async def begin_guided_session_takeover(
    session_id: int,
    svc: GuidedTaskService = Depends(get_guided_task_service),
    _auth: AuthContext = Depends(require_permission("guided_sessions:takeover")),
) -> GuidedSessionOut:
    return await svc.begin_takeover(session_id)


@router.post("/{session_id}/say", response_model=GuidedSessionOut)
async def say_guided_session_message(
    session_id: int,
    payload: GuidedSessionSayIn,
    svc: GuidedTaskService = Depends(get_guided_task_service),
    _auth: AuthContext = Depends(require_permission("guided_sessions:takeover")),
) -> GuidedSessionOut:
    return await svc.caregiver_say(session_id, payload.text)


@router.post("/{session_id}/advance", response_model=GuidedSessionAdvanceOut)
async def advance_guided_session_step(
    session_id: int,
    svc: GuidedTaskService = Depends(get_guided_task_service),
    _auth: AuthContext = Depends(require_permission("guided_sessions:takeover")),
) -> GuidedSessionAdvanceOut:
    result = await svc.caregiver_advance(session_id)
    return GuidedSessionAdvanceOut(**result)


@router.post("/{session_id}/complete", response_model=GuidedSessionOut)
async def complete_guided_session_takeover(
    session_id: int,
    svc: GuidedTaskService = Depends(get_guided_task_service),
    _auth: AuthContext = Depends(require_permission("guided_sessions:takeover")),
) -> GuidedSessionOut:
    return await svc.caregiver_complete(session_id)


@router.post("/{session_id}/release", response_model=GuidedSessionOut)
async def release_guided_session_takeover(
    session_id: int,
    svc: GuidedTaskService = Depends(get_guided_task_service),
    _auth: AuthContext = Depends(require_permission("guided_sessions:takeover")),
) -> GuidedSessionOut:
    return await svc.release_takeover(session_id)
