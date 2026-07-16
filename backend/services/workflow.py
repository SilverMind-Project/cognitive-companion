"""Workflow pipeline  matches sensor events to rules and delegates
execution to the :class:`PipelineExecutor`.

This module acts as the entry point for all sensor-triggered processing.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.models.pipeline import WorkflowExecution
from backend.models.rule import Rule
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

        Returns a list of :class:`WorkflowExecution` objects  one per matched
        rule whose concurrent execution limit was not exceeded.
        """
        sensor = db.query(Sensor).filter(Sensor.id == sensor_id, Sensor.enabled.is_(True)).first()
        if not sensor:
            logger.warning("sensor_not_found_or_disabled", sensor_id=sensor_id)
            return []

        room_name = sensor.room.name if sensor.room else "Unknown"
        matched_rules = await self.rules_engine.get_matching_rules(sensor, db)

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

        allowed = [r for r in matched_rules if self._concurrent_limit_allows(r, db)]
        logger.info(
            "workflow_dispatching",
            sensor_id=sensor_id,
            matched=len(matched_rules),
            allowed=len(allowed),
            allowed_names=[r.name for r in allowed],
        )
        tasks = [self.pipeline_executor.execute(rule, trigger, db) for rule in allowed]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        executions: list[WorkflowExecution] = []
        for rule, result in zip(allowed, results, strict=False):
            if isinstance(result, WorkflowExecution):
                executions.append(result)
            elif isinstance(result, Exception):
                logger.error(
                    "rule_execution_error",
                    rule_id=rule.id,
                    rule=rule.name,
                    sensor_id=sensor_id,
                    error=str(result),
                )

        return executions

    async def process_occupancy_event(
        self,
        sensor: Sensor,
        room_name: str,
        duration_minutes: float,
        db: Session,
    ) -> list[WorkflowExecution]:
        """Fire occupancy_duration rules whose threshold has been reached.

        Called by :class:`SensorPollingService` on each poll cycle for sensors
        that are currently occupied. The rules engine filters by
        ``primary_sensor_id``, ``occupancy_config.min_minutes``, context
        filters, and rate limits  so this method fires at most once per
        ``cool_off_minutes`` per rule even though polling runs every 30 s.
        """
        matched_rules = await self.rules_engine.get_matching_rules(
            sensor,
            db,
            trigger_type="occupancy_duration",
            occupancy_minutes=duration_minutes,
        )

        if not matched_rules:
            return []

        trigger = TriggerContext(
            trigger_type="occupancy_duration",
            sensor_id=sensor.id,
            room_name=room_name,
            occupancy_duration_minutes=duration_minutes,
        )

        allowed = [r for r in matched_rules if self._concurrent_limit_allows(r, db)]
        tasks = [self.pipeline_executor.execute(rule, trigger, db) for rule in allowed]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        executions: list[WorkflowExecution] = []
        for rule, result in zip(allowed, results, strict=False):
            if isinstance(result, WorkflowExecution):
                executions.append(result)
            elif isinstance(result, Exception):
                logger.error(
                    "occupancy_rule_execution_error",
                    rule_id=rule.id,
                    rule=rule.name,
                    sensor_id=sensor.id,
                    error=str(result),
                )

        return executions

    # -- helpers --------------------------------------------------------------

    def _concurrent_limit_allows(self, rule: Rule, db: Session) -> bool:
        """Return True if a new execution is permitted under the concurrency limit.

        ``max_concurrent_executions == 0`` means unlimited.  Otherwise, the
        number of currently running or waiting executions for this rule must be
        strictly less than the configured limit.

        Note: this check is optimistic (not transactional).  Two simultaneous
        incoming events for the same rule could both pass.  The check is
        sufficient for the typical case where sensor events are spaced apart.
        """
        if rule.max_concurrent_executions <= 0:
            return True

        running = (
            db.query(WorkflowExecution)
            .filter(
                WorkflowExecution.rule_id == rule.id,
                WorkflowExecution.status.in_(["running", "waiting"]),
            )
            .count()
        )
        if running >= rule.max_concurrent_executions:
            logger.warning(
                "concurrent_limit_reached",
                rule_id=rule.id,
                rule=rule.name,
                running=running,
                limit=rule.max_concurrent_executions,
            )
            return False
        return True
