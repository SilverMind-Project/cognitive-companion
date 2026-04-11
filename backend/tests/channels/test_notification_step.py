"""Tests for the notification pipeline step handler."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock

import pytest

from backend.steps.builtin.notification import NotificationHandler, _format_channel_message


@dataclass
class FakeTriggerContext:
    sensor_id: str = "cam_1"
    room_name: str = "kitchen"
    media_paths: list[str] = field(default_factory=list)
    trigger_type: str = "sensor_event"
    webhook_payload: dict | None = None
    occupancy_duration_minutes: int | None = None


@dataclass
class FakePipelineStep:
    config_json: dict = field(default_factory=dict)


@dataclass
class FakeWorkflowExecution:
    id: int = 1


@dataclass
class FakeServiceContainer:
    notification_dispatcher: AsyncMock | None = None


class TestFormatChannelMessage:
    def test_returns_base_when_template_is_empty(self):
        result = _format_channel_message("", "hello", FakeTriggerContext(), {})
        assert result == "hello"

    def test_formats_template_with_message_and_room(self):
        result = _format_channel_message(
            "Alert: {message} in {room}",
            "fire detected",
            FakeTriggerContext(room_name="kitchen"),
            {},
        )
        assert result == "Alert: fire detected in kitchen"

    def test_formats_with_pipeline_data(self):
        result = _format_channel_message(
            "{message} (from {vision_response})",
            "alert",
            FakeTriggerContext(),
            {"vision_response": "fire visible"},
        )
        assert result == "alert (from fire visible)"

    def test_falls_back_on_key_error(self):
        result = _format_channel_message(
            "{message} {nonexistent_key}",
            "hello",
            FakeTriggerContext(),
            {},
        )
        assert result == "hello"


class TestNotificationHandlerMetadata:
    def test_type_name(self):
        meta = NotificationHandler.metadata()
        assert meta.type_name == "notification"

    def test_has_new_template_fields(self):
        meta = NotificationHandler.metadata()
        props = meta.config_schema["properties"]
        # New fields
        assert "ha_speaker_tts_template" in props
        assert "pwa_popup_text_template" in props
        assert "pwa_realtime_ai_template" in props
        assert "eink_template_id" in props
        assert "eink_expiry_minutes" in props
        # Legacy fields should not exist
        assert "tts_template" not in props
        assert "websocket_template" not in props
        assert "realtime_voice_template" not in props

    def test_default_config_has_new_fields(self):
        meta = NotificationHandler.metadata()
        defaults = meta.default_config
        assert "ha_speaker_tts_template" in defaults
        assert "pwa_popup_text_template" in defaults
        assert "pwa_realtime_ai_template" in defaults
        assert defaults["eink_template_id"] is None
        assert defaults["eink_expiry_minutes"] == 30


class TestNotificationHandlerExecute:
    @pytest.mark.asyncio
    async def test_dispatches_with_default_config(self):
        dispatcher = AsyncMock(return_value={"pwa_popup_text": True})
        services = FakeServiceContainer(notification_dispatcher=dispatcher)
        step = FakePipelineStep(config_json={"alert_level": "info"})
        trigger = FakeTriggerContext(room_name="living_room")
        pipeline_data = {"logic_response": {"user_notification": "Test alert"}}

        handler = NotificationHandler()
        result = await handler.execute(
            step, FakeWorkflowExecution(), pipeline_data, trigger, services
        )

        assert result.data["notification_dispatched"] is True
        dispatcher.dispatch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_when_notification_suppressed(self):
        dispatcher = AsyncMock()
        services = FakeServiceContainer(notification_dispatcher=dispatcher)
        step = FakePipelineStep()
        pipeline_data = {"notification_suppressed": True}

        handler = NotificationHandler()
        result = await handler.execute(
            step, FakeWorkflowExecution(), pipeline_data, FakeTriggerContext(), services
        )

        assert result.data["notification_dispatched"] is False
        dispatcher.dispatch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_passes_eink_template_id_and_expiry(self):
        dispatcher = AsyncMock(return_value={"eink": True})
        services = FakeServiceContainer(notification_dispatcher=dispatcher)
        step = FakePipelineStep(
            config_json={
                "alert_level": "warning",
                "channels": ["eink"],
                "eink_template_id": 3,
                "eink_expiry_minutes": 45,
                "eink_targets": ["hallway_display"],
            }
        )
        pipeline_data = {"logic_response": {"user_notification": "Alert"}}

        handler = NotificationHandler()
        await handler.execute(
            step, FakeWorkflowExecution(), pipeline_data, FakeTriggerContext(), services
        )

        call_kwargs = dispatcher.dispatch.call_args[1]
        assert call_kwargs["rule_config"]["eink_template_id"] == 3
        assert call_kwargs["rule_config"]["eink_expiry_minutes"] == 45
        assert call_kwargs["rule_config"]["eink_targets"] == ["hallway_display"]

    @pytest.mark.asyncio
    async def test_builds_channel_messages_from_templates(self):
        dispatcher = AsyncMock(return_value={})
        services = FakeServiceContainer(notification_dispatcher=dispatcher)
        step = FakePipelineStep(
            config_json={
                "alert_level": "info",
                "ha_speaker_tts_template": "Spoken: {message}",
                "pwa_popup_text_template": "UI: {message}",
            }
        )
        pipeline_data = {"logic_response": {"user_notification": "hello"}}

        handler = NotificationHandler()
        await handler.execute(
            step, FakeWorkflowExecution(), pipeline_data, FakeTriggerContext(), services
        )

        call_kwargs = dispatcher.dispatch.call_args[1]
        channel_messages = call_kwargs["channel_messages"]
        assert channel_messages["ha_speaker_tts"] == "Spoken: hello"
        assert (
            channel_messages["pwa_tts_announcement"] == "Spoken: hello"
        )  # reuses speaker template
        assert channel_messages["pwa_popup_text"] == "UI: hello"

    @pytest.mark.asyncio
    async def test_cooloff_triggered_by_default(self):
        dispatcher = AsyncMock(return_value={})
        services = FakeServiceContainer(notification_dispatcher=dispatcher)
        step = FakePipelineStep(config_json={"alert_level": "info"})
        pipeline_data = {"logic_response": {"user_notification": "test"}}

        handler = NotificationHandler()
        result = await handler.execute(
            step, FakeWorkflowExecution(), pipeline_data, FakeTriggerContext(), services
        )

        assert result.data.get("_cooloff_triggered") is True

    @pytest.mark.asyncio
    async def test_cooloff_not_triggered_when_disabled(self):
        dispatcher = AsyncMock(return_value={})
        services = FakeServiceContainer(notification_dispatcher=dispatcher)
        step = FakePipelineStep(config_json={"alert_level": "info", "trigger_cooloff": False})
        pipeline_data = {"logic_response": {"user_notification": "test"}}

        handler = NotificationHandler()
        result = await handler.execute(
            step, FakeWorkflowExecution(), pipeline_data, FakeTriggerContext(), services
        )

        assert "_cooloff_triggered" not in result.data

    @pytest.mark.asyncio
    async def test_returns_false_without_dispatcher(self):
        services = FakeServiceContainer(notification_dispatcher=None)
        step = FakePipelineStep()

        handler = NotificationHandler()
        result = await handler.execute(
            step, FakeWorkflowExecution(), {}, FakeTriggerContext(), services
        )

        assert result.data["notification_dispatched"] is False

    @pytest.mark.asyncio
    async def test_uses_image_from_trigger_media(self):
        dispatcher = AsyncMock(return_value={})
        services = FakeServiceContainer(notification_dispatcher=dispatcher)
        step = FakePipelineStep(config_json={"alert_level": "info"})
        trigger = FakeTriggerContext(media_paths=["https://minio/img.jpg"])
        pipeline_data = {"logic_response": {"user_notification": "test"}}

        handler = NotificationHandler()
        await handler.execute(step, FakeWorkflowExecution(), pipeline_data, trigger, services)

        call_kwargs = dispatcher.dispatch.call_args[1]
        assert call_kwargs["image_url"] == "https://minio/img.jpg"
