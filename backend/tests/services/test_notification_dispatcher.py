"""Unit tests for ``NotificationDispatcher``.

Uses fake channels registered directly via ``ChannelRegistry._instances`` to
avoid depending on builtin channel side-effects.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.channels import ChannelRegistry, NotificationChannel
from backend.services import notification_dispatcher as nd_module
from backend.services.notification_dispatcher import (
    DispatchServices,
    NotificationDispatcher,
)


class _RecordingChannel(NotificationChannel):
    """Test double that records every send() call and returns a configurable
    success flag.
    """

    def __init__(self, success: bool = True) -> None:
        self.success = success
        self.calls: list[dict[str, Any]] = []

    @classmethod
    def metadata(cls):  # type: ignore[override]
        from backend.channels.base import ChannelMetadata

        return ChannelMetadata(
            channel_name="test",
            display_name="Test",
            description="recording double",
            supports_images=False,
            config_schema={},
        )

    async def send(  # type: ignore[override]
        self,
        message: str,
        alert_level: str,
        room_name: str,
        image_url: str | None = None,
        config: dict | None = None,
        services: Any = None,
    ) -> bool:
        self.calls.append(
            {
                "message": message,
                "alert_level": alert_level,
                "room_name": room_name,
                "image_url": image_url,
                "config": config,
                "services": services,
            }
        )
        return self.success


class _FakeSettings:
    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)


@pytest.fixture
def fake_registry(monkeypatch: pytest.MonkeyPatch):
    """Provide an isolated channel registry for each test."""
    original = ChannelRegistry._instances.copy()
    ChannelRegistry._instances.clear()

    def _register(name: str, channel: _RecordingChannel) -> _RecordingChannel:
        ChannelRegistry._instances[name] = channel
        return channel

    yield _register

    ChannelRegistry._instances.clear()
    ChannelRegistry._instances.update(original)


@pytest.fixture
def default_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        nd_module,
        "settings",
        _FakeSettings(
            {
                "notifications.notification_defaults": {
                    "high": {"channels": ["primary", "secondary"]},
                    "low": {"channels": ["primary"]},
                }
            }
        ),
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_dispatch_services_bag() -> None:
    d = DispatchServices(ws_manager="ws", telegram_client="tg")
    assert d.ws_manager == "ws"
    assert d.telegram_client == "tg"
    assert d.tts_client is None


def test_dispatcher_wires_services() -> None:
    dispatcher = NotificationDispatcher(telegram_client="tg", ws_manager="ws", tts_client="tts")
    services = dispatcher._dispatch_services
    assert services.telegram_client == "tg"
    assert services.ws_manager == "ws"
    assert services.tts_client == "tts"


# ---------------------------------------------------------------------------
# dispatch()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_uses_config_defaults(fake_registry, default_settings) -> None:
    primary = fake_registry("primary", _RecordingChannel())
    secondary = fake_registry("secondary", _RecordingChannel())

    dispatcher = NotificationDispatcher()
    result = await dispatcher.dispatch(alert_level="high", message="hi", room_name="Kitchen")

    assert result == {"primary": True, "secondary": True}
    assert len(primary.calls) == 1
    assert len(secondary.calls) == 1
    assert primary.calls[0]["message"] == "hi"
    assert primary.calls[0]["room_name"] == "Kitchen"


@pytest.mark.asyncio
async def test_dispatch_rule_override_wins(fake_registry, default_settings) -> None:
    primary = fake_registry("primary", _RecordingChannel())
    override = fake_registry("override", _RecordingChannel())

    dispatcher = NotificationDispatcher()
    await dispatcher.dispatch(
        alert_level="high",
        message="hi",
        room_name="Kitchen",
        rule_config={"channels": ["override"]},
    )
    assert len(primary.calls) == 0
    assert len(override.calls) == 1


@pytest.mark.asyncio
async def test_dispatch_falls_back_to_websocket(
    fake_registry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(nd_module, "settings", _FakeSettings({}))
    ws = fake_registry("websocket", _RecordingChannel())

    dispatcher = NotificationDispatcher()
    await dispatcher.dispatch(alert_level="info", message="hi", room_name="Den")
    assert len(ws.calls) == 1


@pytest.mark.asyncio
async def test_dispatch_per_channel_message_override(fake_registry, default_settings) -> None:
    primary = fake_registry("primary", _RecordingChannel())
    secondary = fake_registry("secondary", _RecordingChannel())

    dispatcher = NotificationDispatcher()
    await dispatcher.dispatch(
        alert_level="high",
        message="default",
        room_name="Kitchen",
        channel_messages={"primary": "for_primary"},
    )
    assert primary.calls[0]["message"] == "for_primary"
    assert secondary.calls[0]["message"] == "default"


@pytest.mark.asyncio
async def test_dispatch_unknown_channel_skipped(fake_registry, default_settings) -> None:
    primary = fake_registry("primary", _RecordingChannel())
    # Note: "secondary" is referenced in config but not registered.
    dispatcher = NotificationDispatcher()
    result = await dispatcher.dispatch(alert_level="high", message="hi", room_name="Kitchen")
    assert result == {"primary": True}
    assert len(primary.calls) == 1


@pytest.mark.asyncio
async def test_dispatch_propagates_failure(fake_registry, default_settings) -> None:
    primary = fake_registry("primary", _RecordingChannel(success=False))
    fake_registry("secondary", _RecordingChannel(success=True))

    dispatcher = NotificationDispatcher()
    result = await dispatcher.dispatch(alert_level="high", message="hi", room_name="Kitchen")
    assert result == {"primary": False, "secondary": True}
    assert len(primary.calls) == 1


@pytest.mark.asyncio
async def test_dispatch_passes_services_and_image(fake_registry, default_settings) -> None:
    primary = fake_registry("primary", _RecordingChannel())
    fake_registry("secondary", _RecordingChannel())

    dispatcher = NotificationDispatcher(ws_manager="WS_SENTINEL")
    await dispatcher.dispatch(
        alert_level="high",
        message="hi",
        room_name="Kitchen",
        image_url="http://example.com/img.png",
    )
    call = primary.calls[0]
    assert call["image_url"] == "http://example.com/img.png"
    assert call["services"].ws_manager == "WS_SENTINEL"


@pytest.mark.asyncio
async def test_dispatch_empty_rule_config_channels_falls_back(
    fake_registry, default_settings
) -> None:
    primary = fake_registry("primary", _RecordingChannel())
    fake_registry("secondary", _RecordingChannel())

    dispatcher = NotificationDispatcher()
    # Empty list should fall back to config defaults.
    await dispatcher.dispatch(
        alert_level="high",
        message="hi",
        room_name="Kitchen",
        rule_config={"channels": []},
    )
    assert len(primary.calls) == 1
