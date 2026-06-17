from __future__ import annotations

from types import SimpleNamespace

from backend.core.config import Settings
from backend.services.guided_task.policy import resolve_policy


def _settings() -> Settings:
    return Settings.from_dict(
        {
            "guided_task": {
                "step_timeout_s": 300,
                "max_step_attempts": 3,
                "resume_grace_s": 600,
            }
        }
    )


def _routine(**overrides):
    values = {
        "step_timeout_s_override": None,
        "max_step_attempts_override": None,
        "resume_grace_s_override": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _step(**overrides):
    values = {
        "step_timeout_s_override": None,
        "max_step_attempts_override": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_step_override_wins():
    policy = resolve_policy(
        _routine(step_timeout_s_override=200, max_step_attempts_override=2),
        _step(step_timeout_s_override=100, max_step_attempts_override=5),
        _settings(),
    )

    assert policy.step_timeout_s == 100
    assert policy.max_step_attempts == 5


def test_routine_override_when_no_step():
    policy = resolve_policy(
        _routine(
            step_timeout_s_override=200,
            max_step_attempts_override=2,
            resume_grace_s_override=900,
        ),
        _step(),
        _settings(),
    )

    assert policy.step_timeout_s == 200
    assert policy.max_step_attempts == 2
    assert policy.resume_grace_s == 900


def test_global_when_no_overrides():
    policy = resolve_policy(_routine(), _step(), _settings())

    assert policy.step_timeout_s == 300
    assert policy.max_step_attempts == 3
    assert policy.resume_grace_s == 600


def test_null_override_inherits_upward():
    policy = resolve_policy(
        _routine(step_timeout_s_override=240),
        _step(step_timeout_s_override=None),
        _settings(),
    )

    assert policy.step_timeout_s == 240
