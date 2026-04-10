"""Tests for the E-Ink display notification channel."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from backend.channels.builtin.eink import EInkChannel


@dataclass
class FakeServices:
    image_renderer: AsyncMock = None


def _make_renderer() -> AsyncMock:
    return AsyncMock(return_value=["hallway_display"])


class TestEInkMetadata:
    def test_channel_name(self):
        meta = EInkChannel.metadata()
        assert meta.channel_name == "eink"

    def test_has_template_and_expiry_in_schema(self):
        meta = EInkChannel.metadata()
        props = meta.config_schema["properties"]
        assert "eink_targets" in props
        assert "eink_template_id" in props
        assert "eink_expiry_minutes" in props


class TestEInkSend:
    @pytest.mark.asyncio
    async def test_renders_with_defaults(self):
        renderer = _make_renderer()
        services = FakeServices(image_renderer=renderer)

        channel = EInkChannel()
        result = await channel.send(
            message="Lunch reminder",
            alert_level="reminder",
            room_name="kitchen",
            services=services,
        )

        assert result is True
        renderer.assert_awaited_once_with(
            text="Lunch reminder",
            template="alert",
            template_id=None,
            sensor_ids=None,
            expires_in_minutes=30,
        )

    @pytest.mark.asyncio
    async def test_passes_template_id_and_expiry(self):
        renderer = _make_renderer()
        services = FakeServices(image_renderer=renderer)

        channel = EInkChannel()
        result = await channel.send(
            message="Alert",
            alert_level="warning",
            room_name="bedroom",
            config={
                "eink_targets": ["hallway_display"],
                "eink_template_id": 5,
                "eink_expiry_minutes": 60,
            },
            services=services,
        )

        assert result is True
        renderer.assert_awaited_once_with(
            text="Alert",
            template="alert",
            template_id=5,
            sensor_ids=["hallway_display"],
            expires_in_minutes=60,
        )

    @pytest.mark.asyncio
    async def test_uses_custom_expiry_only(self):
        renderer = _make_renderer()
        services = FakeServices(image_renderer=renderer)

        channel = EInkChannel()
        await channel.send(
            message="Hello",
            alert_level="info",
            room_name="room",
            config={"eink_expiry_minutes": 15},
            services=services,
        )

        renderer.assert_awaited_once()
        call_kwargs = renderer.call_args[1]
        assert call_kwargs["expires_in_minutes"] == 15
        assert call_kwargs["template_id"] is None

    @pytest.mark.asyncio
    async def test_fails_without_renderer(self):
        services = FakeServices(image_renderer=None)

        channel = EInkChannel()
        result = await channel.send(
            message="Test", alert_level="info", room_name="room", services=services,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_fails_on_renderer_error(self):
        renderer = AsyncMock(side_effect=RuntimeError("render failed"))
        services = FakeServices(image_renderer=renderer)

        channel = EInkChannel()
        result = await channel.send(
            message="Test", alert_level="info", room_name="room", services=services,
        )
        assert result is False
