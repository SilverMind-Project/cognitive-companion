"""
Routes notifications to configured channels based on alert level and rule config.
"""

from __future__ import annotations

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


class NotificationDispatcher:
    """Dispatches notifications to Telegram, WebSocket, eInk, TTS."""

    def __init__(
        self,
        telegram_client=None,
        ws_manager=None,
        tts_client=None,
        image_renderer=None,
    ) -> None:
        self.telegram = telegram_client
        self.ws_manager = ws_manager
        self.tts = tts_client
        self.image_renderer = image_renderer

    async def dispatch(
        self,
        alert_level: str,
        message: str,
        room_name: str,
        image_url: str | None = None,
        rule_config: dict | None = None,
    ) -> dict[str, bool]:
        """
        Route notification to configured channels based on alert_level.
        Returns dict of channel -> success.
        """
        notif_cfg = settings.get("notifications.notification_defaults", {})
        level_cfg = notif_cfg.get(alert_level, {})
        channels = level_cfg.get("channels", ["websocket"])

        results: dict[str, bool] = {}

        if "websocket" in channels and self.ws_manager:
            try:
                await self.ws_manager.broadcast({
                    "type": alert_level,
                    "message": message,
                    "room": room_name,
                })
                results["websocket"] = True
            except Exception as e:
                logger.error("ws_dispatch_failed", error=str(e))
                results["websocket"] = False

        if "telegram" in channels and self.telegram:
            try:
                targets = settings.get("notifications.telegram.targets", [])
                for target in targets:
                    if alert_level in target.get("alert_levels", []):
                        if image_url:
                            await self.telegram.send_photo(
                                target["chat_id"], image_url, caption=message
                            )
                        else:
                            await self.telegram.send_message(target["chat_id"], message)
                results["telegram"] = True
            except Exception as e:
                logger.error("telegram_dispatch_failed", error=str(e))
                results["telegram"] = False

        if "eink" in channels and self.image_renderer:
            try:
                eink_targets = rule_config.get("eink_targets") if rule_config else None
                await self.image_renderer(
                    text=message, template="alert", sensor_ids=eink_targets
                )
                results["eink"] = True
            except Exception as e:
                logger.error("eink_dispatch_failed", error=str(e))
                results["eink"] = False

        if "tts" in channels and self.tts:
            try:
                # TTS is handled by the realtime session, just log intent
                results["tts"] = True
            except Exception as e:
                logger.error("tts_dispatch_failed", error=str(e))
                results["tts"] = False

        logger.info(
            "notification_dispatched",
            alert_level=alert_level,
            room=room_name,
            channels=results,
        )
        return results
