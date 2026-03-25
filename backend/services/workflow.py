"""Workflow pipeline — matches sensor events to rules and delegates
execution to the :class:`PipelineExecutor`.

This module acts as the entry point for all sensor-triggered processing.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.models.event import EventLog
from backend.models.pipeline import WorkflowExecution
from backend.models.sensor import Sensor
from backend.services.pipeline_executor import PipelineExecutor, TriggerContext
from backend.services.rules_engine import RulesEngine

logger = get_logger(__name__)


class WorkflowPipeline:
    """Orchestrates rule matching and pipeline execution for sensor events."""

    def __init__(
        self,
        rules_engine: RulesEngine,
        pipeline_executor: PipelineExecutor,
    ) -> None:
        self.rules_engine = rules_engine
        self.pipeline_executor = pipeline_executor

    async def process_event(
        self,
        sensor_id: str,
        media_paths: list[str],
        media_type: str,
        db: Session,
    ) -> list[WorkflowExecution]:
        """Find matching rules for a sensor event and execute their pipelines.

        Returns a list of :class:`WorkflowExecution` objects — one per matched
        rule.
        """
        sensor = (
            db.query(Sensor)
            .filter(Sensor.id == sensor_id, Sensor.enabled.is_(True))
            .first()
        )
        if not sensor:
            logger.warning("sensor_not_found_or_disabled", sensor_id=sensor_id)
            return []

        room_name = sensor.room.name if sensor.room else "Unknown"
        matched_rules = self.rules_engine.get_matching_rules(sensor, db)

        if not matched_rules:
            logger.info("no_matching_rules", sensor_id=sensor_id, room=room_name)
            return []

        trigger = TriggerContext(
            trigger_type="sensor_event",
            sensor_id=sensor_id,
            room_name=room_name,
            media_paths=media_paths,
            media_type=media_type,
        )

        tasks = [
            self.pipeline_executor.execute(rule, trigger, db)
            for rule in matched_rules
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        executions: list[WorkflowExecution] = []
        for result in results:
            if isinstance(result, WorkflowExecution):
                executions.append(result)
            elif isinstance(result, Exception):
                logger.error("rule_execution_error", error=str(result))

        return executions
