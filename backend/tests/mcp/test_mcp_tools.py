"""Tests for MCP tool functions (timeline, reports, sessions)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# Ensure all models are registered
import backend.models  # noqa: F401


@pytest.fixture
def svc():
    """Access the MCP service container, reset after each test."""
    from backend.mcp.server import _svc

    yield _svc
    # Reset timeline/session/report refs after each test
    _svc.activity_timeline = None
    _svc.activity_session = None
    _svc.daily_report = None
    _svc.interactive_response = None


class TestGetPersonTimeline:
    """Tests for get_person_timeline MCP tool."""

    @pytest.mark.asyncio
    async def test_returns_timeline_events(self, svc):
        """Should return timeline events from ActivityTimelineService."""
        mock_service = MagicMock()
        mock_service.get_timeline.return_value = [
            {
                "timestamp": "2026-04-17T10:00:00",
                "event_type": "activity_detected",
                "person_id": "person123",
                "person_name": "Test Person",
                "activity_type": "sleep",
                "room_name": "bedroom",
                "metadata": {"confidence": 0.95},
                "source": "activity",
            }
        ]
        svc.activity_timeline = mock_service

        from backend.mcp.server import get_person_timeline

        result = await get_person_timeline("person123", minutes=60)

        assert len(result) == 1
        assert result[0]["event_type"] == "activity_detected"
        assert result[0]["activity_type"] == "sleep"
        mock_service.get_timeline.assert_called_once()
        call_kwargs = mock_service.get_timeline.call_args.kwargs
        assert call_kwargs["person_id"] == "person123"
        assert call_kwargs["limit"] == 200

    @pytest.mark.asyncio
    async def test_returns_error_when_service_unavailable(self, svc):
        """Should return error dict when timeline service is not available."""
        svc.activity_timeline = None

        from backend.mcp.server import get_person_timeline

        result = await get_person_timeline("person123")
        assert result == [{"error": "Timeline service not available"}]


class TestGetDailyReport:
    """Tests for get_daily_report MCP tool."""

    @pytest.mark.asyncio
    async def test_returns_existing_report(self, svc):
        """Should return existing report without generating."""
        mock_service = MagicMock()
        mock_service.get_report.return_value = {
            "person_id": "person123",
            "report_date": "2026-04-17",
            "status": "complete",
            "sleep_total_minutes": 480,
        }
        svc.daily_report = mock_service

        from backend.mcp.server import get_daily_report

        result = await get_daily_report("person123", "2026-04-17")

        assert result["person_id"] == "person123"
        assert result["status"] == "complete"
        assert result["sleep_total_minutes"] == 480
        mock_service.get_report.assert_called_once_with(
            person_id="person123", date="2026-04-17"
        )
        mock_service.generate_daily_report.assert_not_called()

    @pytest.mark.asyncio
    async def test_generates_report_when_missing(self, svc):
        """Should generate report when none exists for the date."""
        mock_service = MagicMock()
        mock_service.get_report.return_value = None
        mock_service.generate_daily_report.return_value = {
            "person_id": "person123",
            "report_date": "2026-04-17",
            "status": "complete",
            "sleep_total_minutes": 420,
        }
        svc.daily_report = mock_service

        with patch(
            "backend.mcp.server.settings",
            {"get": lambda k, d: "America/New_York"},
        ):
            from backend.mcp.server import get_daily_report

            result = await get_daily_report("person123", "2026-04-17")

        assert result["status"] == "complete"
        mock_service.generate_daily_report.assert_called_once()
        call_kwargs = mock_service.generate_daily_report.call_args.kwargs
        assert call_kwargs["person_id"] == "person123"
        assert call_kwargs["date"] == "2026-04-17"
        assert call_kwargs["tz_name"] == "America/New_York"

    @pytest.mark.asyncio
    async def test_returns_error_when_service_unavailable(self, svc):
        """Should return error dict when daily report service is not available."""
        svc.daily_report = None

        from backend.mcp.server import get_daily_report

        result = await get_daily_report("person123", "2026-04-17")
        assert result == {"error": "Daily report service not available"}


class TestGetOpenSessions:
    """Tests for get_open_sessions MCP tool."""

    @pytest.mark.asyncio
    async def test_returns_open_sessions(self, svc):
        """Should return open sessions from ActivitySessionService."""
        mock_service = MagicMock()
        mock_service.get_open_sessions.return_value = [
            {
                "session_id": "person123_sleep_2026-04-17T02:00:00",
                "person_id": "person123",
                "activity_type": "sleep",
                "room_name": "bedroom",
                "opened_at": datetime.now(UTC) - timedelta(hours=6),
                "timeout_minutes": 720,
            }
        ]
        svc.activity_session = mock_service

        from backend.mcp.server import get_open_sessions

        result = await get_open_sessions("person123")

        assert len(result) == 1
        assert result[0]["activity_type"] == "sleep"
        mock_service.get_open_sessions.assert_called_once_with(person_id="person123")

    @pytest.mark.asyncio
    async def test_returns_all_sessions_when_no_person_id(self, svc):
        """Should return all open sessions when person_id is not provided."""
        mock_service = MagicMock()
        mock_service.get_open_sessions.return_value = []
        svc.activity_session = mock_service

        from backend.mcp.server import get_open_sessions

        result = await get_open_sessions()

        assert result == []
        mock_service.get_open_sessions.assert_called_once_with(person_id=None)

    @pytest.mark.asyncio
    async def test_returns_error_when_service_unavailable(self, svc):
        """Should return error dict when session service is not available."""
        svc.activity_session = None

        from backend.mcp.server import get_open_sessions

        result = await get_open_sessions()
        assert result == [{"error": "Activity session service not available"}]


class TestSubmitUserResponse:
    """Tests for submit_user_response MCP tool."""

    @pytest.mark.asyncio
    async def test_valid_call_with_needs_help_true(self, svc):
        """Should map needs_help=True to action='escalate' and record response."""
        from unittest.mock import AsyncMock

        from backend.models.interactive_response import InteractiveResponse

        mock_service = MagicMock()
        mock_response = InteractiveResponse(
            id=1,
            execution_id=123,
            step_id=456,
            channel="pwa_realtime_ai",
            action="escalate",
            timestamp=datetime.now(UTC),
            raw_response_json={"needs_help": True, "user_statement": "I fell down"},
        )
        mock_service.record_response = AsyncMock(return_value=mock_response)
        svc.interactive_response = mock_service

        from backend.mcp.server import submit_user_response

        result = await submit_user_response(
            execution_id=123,
            step_id=456,
            needs_help=True,
            user_statement="I fell down",
        )

        assert result["success"] is True
        assert result["action"] == "escalate"
        mock_service.record_response.assert_called_once()
        call_kwargs = mock_service.record_response.call_args.kwargs
        assert call_kwargs["execution_id"] == 123
        assert call_kwargs["step_id"] == 456
        assert call_kwargs["channel"] == "pwa_realtime_ai"
        assert call_kwargs["action"] == "escalate"
        assert call_kwargs["raw_response"]["needs_help"] is True
        assert call_kwargs["raw_response"]["user_statement"] == "I fell down"

    @pytest.mark.asyncio
    async def test_valid_call_with_needs_help_false(self, svc):
        """Should map needs_help=False to action='dismiss' and record response."""
        from unittest.mock import AsyncMock

        from backend.models.interactive_response import InteractiveResponse

        mock_service = MagicMock()
        mock_response = InteractiveResponse(
            id=2,
            execution_id=123,
            step_id=456,
            channel="pwa_realtime_ai",
            action="dismiss",
            timestamp=datetime.now(UTC),
            raw_response_json={"needs_help": False},
        )
        mock_service.record_response = AsyncMock(return_value=mock_response)
        svc.interactive_response = mock_service

        from backend.mcp.server import submit_user_response

        result = await submit_user_response(
            execution_id=123,
            step_id=456,
            needs_help=False,
        )

        assert result["success"] is True
        assert result["action"] == "dismiss"
        mock_service.record_response.assert_called_once()
        call_kwargs = mock_service.record_response.call_args.kwargs
        assert call_kwargs["action"] == "dismiss"
        assert call_kwargs["raw_response"]["needs_help"] is False
        assert "user_statement" not in call_kwargs["raw_response"]

    @pytest.mark.asyncio
    async def test_with_user_statement_provided(self, svc):
        """Should store user_statement in raw_response when provided."""
        from unittest.mock import AsyncMock

        from backend.models.interactive_response import InteractiveResponse

        mock_service = MagicMock()
        mock_response = InteractiveResponse(
            id=3,
            execution_id=123,
            step_id=456,
            channel="pwa_realtime_ai",
            action="escalate",
            timestamp=datetime.now(UTC),
            raw_response_json={"needs_help": True, "user_statement": "Help me please"},
        )
        mock_service.record_response = AsyncMock(return_value=mock_response)
        svc.interactive_response = mock_service

        from backend.mcp.server import submit_user_response

        result = await submit_user_response(
            execution_id=123,
            step_id=456,
            needs_help=True,
            user_statement="Help me please",
        )

        assert result["success"] is True
        call_kwargs = mock_service.record_response.call_args.kwargs
        assert call_kwargs["raw_response"]["user_statement"] == "Help me please"

    @pytest.mark.asyncio
    async def test_missing_execution_id(self, svc):
        """Should return error when execution_id is invalid."""
        svc.interactive_response = MagicMock()

        from backend.mcp.server import submit_user_response

        result = await submit_user_response(
            execution_id=0,  # Invalid
            step_id=456,
            needs_help=True,
        )

        assert "error" in result
        assert "execution_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_step_id(self, svc):
        """Should return error when step_id is invalid."""
        svc.interactive_response = MagicMock()

        from backend.mcp.server import submit_user_response

        result = await submit_user_response(
            execution_id=123,
            step_id=-1,  # Invalid
            needs_help=True,
        )

        assert "error" in result
        assert "step_id" in result["error"]

    @pytest.mark.asyncio
    async def test_service_unavailable(self, svc):
        """Should return error when interactive_response service is not available."""
        svc.interactive_response = None

        from backend.mcp.server import submit_user_response

        result = await submit_user_response(
            execution_id=123,
            step_id=456,
            needs_help=True,
        )

        assert "error" in result
        assert "not available" in result["error"]

    @pytest.mark.asyncio
    async def test_service_error_handling(self, svc):
        """Should catch and return error when service raises exception."""
        from unittest.mock import AsyncMock

        mock_service = MagicMock()
        mock_service.record_response = AsyncMock(side_effect=ValueError("Invalid data"))
        svc.interactive_response = mock_service

        from backend.mcp.server import submit_user_response

        result = await submit_user_response(
            execution_id=123,
            step_id=456,
            needs_help=True,
        )

        assert "error" in result
        assert "Validation error" in result["error"]

    @pytest.mark.asyncio
    async def test_duplicate_response_handling(self, svc):
        """Should return success for duplicate responses (idempotent)."""
        from unittest.mock import AsyncMock

        mock_service = MagicMock()
        mock_service.record_response = AsyncMock(return_value=None)  # Indicates duplicate
        svc.interactive_response = mock_service

        from backend.mcp.server import submit_user_response

        result = await submit_user_response(
            execution_id=123,
            step_id=456,
            needs_help=True,
        )

        assert result["success"] is True
        assert "duplicate" in result["message"].lower()
