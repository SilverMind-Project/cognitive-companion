"""Unit tests for InteractivePromptHandler step."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.steps.builtin.interactive_prompt import InteractivePromptHandler


@dataclass
class FakePipelineStep:
    """Fake PipelineStep for testing."""

    id: int
    step_type: str
    config_json: dict
    label: str | None = None


@dataclass
class FakeWorkflowExecution:
    """Fake WorkflowExecution for testing."""

    id: int
    status: str


@dataclass
class FakeTriggerContext:
    """Fake TriggerContext for testing."""

    room_name: str | None = None
    sensor_id: str | None = None


@dataclass
class FakeServiceContainer:
    """Fake ServiceContainer for testing."""

    db_factory: Mock
    notification_dispatcher: Mock | None = None
    scheduler: Mock | None = None
    interactive_response_service: Mock | None = None


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = Mock()
    session.commit = Mock()
    session.close = Mock()
    return session


@pytest.fixture
def mock_connection_manager():
    """Create a mock WebSocket connection manager."""
    manager = Mock()
    manager.broadcast = AsyncMock()
    manager.send_backend_task = AsyncMock()
    return manager


@pytest.fixture
def mock_scheduler():
    """Create a mock scheduler."""
    scheduler = Mock()
    scheduler.apscheduler = Mock()
    scheduler.apscheduler.add_job = Mock()
    return scheduler


@pytest.fixture
def mock_notification_dispatcher(mock_connection_manager):
    """Create a mock notification dispatcher.

    The handler accesses ws_manager via
    ``notification_dispatcher._dispatch_services.ws_manager``, so the
    mock must expose that attribute chain.
    """
    dispatch_services = Mock()
    dispatch_services.ws_manager = mock_connection_manager
    dispatcher = Mock()
    dispatcher._dispatch_services = dispatch_services
    # Also expose connection_manager for tests that assert on it directly
    dispatcher.connection_manager = mock_connection_manager
    return dispatcher


class TestInteractivePromptHandlerMetadata:
    """Test InteractivePromptHandler metadata."""

    def test_metadata_returns_correct_type_name(self):
        """Test that metadata returns correct type_name."""
        metadata = InteractivePromptHandler.metadata()
        assert metadata.type_name == "interactive_prompt"

    def test_metadata_returns_correct_category(self):
        """Test that metadata returns correct category."""
        metadata = InteractivePromptHandler.metadata()
        assert metadata.category == "flow"

    def test_metadata_returns_correct_icon(self):
        """Test that metadata returns correct icon."""
        metadata = InteractivePromptHandler.metadata()
        assert metadata.icon == "mdi-message-question"

    def test_metadata_config_schema_requires_at_least_one_template(self):
        """Test that config schema requires at least one template."""
        metadata = InteractivePromptHandler.metadata()
        assert "anyOf" in metadata.config_schema
        assert {"required": ["voice_prompt_template"]} in metadata.config_schema["anyOf"]
        assert {"required": ["popup_message_template"]} in metadata.config_schema["anyOf"]


class TestInteractivePromptHandlerExecute:
    """Test InteractivePromptHandler execute method."""

    @pytest.mark.asyncio
    async def test_execute_with_popup_only(
        self,
        mock_db_session,
        mock_notification_dispatcher,
        mock_scheduler,
    ):
        """Test execute with only popup message configured."""
        # Arrange
        step = FakePipelineStep(
            id=1,
            step_type="interactive_prompt",
            config_json={
                "popup_message_template": "Are you okay?",
                "countdown_seconds": 30,
                "timeout_action": "escalate",
                "output_key": "interactive_response",
                "escalate_button_text": "I need help",
                "dismiss_button_text": "I'm okay",
            },
        )
        execution = FakeWorkflowExecution(id=123, status="running")
        pipeline_data = {}
        trigger = FakeTriggerContext(room_name="living_room", sensor_id="sensor_1")

        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db_session),
            notification_dispatcher=mock_notification_dispatcher,
            scheduler=mock_scheduler,
        )

        handler = InteractivePromptHandler()

        # Act
        with patch("backend.core.template.render_template") as mock_render:
            mock_render.return_value = "Are you okay?"
            result = await handler.execute(step, execution, pipeline_data, trigger, services)

        # Assert
        assert result.success is True
        assert result.wait_until is not None
        # The executor transitions status to "waiting" after the step returns.
        # The step no longer mutates execution.status directly.

        # Verify popup message was sent
        mock_notification_dispatcher.connection_manager.broadcast.assert_called_once()
        call_args = mock_notification_dispatcher.connection_manager.broadcast.call_args[0][0]
        assert call_args["type"] == "interactive_prompt"
        assert call_args["execution_id"] == 123
        assert call_args["step_id"] == 1
        assert call_args["message"] == "Are you okay?"
        assert call_args["countdown_seconds"] == 30

        # Verify voice prompt was NOT sent
        mock_notification_dispatcher.connection_manager.send_backend_task.assert_not_called()

        # Verify timeout was scheduled
        mock_scheduler.apscheduler.add_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_voice_only(
        self,
        mock_db_session,
        mock_notification_dispatcher,
        mock_scheduler,
    ):
        """Test execute with only voice prompt configured."""
        # Arrange
        step = FakePipelineStep(
            id=2,
            step_type="interactive_prompt",
            config_json={
                "voice_prompt_template": "Do you need help?",
                "countdown_seconds": 30,
                "timeout_action": "escalate",
                "output_key": "interactive_response",
            },
        )
        execution = FakeWorkflowExecution(id=124, status="running")
        pipeline_data = {}
        trigger = FakeTriggerContext()

        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db_session),
            notification_dispatcher=mock_notification_dispatcher,
            scheduler=mock_scheduler,
        )

        handler = InteractivePromptHandler()

        # Act
        with patch("backend.core.template.render_template") as mock_render:
            mock_render.return_value = "Do you need help?"
            result = await handler.execute(step, execution, pipeline_data, trigger, services)

        # Assert
        assert result.success is True
        assert result.wait_until is not None
        # The executor transitions status to "waiting" after the step returns.
        # The step no longer mutates execution.status directly.

        # Verify voice prompt was sent
        mock_notification_dispatcher.connection_manager.send_backend_task.assert_called_once()
        call_args = mock_notification_dispatcher.connection_manager.send_backend_task.call_args
        assert call_args[1]["prompt"] == "Do you need help?"
        assert call_args[1]["metadata"]["execution_id"] == 124
        assert call_args[1]["metadata"]["step_id"] == 2

        # Voice-only path still broadcasts the enable_microphone signal so
        # the frontend can auto-enable the mic for Gemini Live replies.
        mock_notification_dispatcher.connection_manager.broadcast.assert_called_once()
        mic_call = mock_notification_dispatcher.connection_manager.broadcast.call_args[0][0]
        assert mic_call["type"] == "enable_microphone"

        # Verify timeout was scheduled
        mock_scheduler.apscheduler.add_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_both_channels(
        self,
        mock_db_session,
        mock_notification_dispatcher,
        mock_scheduler,
    ):
        """Test execute with both popup and voice channels configured."""
        # Arrange
        step = FakePipelineStep(
            id=3,
            step_type="interactive_prompt",
            config_json={
                "popup_message_template": "Are you okay?",
                "voice_prompt_template": "Do you need help?",
                "countdown_seconds": 30,
                "timeout_action": "escalate",
                "output_key": "interactive_response",
                "escalate_button_text": "I need help",
                "dismiss_button_text": "I'm okay",
            },
        )
        execution = FakeWorkflowExecution(id=125, status="running")
        pipeline_data = {}
        trigger = FakeTriggerContext()

        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db_session),
            notification_dispatcher=mock_notification_dispatcher,
            scheduler=mock_scheduler,
        )

        handler = InteractivePromptHandler()

        # Act
        with patch("backend.core.template.render_template") as mock_render:
            mock_render.side_effect = ["Are you okay?", "Do you need help?"]
            result = await handler.execute(step, execution, pipeline_data, trigger, services)

        # Assert
        assert result.success is True
        assert result.wait_until is not None
        # The executor transitions status to "waiting" after the step returns.
        # The step no longer mutates execution.status directly.

        # Both channels fire: popup broadcast + voice send + enable_microphone broadcast
        assert mock_notification_dispatcher.connection_manager.broadcast.call_count == 2
        broadcast_types = [
            call.args[0]["type"]
            for call in mock_notification_dispatcher.connection_manager.broadcast.call_args_list
        ]
        assert "interactive_prompt" in broadcast_types
        assert "enable_microphone" in broadcast_types
        mock_notification_dispatcher.connection_manager.send_backend_task.assert_called_once()

        # Verify timeout was scheduled
        mock_scheduler.apscheduler.add_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_neither_channel_configured(
        self,
        mock_db_session,
        mock_notification_dispatcher,
        mock_scheduler,
    ):
        """Test execute with neither channel configured (error case)."""
        # Arrange
        step = FakePipelineStep(
            id=4,
            step_type="interactive_prompt",
            config_json={
                "countdown_seconds": 30,
                "timeout_action": "escalate",
                "output_key": "interactive_response",
            },
        )
        execution = FakeWorkflowExecution(id=126, status="running")
        pipeline_data = {}
        trigger = FakeTriggerContext()

        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db_session),
            notification_dispatcher=mock_notification_dispatcher,
            scheduler=mock_scheduler,
        )

        handler = InteractivePromptHandler()

        # Act
        result = await handler.execute(step, execution, pipeline_data, trigger, services)

        # Assert
        assert result.success is True
        assert result.wait_until is None  # No wait since we're failing fast
        assert "interactive_response" in result.data
        assert result.data["interactive_response"]["channel"] == "error"
        assert result.data["interactive_response"]["action"] == "dismiss"
        assert (
            "No channels configured" in result.data["interactive_response"]["raw_response"]["error"]
        )

        # Verify NO channels were sent
        mock_notification_dispatcher.connection_manager.broadcast.assert_not_called()
        mock_notification_dispatcher.connection_manager.send_backend_task.assert_not_called()

        # Verify timeout was NOT scheduled
        mock_scheduler.apscheduler.add_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_with_template_rendering_error(
        self,
        mock_db_session,
        mock_notification_dispatcher,
        mock_scheduler,
    ):
        """Test execute when template rendering fails."""
        # Arrange
        step = FakePipelineStep(
            id=5,
            step_type="interactive_prompt",
            config_json={
                "popup_message_template": "Hello {{invalid_var}}",
                "countdown_seconds": 30,
                "timeout_action": "escalate",
                "output_key": "interactive_response",
            },
        )
        execution = FakeWorkflowExecution(id=127, status="running")
        pipeline_data = {}
        trigger = FakeTriggerContext()

        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db_session),
            notification_dispatcher=mock_notification_dispatcher,
            scheduler=mock_scheduler,
        )

        handler = InteractivePromptHandler()

        # Act
        with patch("backend.core.template.render_template") as mock_render:
            mock_render.side_effect = Exception("Template error")
            result = await handler.execute(step, execution, pipeline_data, trigger, services)

        # Assert
        assert result.success is True
        assert result.wait_until is None
        assert "interactive_response" in result.data
        assert result.data["interactive_response"]["channel"] == "error"
        assert result.data["interactive_response"]["action"] == "dismiss"
        assert (
            "Template rendering failed"
            in result.data["interactive_response"]["raw_response"]["error"]
        )

        # Verify NO channels were sent
        mock_notification_dispatcher.connection_manager.broadcast.assert_not_called()
        mock_notification_dispatcher.connection_manager.send_backend_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_with_popup_send_error(
        self,
        mock_db_session,
        mock_notification_dispatcher,
        mock_scheduler,
    ):
        """Test execute when popup send fails but voice succeeds."""
        # Arrange
        step = FakePipelineStep(
            id=6,
            step_type="interactive_prompt",
            config_json={
                "popup_message_template": "Are you okay?",
                "voice_prompt_template": "Do you need help?",
                "countdown_seconds": 30,
                "timeout_action": "escalate",
                "output_key": "interactive_response",
            },
        )
        execution = FakeWorkflowExecution(id=128, status="running")
        pipeline_data = {}
        trigger = FakeTriggerContext()

        # Make popup send fail
        mock_notification_dispatcher.connection_manager.broadcast.side_effect = Exception(
            "WebSocket error"
        )

        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db_session),
            notification_dispatcher=mock_notification_dispatcher,
            scheduler=mock_scheduler,
        )

        handler = InteractivePromptHandler()

        # Act
        with patch("backend.core.template.render_template") as mock_render:
            mock_render.side_effect = ["Are you okay?", "Do you need help?"]
            result = await handler.execute(step, execution, pipeline_data, trigger, services)

        # Assert
        assert result.success is True
        assert result.wait_until is not None  # Should still wait since voice succeeded
        # The executor transitions status to "waiting" after the step returns.
        # The step no longer mutates execution.status directly.

        # Popup broadcast is attempted; after voice succeeds the handler also
        # broadcasts enable_microphone. Both calls hit the failing mock but
        # are caught and logged.
        assert mock_notification_dispatcher.connection_manager.broadcast.call_count == 2
        broadcast_types = [
            call.args[0]["type"]
            for call in mock_notification_dispatcher.connection_manager.broadcast.call_args_list
        ]
        assert broadcast_types == ["interactive_prompt", "enable_microphone"]

        # Verify voice was sent successfully
        mock_notification_dispatcher.connection_manager.send_backend_task.assert_called_once()

        # Verify timeout was still scheduled
        mock_scheduler.apscheduler.add_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_both_channels_failing(
        self,
        mock_db_session,
        mock_notification_dispatcher,
        mock_scheduler,
    ):
        """Test execute when both channels fail to send."""
        # Arrange
        step = FakePipelineStep(
            id=10,
            step_type="interactive_prompt",
            config_json={
                "popup_message_template": "Are you okay?",
                "voice_prompt_template": "Do you need help?",
                "countdown_seconds": 30,
                "timeout_action": "escalate",
                "output_key": "interactive_response",
            },
        )
        execution = FakeWorkflowExecution(id=132, status="running")
        pipeline_data = {}
        trigger = FakeTriggerContext()

        # Make both channels fail
        mock_notification_dispatcher.connection_manager.broadcast.side_effect = Exception(
            "WebSocket error"
        )
        mock_notification_dispatcher.connection_manager.send_backend_task.side_effect = Exception(
            "Voice error"
        )

        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db_session),
            notification_dispatcher=mock_notification_dispatcher,
            scheduler=mock_scheduler,
        )

        handler = InteractivePromptHandler()

        # Act
        with patch("backend.core.template.render_template") as mock_render:
            mock_render.side_effect = ["Are you okay?", "Do you need help?"]
            result = await handler.execute(step, execution, pipeline_data, trigger, services)

        # Assert
        assert result.success is True
        assert result.wait_until is None  # No wait since both channels failed
        assert "interactive_response" in result.data
        assert result.data["interactive_response"]["channel"] == "error"
        assert result.data["interactive_response"]["action"] == "dismiss"
        assert (
            "All channels failed to send"
            in result.data["interactive_response"]["raw_response"]["error"]
        )

        # Verify both channels were attempted
        mock_notification_dispatcher.connection_manager.broadcast.assert_called_once()
        mock_notification_dispatcher.connection_manager.send_backend_task.assert_called_once()

        # Verify timeout was NOT scheduled since both failed
        mock_scheduler.apscheduler.add_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_with_timeout_scheduling_error(
        self,
        mock_db_session,
        mock_notification_dispatcher,
        mock_scheduler,
    ):
        """Test execute when timeout scheduling fails."""
        # Arrange
        step = FakePipelineStep(
            id=7,
            step_type="interactive_prompt",
            config_json={
                "popup_message_template": "Are you okay?",
                "countdown_seconds": 30,
                "timeout_action": "escalate",
                "output_key": "interactive_response",
            },
        )
        execution = FakeWorkflowExecution(id=129, status="running")
        pipeline_data = {}
        trigger = FakeTriggerContext()

        # Make timeout scheduling fail
        mock_scheduler.apscheduler.add_job.side_effect = Exception("Scheduler error")

        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db_session),
            notification_dispatcher=mock_notification_dispatcher,
            scheduler=mock_scheduler,
        )

        handler = InteractivePromptHandler()

        # Act
        with patch("backend.core.template.render_template") as mock_render:
            mock_render.return_value = "Are you okay?"
            result = await handler.execute(step, execution, pipeline_data, trigger, services)

        # Assert
        assert result.success is True
        assert result.wait_until is None  # No wait since timeout scheduling failed
        assert "interactive_response" in result.data
        assert result.data["interactive_response"]["channel"] == "error"
        assert result.data["interactive_response"]["action"] == "dismiss"
        assert (
            "Timeout scheduling failed"
            in result.data["interactive_response"]["raw_response"]["error"]
        )

    @pytest.mark.asyncio
    async def test_execute_with_template_variables(
        self,
        mock_db_session,
        mock_notification_dispatcher,
        mock_scheduler,
    ):
        """Test execute with template variable substitution."""
        # Arrange
        step = FakePipelineStep(
            id=8,
            step_type="interactive_prompt",
            config_json={
                "popup_message_template": "Hello {{name}}, are you in {{room_name}}?",
                "countdown_seconds": 30,
                "timeout_action": "escalate",
                "output_key": "interactive_response",
            },
        )
        execution = FakeWorkflowExecution(id=130, status="running")
        pipeline_data = {"name": "John"}
        trigger = FakeTriggerContext(room_name="bedroom")

        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db_session),
            notification_dispatcher=mock_notification_dispatcher,
            scheduler=mock_scheduler,
        )

        handler = InteractivePromptHandler()

        # Act
        with patch("backend.core.template.render_template") as mock_render:
            mock_render.return_value = "Hello John, are you in bedroom?"
            result = await handler.execute(step, execution, pipeline_data, trigger, services)

            # Verify render_template was called with correct arguments
            mock_render.assert_called_once()
            args, _kwargs = mock_render.call_args
            assert args[0] == "Hello {{name}}, are you in {{room_name}}?"
            assert args[1] == {"name": "John"}
            assert args[2] == {"room_name": "bedroom", "sensor_id": None}

        # Assert
        assert result.success is True
        assert result.wait_until is not None

    @pytest.mark.asyncio
    async def test_execute_with_custom_output_key(
        self,
        mock_db_session,
        mock_notification_dispatcher,
        mock_scheduler,
    ):
        """Test execute with custom output_key."""
        # Arrange
        step = FakePipelineStep(
            id=9,
            step_type="interactive_prompt",
            config_json={
                "popup_message_template": "Are you okay?",
                "countdown_seconds": 30,
                "timeout_action": "escalate",
                "output_key": "custom_response",
            },
        )
        execution = FakeWorkflowExecution(id=131, status="running")
        pipeline_data = {}
        trigger = FakeTriggerContext()

        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db_session),
            notification_dispatcher=mock_notification_dispatcher,
            scheduler=mock_scheduler,
        )

        handler = InteractivePromptHandler()

        # Act
        with patch("backend.core.template.render_template") as mock_render:
            mock_render.return_value = "Are you okay?"
            result = await handler.execute(step, execution, pipeline_data, trigger, services)

        # Assert
        assert result.success is True
        # Note: output_key is used when recording response, not in the initial execute

    @pytest.mark.asyncio
    async def test_execute_with_auto_escalate_enabled(
        self,
        mock_db_session,
        mock_notification_dispatcher,
        mock_scheduler,
    ):
        """Test execute with auto_escalate enabled in config.

        Verifies that the handler accepts auto_escalate config and executes
        successfully. The actual auto_escalate flag setting is handled by
        InteractiveResponseService when recording responses.
        """
        # Arrange
        step = FakePipelineStep(
            id=11,
            step_type="interactive_prompt",
            config_json={
                "popup_message_template": "Are you okay?",
                "auto_escalate": True,
                "countdown_seconds": 30,
                "timeout_action": "escalate",
                "output_key": "interactive_response",
                "escalate_button_text": "I need help",
                "dismiss_button_text": "I'm okay",
            },
        )
        execution = FakeWorkflowExecution(id=133, status="running")
        pipeline_data = {}
        trigger = FakeTriggerContext()

        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db_session),
            notification_dispatcher=mock_notification_dispatcher,
            scheduler=mock_scheduler,
        )

        handler = InteractivePromptHandler()

        # Act
        with patch("backend.core.template.render_template") as mock_render:
            mock_render.return_value = "Are you okay?"
            result = await handler.execute(step, execution, pipeline_data, trigger, services)

        # Assert
        assert result.success is True
        assert result.wait_until is not None
        # The executor transitions status to "waiting" after the step returns.
        # The step no longer mutates execution.status directly.

        # Verify popup message was sent with correct fields
        mock_notification_dispatcher.connection_manager.broadcast.assert_called_once()
        call_args = mock_notification_dispatcher.connection_manager.broadcast.call_args[0][0]
        assert call_args["type"] == "interactive_prompt"
        assert call_args["execution_id"] == 133
        assert call_args["step_id"] == 11

        # Verify timeout was scheduled
        mock_scheduler.apscheduler.add_job.assert_called_once()

        # Note: The auto_escalate flag is set by InteractiveResponseService
        # when recording responses, not by the handler during execute


class TestInteractivePromptHandlerTimeout:
    """Test InteractivePromptHandler timeout handling."""

    @pytest.mark.asyncio
    async def test_handle_timeout_creates_synthetic_response(self):
        """Test that timeout handler creates synthetic response."""
        # Arrange
        execution_id = 200
        step_id = 10
        timeout_action = "escalate"

        mock_service = Mock()
        mock_service.check_response_exists = Mock(return_value=False)
        mock_service.record_response = AsyncMock()

        services = FakeServiceContainer(
            db_factory=Mock(),
            interactive_response_service=mock_service,
        )

        # Act
        await InteractivePromptHandler._handle_timeout(
            execution_id, step_id, timeout_action, services
        )

        # Assert
        mock_service.check_response_exists.assert_called_once_with(execution_id, step_id)
        mock_service.record_response.assert_called_once()
        call_args = mock_service.record_response.call_args[1]
        assert call_args["execution_id"] == execution_id
        assert call_args["step_id"] == step_id
        assert call_args["channel"] == "timeout"
        assert call_args["action"] == timeout_action
        assert call_args["raw_response"] == {"timeout_action": timeout_action}

    @pytest.mark.asyncio
    async def test_handle_timeout_skips_if_response_exists(self):
        """Test that timeout handler skips if response already exists."""
        # Arrange
        execution_id = 201
        step_id = 11
        timeout_action = "escalate"

        mock_service = Mock()
        mock_service.check_response_exists = Mock(return_value=True)
        mock_service.record_response = AsyncMock()

        services = FakeServiceContainer(
            db_factory=Mock(),
            interactive_response_service=mock_service,
        )

        # Act
        await InteractivePromptHandler._handle_timeout(
            execution_id, step_id, timeout_action, services
        )

        # Assert
        mock_service.check_response_exists.assert_called_once_with(execution_id, step_id)
        mock_service.record_response.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_timeout_with_no_service(self):
        """Test that timeout handler handles missing service gracefully."""
        # Arrange
        execution_id = 202
        step_id = 12
        timeout_action = "escalate"

        services = FakeServiceContainer(
            db_factory=Mock(),
            interactive_response_service=None,
        )

        # Act (should not raise exception)
        await InteractivePromptHandler._handle_timeout(
            execution_id, step_id, timeout_action, services
        )

        # Assert - no exception raised

    @pytest.mark.asyncio
    async def test_handle_timeout_with_record_error(self):
        """Test that timeout handler handles record_response errors gracefully."""
        # Arrange
        execution_id = 203
        step_id = 13
        timeout_action = "escalate"

        mock_service = Mock()
        mock_service.check_response_exists = Mock(return_value=False)
        mock_service.record_response = AsyncMock(side_effect=Exception("Database error"))

        services = FakeServiceContainer(
            db_factory=Mock(),
            interactive_response_service=mock_service,
        )

        # Act (should not raise exception)
        await InteractivePromptHandler._handle_timeout(
            execution_id, step_id, timeout_action, services
        )

        # Assert - no exception raised, error was logged
