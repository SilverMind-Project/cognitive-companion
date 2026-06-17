from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from backend.core.logging import get_logger

if TYPE_CHECKING:
    from backend.websocket.connection_manager import ConnectionManager

logger = get_logger(__name__)


async def inject_session_prompt(
    ws_manager: ConnectionManager,
    *,
    prompt: str,
    delivery_type: str,
    session_id: int,
    execution_id: int | None = None,
    voice_instruction: str | None = None,
    callback: Callable | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> None:
    """Inject a prompt for an interactive session into the live agent."""
    metadata: dict[str, Any] = dict(extra_metadata or {})
    metadata.update(
        {
            "delivery_type": delivery_type,
            "session_id": session_id,
        }
    )
    if execution_id is not None:
        metadata["execution_id"] = execution_id

    await ws_manager.send_backend_task(
        prompt=prompt,
        callback=callback,
        voice_instruction=voice_instruction or None,
        metadata=metadata,
    )
    logger.info(
        "interactive_session_prompt_injected",
        delivery_type=delivery_type,
        session_id=session_id,
    )
