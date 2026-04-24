"""Interactive response service for managing user responses to interactive prompts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.models.interactive_response import InteractiveResponse

logger = get_logger(__name__)


@dataclass
class InteractiveResponseService:
    """Manages interactive response lifecycle with dependency injection."""

    db_factory: Callable[[], Session]  # Session factory, not global connection
    scheduler: Any  # Scheduler service for resume scheduling

    async def record_response(
        self,
        execution_id: int,
        step_id: int,
        channel: str,
        action: str,
        timestamp: datetime,
        raw_response: dict,
    ) -> InteractiveResponse | None:
        """Record a user response and trigger pipeline resumption.

        Args:
            execution_id: Workflow execution ID
            step_id: Pipeline step ID
            channel: Response channel (pwa_popup_text, pwa_realtime_ai, timeout)
            action: User action (escalate, dismiss)
            timestamp: Response timestamp
            raw_response: Channel-specific response data

        Returns:
            InteractiveResponse if successfully recorded, None if duplicate

        Raises:
            ValueError: If required fields are missing or invalid
        """
        # Validate required fields
        if not isinstance(execution_id, int) or execution_id <= 0:
            raise ValueError("execution_id must be a positive integer")
        if not isinstance(step_id, int) or step_id <= 0:
            raise ValueError("step_id must be a positive integer")
        if channel not in ("pwa_popup_text", "pwa_realtime_ai", "timeout"):
            raise ValueError(
                f"channel must be one of pwa_popup_text, pwa_realtime_ai, timeout; got {channel}"
            )
        if action not in ("escalate", "dismiss"):
            raise ValueError(f"action must be one of escalate, dismiss; got {action}")
        if not isinstance(timestamp, datetime):
            raise ValueError("timestamp must be a datetime object")
        if not isinstance(raw_response, dict):
            raise ValueError("raw_response must be a dict")

        db: Session = self.db_factory()
        try:
            # Create response record
            response = InteractiveResponse(
                execution_id=execution_id,
                step_id=step_id,
                channel=channel,
                action=action,
                timestamp=timestamp,
                raw_response_json=raw_response,
            )

            db.add(response)
            try:
                db.commit()
                db.refresh(response)
            except IntegrityError:
                # Duplicate response (unique constraint on execution_id, step_id)
                db.rollback()
                logger.info(
                    "interactive_duplicate_response",
                    execution_id=execution_id,
                    step_id=step_id,
                    channel=channel,
                )
                return None

            logger.info(
                "interactive_response_recorded",
                execution_id=execution_id,
                step_id=step_id,
                channel=channel,
                action=action,
            )

            # Update pipeline_data with response and auto-escalation logic
            await self._update_pipeline_data(
                db, execution_id, step_id, channel, action, timestamp, raw_response
            )

            # Trigger pipeline resumption via scheduler
            await self._trigger_resume(execution_id)

            return response

        finally:
            db.close()

    def get_response(
        self,
        execution_id: int,
        step_id: int,
    ) -> InteractiveResponse | None:
        """Retrieve a response by execution and step ID.

        Args:
            execution_id: Workflow execution ID
            step_id: Pipeline step ID

        Returns:
            InteractiveResponse if found, None otherwise
        """
        db: Session = self.db_factory()
        try:
            response = (
                db.query(InteractiveResponse)
                .filter(
                    InteractiveResponse.execution_id == execution_id,
                    InteractiveResponse.step_id == step_id,
                )
                .first()
            )
            return response
        finally:
            db.close()

    def check_response_exists(
        self,
        execution_id: int,
        step_id: int,
    ) -> bool:
        """Check if a response already exists (for timeout handling).

        Args:
            execution_id: Workflow execution ID
            step_id: Pipeline step ID

        Returns:
            True if response exists, False otherwise
        """
        db: Session = self.db_factory()
        try:
            exists = (
                db.query(InteractiveResponse)
                .filter(
                    InteractiveResponse.execution_id == execution_id,
                    InteractiveResponse.step_id == step_id,
                )
                .first()
                is not None
            )
            return exists
        finally:
            db.close()

    async def cancel_pending_response(
        self,
        execution_id: int,
        step_id: int,
    ) -> None:
        """Cancel timeout task when response arrives early.

        Args:
            execution_id: Workflow execution ID
            step_id: Pipeline step ID
        """
        # Cancel the timeout job if it exists
        job_id = f"interactive_timeout_{execution_id}_{step_id}"
        try:
            self.scheduler.apscheduler.remove_job(job_id)
            logger.info(
                "interactive_timeout_cancelled",
                execution_id=execution_id,
                step_id=step_id,
            )
        except Exception:
            # Job may not exist or already fired - this is fine
            logger.debug(
                "interactive_timeout_cancel_skipped",
                execution_id=execution_id,
                step_id=step_id,
            )

    async def _update_pipeline_data(
        self,
        db: Session,
        execution_id: int,
        step_id: int,
        channel: str,
        action: str,
        timestamp: datetime,
        raw_response: dict,
    ) -> None:
        """Update pipeline_data with response and auto-escalation logic.

        Args:
            db: Database session
            execution_id: Workflow execution ID
            step_id: Pipeline step ID
            channel: Response channel
            action: User action
            timestamp: Response timestamp
            raw_response: Channel-specific response data
        """
        from sqlalchemy.orm.attributes import flag_modified

        from backend.models.pipeline import PipelineStep, WorkflowExecution

        # Load WorkflowExecution
        execution = db.query(WorkflowExecution).filter(
            WorkflowExecution.id == execution_id
        ).first()

        if not execution:
            logger.warning(
                "interactive_response_execution_not_found",
                execution_id=execution_id,
                step_id=step_id,
            )
            return

        # Load PipelineStep to get config
        step = db.query(PipelineStep).filter(PipelineStep.id == step_id).first()

        if not step:
            logger.warning(
                "interactive_response_step_not_found",
                execution_id=execution_id,
                step_id=step_id,
            )
            return

        # Get step config
        config = step.config_json or {}
        output_key = config.get("output_key", "interactive_response")
        auto_escalate = config.get("auto_escalate", False)

        # Initialize pipeline_data if needed
        if execution.pipeline_data_json is None:
            execution.pipeline_data_json = {}

        pipeline_data = execution.pipeline_data_json

        # Add response data to pipeline_data
        pipeline_data[output_key] = {
            "channel": channel,
            "action": action,
            "timestamp": timestamp.isoformat(),
            "raw_response": raw_response,
        }

        # Implement auto-escalation logic (Requirements 17.1-17.4)
        if auto_escalate:
            # Set auto_escalate_triggered when action="escalate" (Requirement 17.2)
            if action == "escalate":
                pipeline_data["auto_escalate_triggered"] = True
                logger.info(
                    "interactive_auto_escalate_triggered",
                    execution_id=execution_id,
                    step_id=step_id,
                    reason="action_escalate",
                )
            # Set auto_escalate_triggered when channel="timeout" (Requirement 17.3)
            elif channel == "timeout":
                pipeline_data["auto_escalate_triggered"] = True
                logger.info(
                    "interactive_auto_escalate_triggered",
                    execution_id=execution_id,
                    step_id=step_id,
                    reason="timeout",
                )

        # Mark pipeline_data as modified for SQLAlchemy to track the change
        flag_modified(execution, "pipeline_data_json")
        db.commit()

        logger.info(
            "interactive_pipeline_data_updated",
            execution_id=execution_id,
            step_id=step_id,
            output_key=output_key,
            auto_escalate=auto_escalate,
        )

    async def _trigger_resume(self, execution_id: int) -> None:
        """Trigger immediate pipeline resumption.

        Args:
            execution_id: Workflow execution ID
        """
        from datetime import UTC

        # Schedule immediate resume (use current time as resume_at)
        resume_at = datetime.now(UTC)
        self.scheduler.schedule_workflow_resume(execution_id, resume_at)
        logger.info(
            "interactive_pipeline_resume_scheduled",
            execution_id=execution_id,
        )
