"""Guided-task session endpoints: the caregiver console (list, detail, takeover)
and the resident's companion screen (its resident-safe state)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.core.auth import AuthContext, require_permission
from backend.routers.dependencies import get_guided_task_service
from backend.schemas.guided_task import (
    GuidedSessionAdvanceOut,
    GuidedSessionDetailOut,
    GuidedSessionListOut,
    GuidedSessionOut,
    GuidedSessionSayIn,
)
from backend.schemas.guided_task_ws import ResidentGuidedStateOut
from backend.services.guided_task.service import GuidedTaskService

router = APIRouter(prefix="/guided-sessions", tags=["guided-sessions"])


@router.get("", response_model=GuidedSessionListOut)
def list_guided_sessions(
    person_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    svc: GuidedTaskService = Depends(get_guided_task_service),
    _auth: AuthContext = Depends(require_permission("guided_sessions:read")),
) -> GuidedSessionListOut:
    return svc.list_sessions(person_id=person_id, status=status, limit=limit, offset=offset)


@router.get("/resident-state", response_model=ResidentGuidedStateOut)
async def get_resident_guided_state(
    person_id: str | None = Query(default=None),
    svc: GuidedTaskService = Depends(get_guided_task_service),
    _auth: AuthContext = Depends(require_permission("guided_sessions.resident_state:read")),
) -> ResidentGuidedStateOut:
    """The companion tablet's hydration read: what a ``guided_session_state``
    broadcast would show for the session in progress (none, when idle).

    Its own token, because a tablet must not need ``guided_sessions:read``,
    which exposes failure reasons and transcripts. No MCP twin: the agent reads
    the same session through ``get_active_guided_step``.
    """
    return ResidentGuidedStateOut(session=await svc.get_resident_state(person_id))


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
