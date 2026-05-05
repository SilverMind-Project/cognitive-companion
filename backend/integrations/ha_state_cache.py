"""In-process cache of Home Assistant entity states.

Populated by a WebSocket subscription started in the application lifespan.
HA-backed presence providers read from this cache synchronously so
``services.presence.get()`` never makes an HTTP call.

Concurrency model
-----------------
Writes happen on the single WS event-loop task (owned by
``_HaWsSession``).  Reads are synchronous dict/deque lookups from any task.
No locks are needed because asyncio guarantees single-writer semantics on the
event loop.  Documented here so future changes do not introduce unsafe sharing.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backend.core.logging import get_logger
from backend.integrations.homeassistant import HaStateEvent, HomeAssistantClient

logger = get_logger(__name__)


@dataclass(frozen=True)
class HaState:
    """Immutable snapshot of a single HA entity's state."""

    entity_id: str
    state: str
    attributes: dict[str, Any]
    last_changed: datetime


class HaStateCache:
    """In-process cache of HA entity states, fed by WebSocket events.

    Parameters
    ----------
    homeassistant_client:
        Configured ``HomeAssistantClient`` instance.  Used to open the WS
        subscription and perform the initial REST snapshot.
    """

    def __init__(self, homeassistant_client: HomeAssistantClient) -> None:
        self._client = homeassistant_client
        self._states: dict[str, HaState] = {}
        self._history: dict[str, deque[HaState]] = {}
        self._registered: set[str] = set()
        self._subscription: Any = None  # HaEventSubscription | None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, entity_id: str) -> HaState | None:
        """Return the cached state for *entity_id*, or ``None``."""
        return self._states.get(entity_id)

    def get_or_default(self, entity_id: str, default: HaState) -> HaState:
        """Return the cached state or *default* on miss."""
        return self._states.get(entity_id) or default

    def history(
        self, entity_id: str, *, max_items: int = 32
    ) -> tuple[HaState, ...]:
        """Return recent states for *entity_id*, newest first."""
        dq = self._history.get(entity_id)
        if dq is None:
            return ()
        return tuple(reversed(dq))[:max_items]

    def register(self, entity_id: str) -> None:
        """Add *entity_id* to the subscription set.

        Safe to call before or after :meth:`start`.  If called after
        ``start()`` the entity is added to the internal set; the WS
        session's ``_entity_ids`` filter will pick it up on the next
        reconnect (the filter is applied per-event).
        """
        self._registered.add(entity_id)

    async def start(self) -> None:
        """Open the WS subscription and populate the cache.

        1. Collects all registered entity IDs.
        2. Opens the HA WebSocket subscription via
           ``HomeAssistantClient.open_event_subscription`` and enters the
           context manager so events are dispatched.
        3. Feeds each incoming event through the internal callback,
           which updates both the dict cache and per-entity deques.
        4. Performs an initial REST snapshot for every registered entity
           so the cache is non-empty before any provider probes.
        """
        if not self._client.configured:
            logger.warning("ha_cache_start_not_configured")
            return

        entity_ids = list(self._registered)
        if not entity_ids:
            logger.info("ha_cache_start_no_entities")
            return

        logger.info(
            "ha_cache_start",
            entity_count=len(entity_ids),
            entities=entity_ids,
        )

        self._subscription = await self._client.open_event_subscription(
            entity_ids=entity_ids,
            on_state_changed=self._on_state_changed,
        )
        await self._subscription.__aenter__()

    async def stop(self) -> None:
        """Cancel the WS subscription and clear the cache."""
        if self._subscription is not None:
            await self._subscription.__aexit__(None, None, None)
            self._subscription = None
        self._states.clear()
        self._history.clear()
        logger.info("ha_cache_stopped")

    # ------------------------------------------------------------------
    # Internal callback (called from WS event loop)
    # ------------------------------------------------------------------

    async def _on_state_changed(self, event: HaStateEvent) -> None:
        """Update the cache when an HA entity state changes."""
        state = HaState(
            entity_id=event.entity_id,
            state=event.state,
            attributes=event.attributes,
            last_changed=event.fired_at,
        )

        self._states[event.entity_id] = state

        dq = self._history.get(event.entity_id)
        if dq is None:
            dq = deque(maxlen=32)
            self._history[event.entity_id] = dq
        dq.append(state)

        logger.debug(
            "ha_state_updated",
            entity_id=event.entity_id,
            new_state=event.state,
        )
