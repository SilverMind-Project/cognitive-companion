"""M27/G5: resident-language localization for the guided companion."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.core.config import Settings
from backend.models.guided_task import Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.services.guided_task.agent_voice import AgentSessionVoice
from backend.services.guided_task.service import GuidedTaskService
from backend.services.knowledge.voice_instructions import VoiceInstructionConfig


def _settings(**guided_task_overrides) -> Settings:
    guided_task = {
        "max_step_attempts": 3,
        "step_timeout_s": 300,
        "resume_grace_s": 600,
        "summon_channels": ["ha_speaker_tts"],
        "summon_messages": {
            "en": "Please come to the companion screen when you are ready for your routine.",
            "ta": "ta-summon-text",
        },
    }
    guided_task.update(guided_task_overrides)
    return Settings.from_dict(
        {
            "app": {"language_names": {"ta": "Chennai Tamil", "en": "simple English"}},
            "tts": {"default_language": "ta"},
            "guided_task": guided_task,
        }
    )


def _voice_config() -> VoiceInstructionConfig:
    return VoiceInstructionConfig(
        guided_task_default="Speak one step at a time.",
        guided_task_language_directive="For this routine, speak only in {{ language }}.",
        guided_task_auto_advance_prefix=(
            "Acknowledge warmly that you can see the step is done, then give the next instruction."
        ),
    )


class _Ws:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send_backend_task(self, **kwargs) -> None:
        self.calls.append(kwargs)


class _Dispatcher:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def dispatch(self, **kwargs) -> dict[str, bool]:
        self.calls.append(kwargs)
        return {"ha_speaker_tts": True}


def _add_routine(db_session, *, person_id: str = "person-1", **routine_kwargs) -> Routine:
    db_session.add(HouseholdMember(id=person_id, name="Ruth"))
    db_session.commit()
    routine = Routine(name="Make tea", person_id=person_id, is_enabled=True, **routine_kwargs)
    routine.steps.append(RoutineStep(ord=0, prompt_template="Boil water."))
    db_session.add(routine)
    db_session.commit()
    db_session.refresh(routine)
    return routine


def _session(**overrides) -> SimpleNamespace:
    values = {
        "id": 3,
        "execution_id": 42,
        "person_id": "resident-1",
        "resident_name": "Ruth",
        "routine_system_instruction_override": None,
        "language_override": None,
        "voice_override": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


# -- Part A.2: AgentSessionVoice.speak_step -----------------------------------


@pytest.mark.asyncio
async def test_speak_step_appends_language_directive() -> None:
    ws = _Ws()
    speaker = AgentSessionVoice(ws, _voice_config(), settings=_settings())

    await speaker.speak_step(
        session=_session(language_override="ta"),
        step=SimpleNamespace(ord=0),
        rendered_prompt="Boil water.",
        is_retry=False,
    )

    voice_instruction = ws.calls[0]["voice_instruction"]
    assert "For this routine, speak only in Chennai Tamil." in voice_instruction


@pytest.mark.asyncio
async def test_speak_step_without_override_unchanged() -> None:
    ws = _Ws()
    speaker = AgentSessionVoice(ws, _voice_config(), settings=_settings())

    await speaker.speak_step(
        session=_session(),
        step=SimpleNamespace(ord=0),
        rendered_prompt="Boil water.",
        is_retry=False,
    )

    voice_instruction = ws.calls[0]["voice_instruction"]
    assert "speak only in" not in voice_instruction
    assert "voice" not in ws.calls[0]["metadata"]


@pytest.mark.asyncio
async def test_speak_step_unknown_language_code_passes_through_and_warns(caplog) -> None:
    ws = _Ws()
    speaker = AgentSessionVoice(ws, _voice_config(), settings=_settings())

    await speaker.speak_step(
        session=_session(language_override="xx"),
        step=SimpleNamespace(ord=0),
        rendered_prompt="Boil water.",
        is_retry=False,
    )

    voice_instruction = ws.calls[0]["voice_instruction"]
    assert "speak only in xx." in voice_instruction
    assert any("guided_language_name_unknown" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_speak_step_voice_override_logs_unsupported_once_per_session(caplog) -> None:
    ws = _Ws()
    speaker = AgentSessionVoice(ws, _voice_config(), settings=_settings())
    session = _session(voice_override="warm-female")

    await speaker.speak_step(
        session=session, step=SimpleNamespace(ord=0), rendered_prompt="Boil water.", is_retry=False
    )
    await speaker.speak_step(
        session=session, step=SimpleNamespace(ord=1), rendered_prompt="Pour tea.", is_retry=False
    )

    assert ws.calls[0]["metadata"]["voice"] == "warm-female"
    assert ws.calls[1]["metadata"]["voice"] == "warm-female"
    warnings = [r for r in caplog.records if "guided_voice_override_unsupported" in r.getMessage()]
    assert len(warnings) == 1


# -- Part A.3: caregiver relay --------------------------------------------------


@pytest.mark.asyncio
async def test_caregiver_relay_includes_directive(db_factory, db_session) -> None:
    routine = _add_routine(db_session, language_override="ta")

    ws = _Ws()
    svc = GuidedTaskService(
        db_factory=db_factory,
        ws_manager=ws,
        voice_instructions=_voice_config(),
        settings=_settings(),
        time_fn=lambda: datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
    )
    session = SimpleNamespace(id=1, execution_id=None, person_id="person-1")

    await svc._inject_caregiver_message(session, routine, "Time for a cup of tea.")

    assert "For this routine, speak only in Chennai Tamil." in ws.calls[0]["voice_instruction"]


@pytest.mark.asyncio
async def test_caregiver_relay_without_override_unchanged(db_factory, db_session) -> None:
    routine = _add_routine(db_session)

    ws = _Ws()
    svc = GuidedTaskService(
        db_factory=db_factory,
        ws_manager=ws,
        voice_instructions=_voice_config(),
        settings=_settings(),
        time_fn=lambda: datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
    )
    session = SimpleNamespace(id=1, execution_id=None, person_id="person-1")

    await svc._inject_caregiver_message(session, routine, "Time for a cup of tea.")

    assert ws.calls[0]["voice_instruction"] is None


def _add_session(db_session, routine: Routine, now: datetime) -> SimpleNamespace:
    from backend.models.guided_task import GuidedSession

    session = GuidedSession(
        routine_id=routine.id,
        person_id=routine.person_id,
        status="summoning",
        current_step_ord=0,
        attempts=0,
        started_at=now,
        last_activity_at=now,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


# -- Part B: literal-TTS summon --------------------------------------------------


@pytest.mark.asyncio
async def test_summon_message_localized(db_factory, db_session) -> None:
    now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
    routine = _add_routine(db_session, language_override="ta")
    session = _add_session(db_session, routine, now)

    dispatcher = _Dispatcher()
    svc = GuidedTaskService(
        db_factory=db_factory, notification_dispatcher=dispatcher, settings=_settings(), time_fn=lambda: now
    )

    await svc._announce_summon(session=session, routine=routine, room_name="kitchen", broad=False)

    assert dispatcher.calls[0]["message"] == "ta-summon-text"
    assert dispatcher.calls[0]["rule_config"]["tts_language"] == "ta"


@pytest.mark.asyncio
async def test_summon_language_fallback_logs(db_factory, db_session, caplog) -> None:
    now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
    routine = _add_routine(db_session, language_override="xx")
    session = _add_session(db_session, routine, now)

    dispatcher = _Dispatcher()
    svc = GuidedTaskService(
        db_factory=db_factory, notification_dispatcher=dispatcher, settings=_settings(), time_fn=lambda: now
    )

    await svc._announce_summon(session=session, routine=routine, room_name="kitchen", broad=False)

    assert dispatcher.calls[0]["message"] == (
        "Please come to the companion screen when you are ready for your routine."
    )
    assert dispatcher.calls[0]["rule_config"]["tts_language"] == "en"
    assert any("guided_summon_language_missing" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_summon_defaults_to_household_language_when_no_routine_override(
    db_factory, db_session
) -> None:
    now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
    routine = _add_routine(db_session)
    session = _add_session(db_session, routine, now)

    dispatcher = _Dispatcher()
    svc = GuidedTaskService(
        db_factory=db_factory, notification_dispatcher=dispatcher, settings=_settings(), time_fn=lambda: now
    )

    await svc._announce_summon(session=session, routine=routine, room_name="kitchen", broad=False)

    # tts.default_language is "ta" in _settings()
    assert dispatcher.calls[0]["message"] == "ta-summon-text"
    assert dispatcher.calls[0]["rule_config"]["tts_language"] == "ta"


# -- Part C: auto-advance prefix is an agent instruction, not a literal --------


@pytest.mark.asyncio
async def test_auto_advance_prefix_is_agent_instruction(db_factory, db_session) -> None:
    from backend.core.template import render_template

    routine = _add_routine(db_session)
    step = routine.steps[0]
    now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
    session = _add_session(db_session, routine, now)

    ws = _Ws()
    voice_config = _voice_config()
    svc = GuidedTaskService(
        db_factory=db_factory,
        voice=AgentSessionVoice(ws, voice_config, settings=_settings()),
        voice_instructions=voice_config,
        settings=_settings(),
        time_fn=lambda: now,
    )
    prefix = render_template(svc._voice_instructions.guided_task_auto_advance_prefix, {})

    await svc._speak(session, step, is_retry=False, prefix=prefix)

    prompt = ws.calls[0]["prompt"]
    assert "Acknowledge warmly that you can see the step is done" in prompt
    assert "lovely" not in prompt


def test_no_hardcoded_english_summon_or_prefix_literal_in_service() -> None:
    import inspect

    # M29 moved the summon announcement into summon.py and the watch
    # auto-advance prefix into watch.py; guard the modules that actually
    # own this logic now; otherwise this regression guard goes vacuous.
    from backend.services.guided_task import summon as summon_module
    from backend.services.guided_task import watch as watch_module

    for module in (summon_module, watch_module):
        source = inspect.getsource(module)
        assert "Please come to the companion screen" not in source
        assert "lovely, now" not in source
