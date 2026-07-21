"""DL-M04 Part D: MCP allowlist coverage + router/MCP parity for the
activity-ledger query surface (get_daily_report, get_person_timeline,
get_open_sessions).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.core.config import settings


def test_ledger_tools_are_in_gemini_allowlist() -> None:
    tools = set(settings.as_list("mcp.gemini_tools"))
    assert {"get_daily_report", "get_person_timeline", "get_open_sessions"}.issubset(tools)


def test_registry_resolves_all_ledger_tools() -> None:
    from backend.mcp.server import _tool_handlers

    for name in {"get_daily_report", "get_person_timeline", "get_open_sessions"}:
        assert name in _tool_handlers


@pytest.fixture
def daily_report_service():
    from backend.mcp.server import _svc

    original = _svc.daily_report
    service = MagicMock()
    _svc.daily_report = service
    yield service
    _svc.daily_report = original


@pytest.fixture
def activity_timeline_service():
    from backend.mcp.server import _svc

    original = _svc.activity_timeline
    service = AsyncMock()
    _svc.activity_timeline = service
    yield service
    _svc.activity_timeline = original


@pytest.fixture
def activity_session_service():
    from backend.mcp.server import _svc

    original = _svc.activity_session
    service = MagicMock()
    _svc.activity_session = service
    yield service
    _svc.activity_session = original


def _sample_report(person_id: str, date: str) -> dict:
    return {
        "person_id": person_id,
        "report_date": date,
        "tz_name": "UTC",
        "generated_at": datetime.now(UTC),
        "sleep": {"total_minutes": 0, "session_count": 0, "quality_score": 0.0, "disruptions": 0},
        "meals": {"prep_count": 0, "eating_count": 0, "avg_duration_minutes": None},
        "medication": {"doses_taken": 0, "doses_due": 3, "adherence_pct": 0.0},
        "bathroom_visits": {"visit_count": 0, "total_minutes": 0},
        "exercise": {"session_count": 0, "total_minutes": 0},
        "tv": {"session_count": 1, "total_minutes": 45},
        "room_time": {"distribution": {}, "total_minutes": 0},
        "summary_text": None,
        "wellness_score": 80.0,
        "wellness_alerts": [],
    }


class TestGetDailyReportParity:
    async def test_mcp_falls_back_to_generate_with_same_args_as_router(
        self, daily_report_service, monkeypatch
    ):
        from backend.mcp.server import get_daily_report
        from backend.routers.activities import get_daily_report as router_get_daily_report
        from backend.schemas.activity import DailyReportQueryParams

        daily_report_service.get_report.return_value = None
        report = _sample_report("mom", "2026-06-01")
        daily_report_service.generate_daily_report = AsyncMock(return_value=report)

        mcp_result = await get_daily_report(person_id="mom", date="2026-06-01")
        assert mcp_result == report

        import backend.main as main_module

        monkeypatch.setattr(
            main_module.app.state, "daily_report_service", daily_report_service, raising=False
        )
        router_result = await router_get_daily_report(
            person_id="mom",
            date="2026-06-01",
            params=DailyReportQueryParams(),
            db=None,
            _auth=None,
        )

        # Both adapters read the same service method with the same
        # identifying args; only the BFF also passes tz_name/include_* from
        # query params and returns a validated envelope.
        assert daily_report_service.generate_daily_report.call_count == 2
        for call in daily_report_service.generate_daily_report.call_args_list:
            assert call.kwargs["person_id"] == "mom"
            assert call.kwargs["date"] == "2026-06-01"
        assert router_result.tv == {"session_count": 1, "total_minutes": 45}

    async def test_mcp_cached_report_shape_validates_against_wire_schema(
        self, daily_report_service
    ):
        """Regression: get_report used to return a shape DailyReportOut could
        not validate (bare-int sleep, no tv/wellness_score); the MCP tool
        returns get_report's dict directly with no schema check, so this
        pinned the divergence from the caller's side."""
        from backend.mcp.server import get_daily_report
        from backend.schemas.activity import DailyReportOut

        report = _sample_report("mom", "2026-06-01")
        daily_report_service.get_report.return_value = report

        result = await get_daily_report(person_id="mom", date="2026-06-01")

        assert result == report
        DailyReportOut(**result)  # must not raise


class TestGetPersonTimelineParity:
    async def test_mcp_and_router_call_the_same_service_method(
        self, activity_timeline_service, monkeypatch
    ):
        from backend.mcp.server import get_person_timeline
        from backend.routers.activities import get_activity_timeline as router_get_timeline

        activity_timeline_service.get_timeline.return_value = [{"kind": "session"}]

        import backend.main as main_module

        monkeypatch.setattr(
            main_module.app.state,
            "activity_timeline_service",
            activity_timeline_service,
            raising=False,
        )

        mcp_result = await get_person_timeline(person_id="mom", minutes=60)
        router_result = await router_get_timeline(
            person_id="mom",
            start_time=None,
            end_time=None,
            limit=100,
            event_types=None,
            db=None,
            _auth=None,
        )

        assert mcp_result == [{"kind": "session"}]
        assert router_result == [{"kind": "session"}]
        assert activity_timeline_service.get_timeline.call_count == 2
        for call in activity_timeline_service.get_timeline.call_args_list:
            assert call.kwargs["person_id"] == "mom"


class TestGetOpenSessionsParity:
    async def test_mcp_and_router_call_the_same_service_method(
        self, activity_session_service, monkeypatch
    ):
        from backend.mcp.server import get_open_sessions as mcp_get_open_sessions
        from backend.routers.activities import list_open_sessions as router_list_open_sessions

        activity_session_service.get_open_sessions.return_value = [
            {"activity_type": "watching_tv"}
        ]

        import backend.main as main_module

        monkeypatch.setattr(
            main_module.app.state,
            "activity_session_service",
            activity_session_service,
            raising=False,
        )

        mcp_result = await mcp_get_open_sessions(person_id="mom")
        router_result = router_list_open_sessions(person_id="mom", db=None, _auth=None)

        assert mcp_result == [{"activity_type": "watching_tv"}]
        assert router_result == [{"activity_type": "watching_tv"}]
        assert activity_session_service.get_open_sessions.call_count == 2
        for call in activity_session_service.get_open_sessions.call_args_list:
            assert call.kwargs["person_id"] == "mom"
