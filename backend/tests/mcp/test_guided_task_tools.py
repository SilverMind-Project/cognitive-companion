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


@pytest.fixture
def knowledge_ingestion():
    from backend.mcp.server import _svc

    original = _svc.knowledge_ingestion
    service = AsyncMock()
    _svc.knowledge_ingestion = service
    yield service
    _svc.knowledge_ingestion = original


def test_registry_resolves_all_guided_tools() -> None:
    from backend.mcp.server import _tool_handlers

    for name in {
        "get_active_guided_step",
        "mark_guided_step_complete",
        "repeat_guided_step",
        "report_step_blocked",
        "request_caregiver_help",
        "record_resident_preference",
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
        "record_resident_preference",
    }.issubset(tools)


@pytest.mark.asyncio
async def test_record_resident_preference_writes_tagged_document(knowledge_ingestion) -> None:
    from backend.mcp.server import record_resident_preference

    doc = type("Doc", (), {"id": 42})()
    knowledge_ingestion.create_document.return_value = doc

    result = await record_resident_preference("resident-1", "Two sugars in her tea", "said during tea routine")

    assert result == {"document_id": 42, "recorded": True}
    knowledge_ingestion.create_document.assert_awaited_once()
    call_kwargs = knowledge_ingestion.create_document.call_args.kwargs
    assert call_kwargs["tags"] == ["resident_preference", "resident-1"]
    assert call_kwargs["created_by"] == "guided_companion"
    assert "Two sugars in her tea" in call_kwargs["source_text"]
    assert "said during tea routine" in call_kwargs["source_text"]


@pytest.mark.asyncio
async def test_record_resident_preference_missing_service_returns_error() -> None:
    from backend.mcp.server import _svc, record_resident_preference

    original = _svc.knowledge_ingestion
    _svc.knowledge_ingestion = None
    try:
        result = await record_resident_preference("resident-1", "Two sugars")
    finally:
        _svc.knowledge_ingestion = original

    assert "error" in result


@pytest.mark.asyncio
async def test_record_resident_preference_rejects_empty_preference(knowledge_ingestion) -> None:
    from backend.mcp.server import record_resident_preference

    result = await record_resident_preference("resident-1", "   ")

    assert "error" in result
    knowledge_ingestion.create_document.assert_not_awaited()


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
