"""Telegram command trigger service.

Polls the Telegram Bot API for incoming messages and dispatches matching
commands to rules whose ``trigger_type`` is ``"telegram"``.

Design
------
The dispatch path is *identical* to webhook triggers -- a ``TriggerContext``
with ``trigger_type="telegram"`` is built and passed to ``PipelineExecutor``.
The only difference from webhooks is the delivery channel: instead of an
inbound HTTP POST, the trigger arrives as a Telegram text message.

The Telegram message payload is made available in ``pipeline_data["trigger_input"]``
(the same key used for webhook payloads), so prompts and conditions can
reference ``{{trigger_input.command}}``, ``{{trigger_input.chat_id}}``, and
``{{trigger_input.args}}``.

Rule configuration (``telegram_trigger_config``)
-------------------------------------------------
- ``command`` (str): Telegram command to match, e.g. ``"/medication"``.
  Case-insensitive.  Omit (or set to ``""``) to match *any* command.
- ``allowed_chat_ids`` (list[str | int]): Whitelist of Telegram chat IDs that
  may trigger this rule.  An empty list allows any chat ID.
- ``respond_with_ack`` (bool, default ``true``): Send a brief acknowledgment
  message back to the chat when the rule is dispatched.

Example ``settings.yaml`` snippet::

    notifications:
      telegram:
        trigger_poll_interval_seconds: 5   # how often to poll (default 5)
"""

from __future__ import annotations

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.models.rule import Rule
from backend.steps.base import TriggerContext

logger = get_logger(__name__)


class TelegramTriggerService:
    """Maps incoming Telegram commands to pipeline rule executions.

    The service is driven by a scheduler job (see ``backend/main.py``).  On
    each ``poll()`` call it fetches new updates from the Bot API, advances the
    internal offset to avoid re-processing, and dispatches any matching
    commands.
    """

    def __init__(
        self,
        telegram_client,
        pipeline_executor,
        db_session_factory,
    ) -> None:
        self._client = telegram_client
        self._executor = pipeline_executor
        self._db_factory = db_session_factory
        self._offset: int | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def poll(self) -> None:
        """Fetch one batch of updates and dispatch any matching commands.

        Designed to be called from a short-interval APScheduler job.  Uses
        short-polling (timeout=0) so the job does not block the scheduler.
        """
        if not self._client.configured:
            return

        updates = await self._client.get_updates(offset=self._offset, timeout=0)
        if not updates:
            return

        for update in updates:
            update_id = update.get("update_id")
            if update_id is not None:
                self._offset = update_id + 1

            message = update.get("message")
            if not message:
                continue

            text = (message.get("text") or "").strip()
            if not text.startswith("/"):
                continue

            chat_id = str((message.get("chat") or {}).get("id", ""))
            from_user = message.get("from") or {}

            # Separate command and args; strip @BotName suffix if present
            parts = text.split()
            raw_command = parts[0].lower()
            command = raw_command.split("@")[0]
            args = parts[1:]

            await self._dispatch_command(
                command=command,
                chat_id=chat_id,
                from_user=from_user,
                args=args,
                raw_text=text,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _dispatch_command(
        self,
        command: str,
        chat_id: str,
        from_user: dict,
        args: list[str],
        raw_text: str,
    ) -> None:
        """Find all enabled telegram-triggered rules matching *command* and fire them."""
        db = self._db_factory()
        try:
            rules = (
                db.query(Rule)
                .filter(
                    Rule.enabled.is_(True),
                    Rule.trigger_type == "telegram",
                )
                .all()
            )
        finally:
            db.close()

        for rule in rules:
            cfg: dict = rule.telegram_trigger_config or {}

            # --- command match ---
            rule_command = (cfg.get("command") or "").lower().split("@")[0]
            if rule_command and rule_command != command:
                continue

            # --- chat_id whitelist ---
            allowed: list = cfg.get("allowed_chat_ids") or []
            if allowed and chat_id not in [str(c) for c in allowed]:
                logger.warning(
                    "telegram_command_unauthorized",
                    chat_id=chat_id,
                    command=command,
                    rule=rule.name,
                )
                continue

            logger.info(
                "telegram_command_matched",
                command=command,
                chat_id=chat_id,
                rule=rule.name,
            )

            await self._execute_rule(rule, command, args, raw_text, chat_id, from_user, cfg)

    async def _execute_rule(
        self,
        rule: Rule,
        command: str,
        args: list[str],
        raw_text: str,
        chat_id: str,
        from_user: dict,
        cfg: dict,
    ) -> None:
        """Build a TriggerContext and dispatch via PipelineExecutor."""
        trigger = TriggerContext(
            trigger_type="telegram",
            sensor_id=rule.primary_sensor_id,
            # Expose message metadata via the same key as webhook payloads so
            # downstream steps can access {{trigger_input.command}} etc.
            webhook_payload={
                "command": command,
                "args": args,
                "text": raw_text,
                "chat_id": chat_id,
                "from_user": from_user,
            },
        )

        db = self._db_factory()
        try:
            execution = await self._executor.execute(rule, trigger, db)
            logger.info(
                "telegram_rule_dispatched",
                rule=rule.name,
                execution_id=execution.id,
                status=execution.status,
            )

            if cfg.get("respond_with_ack", True):
                await self._client.send_message(
                    chat_id,
                    f"Running rule: <b>{rule.name}</b>",
                )
        except Exception:
            logger.exception(
                "telegram_dispatch_failed",
                rule=rule.name,
                command=command,
                chat_id=chat_id,
            )
        finally:
            db.close()
