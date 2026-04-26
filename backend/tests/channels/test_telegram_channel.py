"""Tests for multi-image Telegram notification delivery.

Covers the bug fix where only the first image was sent even when multiple
images were selected: _select_telegram_image_urls now returns a list, the
dispatcher threads it as image_urls, and TelegramChannel uses send_media_group
when more than one image is present.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, patch

import pytest

from backend.channels.builtin.telegram import TelegramChannel

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeTelegramClient:
    configured: bool = True
    send_photo: AsyncMock = field(default_factory=lambda: AsyncMock(return_value=True))
    send_media_group: AsyncMock = field(default_factory=lambda: AsyncMock(return_value=True))
    send_message: AsyncMock = field(default_factory=lambda: AsyncMock(return_value=True))


@dataclass
class FakeServices:
    telegram_client: FakeTelegramClient | None = None


_SINGLE_TARGET = [{"alert_levels": ["warning", "emergency", "info"], "chat_id": "chat_99"}]
_TWO_TARGETS = [
    {"alert_levels": ["warning"], "chat_id": "chat_1"},
    {"alert_levels": ["warning"], "chat_id": "chat_2"},
]


def _fake_image_bytes(url: str) -> bytes:
    return url.encode()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_settings(targets, max_side=1920):
    cfg = {
        "notifications.telegram.targets": targets,
        "notifications.telegram.max_image_side": max_side,
    }

    class _S:
        def get(self, key, default=None):
            return cfg.get(key, default)

    return patch("backend.channels.builtin.telegram.settings", _S())


def _patch_fetch(side_effect=None, return_value=b"img"):
    """Patch fetch_and_prepare_image so no real HTTP calls are made."""
    if side_effect is not None:
        return patch(
            "backend.channels.builtin.telegram.fetch_and_prepare_image",
            new=AsyncMock(side_effect=side_effect),
        )
    return patch(
        "backend.channels.builtin.telegram.fetch_and_prepare_image",
        new=AsyncMock(return_value=return_value),
    )


# ---------------------------------------------------------------------------
# No images -- falls back to send_message
# ---------------------------------------------------------------------------


class TestTelegramChannelNoImages:
    @pytest.mark.asyncio
    async def test_sends_text_when_no_images(self):
        client = FakeTelegramClient()
        services = FakeServices(telegram_client=client)

        with _patch_settings(_SINGLE_TARGET):
            channel = TelegramChannel()
            ok = await channel.send(
                message="hello",
                alert_level="info",
                room_name="kitchen",
                services=services,
            )

        assert ok is True
        client.send_message.assert_awaited_once_with("chat_99", "hello")
        client.send_photo.assert_not_awaited()
        client.send_media_group.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sends_text_when_image_source_none(self):
        client = FakeTelegramClient()
        services = FakeServices(telegram_client=client)

        with _patch_settings(_SINGLE_TARGET):
            channel = TelegramChannel()
            ok = await channel.send(
                message="hello",
                alert_level="info",
                room_name="kitchen",
                image_urls=[],
                services=services,
            )

        assert ok is True
        client.send_message.assert_awaited_once()
        client.send_photo.assert_not_awaited()
        client.send_media_group.assert_not_awaited()


# ---------------------------------------------------------------------------
# Single image -- uses send_photo
# ---------------------------------------------------------------------------


class TestTelegramChannelSingleImage:
    @pytest.mark.asyncio
    async def test_single_image_url_uses_send_photo(self):
        client = FakeTelegramClient()
        services = FakeServices(telegram_client=client)

        with _patch_settings(_SINGLE_TARGET), _patch_fetch(return_value=b"bytes1"):
            channel = TelegramChannel()
            ok = await channel.send(
                message="alert",
                alert_level="warning",
                room_name="living_room",
                image_urls=["https://minio/img1.jpg"],
                services=services,
            )

        assert ok is True
        client.send_photo.assert_awaited_once_with("chat_99", b"bytes1", caption="alert")
        client.send_media_group.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_legacy_image_url_uses_send_photo(self):
        """image_url (str) is still handled when image_urls is not provided."""
        client = FakeTelegramClient()
        services = FakeServices(telegram_client=client)

        with _patch_settings(_SINGLE_TARGET), _patch_fetch(return_value=b"legacy"):
            channel = TelegramChannel()
            ok = await channel.send(
                message="alert",
                alert_level="warning",
                room_name="hall",
                image_url="https://minio/legacy.jpg",
                services=services,
            )

        assert ok is True
        client.send_photo.assert_awaited_once_with("chat_99", b"legacy", caption="alert")
        client.send_media_group.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fetch_failure_falls_back_to_text(self):
        client = FakeTelegramClient()
        services = FakeServices(telegram_client=client)

        with _patch_settings(_SINGLE_TARGET), _patch_fetch(return_value=None):
            channel = TelegramChannel()
            ok = await channel.send(
                message="alert",
                alert_level="warning",
                room_name="kitchen",
                image_urls=["https://minio/broken.jpg"],
                services=services,
            )

        assert ok is True
        client.send_message.assert_awaited_once_with("chat_99", "alert")
        client.send_photo.assert_not_awaited()


# ---------------------------------------------------------------------------
# Multiple images -- uses send_media_group
# ---------------------------------------------------------------------------


class TestTelegramChannelMultipleImages:
    @pytest.mark.asyncio
    async def test_two_images_uses_send_media_group(self):
        client = FakeTelegramClient()
        services = FakeServices(telegram_client=client)

        fetched = [b"bytes_a", b"bytes_b"]
        fetch_mock = AsyncMock(side_effect=fetched)

        with _patch_settings(_SINGLE_TARGET), patch(
            "backend.channels.builtin.telegram.fetch_and_prepare_image", new=fetch_mock
        ):
            channel = TelegramChannel()
            ok = await channel.send(
                message="multi alert",
                alert_level="warning",
                room_name="backyard",
                image_urls=["https://minio/a.jpg", "https://minio/b.jpg"],
                services=services,
            )

        assert ok is True
        client.send_media_group.assert_awaited_once_with(
            "chat_99", [b"bytes_a", b"bytes_b"], caption="multi alert"
        )
        client.send_photo.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_three_images_all_sent_in_group(self):
        client = FakeTelegramClient()
        services = FakeServices(telegram_client=client)

        fetched = [b"a", b"b", b"c"]
        fetch_mock = AsyncMock(side_effect=fetched)

        with _patch_settings(_SINGLE_TARGET), patch(
            "backend.channels.builtin.telegram.fetch_and_prepare_image", new=fetch_mock
        ):
            channel = TelegramChannel()
            await channel.send(
                message="three",
                alert_level="emergency",
                room_name="garden",
                image_urls=["u1", "u2", "u3"],
                services=services,
            )

        call_args = client.send_media_group.call_args
        assert call_args[0][1] == [b"a", b"b", b"c"]

    @pytest.mark.asyncio
    async def test_partial_fetch_failure_sends_successful_images(self):
        """Images that fail to fetch are dropped; the rest still go as a group."""
        client = FakeTelegramClient()
        services = FakeServices(telegram_client=client)

        # First URL fails, second succeeds
        fetch_mock = AsyncMock(side_effect=[None, b"good"])

        with _patch_settings(_SINGLE_TARGET), patch(
            "backend.channels.builtin.telegram.fetch_and_prepare_image", new=fetch_mock
        ):
            channel = TelegramChannel()
            ok = await channel.send(
                message="alert",
                alert_level="warning",
                room_name="hall",
                image_urls=["https://minio/broken.jpg", "https://minio/good.jpg"],
                services=services,
            )

        assert ok is True
        # Only one image survived -- should use send_photo not send_media_group
        client.send_photo.assert_awaited_once_with("chat_99", b"good", caption="alert")
        client.send_media_group.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_images_fetched_once_shared_across_targets(self):
        """Fetch happens once; both targets receive the same bytes."""
        client = FakeTelegramClient()
        services = FakeServices(telegram_client=client)

        fetched = [b"x", b"y"]
        fetch_mock = AsyncMock(side_effect=fetched)

        with _patch_settings(_TWO_TARGETS), patch(
            "backend.channels.builtin.telegram.fetch_and_prepare_image", new=fetch_mock
        ):
            channel = TelegramChannel()
            await channel.send(
                message="alert",
                alert_level="warning",
                room_name="yard",
                image_urls=["https://minio/x.jpg", "https://minio/y.jpg"],
                services=services,
            )

        # fetch called twice (once per URL), not four times (once per URL per target)
        assert fetch_mock.await_count == 2
        # Both targets received the media group
        assert client.send_media_group.await_count == 2
        calls = client.send_media_group.call_args_list
        assert calls[0][0][0] == "chat_1"
        assert calls[1][0][0] == "chat_2"


# ---------------------------------------------------------------------------
# Alert level filtering
# ---------------------------------------------------------------------------


class TestTelegramChannelAlertLevelFiltering:
    @pytest.mark.asyncio
    async def test_skips_target_when_alert_level_not_in_list(self):
        client = FakeTelegramClient()
        services = FakeServices(telegram_client=client)

        targets = [{"alert_levels": ["emergency"], "chat_id": "vip"}]
        with _patch_settings(targets):
            channel = TelegramChannel()
            ok = await channel.send(
                message="hello",
                alert_level="info",
                room_name="kitchen",
                services=services,
            )

        assert ok is False
        client.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# Guard conditions
# ---------------------------------------------------------------------------


class TestTelegramChannelGuards:
    @pytest.mark.asyncio
    async def test_returns_false_without_client(self):
        services = FakeServices(telegram_client=None)
        channel = TelegramChannel()
        ok = await channel.send(message="x", alert_level="info", room_name="y", services=services)
        assert ok is False

    @pytest.mark.asyncio
    async def test_returns_false_when_client_not_configured(self):
        client = FakeTelegramClient(configured=False)
        services = FakeServices(telegram_client=client)
        channel = TelegramChannel()
        with _patch_settings(_SINGLE_TARGET):
            ok = await channel.send(
                message="x", alert_level="info", room_name="y", services=services
            )
        assert ok is False

    @pytest.mark.asyncio
    async def test_returns_false_with_no_targets(self):
        client = FakeTelegramClient()
        services = FakeServices(telegram_client=client)
        channel = TelegramChannel()
        with _patch_settings([]):
            ok = await channel.send(
                message="x", alert_level="info", room_name="y", services=services
            )
        assert ok is False
