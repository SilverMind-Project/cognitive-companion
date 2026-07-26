"""Tests for the notification pipeline step handler."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock

import pytest

from backend.steps.builtin.notification import (
    NotificationHandler,
    _format_channel_message,
    _select_telegram_image_urls,
)


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
    event_aggregator: AsyncMock | None = None
    minio_client: object | None = None


class TestFormatChannelMessage:
    def test_returns_base_when_template_is_empty(self):
        result = _format_channel_message("", "hello", FakeTriggerContext(), {})
        assert result == "hello"

    def test_formats_template_with_message_and_room(self):
        result = _format_channel_message(
            "Alert: {{message}} in {{room_name}}",
            "fire detected",
            FakeTriggerContext(room_name="kitchen"),
            {},
        )
        assert result == "Alert: fire detected in kitchen"

    def test_formats_with_pipeline_data(self):
        result = _format_channel_message(
            "{{message}} (from {{vision_response}})",
            "alert",
            FakeTriggerContext(),
            {"vision_response": "fire visible"},
        )
        assert result == "alert (from fire visible)"

    def test_falls_back_on_key_error(self):
        result = _format_channel_message(
            "{{message}} {{nonexistent_key}}",
            "hello",
            FakeTriggerContext(),
            {},
        )
        assert result == "hello {{nonexistent_key}}"


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
                "ha_speaker_tts_template": "Spoken: {{message}}",
                "pwa_popup_text_template": "UI: {{message}}",
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
        assert call_kwargs["image_urls"] == ["https://minio/img.jpg"]

    @pytest.mark.asyncio
    async def test_uses_translation_before_non_dict_logic_response(self):
        dispatcher = AsyncMock(return_value={})
        services = FakeServiceContainer(notification_dispatcher=dispatcher)
        step = FakePipelineStep(config_json={"alert_level": "info"})
        pipeline_data = {
            "translation": "translated alert",
            "logic_response": "not-a-dict",
            "vision_response": "fallback alert",
        }

        handler = NotificationHandler()
        await handler.execute(
            step, FakeWorkflowExecution(), pipeline_data, FakeTriggerContext(), services
        )

        call_kwargs = dispatcher.dispatch.call_args[1]
        assert call_kwargs["message"] == "translated alert"

    @pytest.mark.asyncio
    async def test_additional_media_lookup_failure_does_not_fail_dispatch(self):
        dispatcher = AsyncMock(return_value={})
        aggregator = AsyncMock()
        aggregator.query_recent_media.side_effect = RuntimeError("boom")
        services = FakeServiceContainer(
            notification_dispatcher=dispatcher,
            event_aggregator=aggregator,
        )
        step = FakePipelineStep(
            config_json={
                "alert_level": "info",
                "telegram_image_source": "both",
            }
        )
        trigger = FakeTriggerContext(media_paths=["https://minio/trigger.jpg"])
        pipeline_data = {"logic_response": {"user_notification": "test"}}

        handler = NotificationHandler()
        result = await handler.execute(
            step,
            FakeWorkflowExecution(),
            pipeline_data,
            trigger,
            services,
        )

        assert result.data["notification_dispatched"] is True
        call_kwargs = dispatcher.dispatch.call_args[1]
        assert call_kwargs["image_urls"] == ["https://minio/trigger.jpg"]


# ---------------------------------------------------------------------------
# _select_telegram_image_urls -- multi-image collection
# ---------------------------------------------------------------------------


@dataclass
class FakeEventAggregator:
    recent_media: list[str] = field(default_factory=list)
    sensor_media: list[str] = field(default_factory=list)

    async def query_recent_media(self, **_kwargs) -> list[str]:
        return self.recent_media

    async def query_media_by_sensor(self, **_kwargs) -> list[str]:
        return self.sensor_media


class TestSelectTelegramImageUrls:
    @pytest.mark.asyncio
    async def test_trigger_source_returns_trigger_paths(self):
        trigger = FakeTriggerContext(media_paths=["https://minio/t1.jpg", "https://minio/t2.jpg"])
        config = {"telegram_image_source": "trigger"}
        services = FakeServiceContainer()

        urls = await _select_telegram_image_urls(config, trigger, services, {})

        assert urls == ["https://minio/t1.jpg", "https://minio/t2.jpg"]

    @pytest.mark.asyncio
    async def test_none_source_returns_empty_list(self):
        trigger = FakeTriggerContext(media_paths=["https://minio/t1.jpg"])
        config = {"telegram_image_source": "none"}
        services = FakeServiceContainer()

        urls = await _select_telegram_image_urls(config, trigger, services, {})

        assert urls == []

    @pytest.mark.asyncio
    async def test_additional_source_queries_aggregator(self):
        aggregator = FakeEventAggregator(recent_media=["https://minio/a.jpg"])
        trigger = FakeTriggerContext(media_paths=["https://minio/t.jpg"])
        config = {"telegram_image_source": "additional"}
        services = FakeServiceContainer(event_aggregator=aggregator)

        urls = await _select_telegram_image_urls(config, trigger, services, {})

        assert urls == ["https://minio/a.jpg"]

    @pytest.mark.asyncio
    async def test_both_source_combines_trigger_and_additional(self):
        aggregator = FakeEventAggregator(
            recent_media=["https://minio/extra1.jpg", "https://minio/extra2.jpg"]
        )
        trigger = FakeTriggerContext(media_paths=["https://minio/trigger.jpg"])
        config = {"telegram_image_source": "both"}
        services = FakeServiceContainer(event_aggregator=aggregator)

        urls = await _select_telegram_image_urls(config, trigger, services, {})

        assert urls == [
            "https://minio/trigger.jpg",
            "https://minio/extra1.jpg",
            "https://minio/extra2.jpg",
        ]

    @pytest.mark.asyncio
    async def test_deduplicates_across_sources(self):
        aggregator = FakeEventAggregator(
            recent_media=["https://minio/shared.jpg", "https://minio/extra.jpg"]
        )
        trigger = FakeTriggerContext(media_paths=["https://minio/shared.jpg"])
        config = {"telegram_image_source": "both"}
        services = FakeServiceContainer(event_aggregator=aggregator)

        urls = await _select_telegram_image_urls(config, trigger, services, {})

        assert urls == ["https://minio/shared.jpg", "https://minio/extra.jpg"]

    @pytest.mark.asyncio
    async def test_pipeline_source_resolves_dotted_path(self):
        trigger = FakeTriggerContext()
        config = {
            "telegram_image_source": "pipeline",
            "pipeline_image_path": "steps.media_presign_1.outputs.presigned_images",
        }
        services = FakeServiceContainer()
        pipeline_data = {
            "steps": {
                "media_presign_1": {
                    "outputs": {
                        "presigned_images": [
                            "https://minio/today.jpg",
                            "https://minio/yesterday.jpg",
                        ]
                    }
                }
            }
        }

        urls = await _select_telegram_image_urls(config, trigger, services, pipeline_data)

        assert urls == ["https://minio/today.jpg", "https://minio/yesterday.jpg"]

    @pytest.mark.asyncio
    async def test_pipeline_source_missing_path_returns_empty(self):
        trigger = FakeTriggerContext()
        config = {"telegram_image_source": "pipeline", "pipeline_image_path": ""}
        services = FakeServiceContainer()

        urls = await _select_telegram_image_urls(config, trigger, services, {})

        assert urls == []

    @pytest.mark.asyncio
    async def test_execute_passes_all_images_to_dispatch(self):
        """End-to-end: multiple trigger images reach dispatcher as image_urls list."""
        dispatcher = AsyncMock(return_value={})
        services = FakeServiceContainer(notification_dispatcher=dispatcher)
        step = FakePipelineStep(config_json={"alert_level": "info"})
        trigger = FakeTriggerContext(
            media_paths=["https://minio/img1.jpg", "https://minio/img2.jpg"]
        )
        pipeline_data = {"logic_response": {"user_notification": "test"}}

        handler = NotificationHandler()
        await handler.execute(step, FakeWorkflowExecution(), pipeline_data, trigger, services)

        call_kwargs = dispatcher.dispatch.call_args[1]
        assert call_kwargs["image_urls"] == [
            "https://minio/img1.jpg",
            "https://minio/img2.jpg",
        ]

    @pytest.mark.asyncio
    async def test_execute_passes_empty_list_when_no_images(self):
        dispatcher = AsyncMock(return_value={})
        services = FakeServiceContainer(notification_dispatcher=dispatcher)
        step = FakePipelineStep(config_json={"alert_level": "info"})
        trigger = FakeTriggerContext(media_paths=[])
        pipeline_data = {"logic_response": {"user_notification": "test"}}

        handler = NotificationHandler()
        await handler.execute(step, FakeWorkflowExecution(), pipeline_data, trigger, services)

        call_kwargs = dispatcher.dispatch.call_args[1]
        assert call_kwargs["image_urls"] == []
