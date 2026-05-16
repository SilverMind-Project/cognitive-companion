"""Unit tests for InfoCardStep."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, Mock

import pytest

from backend.steps.builtin.info_card import InfoCardStep


@dataclass
class FakePipelineStep:
    id: int
    step_type: str
    config_json: dict
    label: str | None = None
    rule_id: int | None = None


@dataclass
class FakeWorkflowExecution:
    id: int
    status: str


@dataclass
class FakeTriggerContext:
    room_name: str | None = None
    sensor_id: str | None = None


@dataclass
class FakeServiceContainer:
    db_factory: Mock
    knowledge_delivery: Mock | None = None
    notification_dispatcher: Mock | None = None
    scheduler: Mock | None = None


@dataclass
class FakeInfoCard:
    id: int
    title: str
    body_text: str
    layout_id: str
    status: str
    image_slots: list
    voice_instruction: str = ""


class TestInfoCardStepMetadata:
    """Test InfoCardStep metadata."""

    def test_metadata_returns_correct_type_name(self):
        metadata = InfoCardStep.metadata()
        assert metadata.type_name == "info_card"

    def test_metadata_returns_correct_category(self):
        metadata = InfoCardStep.metadata()
        assert metadata.category == "action"

    def test_metadata_has_all_channels_in_enum(self):
        metadata = InfoCardStep.metadata()
        channels_enum = metadata.config_schema["properties"]["channels"]["items"]["enum"]
        assert "pwa" in channels_enum
        assert "eink" in channels_enum
        assert "voice" in channels_enum

    def test_metadata_default_channels_is_pwa(self):
        metadata = InfoCardStep.metadata()
        assert metadata.default_config["channels"] == ["pwa"]


class TestInfoCardStepExecute:
    """Test InfoCardStep execute method."""

    @pytest.mark.asyncio
    async def test_execute_with_missing_knowledge_delivery_returns_error(self):
        """Missing service returns StepResult error."""
        handler = InfoCardStep()
        step = FakePipelineStep(id=1, step_type="info_card", config_json={"info_card_id": 1})
        execution = FakeWorkflowExecution(id=100, status="running")
        card = FakeInfoCard(
            id=1, title="Test", body_text="Body", layout_id="text_only", status="approved", image_slots=[]
        )
        mock_db = Mock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = card
        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db),
            knowledge_delivery=None,
        )

        result = await handler.execute(step, execution, {}, FakeTriggerContext(), services)

        assert result.success is False
        assert "knowledge delivery service not available" in result.data["error"]

    @pytest.mark.asyncio
    async def test_execute_with_missing_info_card_id_returns_error(self):
        """Missing info_card_id in config returns error."""
        handler = InfoCardStep()
        step = FakePipelineStep(id=2, step_type="info_card", config_json={})
        execution = FakeWorkflowExecution(id=101, status="running")
        delivery_svc = Mock()
        services = FakeServiceContainer(
            db_factory=Mock(),
            knowledge_delivery=delivery_svc,
        )

        result = await handler.execute(step, execution, {}, FakeTriggerContext(), services)

        assert result.success is False
        assert "info_card_id is required" in result.data["error"]

    @pytest.mark.asyncio
    async def test_execute_with_card_not_found_returns_error(self):
        """Card not in DB returns error."""
        handler = InfoCardStep()
        step = FakePipelineStep(id=3, step_type="info_card", config_json={"info_card_id": 99})
        execution = FakeWorkflowExecution(id=102, status="running")
        mock_db = Mock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        delivery_svc = Mock()
        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db),
            knowledge_delivery=delivery_svc,
        )

        result = await handler.execute(step, execution, {}, FakeTriggerContext(), services)

        assert result.success is False
        assert "not found" in result.data["error"]

    @pytest.mark.asyncio
    async def test_execute_with_unapproved_card_returns_error(self):
        """Card in draft status returns error."""
        handler = InfoCardStep()
        step = FakePipelineStep(id=4, step_type="info_card", config_json={"info_card_id": 1})
        execution = FakeWorkflowExecution(id=103, status="running")
        card = FakeInfoCard(id=1, title="Test", body_text="Body", layout_id="text_only", status="draft", image_slots=[])
        mock_db = Mock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = card
        delivery_svc = Mock()
        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db),
            knowledge_delivery=delivery_svc,
        )

        result = await handler.execute(step, execution, {}, FakeTriggerContext(), services)

        assert result.success is False
        assert "not approved" in result.data["error"]

    @pytest.mark.asyncio
    async def test_execute_with_approved_card_returns_success(self):
        """Approved card delivery returns success with delivery_id. speak=False when voice not in channels."""
        handler = InfoCardStep()
        step = FakePipelineStep(
            id=5, step_type="info_card", config_json={"info_card_id": 1, "channels": ["pwa"]}, rule_id=10
        )
        execution = FakeWorkflowExecution(id=104, status="running")
        card = FakeInfoCard(
            id=1, title="Test", body_text="Body", layout_id="text_only", status="approved", image_slots=[]
        )
        mock_db = Mock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = card
        delivery_svc = Mock()
        delivery_svc.deliver_info_card = AsyncMock(return_value=Mock(delivery_id=42))
        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db),
            knowledge_delivery=delivery_svc,
        )

        result = await handler.execute(step, execution, {}, FakeTriggerContext(), services)

        assert result.success is True
        assert result.data["info_card_id"] == 1
        assert result.data["delivery_id"] == 42
        delivery_svc.deliver_info_card.assert_called_once_with(
            card=card,
            channels=["pwa"],
            execution_id=execution.id,
            rule_id=step.rule_id,
            voice_instruction=None,
            speak=False,
            dismiss_seconds=60,
            eink_expiry_minutes=30,
        )

    @pytest.mark.asyncio
    async def test_execute_renders_voice_instruction_template(self):
        """Templated voice_instruction is rendered against pipeline_data + trigger."""
        handler = InfoCardStep()
        step = FakePipelineStep(
            id=11,
            step_type="info_card",
            config_json={
                "info_card_id": 1,
                "channels": ["pwa", "voice"],
                "voice_instruction": "Speak gently. It is {{system.local_day_of_week}} in {{trigger.room_name}}.",
            },
            rule_id=10,
        )
        execution = FakeWorkflowExecution(id=105, status="running")
        card = FakeInfoCard(
            id=1, title="T", body_text="B", layout_id="text_only", status="approved", image_slots=[]
        )
        mock_db = Mock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = card
        delivery_svc = Mock()
        delivery_svc.deliver_info_card = AsyncMock(return_value=Mock(delivery_id=44))
        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db),
            knowledge_delivery=delivery_svc,
        )
        pipeline_data = {"system": {"local_day_of_week": "Monday"}}
        trigger = FakeTriggerContext(room_name="kitchen", sensor_id="cam1")

        result = await handler.execute(step, execution, pipeline_data, trigger, services)

        assert result.success is True
        call_kwargs = delivery_svc.deliver_info_card.call_args.kwargs
        assert call_kwargs["voice_instruction"] == "Speak gently. It is Monday in kitchen."

    @pytest.mark.asyncio
    async def test_execute_with_voice_instruction_passed_through(self):
        """Custom voice_instruction is forwarded to delivery service."""
        handler = InfoCardStep()
        step = FakePipelineStep(
            id=6,
            step_type="info_card",
            config_json={"info_card_id": 1, "channels": ["pwa", "voice"], "voice_instruction": "custom"},
            rule_id=10,
        )
        execution = FakeWorkflowExecution(id=105, status="running")
        card = FakeInfoCard(
            id=1, title="Test", body_text="Body", layout_id="text_only", status="approved", image_slots=[]
        )
        mock_db = Mock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = card
        delivery_svc = Mock()
        delivery_svc.deliver_info_card = AsyncMock(return_value=Mock(delivery_id=43))
        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db),
            knowledge_delivery=delivery_svc,
        )

        result = await handler.execute(step, execution, {}, FakeTriggerContext(), services)

        assert result.success is True
        call_kwargs = delivery_svc.deliver_info_card.call_args.kwargs
        assert call_kwargs["voice_instruction"] == "custom"
        assert call_kwargs["speak"] is True
