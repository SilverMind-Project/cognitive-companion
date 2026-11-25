"""Interactive response service for managing user responses to interactive prompts.

Ownership model
---------------
This service is the authoritative writer of :class:`InteractiveResponse` rows.
It does NOT write to ``WorkflowExecution.pipeline_data_json``.

The executor (:class:`PipelineExecutor`) is the sole writer of
``pipeline_data_json``.  When ``resume()`` is called for an
``interactive_prompt`` step, the executor loads the response row and merges it
into pipeline_data via :func:`pipeline_data_manager.apply_interactive_response`.

Resume scheduling
-----------------
After persisting the response row, this service calls
:meth:`_request_resume_when_waiting` which polls the execution status with
bounded exponential backoff.  This handles the race where a user responds
before the executor has committed ``status="waiting"``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from cachetools import TTLCache
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.models.interactive_response import InteractiveResponse
from backend.services.companion_surface.hardware import release_surface
from backend.services.interactive_session.tagging import voice_owner_key

logger = get_logger(__name__)

# Retry schedule for waiting on execution to reach "waiting" status (seconds)
_RESUME_RETRY_DELAYS = (0.05, 0.1, 0.2, 0.4, 0.8)


@dataclass
class InteractiveResponseService:
    """Manages interactive response lifecycle with dependency injection."""

    db_factory: Callable[[], Session]
    scheduler: Any  # Scheduler service for resume scheduling
    ws_manager: Any = None
    _prompt_surfaces: TTLCache[tuple[int, int], str | None] = field(
        default_factory=lambda: TTLCache(maxsize=256, ttl=3600),
        repr=False,
    )

    def track_surface(self, execution_id: int, step_id: int, surface_id: str | None) -> None:
        """Remember which companion surface holds the capture lease for this prompt."""
        self._prompt_surfaces[(execution_id, step_id)] = surface_id

    async def release_prompt_resources(self, execution_id: int, step_id: int) -> None:
        """Restore the companion persona and close the surface lease for this prompt."""
        surface_id = self._prompt_surfaces.pop((execution_id, step_id), None)
        if self.ws_manager is None:
            return
        owner = voice_owner_key("interactive_prompt", f"{execution_id}:{step_id}")
        release_voice = getattr(self.ws_manager, "release_voice_instruction", None)
        if callable(release_voice):
            try:
                await release_voice(owner)
            except Exception:  # noqa: BLE001 - best-effort cleanup after response/timeout
                logger.warning(
                    "interactive_prompt_voice_release_failed",
                    execution_id=execution_id,
                    step_id=step_id,
                )
        try:
            await release_surface(
                self.ws_manager, surface_id, owner=owner, reason="interactive_prompt"
            )
        except Exception:  # noqa: BLE001 - best-effort cleanup after response/timeout
            logger.warning(
                "interactive_prompt_surface_release_failed",
                execution_id=execution_id,
                step_id=step_id,
            )

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

            # Cancel the timeout job when a real (non-timeout) response arrives
            if channel != "timeout":
                await self.cancel_pending_response(execution_id, step_id)

            # Release the prompt's persona override and surface capture lease.
            await self.release_prompt_resources(execution_id, step_id)

            # Schedule resume once the execution reaches "waiting" status
            await self._request_resume_when_waiting(execution_id)

            return response

        finally:
            db.close()

    def get_response(
        self,
        execution_id: int,
        step_id: int,
    ) -> InteractiveResponse | None:
        """Retrieve a response by execution and step ID."""
        db: Session = self.db_factory()
        try:
            return (
                db.query(InteractiveResponse)
                .filter(
                    InteractiveResponse.execution_id == execution_id,
                    InteractiveResponse.step_id == step_id,
                )
                .first()
            )
        finally:
            db.close()

    def check_response_exists(
        self,
        execution_id: int,
        step_id: int,
    ) -> bool:
        """Check if a response already exists (for timeout handling)."""
        db: Session = self.db_factory()
        try:
            return (
                db.query(InteractiveResponse)
                .filter(
                    InteractiveResponse.execution_id == execution_id,
                    InteractiveResponse.step_id == step_id,
                )
                .first()
                is not None
            )
        finally:
            db.close()

    async def cancel_pending_response(
        self,
        execution_id: int,
        step_id: int,
    ) -> None:
        """Cancel the timeout job when a real response arrives early."""
        job_id = f"interactive_timeout_{execution_id}_{step_id}"
        try:
            self.scheduler.apscheduler.remove_job(job_id)
            logger.info(
                "interactive_timeout_cancelled",
                execution_id=execution_id,
                step_id=step_id,
            )
        except Exception:  # noqa: BLE001
            # Job may not exist or already fired -- this is fine
            logger.debug(
                "interactive_timeout_cancel_skipped",
                execution_id=execution_id,
                step_id=step_id,
            )

    async def _request_resume_when_waiting(self, execution_id: int) -> None:
        """Schedule an immediate resume once the execution is in 'waiting' status.

        Polls with bounded exponential backoff to handle the race where the
        user responds before the executor has committed ``status="waiting"``.
        If the execution is already terminal, stops without scheduling.
        """
        from backend.models.pipeline import WorkflowExecution

        for delay in _RESUME_RETRY_DELAYS:
            db: Session = self.db_factory()
            try:
                execution = (
                    db.query(WorkflowExecution).filter(WorkflowExecution.id == execution_id).first()
                )
                if execution is None:
                    logger.warning(
                        "interactive_resume_execution_not_found",
                        execution_id=execution_id,
                    )
                    return

                status = execution.status
            finally:
                db.close()

            if status == "waiting":
                resume_at = datetime.now(UTC)
                self.scheduler.schedule_workflow_resume(execution_id, resume_at)
                logger.info(
                    "interactive_pipeline_resume_scheduled",
                    execution_id=execution_id,
                )
                return

            if status in ("completed", "failed", "cancelled"):
                logger.info(
                    "interactive_resume_execution_terminal",
                    execution_id=execution_id,
                    status=status,
                )
                return

            # Still "running" -- executor hasn't committed "waiting" yet
            logger.debug(
                "interactive_resume_waiting_for_status",
                execution_id=execution_id,
                status=status,
                retry_delay=delay,
            )
            await asyncio.sleep(delay)

        # Exhausted retries -- log hard error
        logger.error(
            "interactive_resume_retries_exhausted",
            execution_id=execution_id,
        )
