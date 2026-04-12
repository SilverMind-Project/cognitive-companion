"""Telegram command trigger service.

Polls the Telegram Bot API for incoming messages and dispatches matching
commands to rules whose ``trigger_type`` is ``"telegram"``.

Design
------
The dispatch path is identical to webhook triggers: a ``TriggerContext`` with
``trigger_type="telegram"`` is built and passed to ``PipelineExecutor``.  The
Telegram message payload is exposed under ``pipeline_data["trigger_input"]``
(the same key used for webhook payloads), so prompts and conditions can
reference ``{{trigger_input.command}}``, ``{{trigger_input.chat_id}}``, and
``{{trigger_input.args}}``.

Rule configuration (``telegram_trigger_config``)
-------------------------------------------------
- ``command`` (str): Telegram command to match, e.g. ``"/medication"``.
  Case-insensitive.  Omit (or set to ``""``) to match *any* command.
- ``allowed_chat_ids`` (list[str | int]): Per-rule chat-ID whitelist.  Falls
  back to ``notifications.telegram.trigger_allowed_chat_ids`` in settings.
  An absent or empty whitelist is treated as **blocked** (fail-closed).
- ``respond_with_ack`` (bool, default ``true``): Send a brief acknowledgment
  back to the chat when the rule is dispatched.

Example ``settings.yaml`` snippet::

    notifications:
      telegram:
        trigger_poll_interval_seconds: 5   # how often to poll (default 5)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session, selectinload

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.models.rule import Rule
from backend.steps.base import TriggerContext

logger = get_logger(__name__)

_ACK_TEMPLATE = "Running rule: <b>{name}</b>"


# ---------------------------------------------------------------------------
# Dependency protocols
# ---------------------------------------------------------------------------


class _TelegramClient(Protocol):
    @property
    def configured(self) -> bool: ...

    async def get_updates(self, *, offset: int | None, timeout: int) -> list[dict[str, Any]]: ...

    async def send_message(
        self, chat_id: str | int, text: str, parse_mode: str | None = ...
    ) -> bool: ...


class _PipelineExecutor(Protocol):
    async def execute(self, rule: Rule, trigger: TriggerContext, db: Session): ...


# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _ParsedCommand:
    """A normalised Telegram command extracted from one update message."""

    command: str        # e.g. "/remind"
    args: list[str]     # tokens after the command
    raw_text: str       # full original text
    chat_id: str        # string form of the Telegram chat ID
    from_user: dict[str, Any]

    @classmethod
    def from_message(cls, message: dict[str, Any]) -> _ParsedCommand | None:
        """Return a parsed command or ``None`` if the message is not a command."""
        text = (message.get("text") or "").strip()
        if not text.startswith("/"):
            return None

        parts = text.split()
        return cls(
            command=parts[0].lower().split("@")[0],
            args=parts[1:],
            raw_text=text,
            chat_id=str((message.get("chat") or {}).get("id", "")),
            from_user=message.get("from") or {},
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class TelegramTriggerService:
    """Maps incoming Telegram commands to pipeline rule executions.

    Driven by a short-interval APScheduler job (see ``backend/main.py``).
    Each :meth:`poll` call fetches one batch of updates via short-polling
    (``timeout=0``), advances the internal offset to prevent re-processing,
    and dispatches any matching commands.
    """

    def __init__(
        self,
        telegram_client: _TelegramClient,
        pipeline_executor: _PipelineExecutor,
        db_session_factory: Callable[[], Session],
    ) -> None:
        self._client = telegram_client
        self._executor = pipeline_executor
        self._db_factory = db_session_factory
        self._offset: int | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def poll(self) -> None:
        """Fetch one batch of updates and dispatch any matching commands."""
        if not self._client.configured:
            return

        updates = await self._client.get_updates(offset=self._offset, timeout=0)
        if not updates:
            return

        for update in updates:
            self._advance_offset(update)

            message = update.get("message")
            if not message:
                continue

            cmd = _ParsedCommand.from_message(message)
            if cmd is not None:
                await self._dispatch(cmd)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _advance_offset(self, update: dict[str, Any]) -> None:
        update_id = update.get("update_id")
        if update_id is not None:
            self._offset = update_id + 1

    async def _dispatch(self, cmd: _ParsedCommand) -> None:
        """Load matching enabled rules and fire each authorised one."""
        rules = self._load_telegram_rules()

        for rule in rules:
            cfg: dict[str, Any] = rule.telegram_trigger_config or {}

            if not _command_matches(cmd.command, cfg):
                continue

            whitelist = self._resolve_whitelist(cfg)
            if not whitelist:
                logger.error(
                    "telegram_command_blocked_no_whitelist",
                    command=cmd.command,
                    rule=rule.name,
                    hint=(
                        "Set notifications.telegram.trigger_allowed_chat_ids "
                        "in notifications.yaml or allowed_chat_ids on the rule."
                    ),
                )
                continue

            if cmd.chat_id not in whitelist:
                logger.warning(
                    "telegram_command_unauthorized",
                    chat_id=cmd.chat_id,
                    command=cmd.command,
                    rule=rule.name,
                )
                continue

            logger.info(
                "telegram_command_matched",
                command=cmd.command,
                chat_id=cmd.chat_id,
                rule=rule.name,
            )
            await self._execute_rule(rule, cfg, cmd)

    def _load_telegram_rules(self) -> list[Rule]:
        """Return all enabled telegram-triggered rules with steps pre-loaded.

        Steps are fetched eagerly so the returned ``Rule`` objects remain
        usable after this session closes.
        """
        db = self._db_factory()
        try:
            return (
                db.query(Rule)
                .options(selectinload(Rule.steps))
                .filter(Rule.enabled.is_(True), Rule.trigger_type == "telegram")
                .all()
            )
        finally:
            db.close()

    def _resolve_whitelist(self, cfg: dict[str, Any]) -> list[str]:
        """Return the effective chat-ID whitelist for a rule config.

        Resolution order:

        1. Per-rule ``allowed_chat_ids`` from ``telegram_trigger_config``
        2. System-wide ``notifications.telegram.trigger_allowed_chat_ids``

        Empty strings (e.g. from unset env vars) are discarded.  Returns
        ``[]`` when no whitelist is configured; callers treat that as blocked.
        """
        per_rule = [str(c) for c in (cfg.get("allowed_chat_ids") or []) if c]
        if per_rule:
            return per_rule
        return [
            str(c)
            for c in (settings.get("notifications.telegram.trigger_allowed_chat_ids") or [])
            if c
        ]

    async def _execute_rule(
        self,
        rule: Rule,
        cfg: dict[str, Any],
        cmd: _ParsedCommand,
    ) -> None:
        """Build a TriggerContext and dispatch via PipelineExecutor."""
        trigger = TriggerContext(
            trigger_type="telegram",
            sensor_id=rule.primary_sensor_id,
            # Shared with HTTP webhook triggers so downstream steps can
            # reference {{trigger_input.command}}, {{trigger_input.args}}, etc.
            webhook_payload={
                "command": cmd.command,
                "args": cmd.args,
                "text": cmd.raw_text,
                "chat_id": cmd.chat_id,
                "from_user": cmd.from_user,
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
                    cmd.chat_id,
                    _ACK_TEMPLATE.format(name=rule.name),
                )
        except Exception:
            logger.exception(
                "telegram_dispatch_failed",
                rule=rule.name,
                command=cmd.command,
                chat_id=cmd.chat_id,
            )
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _command_matches(command: str, cfg: dict[str, Any]) -> bool:
    """Return ``True`` if *cfg* matches *command* (or matches any command)."""
    rule_command = (cfg.get("command") or "").lower().split("@")[0]
    return not rule_command or rule_command == command
