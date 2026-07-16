"""Write-time JSONSchema validation of pipeline step `config_json`.

Every step handler declares a `config_schema` (`backend/steps/base.py`) that is served to the
frontend for the palette and auto-form generation, but nothing enforced it against a saved
`config_json` until this module. See `codebase-hardening-m14-cc-step-config-validation-and-
vocabularies.md` for the finding (C7) and the write-path design decisions.

An empty config (`{}` or `None`) is never validated. Step creation from the canvas palette
(`PipelineCanvas.vue: onStepSelected`) always posts an empty `config_json`; the step is
configured afterward through the config dialog, which is where a real, non-empty config first
appears and gets validated. Several builtin steps (`guided_task_start`, `quiz_start`,
`info_card`) have a `required` identifier field with no sensible default, so validating the
empty placeholder would reject step creation itself, not a malformed config.

Keys whose value is `None` are stripped before validation. Vuetify's `clearable` form controls
(e.g. `PresenceQueryConfig.vue`'s signal-kind combobox) emit `null` when a field is cleared, and
`StepConfigDialog.vue`'s save handler forwards that raw value into `config_json` with no
normalization. None of these optional fields are JSONSchema `required`, so a cleared field is
semantically "not provided," not an invalid value; treating a present `null` the same as an
absent key means clearing a field never itself produces a 422.
"""

from __future__ import annotations

from jsonschema import Draft202012Validator

from backend.steps import StepRegistry

_validator_cache: dict[str, Draft202012Validator] = {}


def _get_validator(step_type: str) -> Draft202012Validator | None:
    if step_type in _validator_cache:
        return _validator_cache[step_type]

    StepRegistry.discover()
    handler = StepRegistry.get(step_type)
    if handler is None:
        return None

    validator = Draft202012Validator(handler.metadata().config_schema)
    _validator_cache[step_type] = validator
    return validator


def validate_step_config_schema(step_type: str, config: dict) -> list[str]:
    """Return human-readable error strings for *config* against its step's `config_schema`.

    Returns an empty list when valid, when the step type is unknown (rejected elsewhere), or
    when *config* is empty (an unconfigured placeholder, not a malformed config; see module
    docstring).
    """
    if not config:
        return []

    validator = _get_validator(step_type)
    if validator is None:
        return []

    config = {k: v for k, v in config.items() if v is not None}
    if not config:
        return []

    errors = sorted(validator.iter_errors(config), key=lambda e: list(e.path))
    return [
        f"{'.'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors
    ]
