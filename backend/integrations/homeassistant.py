"""
Home Assistant integration - rooms, sensors, occupancy time-series, announcements.

Provides:
- Room discovery from HA areas
- Sensor import from HA entities
- Time-series state history queries with noise smoothing
- Announcement / media playback on smart speakers
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from httpx_ws import aconnect_ws

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


class HomeAssistantClient:
    """Async client for the Home Assistant REST API."""

    def __init__(self) -> None:
        self.base_url: str = settings.as_str("homeassistant.url").rstrip("/")
        self.token: str = settings.as_str("homeassistant.token")
        self._headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.token)

    # ------------------------------------------------------------------
    # Room / area discovery
    # ------------------------------------------------------------------

    async def get_areas(self) -> list[dict[str, Any]]:
        """Fetch all areas (rooms) from Home Assistant.

        Returns list of ``{"area_id": ..., "name": ..., "floor": ...}``.
        """
        if not self.configured:
            logger.warning("homeassistant_not_configured")
            return []

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{self.base_url}/api/template",
                    headers=self._headers,
                    json={"template": "{{ areas() | list }}"},
                )
                resp.raise_for_status()
                area_ids = _parse_template_list(resp.text)

                areas: list[dict[str, Any]] = []
                for area_id in area_ids:
                    detail = await self._get_area_detail(client, area_id)
                    if detail:
                        areas.append(detail)
                return areas
        except Exception:
            logger.exception("ha_get_areas_error")
            return []

    async def _get_area_detail(
        self, client: httpx.AsyncClient, area_id: str
    ) -> dict[str, Any] | None:
        """Get area name and optional floor via template API."""
        try:
            resp = await client.post(
                f"{self.base_url}/api/template",
                headers=self._headers,
                json={
                    "template": (
                        "{{ area_name('" + area_id + "') }}|{{ area_id('" + area_id + "') }}"
                    )
                },
            )
            resp.raise_for_status()
            parts = resp.text.strip().split("|")
            return {
                "area_id": area_id,
                "name": parts[0].strip() if parts else area_id,
            }
        except Exception:
            logger.warning("ha_area_detail_error", area_id=area_id)
            return None

    # ------------------------------------------------------------------
    # Sensor discovery
    # ------------------------------------------------------------------

    async def get_entities_for_area(self, area_id: str) -> list[dict[str, Any]]:
        """Get all entities belonging to an area.

        Useful for discovering sensors (mr60bha2, light sensors, etc.)
        that are configured in HA via ESPHome.
        """
        if not self.configured:
            return []

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{self.base_url}/api/template",
                    headers=self._headers,
                    json={"template": "{{ area_entities('" + area_id + "') | list }}"},
                )
                resp.raise_for_status()
                entity_ids = _parse_template_list(resp.text)

                entities: list[dict[str, Any]] = []
                for eid in entity_ids:
                    state = await self.get_entity_state(eid)
                    if state:
                        entities.append(state)
                return entities
        except Exception:
            logger.exception("ha_get_entities_error", area_id=area_id)
            return []

    # ------------------------------------------------------------------
    # Entity state
    # ------------------------------------------------------------------

    async def get_entity_state(self, entity_id: str) -> dict[str, Any] | None:
        """Get the current state of a single entity."""
        if not self.configured:
            return None

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.base_url}/api/states/{entity_id}",
                    headers=self._headers,
                )
                if resp.status_code == 200:
                    return resp.json()
                return None
        except Exception:
            logger.warning("ha_entity_state_error", entity_id=entity_id)
            return None

    async def get_person_info_state(self, sensor_id: str) -> str | None:
        """Get person presence binary sensor state for an MR60BHA2 sensor."""
        entity_id = f"binary_sensor.{sensor_id}_person_information"
        state = await self.get_entity_state(entity_id)
        return state.get("state") if state else None

    async def get_distance_state(self, sensor_id: str) -> str | None:
        """Get distance-to-detection-object state for an MR60BHA2 sensor."""
        entity_id = f"sensor.{sensor_id}_distance_to_detection_object"
        state = await self.get_entity_state(entity_id)
        return state.get("state") if state else None

    # ------------------------------------------------------------------
    # Time-series history with noise smoothing
    # ------------------------------------------------------------------

    async def get_state_history(
        self,
        entity_id: str,
        hours: float = 1.0,
        significant_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Fetch recent state history for an entity.

        Returns list of ``{"state": ..., "last_changed": ..., "last_updated": ...}``.
        """
        if not self.configured:
            return []

        start = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
        params: dict[str, Any] = {
            "filter_entity_id": entity_id,
            "significant_changes_only": int(significant_only),
            "minimal_response": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{self.base_url}/api/history/period/{start}",
                    headers=self._headers,
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
                if data and isinstance(data, list) and data[0]:
                    return data[0]
                return []
        except Exception:
            logger.exception("ha_history_error", entity_id=entity_id)
            return []

    def smooth_occupancy(
        self,
        history: list[dict[str, Any]],
        min_gap_seconds: int = 120,
    ) -> list[dict[str, str]]:
        """Smooth occupancy time-series by filling short gaps.

        If a single "off" reading is surrounded by "on" readings within
        ``min_gap_seconds``, treat it as continuously occupied. This removes
        noise from brief sensor dropouts.

        Returns list of ``{"state": "on"|"off", "start": iso, "end": iso}``.
        """
        if not history:
            return []

        # Build raw intervals
        intervals: list[dict[str, Any]] = []
        for entry in history:
            state = entry.get("state", "").lower()
            ts_str = entry.get("last_changed") or entry.get("last_updated", "")
            if state in ("on", "off") and ts_str:
                intervals.append({"state": state, "time": ts_str})

        if not intervals:
            return []

        # Fill short gaps: if an "off" is < min_gap_seconds and bracketed by "on", flip it
        smoothed = list(intervals)
        for i in range(1, len(smoothed) - 1):
            if smoothed[i]["state"] == "off":
                prev_t = _parse_ts(smoothed[i - 1]["time"])
                next_t = _parse_ts(smoothed[i + 1]["time"])
                curr_t = _parse_ts(smoothed[i]["time"])
                if (
                    prev_t
                    and next_t
                    and curr_t
                    and smoothed[i - 1]["state"] == "on"
                    and smoothed[i + 1]["state"] == "on"
                    and (next_t - curr_t).total_seconds() < min_gap_seconds
                ):
                    smoothed[i]["state"] = "on"

        # Collapse consecutive same-state entries into ranges
        ranges: list[dict[str, str]] = []
        current = smoothed[0]
        for entry in smoothed[1:]:
            if entry["state"] == current["state"]:
                continue
            ranges.append(
                {
                    "state": current["state"],
                    "start": current["time"],
                    "end": entry["time"],
                }
            )
            current = entry
        # Final range
        ranges.append(
            {
                "state": current["state"],
                "start": current["time"],
                "end": datetime.now(UTC).isoformat(),
            }
        )

        return ranges

    # ------------------------------------------------------------------
    # Light level
    # ------------------------------------------------------------------

    async def get_light_level(self, entity_id: str) -> float | None:
        """Get current illuminance from a light sensor entity."""
        state = await self.get_entity_state(entity_id)
        if state:
            try:
                return float(state["state"])
            except ValueError, KeyError:
                return None
        return None

    # ------------------------------------------------------------------
    # Entity discovery
    # ------------------------------------------------------------------

    async def get_entities_by_domain(self, domain: str) -> list[dict[str, Any]]:
        """Return all HA state objects whose entity_id starts with ``domain.``."""
        if not self.configured:
            return []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self.base_url}/api/states",
                    headers=self._headers,
                )
                resp.raise_for_status()
                prefix = f"{domain}."
                return [s for s in resp.json() if s.get("entity_id", "").startswith(prefix)]
        except Exception:
            logger.exception("ha_get_entities_by_domain_error", domain=domain)
            return []

    async def get_media_players(self) -> list[dict[str, Any]]:
        """Return all ``media_player.*`` entity state objects from HA."""
        return await self.get_entities_by_domain("media_player")

    # ------------------------------------------------------------------
    # Announcements / media playback
    # ------------------------------------------------------------------

    async def announce(self, message: str) -> None:
        """Send a persistent notification to HA."""
        if not self.configured:
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"{self.base_url}/api/services/notify/persistent_notification",
                    headers=self._headers,
                    json={"message": message},
                )
        except Exception:
            logger.exception("ha_announce_error")

    async def turn_on_media_player(self, entity_id: str) -> None:
        """Turn on a media player entity (wakes idle/standby devices like Google Home)."""
        await self._call_service("media_player", "turn_on", {"entity_id": entity_id})

    async def play_audio(
        self, audio_url: str, entity_id: str = "media_player.living_room_speaker"
    ) -> None:
        """Play audio from a URL on a specific media player."""
        if not self.configured:
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"{self.base_url}/api/services/media_player/play_media",
                    headers=self._headers,
                    json={
                        "entity_id": entity_id,
                        "media_content_id": audio_url,
                        "media_content_type": "music",
                    },
                )
        except Exception:
            logger.exception("ha_play_audio_error", entity_id=entity_id)

    # ------------------------------------------------------------------
    # Person location propagation
    # ------------------------------------------------------------------

    async def set_person_location(self, person_id: str, room_name: str, confidence: float) -> None:
        """Push person location to HA as an input_text helper entity.

        Requires ``input_text.cc_{person_id}_location`` to be configured in HA.
        """
        entity_id = f"input_text.cc_{person_id}_location"
        await self._call_service(
            "input_text",
            "set_value",
            {"entity_id": entity_id, "value": f"{room_name} ({confidence:.0%})"},
        )

    async def _call_service(self, domain: str, service: str, data: dict) -> None:
        """Call a Home Assistant service."""
        if not self.configured:
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"{self.base_url}/api/services/{domain}/{service}",
                    headers=self._headers,
                    json=data,
                )
        except Exception:
            logger.exception("ha_call_service_error", domain=domain, service=service)

    # ------------------------------------------------------------------
    # WebSocket event subscription
    # ------------------------------------------------------------------

    async def open_event_subscription(
        self,
        entity_ids: Any,  # Iterable[str]
        on_state_changed: Any,  # Callable[[HaStateEvent], Awaitable[None]]
    ) -> HaEventSubscription:
        """Open a WebSocket subscription for HA state-changed events.

        Parameters
        ----------
        entity_ids:
            Iterable of entity IDs to subscribe to.  Events for other
            entities are silently dropped.
        on_state_changed:
            Async callback invoked for each matching state change.

        Returns
        -------
        HaEventSubscription
            An async context manager that starts the subscription on
            ``__aenter__`` and cancels it on ``__aexit__``.
        """
        if not self.configured:
            logger.warning("ha_websocket_not_configured")
            raise RuntimeError("Home Assistant is not configured (url/token missing)")

        entity_set = set(entity_ids)
        session = _HaWsSession(
            base_url=self.base_url,
            token=self.token,
            entity_ids=entity_set,
            on_state_changed=on_state_changed,
        )
        return HaEventSubscription(session)


class HaEventSubscription:
    """Async context manager for a single HA WebSocket session.

    Usage::

        async with client.open_event_subscription(
            entity_ids=["binary_sensor.bed_occupancy"],
            on_state_changed=my_callback,
        ):
            # subscription is active here
            pass
        # subscription is cancelled here
    """

    def __init__(self, session: _HaWsSession) -> None:
        self._session = session

    async def __aenter__(self) -> HaEventSubscription:
        await self._session.start()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self._session.stop()


# -- Helpers ------------------------------------------------------------------


def _parse_template_list(raw: str) -> list[str]:
    """Parse a Jinja-rendered list string like "['a', 'b']" into a Python list."""
    import ast

    try:
        result = ast.literal_eval(raw.strip())
        if isinstance(result, list):
            return [str(x) for x in result]
    except ValueError, SyntaxError:
        pass
    return []


def _parse_ts(ts_str: str) -> datetime | None:
    """Parse an ISO timestamp string."""
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except ValueError, AttributeError:
        return None


# ---------------------------------------------------------------------------
# WebSocket support
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HaStateEvent:
    """A state-changed event from Home Assistant via WebSocket."""

    entity_id: str
    state: str
    attributes: dict[str, Any]
    fired_at: datetime


class _HaWsSession:
    """Internal state for a single HA WebSocket session.

    Manages the auth handshake, entity subscription, event dispatch,
    and exponential-backoff reconnect loop.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        entity_ids: set[str],
        on_state_changed: Any,  # Callable[[HaStateEvent], Awaitable[None]]
    ) -> None:
        self._base_url = base_url
        self._token = token
        self._entity_ids = entity_ids
        self._on_state_changed = on_state_changed
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        """Open the WebSocket and begin the event loop."""
        self._stop.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self, timeout: float = 5.0) -> None:
        """Cancel the event loop and await with *timeout*."""
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._task),
                    timeout=timeout,
                )
            except TimeoutError:
                logger.warning("ha_ws_stop_timeout", entity_count=len(self._entity_ids))
                self._task.cancel()
            self._task = None

    # -- internal ----------------------------------------------------------

    async def _run_loop(self) -> None:
        """Reconnect loop with exponential back-off."""
        delay = 1.0
        max_delay = 30.0

        while not self._stop.is_set():
            try:
                await self._connect_and_dispatch()
                # Successful connection → reset back-off on next disconnect
                delay = 1.0
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "ha_ws_reconnect",
                    delay_seconds=delay,
                    entity_count=len(self._entity_ids),
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)

    async def _connect_and_dispatch(self) -> None:
        """Open a WS connection, subscribe, dispatch events until disconnect."""
        ws_url = self._base_url.replace("http", "ws").rstrip("/") + "/api/websocket"
        headers = {"Authorization": f"Bearer {self._token}"}

        async with aconnect_ws(
            ws_url,
            httpx.AsyncClient(timeout=httpx.Timeout(30.0)),
            headers=headers,
        ) as _ws:
            ws: Any = _ws
            # Auth handshake
            msg = await ws.receive_text()
            auth_msg = _parse_ws_message(msg)
            if auth_msg is None or auth_msg.get("type") != "auth_ok":
                # Try receiving auth_required first, then send auth
                msg2 = await ws.receive_text()
                auth_req = _parse_ws_message(msg2)
                if auth_req and auth_req.get("type") == "auth_required":
                    await ws.send_text(_format_ws_message(type="auth", access_token=self._token))
                    msg3 = await ws.receive_text()
                    auth_msg = _parse_ws_message(msg3)
                    if auth_msg is None or auth_msg.get("type") != "auth_ok":
                        raise RuntimeError(f"HA WebSocket auth failed: {auth_msg}")

            # Subscribe to state_changed events
            sub_msg = _format_ws_message(
                id=1,
                type="subscribe_events",
                event_type="state_changed",
            )
            await ws.send_text(sub_msg)

            # Initial REST snapshot for registered entities
            await self._fetch_initial_state()

            # Event dispatch loop
            while not self._stop.is_set():
                try:
                    msg = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                    self._handle_message(msg)
                except TimeoutError:
                    # Keep-alive ping — do nothing, loop continues
                    continue

    async def _fetch_initial_state(self) -> None:
        """Fetch current state for every registered entity via REST."""
        if not self._entity_ids:
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                for entity_id in self._entity_ids:
                    resp = await client.get(
                        f"{self._base_url}/api/states/{entity_id}",
                        headers={"Authorization": f"Bearer {self._token}"},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        state_str = data.get("state", "unknown")
                        attrs = data.get("attributes", {})
                        last_changed = data.get("last_changed")
                        fired_at = _parse_ts(last_changed) or datetime.now(UTC)
                        event = HaStateEvent(
                            entity_id=entity_id,
                            state=state_str,
                            attributes=attrs,
                            fired_at=fired_at,
                        )
                        await self._on_state_changed(event)
        except Exception:
            logger.warning(
                "ha_ws_initial_snapshot_error",
                entity_count=len(self._entity_ids),
            )

    def _handle_message(self, raw: str) -> None:
        """Parse and dispatch a single WS message."""
        parsed = _parse_ws_message(raw)
        if parsed is None:
            return
        if parsed.get("type") != "event":
            return
        event = parsed.get("event")
        if event is None:
            return
        event_data = event.get("data", {})
        if event.get("event_type") != "state_changed":
            return

        entity_id = event_data.get("entity_id", "")
        if entity_id not in self._entity_ids:
            return  # filtered out

        new_state = event_data.get("new_state")
        if new_state is None:
            return

        state_str = new_state.get("state", "unknown")
        attrs = new_state.get("attributes", {})
        last_changed = new_state.get("last_changed")
        fired_at = _parse_ts(last_changed) or datetime.now(UTC)

        ha_event = HaStateEvent(
            entity_id=entity_id,
            state=state_str,
            attributes=attrs,
            fired_at=fired_at,
        )
        # Fire-and-forget: the callback processes the event without
        # blocking the WS read loop.  The task is tracked by the event
        # loop; we do not need to await it.
        asyncio.create_task(self._on_state_changed(ha_event))  # noqa: RUF006


def _parse_ws_message(raw: str) -> dict[str, Any] | None:
    """Parse a Home Assistant WebSocket JSON message."""
    import json

    try:
        return json.loads(raw)
    except ValueError, TypeError:
        return None


def _format_ws_message(**kwargs: Any) -> str:
    """Format keyword args into a HA WebSocket JSON message."""
    import json

    return json.dumps(kwargs)
