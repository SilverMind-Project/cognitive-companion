"""Activity and zone-presence completion evaluators."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from backend.core.logging import get_logger
from backend.services.guided_task.completion.base import CompletionEvaluator, CompletionResult

logger = get_logger(__name__)


class ActivitySignalEvaluator:
    """Completion gate backed by ``ActivityService.query_in_window``."""

    kind = "activity_signal"

    def __init__(self, *, activity_service: Any | None, gate_config: dict | None = None) -> None:
        self._activity_service = activity_service
        self._gate_config = gate_config or {}

    async def is_complete(
        self,
        *,
        session: Any,
        step: Any,
        evidence: dict,
    ) -> CompletionResult:
        activity = (
            self._gate_config.get("activity_signal") or self._gate_config.get("activity") or {}
        )
        activity_type = activity.get("activity_type") or activity.get("type")
        if not activity_type:
            return CompletionResult(False, 0.0, "activity_type_missing")
        if self._activity_service is None:
            logger.warning("guided_activity_evaluator_unavailable", session_id=session.id)
            return CompletionResult(False, 0.0, "activity_service_unavailable")

        window_minutes = float(activity.get("window_minutes", activity.get("within_minutes", 10)))
        window_end = evidence.get("now")
        window_start = None
        if window_end is not None:
            window_start = window_end - timedelta(minutes=window_minutes)
        rows = await self._activity_service.query_in_window(
            person_id=session.person_id,
            activity_type=str(activity_type),
            window_start=window_start,
            window_end=window_end,
            within_minutes=None if window_start is not None else window_minutes,
            min_confidence=float(activity.get("min_confidence", 0.0)),
            room_name=activity.get("room_name"),
        )
        if rows:
            return CompletionResult(True, 1.0, "activity_signal_matched")
        return CompletionResult(False, 0.0, "activity_signal_not_found")


class ZonePresenceEvaluator:
    """Completion gate backed by the M6 zone service."""

    kind = "zone_presence"

    def __init__(self, *, zone_service: Any | None, gate_config: dict | None = None) -> None:
        self._zone_service = zone_service
        self._gate_config = gate_config or {}

    async def is_complete(
        self,
        *,
        session: Any,
        step: Any,
        evidence: dict,
    ) -> CompletionResult:
        _ = evidence
        target_zone_id = self._target_zone_id(step)
        if target_zone_id is None:
            return CompletionResult(False, 0.0, "target_zone_missing")
        if self._zone_service is None:
            logger.warning("guided_zone_evaluator_unavailable", session_id=session.id)
            return CompletionResult(False, 0.0, "zone_service_unavailable")

        zone = await self._zone_service.current_zone(session.person_id)
        current_zone_id = getattr(zone, "id", None) if zone is not None else None
        if current_zone_id == target_zone_id:
            return CompletionResult(True, 1.0, "zone_presence_matched")
        return CompletionResult(False, 0.0, "zone_presence_not_matched")

    def _target_zone_id(self, step: Any) -> int | None:
        zone_presence = self._gate_config.get("zone_presence") or {}
        configured = zone_presence.get("zone_id") or self._gate_config.get("zone_id")
        zone_id = configured if configured is not None else getattr(step, "zone_id", None)
        return int(zone_id) if zone_id is not None else None


def build_skip_evaluator(
    skip_condition: dict[str, Any] | None,
    *,
    activity_service: Any | None,
    zone_service: Any | None,
) -> CompletionEvaluator | None:
    """Build the entry-time skip evaluator a step's ``skip_condition`` names (G4).

    Reuses :class:`ActivitySignalEvaluator` / :class:`ZonePresenceEvaluator` by
    narrowing ``skip_condition`` (``{"kind": ..., ...}``) into the same nested
    ``gate_config`` shape those evaluators already read from a completion
    gate. Returns ``None`` for a step with no skip condition, or one whose
    kind is not evaluated on entry (``response_says_done`` fires only via the
    ``already_done`` evidence path in ``handle_completion``).
    """
    if not skip_condition:
        return None
    kind = skip_condition.get("kind")
    if kind == "activity_signal":
        return ActivitySignalEvaluator(
            activity_service=activity_service,
            gate_config={"activity_signal": skip_condition},
        )
    if kind == "zone_presence":
        return ZonePresenceEvaluator(
            zone_service=zone_service,
            gate_config={"zone_presence": skip_condition},
        )
    return None
