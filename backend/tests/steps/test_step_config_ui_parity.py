"""Every key a step's Vue config authors must be one the backend actually reads.

``semantic_memory_write`` drifted until its Vue ``stepDefaults`` and the
handler's ``config_schema`` shared exactly one key (``source``): the form
authored literal values (``write_type``, ``description``, ``object_list``)
while the handler only ever read ``*_key`` pipeline-data paths. Everything
typed into that form was silently discarded, and nothing failed.

The two sides live in different languages and no generated artifact carries
``config_schema``, so this test parses the Vue files directly.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.channels import ChannelRegistry
from backend.steps import StepRegistry

_VUE_DIR = (
    Path(__file__).resolve().parents[3] / "frontend/src/components/pipeline/steps"
)
_BACKEND_HEADER = re.compile(r"Backend: backend/steps/builtin/(\w+)\.py")
_DEFAULTS_BLOCK = re.compile(r"export const stepDefaults = \{(.*?)\n\};", re.S)
_KEY = re.compile(r"^\s{2}([A-Za-z_]\w*)\s*:", re.M)


def _channel_config_keys() -> set[str]:
    """Keys any notification channel accepts.

    The ``notification`` step embeds per-channel config (``tts_language`` and
    friends) alongside its own, so those keys are legitimately present in the
    Vue defaults without appearing in the step's own schema.
    """
    ChannelRegistry.discover()
    keys: set[str] = set()
    for meta in ChannelRegistry.all_metadata():
        keys |= set((meta.config_schema or {}).get("properties", {}))
    return keys


def _vue_configs() -> list[tuple[str, Path, set[str]]]:
    """Return ``(step_type, path, default_keys)`` for each Vue step config."""
    StepRegistry.discover()
    known = {m.type_name for m in StepRegistry.all_metadata()}
    found = []
    for path in sorted(_VUE_DIR.glob("*Config.vue")):
        text = path.read_text()
        header = _BACKEND_HEADER.search(text)
        block = _DEFAULTS_BLOCK.search(text)
        if not header or not block or header.group(1) not in known:
            continue
        found.append((header.group(1), path, set(_KEY.findall(block.group(1)))))
    return found


def test_vue_dir_is_discoverable() -> None:
    """Guard the parametrization: a bad path would make every case vanish."""
    assert _VUE_DIR.is_dir(), f"missing {_VUE_DIR}"
    assert len(_vue_configs()) > 10


@pytest.mark.parametrize(
    ("step_type", "path", "default_keys"),
    _vue_configs(),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_vue_step_defaults_are_read_by_the_backend(
    step_type: str, path: Path, default_keys: set[str]
) -> None:
    """No Vue default may name a key absent from the handler's config_schema."""
    StepRegistry.discover()
    meta = next(m for m in StepRegistry.all_metadata() if m.type_name == step_type)
    schema_keys = set((meta.config_schema or {}).get("properties", {}))

    orphans = default_keys - schema_keys - _channel_config_keys()
    assert not orphans, (
        f"{path.name} authors {sorted(orphans)}, which {step_type}'s config_schema "
        f"does not declare. The backend will silently ignore these. "
        f"Backend accepts: {sorted(schema_keys)}"
    )


def test_semantic_memory_write_defaults_match_backend_exactly() -> None:
    """Regression lock for the step whose form was entirely disconnected."""
    StepRegistry.discover()
    meta = next(
        m for m in StepRegistry.all_metadata() if m.type_name == "semantic_memory_write"
    )
    schema_keys = set((meta.config_schema or {}).get("properties", {}))
    _, _, default_keys = next(
        c for c in _vue_configs() if c[0] == "semantic_memory_write"
    )
    assert default_keys == schema_keys, (
        "semantic_memory_write's Vue defaults and config_schema must stay in "
        f"lockstep. Vue-only: {sorted(default_keys - schema_keys)}, "
        f"backend-only: {sorted(schema_keys - default_keys)}"
    )


_SCALAR_DEFAULT = re.compile(
    r"^\s{2}([A-Za-z_]\w*)\s*:\s*(true|false|-?\d+(?:\.\d+)?|\[\]|\"[^\"]*\")\s*,?\s*$",
    re.M,
)
_JS_SCALARS = {"true": True, "false": False, "[]": []}


def _vue_scalar_defaults(text: str) -> dict[str, object]:
    """Parse the scalar entries of a ``stepDefaults`` block.

    Objects and nested arrays are skipped; booleans, numbers, strings and empty
    arrays cover the values worth diffing against ``default_config``.
    """
    block = _DEFAULTS_BLOCK.search(text)
    if not block:
        return {}
    parsed: dict[str, object] = {}
    for key, raw in _SCALAR_DEFAULT.findall(block.group(1)):
        if raw in _JS_SCALARS:
            parsed[key] = _JS_SCALARS[raw]
        elif raw.startswith('"'):
            parsed[key] = raw[1:-1]
        else:
            parsed[key] = float(raw) if "." in raw else int(raw)
    return parsed


# Pre-existing, deliberate divergences: the Vue form starts a field blank to
# force the author to choose, while default_config carries a palette suggestion.
# signal_emit reads config.get("kind", ""), so blank is what the handler expects
# at runtime. Ratchet only: do not add entries without confirming the handler
# tolerates the Vue value, and prefer fixing the drift to widening this set.
_KNOWN_VALUE_DRIFT: dict[str, set[str]] = {
    "activity_detection": {"confidence"},  # Vue stores "0.8" as a string
    "daily_report": {"summary_model_id"},
    "ha_action": {"data"},
    "interactive_prompt": {
        "escalate_button_text",
        "dismiss_button_text",
        "popup_title",
    },
    "signal_emit": {"kind"},
}


@pytest.mark.parametrize(
    ("step_type", "path", "default_keys"),
    _vue_configs(),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_vue_and_backend_agree_on_default_values(
    step_type: str, path: Path, default_keys: set[str]
) -> None:
    """Where both sides define a scalar default, the values must match.

    ``semantic_memory_query`` defaulted ``use_trigger_room`` to false in the Vue
    form and true in the handler, so a step created through the UI queried a
    different room than one created programmatically. Key-level parity does not
    catch that.
    """
    StepRegistry.discover()
    meta = next(m for m in StepRegistry.all_metadata() if m.type_name == step_type)
    backend_defaults = meta.default_config or {}
    vue_defaults = _vue_scalar_defaults(path.read_text())
    allowed = _KNOWN_VALUE_DRIFT.get(step_type, set())

    mismatched = {
        key: {"vue": value, "backend": backend_defaults[key]}
        for key, value in vue_defaults.items()
        if key not in allowed
        and key in backend_defaults
        and backend_defaults[key] != value
    }
    assert not mismatched, (
        f"{path.name} and {step_type}'s default_config disagree: "
        f"{json.dumps(mismatched, indent=2, default=str)}"
    )


def test_known_value_drift_allowlist_has_no_stale_entries() -> None:
    """An allowlisted key that no longer drifts must leave the allowlist."""
    StepRegistry.discover()
    stale: dict[str, list[str]] = {}
    by_type = {c[0]: c for c in _vue_configs()}
    for step_type, keys in _KNOWN_VALUE_DRIFT.items():
        entry = by_type.get(step_type)
        assert entry is not None, f"{step_type} has no Vue config; drop it"
        meta = next(m for m in StepRegistry.all_metadata() if m.type_name == step_type)
        backend_defaults = meta.default_config or {}
        vue_defaults = _vue_scalar_defaults(entry[1].read_text())
        resolved = [
            key
            for key in keys
            if key not in vue_defaults
            or key not in backend_defaults
            or backend_defaults[key] == vue_defaults[key]
        ]
        if resolved:
            stale[step_type] = sorted(resolved)
    assert not stale, f"remove from _KNOWN_VALUE_DRIFT: {json.dumps(stale, indent=2)}"


def test_default_config_matches_config_schema_properties() -> None:
    """A handler's own default_config must not name undeclared keys either."""
    StepRegistry.discover()
    offenders: dict[str, list[str]] = {}
    for meta in StepRegistry.all_metadata():
        schema_keys = set((meta.config_schema or {}).get("properties", {}))
        extra = set(meta.default_config or {}) - schema_keys
        if extra:
            offenders[meta.type_name] = sorted(extra)
    assert not offenders, json.dumps(offenders, indent=2)
