"""presence_query pipeline step: inject fused presence context.

Queries :class:`~backend.services.presence.PresenceService` for the current
fused location and status of a person, then emits a structured dict and
flat keys into ``pipeline_data`` for downstream steps to consume.

Result keys written to ``pipeline_data``
-----------------------------------------
``presence`` (dict, keyed by ``output_key``)
    Full presence snapshot:

    * ``available`` (bool)
    * ``person_id`` (str)
    * ``status`` (str: one of ``PresenceStatus`` values)
    * ``room_id`` (str | None)
    * ``room_name`` (str | None)
    * ``confidence`` (float)
    * ``last_seen_at`` (str | None)
    * ``dwell_minutes`` (float | None)
    * ``sources`` (list[dict])
    * ``notes`` (str | None)
    * ``inferred_at`` (str)

Flat keys (always written at top level for ``condition`` / filter steps):
``presence_status``
    The ``PresenceStatus`` value string.
``presence_room_name``
    Current room name (None when unknown).
``presence_dwell_minutes``
    Dwell duration in minutes (None when unknown).
``presence_at_home``
    True when status is ``present_room``, ``present_home``, or ``asleep``.
``presence_asleep``
    True when status is ``asleep``.
``presence_away``
    True when status is ``away``.

When no person is resolvable, ``presence_available`` is set to ``false``
and all other keys default to empty/None.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from backend.core.logging import get_logger
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.models.room import Room
from backend.services.cts.signal_config import ALL_SIGNAL_KINDS
from backend.steps import StepRegistry
from backend.steps._helpers import resolve_person_id
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

logger = get_logger(__name__)

_HISTORY_ZERO_RESULT: dict[str, Any] = {
    "had_dwell": False,
    "qualifying_episodes": 0,
    "total_minutes": 0.0,
    "longest_minutes": 0.0,
}


@StepRegistry.register
class PresenceQueryHandler(StepHandler):
    """Query fused presence (location + status) for a person."""

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="presence_query",
            display_name="Presence Query",
            category="perception",
            icon="mdi-map-marker-radius",
            description=(
                "Query the fused presence service for the current location "
                "and status of a person. Returns status (present_room, "
                "present_home, asleep, away, stale, unknown), room name, "
                "confidence, dwell time, and signal sources."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "query_mode": {
                        "type": "string",
                        "enum": ["current", "room_dwell_history"],
                        "default": "current",
                        "description": (
                            "'current' = fused presence snapshot (existing behavior). "
                            "'room_dwell_history' = qualifying dwell episodes in one "
                            "room over a historical lookback window (e.g. a bathroom "
                            "wash-up proxy)."
                        ),
                    },
                    "person_id": {
                        "type": "string",
                        "description": (
                            "Person to query. Leave blank to use the first "
                            "person found in pipeline_data (sightings/persons)."
                        ),
                    },
                    "room_name": {
                        "type": "string",
                        "default": "",
                        "description": "room_dwell_history mode: room to check dwell in.",
                    },
                    "window_hours": {
                        "type": "number",
                        "minimum": 0.1,
                        "default": 26,
                        "description": "room_dwell_history mode: lookback window, in hours.",
                    },
                    "min_episode_minutes": {
                        "type": "number",
                        "minimum": 0,
                        "default": 8,
                        "description": (
                            "room_dwell_history mode: minimum merged-episode duration "
                            "to count as a qualifying dwell."
                        ),
                    },
                    "merge_gap_minutes": {
                        "type": "number",
                        "minimum": 0,
                        "default": 2,
                        "description": (
                            "room_dwell_history mode: gap-merge adjacent segments in "
                            "the room within this many minutes of each other."
                        ),
                    },
                    "signal_kind": {
                        "type": "string",
                        # "" is the config dialog's unset state ("leave blank to include all
                        # kinds"); the enum otherwise pins the value to the canonical set so a
                        # typo (e.g. "gait_slowng") is rejected at save time.
                        "enum": ["", *ALL_SIGNAL_KINDS],
                        "description": (
                            "Filter recent dementia signals to this kind "
                            "(e.g. 'bathroom_dwell_anomaly')."
                        ),
                    },
                    "signal_severity_min": {
                        "type": "string",
                        "enum": ["info", "warning", "emergency"],
                        "default": "info",
                        "description": "Minimum severity for signal match.",
                    },
                    "signal_window_minutes": {
                        "type": "integer",
                        "minimum": 1,
                        "default": 30,
                        "description": ("Lookback for dementia signals, in minutes."),
                    },
                    "output_key": {
                        "type": "string",
                        "default": "presence",
                        "description": (
                            "pipeline_data key for the result dict. "
                            "Flat keys are always written at top level."
                        ),
                    },
                },
                "required": [],
            },
            default_config={
                "query_mode": "current",
                "signal_severity_min": "info",
                "signal_window_minutes": 30,
                "output_key": "presence",
                "room_name": "",
                "window_hours": 26,
                "min_episode_minutes": 8,
                "merge_gap_minutes": 2,
            },
            gate_safe=True,
        )

    async def execute(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
        services: ServiceContainer,
    ) -> StepResult:
        config = step.config_json or {}

        if config.get("query_mode", "current") == "room_dwell_history":
            return await self._execute_room_dwell_history(config, pipeline_data, services)

        person_id = resolve_person_id(config, pipeline_data)
        output_key = (config.get("output_key") or "presence").strip() or "presence"

        if not person_id:
            return StepResult(
                data={
                    f"{output_key}_available": False,
                    "presence_status": None,
                    "presence_room_name": None,
                    "presence_dwell_minutes": None,
                    "presence_at_home": False,
                    "presence_asleep": False,
                    "presence_away": False,
                },
            )

        if services.presence is None:
            logger.warning(
                "presence_query: PresenceService not available",
                person_id=person_id,
            )
            return StepResult(
                data={
                    f"{output_key}_available": False,
                    "presence_status": None,
                    "presence_room_name": None,
                    "presence_dwell_minutes": None,
                    "presence_at_home": False,
                    "presence_asleep": False,
                    "presence_away": False,
                },
            )

        snapshot = await services.presence.get(person_id)

        data: dict[str, Any] = {
            f"{output_key}_available": True,
            f"{output_key}_person_id": person_id,
            f"{output_key}_status": snapshot.status.value,
            f"{output_key}_room_id": snapshot.room_id,
            f"{output_key}_room_name": snapshot.room_name,
            f"{output_key}_confidence": snapshot.confidence,
            f"{output_key}_last_seen_at": (
                snapshot.last_seen_at.isoformat() if snapshot.last_seen_at else None
            ),
            f"{output_key}_dwell_minutes": snapshot.dwell_minutes,
            f"{output_key}_sources": [
                {"name": s.name, "confidence": s.confidence} for s in snapshot.sources
            ],
            f"{output_key}_notes": snapshot.notes,
            f"{output_key}_inferred_at": snapshot.inferred_at.isoformat(),
            # Flat keys for condition/step expressions.
            "presence_status": snapshot.status.value,
            "presence_room_name": snapshot.room_name,
            "presence_dwell_minutes": snapshot.dwell_minutes,
            "presence_at_home": snapshot.status.value in ("present_room", "present_home", "asleep"),
            "presence_asleep": snapshot.status.value == "asleep",
            "presence_away": snapshot.status.value == "away",
        }

        # -- recent dementia signals (optional) -------------------------------
        signals: list[dict[str, Any]] = []
        if services.signals is not None:
            signals = await services.signals.list_recent(
                person_id=person_id,
                signal_kind=config.get("signal_kind"),
                severity_min=config.get("signal_severity_min", "info"),
                window_minutes=int(config.get("signal_window_minutes", 30)),
            )

        data[f"{output_key}_recent_signals"] = signals
        data[f"{output_key}_signal_count"] = len(signals)

        return StepResult(data=data)

    # -- internals ----------------------------------------------------------

    async def _execute_room_dwell_history(
        self,
        config: dict,
        pipeline_data: dict,
        services: ServiceContainer,
    ) -> StepResult:
        """room_dwell_history mode: qualifying dwell episodes over a lookback window.

        Built on ``PersonLocationService.dwell_episodes`` (room_segments-based,
        so inferred-only rooms like a camera-less bathroom are covered). Every
        failure path here (missing config, missing service, unknown room) is
        fail-silent to the zero-value result, matching the "current" mode's
        degradation convention above: a wellness-proxy rule should treat
        "insufficient evidence" as "no qualifying dwell found", never as an
        exception that aborts the pipeline.
        """
        output_key = (config.get("output_key") or "presence").strip() or "presence"
        person_id = resolve_person_id(config, pipeline_data)
        room_name = (config.get("room_name") or "").strip()

        if not person_id or not room_name:
            logger.warning(
                "presence_query_room_dwell_history_missing_config",
                person_id=person_id,
                room_name=room_name,
            )
            return StepResult(data=self._history_output(output_key, _HISTORY_ZERO_RESULT))

        if services.person_location is None:
            logger.warning("presence_query: PersonLocationService not available")
            return StepResult(data=self._history_output(output_key, _HISTORY_ZERO_RESULT))

        db = services.db_factory()
        try:
            room = db.query(Room).filter(Room.name == room_name).first()
        finally:
            db.close()

        if room is None:
            logger.warning("presence_query_room_not_found", room_name=room_name)
            return StepResult(data=self._history_output(output_key, _HISTORY_ZERO_RESULT))

        window_hours = float(config.get("window_hours", 26))
        min_episode_minutes = float(config.get("min_episode_minutes", 8))
        merge_gap_s = int(float(config.get("merge_gap_minutes", 2)) * 60)

        now = datetime.now(UTC)
        start = now - timedelta(hours=window_hours)

        episodes = await services.person_location.dwell_episodes(
            person_id,
            room.id,
            start,
            now,
            now=now,
            merge_gap_s=merge_gap_s,
        )
        qualifying = [e for e in episodes if e.minutes >= min_episode_minutes]

        result: dict[str, Any] = {
            "had_dwell": bool(qualifying),
            "qualifying_episodes": len(qualifying),
            "total_minutes": round(sum(e.minutes for e in qualifying), 2),
            "longest_minutes": round(max((e.minutes for e in qualifying), default=0.0), 2),
        }
        return StepResult(data=self._history_output(output_key, result))

    @staticmethod
    def _history_output(output_key: str, result: dict[str, Any]) -> dict[str, Any]:
        return {
            f"{output_key}_had_dwell": result["had_dwell"],
            f"{output_key}_qualifying_episodes": result["qualifying_episodes"],
            f"{output_key}_total_minutes": result["total_minutes"],
            f"{output_key}_longest_minutes": result["longest_minutes"],
        }
