"""Interactive prompt step -- ask user a question and wait for response."""

from __future__ import annotations

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
class InteractivePromptHandler(StepHandler):
    """Pipeline step for interactive user prompts.

    This step sends a question to the user via configured channels
    (popup text, voice AI) and pauses pipeline execution until a
    response is received or timeout occurs.
    """

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="interactive_prompt",
            display_name="Interactive Prompt",
            category="flow",
            icon="mdi-message-question",
            description="Ask user a question and wait for response",
            config_schema={
                "type": "object",
                "properties": {
                    "voice_prompt_template": {
                        "type": "string",
                        "description": "Voice prompt template with {{variable}} syntax",
                    },
                    "popup_message_template": {
                        "type": "string",
                        "description": "Popup message template with {{variable}} syntax",
                    },
                    "popup_title": {
                        "type": "string",
                        "default": "Question for You",
                        "description": "Title shown at the top of the popup dialog",
                    },
                    "popup_icon": {
                        "type": "string",
                        "enum": [
                            "mdi-message-question",
                            "mdi-help-circle",
                            "mdi-alert",
                            "mdi-alert-circle",
                            "mdi-alert-octagon",
                            "mdi-bell",
                            "mdi-bell-ring",
                            "mdi-information",
                            "mdi-volume-high",
                            "mdi-account-voice",
                            "mdi-check-circle",
                            "mdi-heart-pulse",
                            "mdi-pill",
                            "mdi-human-greeting",
                        ],
                        "default": "mdi-message-question",
                        "description": "Material Design icon displayed in the popup",
                    },
                    "auto_escalate": {
                        "type": "boolean",
                        "default": False,
                        "description": "Automatically escalate on timeout or affirmative response",
                    },
                    "escalate_button_text": {
                        "type": "string",
                        "default": "I need help",
                        "description": "Text for escalation button",
                    },
                    "dismiss_button_text": {
                        "type": "string",
                        "default": "I'm okay",
                        "description": "Text for dismiss button",
                    },
                    "countdown_seconds": {
                        "type": "integer",
                        "minimum": 5,
                        "maximum": 300,
                        "default": 30,
                        "description": "Timeout duration in seconds",
                    },
                    "timeout_action": {
                        "type": "string",
                        "enum": ["escalate", "dismiss"],
                        "default": "escalate",
                        "description": "Action to take when timeout occurs",
                    },
                    "output_key": {
                        "type": "string",
                        "default": "interactive_response",
                        "description": "Key for storing response in pipeline_data",
                    },
                },
                "anyOf": [
                    {"required": ["voice_prompt_template"]},
                    {"required": ["popup_message_template"]},
                ],
            },
            default_config={
                "popup_title": "Question for You",
                "popup_icon": "mdi-message-question",
                "auto_escalate": False,
                "escalate_button_text": "I need help",
                "dismiss_button_text": "I'm okay",
                "countdown_seconds": 30,
                "timeout_action": "escalate",
                "output_key": "interactive_response",
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
        """Send interactive prompt and pause execution.

        Renders templates, sends prompts via configured channels, schedules
        timeout, and returns StepResult with wait_until to pause pipeline.
        """
        from datetime import UTC, datetime, timedelta

        from backend.core.template import render_template

        config = step.config_json or {}

        # Extract configuration
        voice_prompt_template = config.get("voice_prompt_template")
        popup_message_template = config.get("popup_message_template")
        countdown_seconds = config.get("countdown_seconds", 30)
        timeout_action = config.get("timeout_action", "escalate")
        output_key = config.get("output_key", "interactive_response")
        escalate_button_text = config.get("escalate_button_text", "I need help")
        dismiss_button_text = config.get("dismiss_button_text", "I'm okay")
        popup_title = config.get("popup_title", "Question for You")
        popup_icon = config.get("popup_icon", "mdi-message-question")

        # Validate that at least one channel is configured
        if not voice_prompt_template and not popup_message_template:
            logger.error(
                "interactive_prompt_no_channels",
                execution_id=execution.id,
                step_id=step.id,
            )
            # Fail-safe: continue with action="dismiss"
            pipeline_data[output_key] = {
                "channel": "error",
                "action": "dismiss",
                "timestamp": datetime.now(UTC).isoformat(),
                "raw_response": {"error": "No channels configured"},
            }
            return StepResult(
                success=True,
                data={output_key: pipeline_data[output_key]},
            )

        # Prepare trigger variables for template rendering
        trigger_vars = {
            "room_name": trigger.room_name,
            "sensor_id": trigger.sensor_id,
        }

        # Render templates
        rendered_voice_prompt = None
        rendered_popup_message = None

        try:
            if voice_prompt_template:
                rendered_voice_prompt = render_template(
                    voice_prompt_template,
                    pipeline_data,
                    trigger_vars,
                )

            if popup_message_template:
                rendered_popup_message = render_template(
                    popup_message_template,
                    pipeline_data,
                    trigger_vars,
                )
        except Exception as e:
            logger.error(
                "interactive_prompt_template_error",
                execution_id=execution.id,
                step_id=step.id,
                error=str(e),
            )
            # Fail-safe: continue with action="dismiss"
            pipeline_data[output_key] = {
                "channel": "error",
                "action": "dismiss",
                "timestamp": datetime.now(UTC).isoformat(),
                "raw_response": {"error": f"Template rendering failed: {e!s}"},
            }
            return StepResult(
                success=True,
                data={output_key: pipeline_data[output_key]},
            )

        # Update WorkflowExecution status to "waiting_for_response"
        db = services.db_factory()
        try:
            execution.status = "waiting_for_response"
            db.commit()
        finally:
            db.close()

        # Calculate timeout timestamp
        timeout_timestamp = datetime.now(UTC) + timedelta(seconds=countdown_seconds)
        server_timestamp = datetime.now(UTC).isoformat()

        # Track whether at least one channel succeeded
        popup_sent = False
        voice_sent = False

        # Send interactive_prompt message via WebSocket for popup channel
        if rendered_popup_message:
            # Get WebSocket manager from notification dispatcher
            notification_dispatcher = services.notification_dispatcher
            ws_manager = None
            if notification_dispatcher and hasattr(notification_dispatcher, "_dispatch_services"):
                ws_manager = notification_dispatcher._dispatch_services.ws_manager

            if ws_manager:
                try:
                    await ws_manager.broadcast({
                        "type": "interactive_prompt",
                        "execution_id": execution.id,
                        "step_id": step.id,
                        "message": rendered_popup_message,
                        "title": popup_title,
                        "icon": popup_icon,
                        "escalate_button_text": escalate_button_text,
                        "dismiss_button_text": dismiss_button_text,
                        "countdown_seconds": countdown_seconds,
                        "server_timestamp": server_timestamp,
                    })
                    popup_sent = True
                    logger.info(
                        "interactive_prompt_sent",
                        execution_id=execution.id,
                        step_id=step.id,
                        channel="pwa_popup_text",
                        countdown_seconds=countdown_seconds,
                    )
                except Exception as e:
                    logger.error(
                        "interactive_prompt_send_error",
                        execution_id=execution.id,
                        step_id=step.id,
                        channel="pwa_popup_text",
                        error=str(e),
                        exc_info=True,
                    )
            else:
                logger.error(
                    "interactive_prompt_no_ws_manager",
                    execution_id=execution.id,
                    step_id=step.id,
                )

        # Send voice prompt via Gemini Live for voice channel
        if rendered_voice_prompt:
            # Get WebSocket manager from notification dispatcher
            notification_dispatcher = services.notification_dispatcher
            ws_manager = None
            if notification_dispatcher and hasattr(notification_dispatcher, "_dispatch_services"):
                ws_manager = notification_dispatcher._dispatch_services.ws_manager

            if ws_manager:
                try:
                    # Send voice prompt with execution context for MCP tool correlation
                    prompt_with_context = (
                        f"{rendered_voice_prompt}\n\n"
                        f"[System context: execution_id={execution.id}, step_id={step.id}]"
                    )
                    await ws_manager.send_backend_task(
                        prompt=prompt_with_context,
                        callback=None,
                    )
                    voice_sent = True
                    logger.info(
                        "interactive_prompt_sent",
                        execution_id=execution.id,
                        step_id=step.id,
                        channel="pwa_realtime_ai",
                        countdown_seconds=countdown_seconds,
                    )
                    # Signal frontend to auto-enable microphone so the user
                    # can respond to Gemini Live without tapping the mic.
                    try:
                        await ws_manager.broadcast({
                            "type": "enable_microphone",
                            "reason": "interactive_prompt_voice",
                            "execution_id": execution.id,
                            "step_id": step.id,
                        })
                    except Exception as broadcast_error:
                        logger.error(
                            "interactive_prompt_enable_mic_error",
                            execution_id=execution.id,
                            step_id=step.id,
                            error=str(broadcast_error),
                        )
                except Exception as e:
                    logger.error(
                        "interactive_prompt_send_error",
                        execution_id=execution.id,
                        step_id=step.id,
                        channel="pwa_realtime_ai",
                        error=str(e),
                        exc_info=True,
                    )
            else:
                logger.error(
                    "interactive_prompt_no_ws_manager_voice",
                    execution_id=execution.id,
                    step_id=step.id,
                )

        # If both channels failed to send, fail-safe with action="dismiss"
        if not popup_sent and not voice_sent:
            logger.error(
                "interactive_prompt_all_channels_failed",
                execution_id=execution.id,
                step_id=step.id,
            )
            # Fail-safe: continue with action="dismiss"
            pipeline_data[output_key] = {
                "channel": "error",
                "action": "dismiss",
                "timestamp": datetime.now(UTC).isoformat(),
                "raw_response": {"error": "All channels failed to send"},
            }
            return StepResult(
                success=True,
                data={output_key: pipeline_data[output_key]},
            )

        # Schedule timeout task via scheduler
        if services.scheduler:
            try:
                job_id = f"interactive_timeout_{execution.id}_{step.id}"
                services.scheduler.apscheduler.add_job(
                    self._handle_timeout,
                    "date",
                    run_date=timeout_timestamp,
                    id=job_id,
                    args=[execution.id, step.id, timeout_action, services],
                    replace_existing=True,
                )
                logger.info(
                    "interactive_timeout_scheduled",
                    execution_id=execution.id,
                    step_id=step.id,
                    timeout_at=timeout_timestamp.isoformat(),
                )
            except Exception as e:
                logger.error(
                    "interactive_timeout_schedule_error",
                    execution_id=execution.id,
                    step_id=step.id,
                    error=str(e),
                )
                # Fail-safe: continue with action="dismiss"
                pipeline_data[output_key] = {
                    "channel": "error",
                    "action": "dismiss",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "raw_response": {"error": f"Timeout scheduling failed: {e!s}"},
                }
                return StepResult(
                    success=True,
                    data={output_key: pipeline_data[output_key]},
                )

        # Return StepResult with wait_until set to timeout timestamp
        return StepResult(
            success=True,
            data={},
            wait_until=timeout_timestamp,
        )

    @staticmethod
    async def _handle_timeout(
        execution_id: int,
        step_id: int,
        timeout_action: str,
        services: ServiceContainer,
    ) -> None:
        """Handle timeout when no response is received.

        Creates a synthetic timeout response if no user response exists.
        """
        from datetime import UTC, datetime

        interactive_response_service = services.interactive_response_service
        if not interactive_response_service:
            logger.error(
                "interactive_timeout_no_service",
                execution_id=execution_id,
                step_id=step_id,
            )
            return

        # Check if response already exists
        if interactive_response_service.check_response_exists(execution_id, step_id):
            logger.info(
                "interactive_timeout_response_exists",
                execution_id=execution_id,
                step_id=step_id,
            )
            return

        # Create synthetic timeout response
        try:
            await interactive_response_service.record_response(
                execution_id=execution_id,
                step_id=step_id,
                channel="timeout",
                action=timeout_action,
                timestamp=datetime.now(UTC),
                raw_response={"timeout_action": timeout_action},
            )
            logger.info(
                "interactive_timeout_fired",
                execution_id=execution_id,
                step_id=step_id,
                timeout_action=timeout_action,
            )
        except Exception as e:
            logger.error(
                "interactive_timeout_record_error",
                execution_id=execution_id,
                step_id=step_id,
                error=str(e),
            )
