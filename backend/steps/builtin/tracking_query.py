"""tracking_query pipeline step: inject CTS identity + location context.

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

from datetime import UTC, datetime, timedelta
from typing import Any

from backend.core.logging import get_logger
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.steps import StepRegistry
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
    """Read CTS identity + location context for rule evaluation."""

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="tracking_query",
            display_name="Tracking Query",
            category="perception",
            icon="mdi-map-marker-radius",
            description=(
                "Query the CTS identity graph for the current or recent "
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
        person_id = self._resolve_person_id(config, pipeline_data)

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

        db = services.db_factory()
        try:
            state = self._read_state(db, person_id)
            dwell_minutes = self._compute_dwell(db, person_id, state)
        finally:
            db.close()

        signals: list[dict[str, Any]] = []
        if services.semantic_memory_client is None:
            # We don't depend on semantic memory for signals; use SignalStore
            # if it's available via db_factory.
            signals = await self._read_signals(
                services.db_factory,
                person_id=person_id,
                kind=config.get("signal_kind"),
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
    def _resolve_person_id(config: dict, pipeline_data: dict) -> str | None:
        person_id = (config.get("person_id") or "").strip() or None
        if person_id:
            return person_id

        # Try upstream step output shape {"persons": [{id: ...}]}
        persons = pipeline_data.get("persons")
        if isinstance(persons, list) and persons:
            first = persons[0]
            if isinstance(first, dict):
                return (first.get("id") or first.get("person_id") or None)

        # Try a plain scalar
        candidate = pipeline_data.get("person_id")
        return candidate if isinstance(candidate, str) and candidate else None

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
    async def _read_signals(
        db_factory,  # type: ignore[no-untyped-def]
        *,
        person_id: str,
        kind: str | None,
        severity_min: str,
        window_minutes: int,
    ) -> list[dict[str, Any]]:
        from backend.services.cts.signal_store import SignalStore

        # Map severity_min to list of severities to accept.
        order = ["info", "warning", "emergency"]
        try:
            idx = order.index(severity_min)
        except ValueError:
            idx = 0
        accept = order[idx:]

        store = SignalStore(db_factory=db_factory)
        results: list[dict[str, Any]] = []
        for sev in accept:
            part = await store.list_recent(
                person_id=person_id,
                signal_type=kind,
                severity=sev,
                window_hours=max(1, (window_minutes + 59) // 60),
                limit=25,
            )
            # SignalStore returns `received_at` timestamps; filter to the window.
            cutoff = datetime.now(UTC) - timedelta(minutes=window_minutes)
            for sig in part:
                raw = sig.get("received_at")
                if raw is None:
                    results.append(sig)
                    continue
                try:
                    ts = datetime.fromisoformat(raw)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=UTC)
                    if ts >= cutoff:
                        results.append(sig)
                except ValueError:
                    continue
        # Deduplicate by id, preserve recent-first order.
        seen: set[int] = set()
        deduped: list[dict[str, Any]] = []
        for sig in results:
            sid = sig.get("id")
            if isinstance(sid, int) and sid in seen:
                continue
            if isinstance(sid, int):
                seen.add(sid)
            deduped.append(sig)
        return deduped

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
