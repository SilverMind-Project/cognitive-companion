from __future__ import annotations

from datetime import UTC, datetime

from backend.schemas.pipeline_ws import (
    EdgeRef,
    PipelineStartedEvent,
    StepCompletedEvent,
    StepNodeRef,
)


def test_pipeline_started_event_schema_validates() -> None:
    event = PipelineStartedEvent(
        execution_id=12,
        rule_id=3,
        rule_name="front-door",
        status="running",
        started_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        sequence=1,
        steps=[
            StepNodeRef(
                id="101",
                label="Detect",
                step_type="scene_analysis",
                enabled=True,
            )
        ],
        edges=[
            EdgeRef(
                source="101",
                source_handle="true",
                target="102",
            )
        ],
    )

    payload = event.model_dump(mode="json")

    assert payload["type"] == "pipeline_event"
    assert payload["event_type"] == "pipeline_started"
    assert payload["steps"][0]["id"] == "101"
    assert payload["edges"][0]["source_handle"] == "true"


def test_step_completed_event_includes_output_port() -> None:
    event = StepCompletedEvent(
        execution_id=12,
        rule_id=3,
        rule_name="front-door",
        step_id="101",
        step_name="Detect",
        step_type="condition",
        status="succeeded",
        finished_at=datetime(2026, 6, 1, 12, 0, 1, tzinfo=UTC),
        output_port="false",
        elapsed_ms=125,
        sequence=4,
    )

    payload = event.model_dump(mode="json")

    assert payload["event_type"] == "step_completed"
    assert payload["output_port"] == "false"
    assert payload["elapsed_ms"] == 125
