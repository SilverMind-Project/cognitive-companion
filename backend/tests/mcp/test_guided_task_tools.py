from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.core.config import settings


@pytest.fixture
def guided_service():
    from backend.mcp.server import _svc

    original = _svc.guided_task_service
    service = AsyncMock()
    _svc.guided_task_service = service
    yield service
    _svc.guided_task_service = original


def test_registry_resolves_all_guided_tools() -> None:
    from backend.mcp.server import _tool_handlers

    for name in {
        "get_active_guided_step",
        "mark_guided_step_complete",
        "repeat_guided_step",
        "report_step_blocked",
        "request_caregiver_help",
    }:
        assert name in _tool_handlers


def test_guided_tools_are_in_gemini_allowlist() -> None:
    tools = set(settings.as_list("mcp.gemini_tools"))

    assert {
        "get_active_guided_step",
        "mark_guided_step_complete",
        "repeat_guided_step",
        "report_step_blocked",
        "request_caregiver_help",
    }.issubset(tools)


@pytest.mark.asyncio
async def test_mark_complete_calls_handle_completion_with_confirmed_evidence(
    guided_service,
) -> None:
    from backend.mcp.server import mark_guided_step_complete

    guided_service.handle_completion.return_value = {"advanced": True}

    result = await mark_guided_step_complete(7, 2, note="done")

    assert result == {"advanced": True}
    guided_service.handle_completion.assert_awaited_once_with(
        7,
        evidence={"confirmed": True, "source": "agent", "step_ord": 2, "note": "done"},
    )


@pytest.mark.asyncio
async def test_mark_complete_forwards_already_done(guided_service) -> None:
    from backend.mcp.server import mark_guided_step_complete

    guided_service.handle_completion.return_value = {"advanced": True}

    result = await mark_guided_step_complete(7, 2, already_done=True)

    assert result == {"advanced": True}
    guided_service.handle_completion.assert_awaited_once_with(
        7,
        evidence={"confirmed": True, "source": "agent", "step_ord": 2, "already_done": True},
    )


@pytest.mark.asyncio
async def test_mark_complete_omits_already_done_by_default(guided_service) -> None:
    from backend.mcp.server import mark_guided_step_complete

    guided_service.handle_completion.return_value = {"advanced": True}

    await mark_guided_step_complete(7, 2)

    guided_service.handle_completion.assert_awaited_once_with(
        7,
        evidence={"confirmed": True, "source": "agent", "step_ord": 2},
    )


@pytest.mark.asyncio
async def test_get_active_step_returns_descriptor(guided_service) -> None:
    from backend.mcp.server import get_active_guided_step

    guided_service.get_active_step.return_value = {"step_ord": 1, "prompt_text": "Pour."}

    result = await get_active_guided_step(7)

    assert result == {"step_ord": 1, "prompt_text": "Pour."}
    guided_service.get_active_step.assert_awaited_once_with(7)


@pytest.mark.asyncio
async def test_repeat_step_does_not_change_state(guided_service) -> None:
    from backend.mcp.server import repeat_guided_step

    guided_service.repeat_step.return_value = {"step_ord": 1, "prompt_text": "Pour."}

    result = await repeat_guided_step(7)

    assert result == {"step_ord": 1, "prompt_text": "Pour."}
    guided_service.repeat_step.assert_awaited_once_with(7)
    guided_service.handle_completion.assert_not_called()


@pytest.mark.asyncio
async def test_request_caregiver_help_invokes_escalator(guided_service) -> None:
    from backend.mcp.server import request_caregiver_help

    guided_service.request_help.return_value = {"acknowledged": True}

    result = await request_caregiver_help(7, reason="resident_requested")

    assert result == {"acknowledged": True}
    guided_service.request_help.assert_awaited_once_with(7, "resident_requested")


@pytest.mark.asyncio
async def test_report_step_blocked_records_event(guided_service) -> None:
    from backend.mcp.server import report_step_blocked

    guided_service.report_blocked.return_value = {"acknowledged": True}

    result = await report_step_blocked(7, "confused")

    assert result == {"acknowledged": True}
    guided_service.report_blocked.assert_awaited_once_with(7, "confused")
