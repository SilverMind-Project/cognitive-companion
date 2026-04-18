# Vision Analysis Deprecation Plan

Deprecate the `vision_analysis` pipeline step and consolidate all its
functionality into the `llm_call` step, making `llm_call` the single unified
LLM interface for the entire pipeline system.

**Status**: Draft
**Author**: Sriram + Claude
**Date**: 2026-04-18

---

## 1. Motivation

The `vision_analysis` and `llm_call` steps share ~90% of their implementation
surface. Both send prompts and images to LLMs, both support structured JSON
output, both query additional cameras. Maintaining two nearly identical steps
creates:

- **Duplication**: Image assembly, JSON schema enforcement, and response
  parsing logic is duplicated across both steps.
- **Inconsistency**: `llm_call` supports features that `vision_analysis` does
  not (model selection, sensor-ordered assembly, hallucination retry,
  configurable output key, context inclusion). New features must be added to
  both or one falls behind.
- **Confusion**: Administrators must understand when to use which step. The
  README already says "Prefer `llm_call` for new pipelines."
- **Legacy coupling**: `vision_analysis` is hardwired to a single
  `VLLMVisionProvider` instance via `services.vision_provider`, bypassing the
  named model registry entirely. This prevents model selection, failover, and
  load balancing for vision tasks.

---

## 2. Current State Analysis

### 2.1 Feature Comparison

| Feature | vision_analysis | llm_call | Gap |
|---------|----------------|----------|-----|
| Model selection | Hardwired to `services.vision_provider` | Named registry via `model_id` | llm_call is superior |
| Prompt with templates | Yes | Yes | None |
| Image source (trigger/additional/both) | Yes | Yes + "none" | None |
| Additional sensor IDs | Yes | Yes | None |
| Additional room names | Yes | Yes | None |
| Image time filter | Yes | Yes | None |
| Max images cap | Yes | Yes | None |
| Sensor-ordered assembly | No | Yes (`sort_by_sensor_then_time`) | llm_call only |
| Images per sensor | No | Yes | llm_call only |
| JSON schema (guided decoding) | Yes (custom format) | Yes (json_schema format) | None |
| JSON free-form | No | Yes (json_free format) | llm_call only |
| Hallucination retry | No | Yes | llm_call only |
| Configurable output key | No (hardcoded `vision_response`) | Yes | llm_call only |
| Special instructions | No | Yes | llm_call only |
| Context key inclusion | No | Yes | llm_call only |
| Thinking (chain-of-thought) | Yes | Yes | None |
| Sampling overrides (temp/top_p/max_tokens) | Yes | Yes | None |
| `use_annotated_image` | Yes (config flag, unused in execute) | No | **Gap: must add to llm_call** |
| Vision capability check | No (always sends images) | Yes (checks model capabilities) | llm_call is superior |

### 2.2 Structured Output: The JSON Parsing Problem

Both steps and the underlying providers have a reliability gap in structured
JSON output handling:

1. **Models prepend markdown fences**: LLMs (especially llama.cpp-served models
   without guided decoding) frequently wrap JSON output in ` ```json ... ``` `
   markdown code blocks. Neither the provider layer nor the step layer strips
   these fences before calling `json.loads`, causing parse failures.

2. **Silent failures**: Both steps use `contextlib.suppress(json.JSONDecodeError)`
   around `json.loads`. When parsing fails, the raw string (including the
   markdown fence) is stored as the result. Downstream steps expecting a dict
   receive a string, causing subtle bugs.

3. **No centralized cleaning**: Each step independently handles JSON parsing
   with identical suppress-and-hope logic. There is no shared utility.

4. **Provider-level gap**: `OpenAICompatibleProvider` returns raw text from
   the model. When `guided_decoding=False` (llama.cpp), the model is
   only instructed via prompt to produce JSON, with no guarantee it will not
   wrap the output.

### 2.3 Dependency Map

Files that reference `vision_analysis` or `vision_provider`:

| File | Reference Type |
|------|---------------|
| `backend/steps/builtin/vision_analysis.py` | Step handler (to be removed) |
| `backend/steps/base.py` | `ServiceContainer.vision_provider` field |
| `backend/services/pipeline_executor.py` | Passes `vision_provider` to `ServiceContainer` |
| `backend/main.py` | Constructs `vision_provider` via `get_provider()` |
| `backend/integrations/llm/vllm.py` | `VLLMVisionProvider` class |
| `backend/integrations/llm/__init__.py` | Legacy provider map entry |
| `backend/models/pipeline.py` | Fallback step types tuple |
| `frontend/.../StepConfigDialog.vue` | UI sections for vision_analysis |
| `frontend/.../StepPalette.vue` | Fallback entry for vision_analysis |
| `frontend/.../PipelineBuilder.vue` | Icon mapping |
| `frontend/.../RuleDetailView.vue` | Icon mapping |
| `backend/steps/builtin/activity_detection.py` | References `vision_response` key (data coupling only) |
| `README.md`, `AGENTS.md`, `CLAUDE.md` | Documentation |

### 2.4 Multiple llm_call Steps in a Pipeline

Already supported. Each `llm_call` step has a configurable `output_key`
(default: `"llm_response"`). Multiple `llm_call` steps coexist by writing to
different keys: `"vision_response"`, `"logic_response"`, `"translation"`, or
any custom key. The `PipelineExecutor` merges each step's `StepResult.data`
into a flat `pipeline_data` dict via `dict.update()`. No structural changes
are needed.

**Example migrated pipeline** (was: `vision_analysis -> logic_reasoning -> notification`):

```
llm_call (model=cosmos_reason2, image_source=trigger, output_key=vision_response)
  -> llm_call (model=gemma4_26b, output_key=logic_response, include_context=[vision_response])
  -> notification
```

---

## 3. Implementation Plan

### Phase 1: Harden Structured JSON Output

**Goal**: Ensure reliable JSON parsing regardless of LLM provider quirks.

#### 1.1 Add `clean_llm_json` utility

Create `backend/integrations/llm/json_utils.py`:

```python
"""Utilities for cleaning and parsing LLM-generated JSON responses."""

import json
import re

_FENCE_RE = re.compile(
    r"^```(?:json)?\s*\n?(.*?)\n?\s*```\s*$",
    re.DOTALL,
)

def clean_llm_json(text: str) -> str:
    """Strip markdown code fences and leading/trailing whitespace from
    LLM-generated JSON text.

    Handles common patterns:
    - ```json\n{...}\n```
    - ```\n{...}\n```
    - Leading/trailing whitespace around valid JSON
    """
    text = text.strip()
    match = _FENCE_RE.match(text)
    if match:
        text = match.group(1).strip()
    return text


def parse_llm_json(text: str) -> dict | list | str:
    """Attempt to parse LLM output as JSON, cleaning fences first.

    Returns the parsed object on success, or the original string on failure.
    Logs a warning on parse failure rather than silently suppressing.
    """
    cleaned = clean_llm_json(text)
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return text
```

**Tests**: Unit tests for `clean_llm_json` and `parse_llm_json` covering:
- Plain JSON (no fences)
- ` ```json\n{...}\n``` `
- ` ```\n{...}\n``` `
- Nested code fences in values (should not strip inner fences)
- Invalid JSON returns original string
- Empty string
- Whitespace around fences

#### 1.2 Integrate into `llm_call` step

Replace the `contextlib.suppress` + `json.loads` pattern in
`llm_call.py:416-418` with `parse_llm_json`:

```python
# Before (fragile):
with suppress(json.JSONDecodeError, TypeError):
    result_value = json.loads(raw_response)

# After (robust):
from backend.integrations.llm.json_utils import parse_llm_json
result_value = parse_llm_json(raw_response)
```

Also replace the schema parsing in `llm_call.py:317-318`.

#### 1.3 Integrate into `OpenAICompatibleProvider`

For non-guided-decoding responses where a `response_schema` was provided,
apply `clean_llm_json` before returning from `call()`. This cleans at the
provider boundary so all consumers benefit.

**Estimated scope**: 1 new file, 2 modified files, ~80 lines of code + ~60
lines of tests.

---

### Phase 2: Close Feature Gaps in llm_call

**Goal**: Ensure `llm_call` covers every `vision_analysis` capability.

#### 2.1 Add `use_annotated_image` support

The `vision_analysis` step has a `use_annotated_image` config flag, although
its `execute()` method does not actually use it (the config is declared in the
schema but not referenced in the execution logic). In practice, the
`person_identification` step writes the annotated image to
`pipeline_data["annotated_image"]` as a base64 string.

**For llm_call**: Rather than adding a boolean flag, leverage the existing
`include_context` mechanism. Users can include `annotated_image` in the
`include_context` list to inject it as context. If the annotated image needs
to be sent as an actual image (not text context), add a new `image_source`
option:

Add to `image_source` enum: `"annotated"` (uses the base64 annotated image
from `pipeline_data["annotated_image"]`).

Alternatively, add a config field `use_annotated_image: bool` that, when true,
replaces trigger media_paths with the annotated image from pipeline_data.
This is simpler and mirrors the original vision_analysis config.

**Recommended approach**: Add `use_annotated_image` as a boolean config field
on `llm_call`. When true and `pipeline_data["annotated_image"]` exists, prepend
it to the media_paths list. This is backward-compatible and straightforward.

Update `llm_call.py` execute method:

```python
# After assembling media_paths, before the model call:
if config.get("use_annotated_image") and pipeline_data.get("annotated_image"):
    annotated_b64 = pipeline_data["annotated_image"]
    # Write to a temp file or pass as data URI directly
    media_paths.insert(0, f"data:image/jpeg;base64,{annotated_b64}")
```

Note: `encode_image_data_uri` in `base.py` already handles `data:` URIs
(it checks for `http://` / `https://` prefixes; a `data:` URI would fail).
We need to ensure the provider can accept pre-encoded data URIs. Looking at
`OpenAICompatibleProvider.call()`, it calls `encode_image_data_uri(img)` for
each image path. We should add a check: if the path already starts with
`data:`, skip encoding and use it directly.

**Changes**:
- `backend/integrations/llm/base.py`: Update `encode_image_data_uri` to
  pass through strings that already start with `data:`.
- `backend/steps/builtin/llm_call.py`: Add `use_annotated_image` to config
  schema and execute logic.
- `frontend/.../StepConfigDialog.vue`: Add checkbox in the Images tab.

#### 2.2 Per-camera frame limits and decoupled image selection

**Problem**: Currently, `images_per_sensor` only takes effect when
`sort_by_sensor_then_time` is enabled, and the same limit applies uniformly
to every additional camera. Users need:

- Per-camera frame counts without requiring sensor-ordered assembly.
- Different frame limits per camera (e.g., 5 frames from a wide-angle
  hallway camera, 2 frames from a close-up doorbell camera).

**Backend config change**: Add a `sensor_frame_limits` field alongside the
existing `images_per_sensor` (which becomes the default fallback).

```python
# New config schema additions in llm_call metadata:
"sensor_frame_limits": {
    "type": "object",
    "additionalProperties": {"type": "integer", "minimum": 1},
    "description": (
        "Per-camera frame limit overrides. Keys are sensor IDs, "
        "values are the max recent frames for that sensor. "
        "Sensors not listed here use images_per_sensor as the default."
    ),
},
```

Example config:

```json
{
  "additional_sensor_ids": ["cam_hallway", "cam_kitchen", "cam_door"],
  "images_per_sensor": 3,
  "sensor_frame_limits": {
    "cam_hallway": 5,
    "cam_door": 1
  }
}
```

Result: 5 frames from hallway, 3 from kitchen (default), 1 from door.

**Backend logic change**: Decouple `images_per_sensor` from
`sort_by_sensor_then_time`. Always use `query_media_by_sensor` when explicit
`additional_sensor_ids` are provided, regardless of the sort flag:

```python
# In llm_call execute, replace the current branching logic:
if resolved_sensors:
    # Determine per-sensor limits
    default_per_sensor = int(config.get("images_per_sensor", 3))
    overrides: dict = config.get("sensor_frame_limits") or {}

    extra = await services.event_aggregator.query_media_by_sensor(
        sensor_ids_ordered=resolved_sensors,
        images_per_sensor=default_per_sensor,
        sensor_frame_limits=overrides,
        max_images=max_images,
        since_minutes=time_filter.get("since_minutes"),
        time_start=time_filter.get("time_start"),
        time_end=time_filter.get("time_end"),
        chronological=bool(config.get("sort_by_sensor_then_time", False)),
    )
    media_paths.extend(extra)
elif additional_rooms or image_source == "additional":
    extra = await services.event_aggregator.query_recent_media(
        sensor_ids=None,
        room_names=additional_rooms if additional_rooms else None,
        limit=max_images,
        since_minutes=time_filter.get("since_minutes"),
        time_start=time_filter.get("time_start"),
        time_end=time_filter.get("time_end"),
    )
    media_paths.extend(extra)
```

The `sort_by_sensor_then_time` flag now controls only whether intra-sensor
ordering is oldest-first (chronological) or newest-first (reverse). It no
longer gates whether `images_per_sensor` applies.

**EventAggregator change**: Update `query_media_by_sensor()` to accept an
optional `sensor_frame_limits: dict[str, int]` parameter. When provided,
per-sensor limits override the default `images_per_sensor` for matching
sensor IDs.

```python
# In event_aggregator.py:
async def query_media_by_sensor(
    self,
    sensor_ids_ordered: list[str],
    images_per_sensor: int = 3,
    sensor_frame_limits: dict[str, int] | None = None,
    max_images: int = 10,
    ...
) -> list[str]:
    limits = sensor_frame_limits or {}
    for sensor_id in sensor_ids_ordered:
        limit = limits.get(sensor_id, images_per_sensor)
        # Query `limit` most recent images for this sensor
        ...
```

#### 2.3 Add `trigger_images_count` config

Currently, all trigger media_paths are included when `image_source` is
`"trigger"` or `"both"`. Add a `trigger_images_count` field that limits how
many trigger frames to include (most recent N). Default: all (no limit).

This is useful for pipelines where the event aggregator batches many frames
but the LLM only needs the latest 1-2 for analysis.

```python
# In llm_call execute:
if image_source in ("trigger", "both"):
    trigger_count = config.get("trigger_images_count")
    frames = trigger.media_paths
    if trigger_count and trigger_count > 0:
        frames = frames[-trigger_count:]  # most recent N
    media_paths.extend(frames)
```

#### 2.4 Frontend: improved camera selection UX for llm_call

**Goal**: Replace the current flat combobox + hidden `images_per_sensor` with
an intuitive camera selection interface that surfaces per-camera frame limits.

**Current UX issues**:

- `images_per_sensor` is hidden behind the `sort_by_sensor_then_time`
  checkbox. Users who want per-camera limits without sensor ordering cannot
  access this control.
- A single global `images_per_sensor` applies to all cameras uniformly.
  No way to differentiate between cameras.
- The combobox for `additional_sensor_ids` shows plain sensor ID strings.
  There is no visibility into what each camera's frame limit is.
- The `image_source` dropdown uses "Additional cameras" which is vague.
  Users must mentally map "additional" to "cameras other than the trigger."

**Proposed UI** (in the Images tab for `llm_call`):

```text
+--------------------------------------------------------------+
| Image Source: [Trigger + selected cameras  v]                |
+--------------------------------------------------------------+
| Trigger Camera                                               |
|   Max frames: [___3___]  (0 = all available)                |
+--------------------------------------------------------------+
| Additional Cameras                                           |
|   Default frames per camera: [___3___]                       |
|                                                              |
|   +--------------------------------------------------+       |
|   | Camera Sensor      | Frames | Remove             |       |
|   |--------------------+--------+--------------------|       |
|   | cam_hallway        | [__5__]| [x]                |       |
|   | cam_kitchen        | [__3__]| [x]                |       |
|   | cam_door           | [__1__]| [x]                |       |
|   +--------------------------------------------------+       |
|   [+ Add Camera v]  (combobox filtered to available cameras) |
|                                                              |
|   [ ] Additional Rooms (pull from all cameras in rooms)      |
|       [room combobox, multi-select]                          |
+--------------------------------------------------------------+
| [v] Group by sensor, then chronological within each sensor   |
+--------------------------------------------------------------+
| Time Filter (optional)                                       |
|   ...existing time filter controls...                        |
+--------------------------------------------------------------+
| Max Images (total): [___10__] (hard cap across all sources)  |
+--------------------------------------------------------------+
```

**Key design decisions**:

1. **Camera table instead of combobox**: Each selected camera appears as a row
   with its own "Frames" number input. The value defaults to the "Default
   frames per camera" setting and can be overridden per-camera.

2. **Trigger frame limit**: When `image_source` includes trigger frames,
   show a `trigger_images_count` control above the additional cameras section.
   This maps to the backend `trigger_images_count` field from section 2.3.

3. **Default + override pattern**: The "Default frames per camera" field maps
   to backend `images_per_sensor`. Per-row overrides write to the
   `sensor_frame_limits` dict. Cameras without an explicit override inherit
   the default. The UI shows the effective value in the input (greyed out
   when using default, solid when overridden).

4. **`sort_by_sensor_then_time` stays visible**: Moved outside the camera
   selection card as a standalone checkbox. It now controls sort order only,
   not whether per-sensor limits apply.

5. **`max_images` (total cap)**: Moved to the bottom of the section to
   emphasize it is a global hard cap applied after per-camera assembly.

**Implementation in `StepConfigDialog.vue`**:

The camera table uses a reactive list derived from `cfg.additional_sensor_ids`
and `cfg.sensor_frame_limits`:

```javascript
// Computed property for camera rows
const cameraRows = computed(() => {
  const sensors = cfg.additional_sensor_ids || [];
  const limits = cfg.sensor_frame_limits || {};
  const defaultLimit = cfg.images_per_sensor || 3;
  return sensors.map(id => ({
    sensor_id: id,
    frames: limits[id] ?? defaultLimit,
    isOverride: id in limits,
  }));
});

// When user changes a camera's frame count
function updateSensorFrameLimit(sensorId, value) {
  const defaultLimit = cfg.images_per_sensor || 3;
  if (!cfg.sensor_frame_limits) cfg.sensor_frame_limits = {};
  if (value === defaultLimit) {
    delete cfg.sensor_frame_limits[sensorId];
  } else {
    cfg.sensor_frame_limits[sensorId] = value;
  }
}

// When user adds a camera
function addCamera(sensorId) {
  if (!cfg.additional_sensor_ids) cfg.additional_sensor_ids = [];
  if (!cfg.additional_sensor_ids.includes(sensorId)) {
    cfg.additional_sensor_ids.push(sensorId);
  }
}

// When user removes a camera
function removeCamera(sensorId) {
  cfg.additional_sensor_ids = cfg.additional_sensor_ids.filter(
    id => id !== sensorId
  );
  if (cfg.sensor_frame_limits) {
    delete cfg.sensor_frame_limits[sensorId];
  }
}
```

**Vuetify components used**: `v-data-table` (or `v-simple-table`) for the
camera rows, `v-text-field` (type=number, density=compact) for per-camera
frame inputs, `v-autocomplete` for the "Add Camera" dropdown (filtered to
exclude already-selected sensors), `v-chip` with close icon for quick
removal.

**Backward compatibility**: Existing configs with `additional_sensor_ids`
(array) and `images_per_sensor` (int) continue to work unchanged. The new
`sensor_frame_limits` field defaults to `{}` (empty, all cameras use the
global default). The frontend reads from both fields and writes
`sensor_frame_limits` only when per-camera overrides exist.

**Estimated scope for Phase 2**: ~180 lines of backend changes, ~200 lines of
frontend changes, ~120 lines of tests.

---

### Phase 3: Deprecation Markers and Migration Path

**Goal**: Mark `vision_analysis` as deprecated; provide clear migration
guidance; allow existing pipelines to keep working.

#### 3.1 Add deprecation warning to vision_analysis step

Update `VisionAnalysisHandler.execute()` to emit a deprecation warning log
on every execution:

```python
logger.warning(
    "vision_analysis_deprecated",
    rule=execution.rule.name,
    message="The vision_analysis step is deprecated. Migrate to llm_call.",
)
```

#### 3.2 Mark as deprecated in metadata

Update `VisionAnalysisHandler.metadata()`:

```python
return StepMetadata(
    type_name="vision_analysis",
    display_name="Vision Analysis (Deprecated)",
    category="perception",
    icon="mdi-eye-off",
    description="DEPRECATED: Use llm_call instead. ...",
    ...
)
```

#### 3.3 Frontend deprecation UI

In `StepPalette.vue`, show deprecated steps with a visual indicator (e.g.,
strikethrough, muted color, "(deprecated)" label). Add a `deprecated` field
to `StepMetadata` and expose it via the `GET /pipeline/step-types` endpoint.

In `StepConfigDialog.vue`, show a migration banner at the top of the
vision_analysis config:

```html
<v-alert type="warning" variant="tonal" class="mb-4">
  This step type is deprecated. Use <strong>LLM Call</strong> instead
  with <code>image_source: "trigger"</code> and
  <code>output_key: "vision_response"</code>.
</v-alert>
```

#### 3.4 Migration guide for existing rules

Document the exact config mapping:

| vision_analysis config | llm_call equivalent |
|----------------------|---------------------|
| `prompt` | `prompt` |
| `image_source: "trigger"` | `image_source: "trigger"` |
| `image_source: "additional"` | `image_source: "additional"` |
| `image_source: "both"` | `image_source: "both"` |
| `max_images` | `max_images` |
| `additional_sensor_ids` | `additional_sensor_ids` |
| `additional_room_names` | `additional_room_names` |
| `image_time_filter` | `image_time_filter` |
| `response_format: "default"` | `response_format: "text"` |
| `response_format: "custom"` | `response_format: "json_schema"` |
| `response_schema` | `response_schema` |
| `response_json_schema` | `response_json_schema` |
| `thinking` | `thinking` |
| `temperature`, `top_p`, `max_tokens` | Same fields |
| `use_annotated_image` | `use_annotated_image` |
| (not available) | `model_id` (required, e.g. `"cosmos_reason2"`) |
| (hardcoded `vision_response`) | `output_key: "vision_response"` |

#### 3.5 Consider a migration API endpoint

Optionally, add a `POST /api/v1/admin/migrate-vision-steps` endpoint that
scans all rules for `vision_analysis` steps and converts them to `llm_call`
with the equivalent config. This is a convenience, not a requirement. The
mapping is deterministic:

```python
def migrate_vision_to_llm_call(vision_config: dict) -> dict:
    """Convert a vision_analysis config to an equivalent llm_call config."""
    response_format_map = {"default": "text", "custom": "json_schema"}
    return {
        "model_id": "cosmos_reason2",  # or configurable default
        "prompt": vision_config.get("prompt", ""),
        "image_source": vision_config.get("image_source", "trigger"),
        "max_images": vision_config.get("max_images", 5),
        "additional_sensor_ids": vision_config.get("additional_sensor_ids", []),
        "additional_room_names": vision_config.get("additional_room_names", []),
        "image_time_filter": vision_config.get("image_time_filter", {}),
        "response_format": response_format_map.get(
            vision_config.get("response_format", "default"), "text"
        ),
        "response_schema": vision_config.get("response_schema", ""),
        "response_json_schema": vision_config.get("response_json_schema", ""),
        "output_key": "vision_response",
        "thinking": vision_config.get("thinking", False),
        "temperature": vision_config.get("temperature"),
        "top_p": vision_config.get("top_p"),
        "max_tokens": vision_config.get("max_tokens"),
        "use_annotated_image": vision_config.get("use_annotated_image", False),
    }
```

**Estimated scope for Phase 3**: ~60 lines backend, ~30 lines frontend, docs.

---

### Phase 4: Remove vision_analysis Step

**Goal**: Delete the deprecated step and all its unique dependencies.

#### 4.1 Delete step handler

Remove `backend/steps/builtin/vision_analysis.py`.

#### 4.2 Remove legacy vision provider wiring

- `backend/main.py`: Remove `vision_provider = get_provider(...)` and the
  `vision_provider=vision_provider` argument to `PipelineExecutor`.
- `backend/services/pipeline_executor.py`: Remove `vision_provider` parameter
  from `__init__`.
- `backend/steps/base.py`: Remove `vision_provider` field from
  `ServiceContainer`.

#### 4.3 Remove legacy VLLMVisionProvider (conditional)

`VLLMVisionProvider` in `backend/integrations/llm/vllm.py` is used only by
the vision_analysis step. After removal, it becomes dead code. However,
`VLLMTranslationProvider` in the same file may still be referenced by legacy
translation config. Check if `llm.translation` settings section is still used
anywhere before removing the entire file.

Remove from `backend/integrations/llm/__init__.py`:
- `"vllm_vision"` entry from `_PROVIDER_MAP`
- `"vllm_vision"` entry from `_SETTINGS_SECTION`

If `VLLMTranslationProvider` is also unused (the `translation` step was
already removed per AGENTS.md), remove the entire `vllm.py` file and its
`_PROVIDER_MAP` / `_SETTINGS_SECTION` entries.

#### 4.4 Clean settings.yaml

Remove the `llm.vision` section from `config/settings.yaml` (lines 25-29).
The `cosmos_reason2` entry in `llm.models` already provides the same model
via the registry.

Remove `VISION_MODEL_URL` from `.env.example` if no other config references
it (the `llm.models` entry already uses `${VISION_MODEL_URL}`).

#### 4.5 Update pipeline model fallback

In `backend/models/pipeline.py`, remove `"vision_analysis"` from the
`get_step_types()` fallback tuple.

#### 4.6 Clean frontend

- `StepConfigDialog.vue`: Remove all `v-if="localStep.step_type === 'vision_analysis'"` blocks, the `vision_analysis` entry from `knownTypes`,
  `STEP_ICONS`, `fallbackDefaults`, and the `imageTimeFilter` reactive state.
- `StepPalette.vue`: Remove the `vision_analysis` fallback entry.
- `PipelineBuilder.vue`: Remove the `vision_analysis` icon mapping.
- `RuleDetailView.vue`: Remove the `vision_analysis` icon mapping.

#### 4.7 Update documentation

- `README.md`: Remove `vision_analysis` from the pipeline step types table
  and example pipeline configurations. Update examples to use `llm_call`.
- `AGENTS.md`: Remove `vision_analysis` references from step type details,
  layout descriptions, and the step type list.
- `CLAUDE.md`: Remove from the step types table. Update `ServiceContainer`
  field list.

#### 4.8 Update tests

- Remove any tests that directly test `VisionAnalysisHandler`.
- Add/update tests for `llm_call` covering the newly migrated features
  (`use_annotated_image`, expanded image selection).
- Update `test_pipeline_executor.py` if it references `vision_analysis`.

**Estimated scope for Phase 4**: ~500 lines removed, ~50 lines of test
updates, documentation changes.

---

### Phase 5: Test and Verify

#### 5.1 Unit tests for `clean_llm_json` / `parse_llm_json`

New test file: `backend/tests/integrations/test_llm_json_utils.py`

Cover:
- Markdown fence stripping (```json, ```, with/without trailing newlines)
- Valid JSON pass-through
- Invalid JSON returns original string
- Empty input
- Nested fences in JSON string values

#### 5.2 Unit tests for `llm_call` step enhancements

New/expanded test file: `backend/tests/steps/test_llm_call.py`

Cover:
- `use_annotated_image` with annotated image in pipeline_data
- `use_annotated_image` without annotated image (graceful no-op)
- `images_per_sensor` without `sort_by_sensor_then_time`
- `trigger_images_count` limiting trigger frames
- `output_key` with different keys for multiple llm_call steps
- JSON response parsing with markdown fences
- JSON response parsing without fences
- `response_format: "json_schema"` with guided_decoding model
- `response_format: "json_schema"` with non-guided model (prompt injection)
- Empty model response handling
- Model without vision capability skips images

#### 5.3 Integration test: migrated pipeline

Test a pipeline previously using `vision_analysis` now using `llm_call` with
`output_key: "vision_response"`. Verify that downstream steps
(`activity_detection` with `capture_scene_description`, `condition` with
`exists(vision_response)`) work identically.

#### 5.4 Frontend verification

- Verify `vision_analysis` no longer appears in the step palette
- Verify `llm_call` Images tab shows the camera table with per-camera frame inputs
- Verify adding/removing cameras updates `additional_sensor_ids` and `sensor_frame_limits`
- Verify per-camera overrides: changing a camera's frame count from the default writes to `sensor_frame_limits`; resetting to default removes the override
- Verify `trigger_images_count` control appears when image source includes trigger
- Verify `images_per_sensor` is always visible (not gated by `sort_by_sensor_then_time`)
- Verify existing `llm_call` steps with old config format (no `sensor_frame_limits`) load correctly
- Test creating a new `llm_call` step with vision capabilities

#### 5.5 Regression test: run full test suite

```bash
make check-all   # lint + typecheck-core + test-core + test-services
make test         # full backend suite
```

---

## 4. Edge Cases and Risk Mitigation

### 4.1 Existing rules with vision_analysis steps

**Risk**: Rules in the database have `step_type = "vision_analysis"`.
After removing the handler, `StepRegistry.get("vision_analysis")` returns
`None`, and `PipelineExecutor._execute_step()` returns
`StepResult(success=False, should_continue=False)`, failing the pipeline.

**Mitigation**: Phase 3 provides a migration window. The step continues to
work during the deprecation period. Before Phase 4 (removal), all existing
rules must be migrated. The optional migration endpoint automates this.

**Alternative**: Keep a thin shim handler that delegates to `LLMCallHandler`
with auto-translated config. This provides backward compatibility
indefinitely but adds complexity. Not recommended since this is an on-premise
system with a single operator.

### 4.2 Pipeline data key compatibility

**Risk**: Downstream steps reference `vision_response` (hardcoded in
`activity_detection.scene_description_key` default). If `llm_call` uses a
different output_key, downstream steps break.

**Mitigation**: The migration sets `output_key: "vision_response"` for
vision-replacement llm_call steps. The `activity_detection` step's
`scene_description_key` config is already configurable, so even custom keys
work.

### 4.3 JSON schema format differences

**Risk**: `vision_analysis` uses `response_format: "custom"` while `llm_call`
uses `response_format: "json_schema"`. Migration must translate.

**Mitigation**: The migration mapping in Phase 3.4 handles this explicitly.
`"default" -> "text"`, `"custom" -> "json_schema"`.

### 4.4 Model ID required in llm_call

**Risk**: `vision_analysis` does not require a `model_id` (it uses the
hardwired provider). `llm_call` requires `model_id`.

**Mitigation**: Migration sets `model_id: "cosmos_reason2"` (matching the
current hardwired vision provider config). The administrator can change
this post-migration.

### 4.5 Provider differences between VLLMVisionProvider and OpenAICompatibleProvider

**Risk**: `VLLMVisionProvider` and `OpenAICompatibleProvider` are nearly
identical (both call `/v1/chat/completions`), but `VLLMVisionProvider` always
passes `guided_json` when `response_schema` is set, while
`OpenAICompatibleProvider` respects the `guided_decoding` flag.

**Mitigation**: The `cosmos_reason2` model registry entry has
`guided_decoding: true`, so `OpenAICompatibleProvider` will behave identically
to `VLLMVisionProvider` for this model. No behavioral change.

### 4.6 Race condition with multiple llm_call steps writing the same key

**Risk**: Two `llm_call` steps with the same `output_key` silently overwrite
each other in `pipeline_data`.

**Mitigation**: This is by design (same as any two steps writing the same
key). Add a warning log when `output_key` collides with an existing
pipeline_data key:

```python
if output_key in pipeline_data:
    logger.warning(
        "llm_call_output_key_collision",
        output_key=output_key,
        rule=execution.rule.name,
    )
```

---

## 5. Opportunities for Code Reduction

### 5.1 Remove legacy provider infrastructure

After Phase 4, the following become dead code:

- `get_provider()` function in `backend/integrations/llm/__init__.py` (the
  `_SETTINGS_SECTION` lookup)
- `_PROVIDER_MAP` entries for `vllm_vision` and potentially `vllm_translation`
- `_build_provider_from_config()` and related chain/pool wiring for legacy
  sections
- `VLLMVisionProvider` class
- `VLLMTranslationProvider` class (if `llm.translation` is also unused)

The entire legacy `get_provider` / `_SETTINGS_SECTION` system can be removed
if no other code uses it. The `LLMModelRegistry` is the replacement.

**Check**: Grep for `get_provider` usage outside of `main.py`:

```bash
grep -r "get_provider\|get_llm_provider" backend/ --include="*.py" \
  | grep -v __pycache__ | grep -v test
```

If only `main.py` uses it (for `vision_provider`), the entire legacy system
can be removed in Phase 4.

### 5.2 Use `pydantic` for LLM response validation

Instead of manual `json.loads` + type checking, consider using Pydantic models
for structured LLM responses. The `response_json_schema` could be used to
construct a Pydantic model at runtime for validation. This is a larger
refactor and not required for the deprecation, but worth noting.

### 5.3 Use `jsonschema` library for schema validation

The `response_json_schema` is currently only passed to the provider (guided
decoding) or appended as prompt text. Adding `jsonschema` validation on the
response would catch malformed output even when guided decoding is used.
This is optional but improves reliability.

---

## 6. Execution Order and Dependencies

```
Phase 1 (JSON utils)          -- no dependencies, can ship independently
    |
Phase 2 (llm_call gaps)       -- depends on Phase 1 for clean JSON parsing
    |
Phase 3 (deprecation markers) -- depends on Phase 2 (llm_call must be ready)
    |
    |  [migration window: existing rules continue working]
    |
Phase 4 (removal)             -- depends on Phase 3 + all rules migrated
    |
Phase 5 (verification)        -- runs after each phase
```

Phases 1 and 2 can be combined into a single PR. Phase 3 is a separate PR.
Phase 4 is a final cleanup PR after confirming all rules are migrated.

---

## 7. Files Changed Per Phase

### Phase 1
| Action | File |
|--------|------|
| Create | `backend/integrations/llm/json_utils.py` |
| Create | `backend/tests/integrations/test_llm_json_utils.py` |
| Modify | `backend/steps/builtin/llm_call.py` |

### Phase 2
| Action | File |
|--------|------|
| Modify | `backend/steps/builtin/llm_call.py` (add use_annotated_image, trigger_images_count, sensor_frame_limits, decouple images_per_sensor) |
| Modify | `backend/services/event_aggregator.py` (add sensor_frame_limits param to query_media_by_sensor) |
| Modify | `backend/integrations/llm/base.py` (data URI pass-through in encode_image_data_uri) |
| Modify | `frontend/.../StepConfigDialog.vue` (camera table UI, per-camera frame inputs, trigger_images_count) |
| Create | `backend/tests/steps/test_llm_call.py` |

### Phase 3
| Action | File |
|--------|------|
| Modify | `backend/steps/builtin/vision_analysis.py` (deprecation warning + metadata) |
| Modify | `backend/steps/base.py` (add deprecated field to StepMetadata) |
| Modify | `frontend/.../StepPalette.vue` (deprecation indicator) |
| Modify | `frontend/.../StepConfigDialog.vue` (migration banner) |

### Phase 4
| Action | File |
|--------|------|
| Delete | `backend/steps/builtin/vision_analysis.py` |
| Delete | `backend/integrations/llm/vllm.py` (if fully unused) |
| Modify | `backend/steps/base.py` (remove vision_provider from ServiceContainer) |
| Modify | `backend/services/pipeline_executor.py` (remove vision_provider param) |
| Modify | `backend/main.py` (remove vision_provider construction) |
| Modify | `backend/integrations/llm/__init__.py` (remove legacy entries) |
| Modify | `backend/models/pipeline.py` (remove from fallback tuple) |
| Modify | `config/settings.yaml` (remove llm.vision section) |
| Modify | `frontend/.../StepConfigDialog.vue` (remove vision_analysis blocks) |
| Modify | `frontend/.../StepPalette.vue` (remove fallback entry) |
| Modify | `frontend/.../PipelineBuilder.vue` (remove icon mapping) |
| Modify | `frontend/.../RuleDetailView.vue` (remove icon mapping) |
| Modify | `README.md`, `AGENTS.md`, `CLAUDE.md` |

---

## 8. Testing Strategy

### Unit test coverage targets

| Component | Target | Notes |
|-----------|--------|-------|
| `json_utils.py` | 100% branch | New file, small surface |
| `llm_call.py` (new features) | 95%+ branch | Test all new config paths |
| `llm_call.py` (existing) | Maintain current | No regressions |
| `OpenAICompatibleProvider` | Add fence-stripping test | Extend existing suite |

### Test patterns

Following existing project conventions:
- Use `@dataclass class _FakeStep` instead of `PipelineStep` for step handler
  tests
- Use `ServiceContainer(db_factory=..., llm_model_registry=mock_registry)` with
  only needed fields
- Use `RulesEngine(tz_name="UTC")` for timestamp consistency
- Use in-memory SQLite via conftest fixtures for DB-touching tests
- Mock LLM providers with `AsyncMock` returning canned responses

### Regression gates

Run after each phase:

```bash
make check-all    # lint + typecheck-core + test-core + test-services
make test         # full 600+ test suite
```

---

## 9. Summary

This deprecation consolidates two overlapping step types into one, removes
~200 lines of duplicated step code, eliminates the legacy hardwired provider
system, fixes the JSON parsing reliability gap, and expands image selection
flexibility. The migration is backward-compatible through a deprecation
window, with an optional automated migration endpoint for existing rules.
