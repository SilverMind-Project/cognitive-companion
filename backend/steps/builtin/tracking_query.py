"""tracking_query pipeline step: inject CTS identity + location context.

.. deprecated::
    This step is superseded by :class:`~backend.steps.builtin.presence_query.PresenceQueryHandler`
    which uses the fused :class:`~backend.services.presence.PresenceService`.
    Use ``presence_query`` for new rules; this step remains for backwards
    compatibility with existing rule definitions.

Replaces the earlier Phase-4 ``cts_context_lookup`` with a broader, more
structured query interface. The step reads ``PersonLocationState`` /
``PersonLocationHistory`` (written by :class:`LocationWriter` from CTS
events) and recent dementia signals from :class:`SignalStore`, and emits
a flat set of keys in ``pipeline_data`` that downstream ``condition``,
``llm_call``, or ``notification`` steps can reference.

The step is additive: it never blocks pipeline execution. When the target
identity has no known location, all outputs default to empty/None and a
``tracking_available: false`` flag is set so downstream rules can react.

Result keys written to ``pipeline_data``
-----------------------------------------
``tracking_available``
    ``True`` if any state row was found for the person.
``tracking_person_id`` / ``tracking_room_name`` / ``tracking_last_seen_at``
    Current inferred location, or ``None``.
``tracking_dwell_minutes``
    How long the person has been in the current room (minutes).
``tracking_recent_signals``
    List of recent dementia-signal dicts matching the filters.
``tracking_signal_count``
    Count of matching signals in the window.
``tracking_satisfied``
    Whether the configured boolean conditions (room, duration_minutes,
    signal) all evaluated True. Convenient for a single ``condition`` step.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.core.logging import get_logger
from backend.models.pipeline import PipelineStep, WorkflowExecution
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


@StepRegistry.register
class TrackingQueryHandler(StepHandler):
    """Read CTS identity + location context for rule evaluation.

    .. deprecated:: Use ``presence_query`` instead.
    """

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="tracking_query",
            display_name="Tracking Query",
            category="perception",
            icon="mdi-map-marker-radius-outline",
            description=(
                "DEPRECATED: Use the ``presence_query`` step instead. "
                "Query the fused presence service for the current or recent "
                "location of a person, plus any recent dementia signals."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "string",
                        "description": (
                            "Person to query. Leave blank to use the first "
                            "person found in pipeline_data (sightings/persons)."
                        ),
                    },
                    "room": {
                        "type": "string",
                        "description": "Require this room name to match.",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "minimum": 0,
                        "description": (
                            "Require the person to have been in the current "
                            "room for at least this many minutes."
                        ),
                    },
                    "signal_kind": {
                        "type": "string",
                        "description": (
                            "Filter tracking_recent_signals to this kind "
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
                        "description": (
                            "Lookback for dementia signal match, in minutes."
                        ),
                    },
                },
                "required": [],
            },
            default_config={
                "signal_severity_min": "info",
                "signal_window_minutes": 30,
            },
            deprecated=True,
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
        person_id = resolve_person_id(config, pipeline_data)

        # Gracefully degrade when nothing is configured or resolvable.
        if not person_id:
            return StepResult(
                data={
                    "tracking_available": False,
                    "tracking_person_id": None,
                    "tracking_room_name": None,
                    "tracking_last_seen_at": None,
                    "tracking_dwell_minutes": None,
                    "tracking_recent_signals": [],
                    "tracking_signal_count": 0,
                    "tracking_satisfied": False,
                },
            )

        # Use the fused presence service instead of direct DB queries.
        if services.presence is not None:
            snapshot = await services.presence.get(person_id)
            state = self._snapshot_to_state_dict(snapshot)
            dwell_minutes = snapshot.dwell_minutes
        else:
            # Fallback: direct DB access for backwards compatibility.
            db = services.db_factory()
            try:
                state = self._read_state(db, person_id)
                dwell_minutes = self._compute_dwell(db, person_id, state)
            finally:
                db.close()

        signals: list[dict[str, Any]] = []
        if services.signals is not None:
            signals = await services.signals.list_recent(
                person_id=person_id,
                signal_kind=config.get("signal_kind"),
                severity_min=config.get("signal_severity_min", "info"),
                window_minutes=int(config.get("signal_window_minutes", 30)),
            )

        satisfied = self._evaluate_conditions(
            state=state,
            dwell_minutes=dwell_minutes,
            signals=signals,
            required_room=config.get("room"),
            required_duration=config.get("duration_minutes"),
            required_signal_kind=config.get("signal_kind"),
        )

        data: dict[str, Any] = {
            "tracking_available": state is not None,
            "tracking_person_id": person_id,
            "tracking_room_name": (state or {}).get("current_room_name"),
            "tracking_last_seen_at": (state or {}).get("last_seen_at"),
            "tracking_dwell_minutes": dwell_minutes,
            "tracking_recent_signals": signals,
            "tracking_signal_count": len(signals),
            "tracking_satisfied": satisfied,
        }
        return StepResult(data=data)

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _snapshot_to_state_dict(snapshot) -> dict[str, Any] | None:
        """Convert a PresenceSnapshot to the legacy state dict shape."""
        from backend.services.presence import PresenceStatus

        if snapshot.status in (PresenceStatus.UNKNOWN, PresenceStatus.STALE):
            return None
        return {
            "person_id": snapshot.person_id,
            "current_room_id": snapshot.room_id,
            "current_room_name": snapshot.room_name,
            "last_seen_at": (
                snapshot.last_seen_at.isoformat() if snapshot.last_seen_at else None
            ),
            "status": snapshot.status.value,
            "confidence": snapshot.confidence,
        }

    @staticmethod
    def _read_state(db: Any, person_id: str) -> dict[str, Any] | None:
        from backend.models.person import PersonLocationState

        row = (
            db.query(PersonLocationState)
            .filter(PersonLocationState.person_id == person_id)
            .first()
        )
        if row is None:
            return None
        return {
            "person_id": row.person_id,
            "current_room_id": row.current_room_id,
            "current_room_name": row.current_room_name,
            "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
            "last_sensor_id": row.last_sensor_id,
            "status": row.status,
            "confidence": row.confidence,
        }

    @staticmethod
    def _compute_dwell(
        db: Any, person_id: str, state: dict[str, Any] | None
    ) -> float | None:
        if state is None or not state.get("current_room_name"):
            return None
        from backend.models.person import PersonLocationHistory

        row = (
            db.query(PersonLocationHistory)
            .filter(
                PersonLocationHistory.person_id == person_id,
                PersonLocationHistory.room_name == state["current_room_name"],
                PersonLocationHistory.exited_at.is_(None),
                PersonLocationHistory.superseded_by_revision_id.is_(None),
            )
            .order_by(PersonLocationHistory.entered_at.desc())
            .first()
        )
        if row is None or row.entered_at is None:
            return None

        entered = row.entered_at
        if entered.tzinfo is None:
            entered = entered.replace(tzinfo=UTC)
        delta = datetime.now(UTC) - entered
        return round(delta.total_seconds() / 60.0, 2)

    @staticmethod
    def _evaluate_conditions(
        *,
        state: dict[str, Any] | None,
        dwell_minutes: float | None,
        signals: list[dict[str, Any]],
        required_room: str | None,
        required_duration: int | None,
        required_signal_kind: str | None,
    ) -> bool:
        if required_room and (
            state is None
            or (state.get("current_room_name") or "").lower() != required_room.lower()
        ):
            return False
        if required_duration is not None and (
            dwell_minutes is None or dwell_minutes < required_duration
        ):
            return False
        if required_signal_kind and not any(
            s.get("signal_type") == required_signal_kind for s in signals
        ):
            return False
        # If no conditions were configured, having state is enough.
        return state is not None
