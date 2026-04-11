"""Tests for TelegramTriggerService.

Covers:
- ``_ParsedCommand.from_message`` -- message parsing and normalisation
- ``_command_matches``             -- pure command-matching logic
- ``TelegramTriggerService.poll``  -- offset tracking, message filtering
- ``TelegramTriggerService._dispatch`` -- authorization (whitelist, fail-closed)
- ``TelegramTriggerService._execute_rule`` -- TriggerContext construction, ack, error handling
- ``TelegramTriggerService._load_telegram_rules`` -- DB integration, eager step loading
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from backend.models.pipeline import PipelineStep
from backend.models.rule import Rule
from backend.services.telegram_trigger import (
    TelegramTriggerService,
    _command_matches,
    _ParsedCommand,
)
from backend.steps.base import TriggerContext

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_client(configured: bool = True) -> MagicMock:
    client = MagicMock()
    client.configured = configured
    client.get_updates = AsyncMock(return_value=[])
    client.send_message = AsyncMock()
    return client


def _make_executor(execution_id: int = 1, status: str = "completed") -> MagicMock:
    execution = MagicMock()
    execution.id = execution_id
    execution.status = status
    executor = MagicMock()
    executor.execute = AsyncMock(return_value=execution)
    return executor


def _make_service(
    client=None,
    executor=None,
    db_factory=None,
) -> TelegramTriggerService:
    return TelegramTriggerService(
        telegram_client=client or _make_client(),
        pipeline_executor=executor or _make_executor(),
        db_session_factory=db_factory or (lambda: MagicMock()),
    )


def _make_rule_obj(
    name: str = "test-rule",
    command: str = "/remind",
    allowed_chat_ids: list | None = None,
    respond_with_ack: bool = True,
    rule_id: int = 1,
) -> Rule:
    """Build a transient Rule ORM object suitable for unit tests.

    Steps default to an empty list; SQLAlchemy returns ``[]`` for transient
    objects without a session, so no explicit assignment is required.
    """
    return Rule(
        id=rule_id,
        name=name,
        enabled=True,
        trigger_type="telegram",
        telegram_trigger_config={
            "command": command,
            "allowed_chat_ids": [] if allowed_chat_ids is None else allowed_chat_ids,
            "respond_with_ack": respond_with_ack,
        },
    )


def _make_update(
    update_id: int = 1,
    text: str = "/remind",
    chat_id: int = 123,
) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "text": text,
            "chat": {"id": chat_id},
            "from": {"id": 42, "first_name": "Alice"},
        },
    }


def _cmd(
    command: str = "/remind",
    chat_id: str = "123",
    args: list[str] | None = None,
) -> _ParsedCommand:
    return _ParsedCommand(
        command=command,
        args=args or [],
        raw_text=command,
        chat_id=chat_id,
        from_user={},
    )


# ---------------------------------------------------------------------------
# _ParsedCommand.from_message
# ---------------------------------------------------------------------------


class TestParsedCommand:
    def test_returns_none_for_plain_text(self):
        assert _ParsedCommand.from_message({"text": "hello world"}) is None

    def test_returns_none_when_text_missing(self):
        assert _ParsedCommand.from_message({}) is None

    def test_returns_none_when_text_is_null(self):
        assert _ParsedCommand.from_message({"text": None}) is None

    def test_parses_bare_command(self):
        cmd = _ParsedCommand.from_message({"text": "/remind", "chat": {"id": 99}, "from": {}})
        assert cmd is not None
        assert cmd.command == "/remind"
        assert cmd.args == []
        assert cmd.chat_id == "99"

    def test_parses_command_with_multiple_args(self):
        cmd = _ParsedCommand.from_message(
            {"text": "/remind take medication now", "chat": {"id": 5}, "from": {}}
        )
        assert cmd.command == "/remind"
        assert cmd.args == ["take", "medication", "now"]

    def test_strips_bot_name_suffix_from_command(self):
        cmd = _ParsedCommand.from_message(
            {"text": "/remind@MyBot arg1", "chat": {"id": 5}, "from": {}}
        )
        assert cmd.command == "/remind"
        assert cmd.args == ["arg1"]

    def test_lowercases_command(self):
        cmd = _ParsedCommand.from_message({"text": "/ReMiNd", "chat": {"id": 5}, "from": {}})
        assert cmd.command == "/remind"

    def test_raw_text_preserved_exactly(self):
        raw = "/remind take medication"
        cmd = _ParsedCommand.from_message({"text": raw, "chat": {"id": 5}, "from": {}})
        assert cmd.raw_text == raw

    def test_missing_chat_yields_empty_chat_id(self):
        cmd = _ParsedCommand.from_message({"text": "/remind"})
        assert cmd is not None
        assert cmd.chat_id == ""

    def test_from_user_defaults_to_empty_dict(self):
        cmd = _ParsedCommand.from_message({"text": "/remind", "chat": {"id": 1}})
        assert cmd.from_user == {}

    def test_from_user_populated_when_present(self):
        msg = {"text": "/cmd", "chat": {"id": 1}, "from": {"id": 7, "first_name": "Bob"}}
        cmd = _ParsedCommand.from_message(msg)
        assert cmd.from_user == {"id": 7, "first_name": "Bob"}


# ---------------------------------------------------------------------------
# _command_matches
# ---------------------------------------------------------------------------


class TestCommandMatches:
    def test_empty_rule_command_matches_any_command(self):
        assert _command_matches("/anything", {}) is True

    def test_empty_string_rule_command_matches_any_command(self):
        assert _command_matches("/remind", {"command": ""}) is True

    def test_exact_match_returns_true(self):
        assert _command_matches("/remind", {"command": "/remind"}) is True

    def test_different_command_returns_false(self):
        assert _command_matches("/status", {"command": "/remind"}) is False

    def test_case_insensitive_match(self):
        assert _command_matches("/remind", {"command": "/REMIND"}) is True

    def test_strips_bot_name_suffix_from_rule_config(self):
        assert _command_matches("/remind", {"command": "/remind@MyBot"}) is True


# ---------------------------------------------------------------------------
# TelegramTriggerService.poll
# ---------------------------------------------------------------------------


class TestPoll:
    async def test_skips_when_client_not_configured(self):
        client = _make_client(configured=False)
        svc = _make_service(client=client)
        await svc.poll()
        client.get_updates.assert_not_awaited()

    async def test_returns_early_on_empty_updates(self):
        svc = _make_service()
        with patch.object(svc, "_dispatch", new_callable=AsyncMock) as mock_dispatch:
            await svc.poll()
        mock_dispatch.assert_not_awaited()

    async def test_advances_offset_past_highest_update_id(self):
        client = _make_client()
        client.get_updates = AsyncMock(
            return_value=[
                _make_update(update_id=10, text="hello"),
                _make_update(update_id=11, text="world"),
            ]
        )
        svc = _make_service(client=client)
        await svc.poll()
        assert svc._offset == 12

    async def test_offset_advances_for_non_command_messages(self):
        client = _make_client()
        client.get_updates = AsyncMock(return_value=[_make_update(update_id=5, text="hello")])
        svc = _make_service(client=client)
        await svc.poll()
        assert svc._offset == 6

    async def test_skips_updates_without_message_field(self):
        client = _make_client()
        client.get_updates = AsyncMock(return_value=[{"update_id": 1}])
        svc = _make_service(client=client)
        with patch.object(svc, "_dispatch", new_callable=AsyncMock) as mock_dispatch:
            await svc.poll()
        mock_dispatch.assert_not_awaited()

    async def test_skips_non_command_messages(self):
        client = _make_client()
        client.get_updates = AsyncMock(return_value=[_make_update(text="hello world")])
        svc = _make_service(client=client)
        with patch.object(svc, "_dispatch", new_callable=AsyncMock) as mock_dispatch:
            await svc.poll()
        mock_dispatch.assert_not_awaited()

    async def test_dispatches_command_with_correct_parsed_fields(self):
        client = _make_client()
        client.get_updates = AsyncMock(
            return_value=[_make_update(text="/remind take medication", chat_id=55)]
        )
        svc = _make_service(client=client)
        with patch.object(svc, "_dispatch", new_callable=AsyncMock) as mock_dispatch:
            await svc.poll()
        mock_dispatch.assert_awaited_once()
        dispatched: _ParsedCommand = mock_dispatch.call_args[0][0]
        assert dispatched.command == "/remind"
        assert dispatched.args == ["take", "medication"]
        assert dispatched.chat_id == "55"

    async def test_passes_current_offset_to_get_updates(self):
        client = _make_client()
        client.get_updates = AsyncMock(return_value=[])
        svc = _make_service(client=client)
        svc._offset = 99
        await svc.poll()
        client.get_updates.assert_awaited_once_with(offset=99, timeout=0)

    async def test_dispatches_all_commands_skipping_non_commands(self):
        client = _make_client()
        client.get_updates = AsyncMock(
            return_value=[
                _make_update(update_id=1, text="/remind"),
                _make_update(update_id=2, text="not a command"),
                _make_update(update_id=3, text="/status"),
            ]
        )
        svc = _make_service(client=client)
        with patch.object(svc, "_dispatch", new_callable=AsyncMock) as mock_dispatch:
            await svc.poll()
        assert mock_dispatch.await_count == 2
        commands = [c[0][0].command for c in mock_dispatch.await_args_list]
        assert commands == ["/remind", "/status"]


# ---------------------------------------------------------------------------
# TelegramTriggerService._dispatch  (authorization + routing)
# ---------------------------------------------------------------------------


class TestDispatch:
    """_dispatch is tested via direct calls with _load_telegram_rules mocked."""

    def _svc_with_rules(self, rules: list) -> TelegramTriggerService:
        svc = _make_service()
        svc._load_telegram_rules = MagicMock(return_value=rules)
        return svc

    async def test_skips_rule_when_command_does_not_match(self):
        rule = _make_rule_obj(command="/status", allowed_chat_ids=["123"])
        svc = self._svc_with_rules([rule])
        with patch.object(svc, "_execute_rule", new_callable=AsyncMock) as mock_exec:
            await svc._dispatch(_cmd(command="/remind", chat_id="123"))
        mock_exec.assert_not_awaited()

    async def test_blocks_rule_with_no_whitelist_configured(self):
        """An absent or empty whitelist must block execution (fail-closed)."""
        rule = _make_rule_obj(command="/remind", allowed_chat_ids=[])
        svc = self._svc_with_rules([rule])
        with patch("backend.services.telegram_trigger.settings") as mock_settings, \
             patch.object(svc, "_execute_rule", new_callable=AsyncMock) as mock_exec:
            mock_settings.get.return_value = []
            await svc._dispatch(_cmd(command="/remind", chat_id="123"))
        mock_exec.assert_not_awaited()

    async def test_blocks_unauthorized_chat_id(self):
        rule = _make_rule_obj(command="/remind", allowed_chat_ids=["999"])
        svc = self._svc_with_rules([rule])
        with patch.object(svc, "_execute_rule", new_callable=AsyncMock) as mock_exec:
            await svc._dispatch(_cmd(command="/remind", chat_id="123"))
        mock_exec.assert_not_awaited()

    async def test_dispatches_authorized_chat_id(self):
        rule = _make_rule_obj(command="/remind", allowed_chat_ids=["123"])
        svc = self._svc_with_rules([rule])
        with patch.object(svc, "_execute_rule", new_callable=AsyncMock) as mock_exec:
            await svc._dispatch(_cmd(command="/remind", chat_id="123"))
        mock_exec.assert_awaited_once()

    async def test_falls_back_to_system_whitelist(self):
        rule = _make_rule_obj(command="/remind", allowed_chat_ids=[])
        svc = self._svc_with_rules([rule])
        with patch("backend.services.telegram_trigger.settings") as mock_settings, \
             patch.object(svc, "_execute_rule", new_callable=AsyncMock) as mock_exec:
            mock_settings.get.return_value = ["456"]
            await svc._dispatch(_cmd(command="/remind", chat_id="456"))
        mock_exec.assert_awaited_once()

    async def test_per_rule_whitelist_takes_precedence_over_system(self):
        """Per-rule whitelist is used and system whitelist is ignored."""
        rule = _make_rule_obj(command="/remind", allowed_chat_ids=["123"])
        svc = self._svc_with_rules([rule])
        with patch("backend.services.telegram_trigger.settings") as mock_settings, \
             patch.object(svc, "_execute_rule", new_callable=AsyncMock) as mock_exec:
            # System has "999"; per-rule only has "123".
            mock_settings.get.return_value = ["999"]
            # "123" is in per-rule → must pass.
            await svc._dispatch(_cmd(command="/remind", chat_id="123"))
            assert mock_exec.await_count == 1
            # "999" is not in per-rule → must block even though it is in system list.
            mock_exec.reset_mock()
            await svc._dispatch(_cmd(command="/remind", chat_id="999"))
            assert mock_exec.await_count == 0

    async def test_wildcard_rule_matches_any_command(self):
        """A rule with an empty command field fires for any incoming command."""
        rule = _make_rule_obj(command="", allowed_chat_ids=["123"])
        svc = self._svc_with_rules([rule])
        with patch.object(svc, "_execute_rule", new_callable=AsyncMock) as mock_exec:
            await svc._dispatch(_cmd(command="/anything", chat_id="123"))
        mock_exec.assert_awaited_once()

    async def test_empty_strings_in_whitelist_treated_as_no_whitelist(self):
        """Empty strings from unset env vars must not be treated as valid IDs."""
        rule = _make_rule_obj(command="/remind", allowed_chat_ids=["", ""])
        svc = self._svc_with_rules([rule])
        with patch("backend.services.telegram_trigger.settings") as mock_settings, \
             patch.object(svc, "_execute_rule", new_callable=AsyncMock) as mock_exec:
            mock_settings.get.return_value = []
            await svc._dispatch(_cmd(command="/remind", chat_id="123"))
        mock_exec.assert_not_awaited()

    async def test_multiple_rules_evaluated_independently(self):
        """A matching rule fires; a non-matching rule for the same command is skipped."""
        authorized = _make_rule_obj(name="auth", allowed_chat_ids=["123"], rule_id=1)
        unauthorized = _make_rule_obj(name="unauth", allowed_chat_ids=["999"], rule_id=2)
        svc = self._svc_with_rules([authorized, unauthorized])
        fired: list[str] = []

        async def _capture(rule, cfg, cmd):
            fired.append(rule.name)

        with patch.object(svc, "_execute_rule", side_effect=_capture):
            await svc._dispatch(_cmd(command="/remind", chat_id="123"))

        assert fired == ["auth"]


# ---------------------------------------------------------------------------
# TelegramTriggerService._execute_rule
# ---------------------------------------------------------------------------


class TestExecuteRule:
    async def test_builds_trigger_context_correctly(self):
        executor = _make_executor()
        svc = _make_service(executor=executor)
        rule = _make_rule_obj()
        rule.primary_sensor_id = "sensor-1"
        cfg = {"respond_with_ack": False}
        cmd = _ParsedCommand(
            command="/remind",
            args=["take", "medication"],
            raw_text="/remind take medication",
            chat_id="123",
            from_user={"id": 42},
        )

        await svc._execute_rule(rule, cfg, cmd)

        trigger: TriggerContext = executor.execute.call_args[0][1]
        assert trigger.trigger_type == "telegram"
        assert trigger.sensor_id == "sensor-1"
        payload = trigger.webhook_payload
        assert payload["command"] == "/remind"
        assert payload["args"] == ["take", "medication"]
        assert payload["text"] == "/remind take medication"
        assert payload["chat_id"] == "123"
        assert payload["from_user"] == {"id": 42}

    async def test_sends_ack_containing_rule_name(self):
        client = _make_client()
        svc = _make_service(client=client)
        rule = _make_rule_obj(name="my-rule", respond_with_ack=True)
        cfg = rule.telegram_trigger_config
        cmd = _cmd(chat_id="123")

        await svc._execute_rule(rule, cfg, cmd)

        client.send_message.assert_awaited_once()
        sent_chat_id, text = client.send_message.call_args[0]
        assert sent_chat_id == "123"
        assert "my-rule" in text

    async def test_skips_ack_when_disabled(self):
        client = _make_client()
        svc = _make_service(client=client)
        rule = _make_rule_obj(respond_with_ack=False)
        cfg = rule.telegram_trigger_config
        cmd = _cmd()

        await svc._execute_rule(rule, cfg, cmd)

        client.send_message.assert_not_awaited()

    async def test_ack_defaults_to_enabled_when_key_absent(self):
        client = _make_client()
        svc = _make_service(client=client)
        rule = _make_rule_obj()
        cfg: dict = {}  # respond_with_ack absent → should default to True
        cmd = _cmd()

        await svc._execute_rule(rule, cfg, cmd)

        client.send_message.assert_awaited_once()

    async def test_catches_executor_exception_without_raising(self):
        executor = MagicMock()
        executor.execute = AsyncMock(side_effect=RuntimeError("boom"))
        svc = _make_service(executor=executor)
        rule = _make_rule_obj()

        # Must not propagate the exception
        await svc._execute_rule(rule, rule.telegram_trigger_config, _cmd())

    async def test_db_session_closed_on_success(self):
        db_session = MagicMock()
        svc = _make_service(db_factory=MagicMock(return_value=db_session))
        rule = _make_rule_obj()

        await svc._execute_rule(rule, rule.telegram_trigger_config, _cmd())

        db_session.close.assert_called_once()

    async def test_db_session_closed_on_executor_failure(self):
        executor = MagicMock()
        executor.execute = AsyncMock(side_effect=RuntimeError("boom"))
        db_session = MagicMock()
        svc = _make_service(
            executor=executor,
            db_factory=MagicMock(return_value=db_session),
        )
        rule = _make_rule_obj()

        await svc._execute_rule(rule, rule.telegram_trigger_config, _cmd())

        db_session.close.assert_called_once()


# ---------------------------------------------------------------------------
# TelegramTriggerService._load_telegram_rules  (DB integration)
# ---------------------------------------------------------------------------


class TestLoadTelegramRules:
    """These tests write to the shared in-memory DB to verify the query filters
    and eager loading of ``Rule.steps``."""

    def test_returns_only_enabled_telegram_rules(self, db_session, db_factory):
        telegram_rule = Rule(
            name="telegram-rule",
            enabled=True,
            trigger_type="telegram",
            telegram_trigger_config={"command": "/remind", "allowed_chat_ids": ["1"]},
        )
        cron_rule = Rule(name="cron-rule", enabled=True, trigger_type="cron")
        disabled = Rule(
            name="disabled-telegram",
            enabled=False,
            trigger_type="telegram",
            telegram_trigger_config={"command": "/remind"},
        )
        db_session.add_all([telegram_rule, cron_rule, disabled])
        db_session.commit()

        svc = TelegramTriggerService(
            telegram_client=_make_client(),
            pipeline_executor=_make_executor(),
            db_session_factory=db_factory,
        )
        rules = svc._load_telegram_rules()

        assert len(rules) == 1
        assert rules[0].name == "telegram-rule"

    def test_steps_are_pre_loaded_avoiding_detached_instance_error(self, db_session, db_factory):
        """Accessing rule.steps after the session closes must not raise
        ``DetachedInstanceError``; this is the selectinload regression test."""
        rule = Rule(
            name="rule-with-steps",
            enabled=True,
            trigger_type="telegram",
            telegram_trigger_config={"command": "/test", "allowed_chat_ids": ["1"]},
        )
        db_session.add(rule)
        db_session.flush()

        step = PipelineStep(
            rule_id=rule.id,
            order=1,
            step_type="notification",
            config_json={},
            enabled=True,
        )
        db_session.add(step)
        db_session.commit()

        svc = TelegramTriggerService(
            telegram_client=_make_client(),
            pipeline_executor=_make_executor(),
            db_session_factory=db_factory,
        )
        rules = svc._load_telegram_rules()

        assert len(rules) == 1
        # _load_telegram_rules closes its session; this must not raise
        steps = rules[0].steps
        assert len(steps) == 1
        assert steps[0].step_type == "notification"
