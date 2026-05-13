# Pipeline Improvements: Design & Implementation Plan

Status: draft for review
Author: agent-assisted design
Scope: `cognitive-companion/` (backend + frontend)
Audience: future engineers / agents touching pipeline UX, scheduling, import-export, and template tooling

---

## 0. Reading guide

This plan is grouped into six work areas. They are largely independent and can be sequenced as separate PRs:

1. **Plugin authoring ergonomics**; make adding a step / filter / channel friction-free.
2. **Rule import / export**; versioned, portable, community-shareable rule artifacts.
3. **Execution lifecycle**; cancel, rerun, and a real execution detail view.
4. **Human-friendly scheduling**; UI cron builder with strict TZ semantics.
5. **Template + condition unification**; single `{{ ... }}` surface with validation and autocomplete.
6. **AI agent surface**; MCP tools for rule authoring by agents.

A final section (§7) covers cross-cutting test, telemetry, and rollout concerns.

The guiding principles, in priority order:

- **Leverage what already exists.** The plugin contract, [render_template](backend/core/template.py), [ConditionEvaluator](backend/services/condition_evaluator.py), [PipelineExecutor](backend/services/pipeline_executor.py), and `MutableDict.as_mutable(JSON)` execution snapshots are good. We extend, we don't rewrite.
- **Prefer libraries to bespoke code.** `jsonschema`, `croniter`, `cronstrue`, `Lark`, `CodeMirror 6`, `jsondiff`. List per area below.
- **Schema, not branching.** Where today's UI branches by `step_type`, tomorrow's UI consumes a JSONSchema augmented with UI hints. New step types should require zero frontend edits in the common case.
- **No new ID coupling.** Anything that crosses an install boundary (export, MCP) is keyed on stable string `name`/`label`/`type_name`, never DB ids.
- **Append-only contract evolution.** Plugin metadata gains optional fields (`version`, `migrations`, `ui_hints`); never breaks existing handlers.

---

## 1. Plugin authoring ergonomics

### 1.1 Problem

Adding a step today requires:

1. A new file under [backend/steps/builtin/](backend/steps/builtin/) implementing [`StepHandler`](backend/steps/base.py).
2. A new Vue config component under [frontend/src/components/pipeline/steps/](frontend/src/components/pipeline/steps/).
3. An entry in [stepConfigMap](frontend/src/components/pipeline/steps/index.js) wiring component + defaults + tabs.
4. Icon + label entry in `STEP_ICONS` / `STEP_LABELS`.
5. A variable-reference entry in the static `pipelineDataReference` array inside [StepConfigDialog.vue:238-275](frontend/src/components/pipeline/StepConfigDialog.vue#L238-L275).
6. A test under `backend/tests/steps/`.

Steps 2–5 are pure boilerplate driven by data the backend already owns. Step 5 is *already a divergence risk*; the list is hand-maintained and silently goes stale.

### 1.2 Goal

A new step type ships in **one Python file** by default. A custom UI is opt-in, not required.

### 1.3 Design

#### 1.3.1 Enrich `StepMetadata` (additive, backward-compatible)

[backend/steps/base.py](backend/steps/base.py); add optional fields:

```python
@dataclass(frozen=True)
class StepMetadata:
    type_name: str
    display_name: str
    category: str
    icon: str
    description: str
    config_schema: dict
    default_config: dict
    deprecated: bool = False

    # NEW; all optional, defaults preserve current behaviour
    schema_version: int = 1
    ui_hints: dict = field(default_factory=dict)  # see §1.3.2
    output_schema: dict = field(default_factory=dict)  # JSONSchema describing pipeline_data.steps.<label>.outputs.*
    migrations: tuple["ConfigMigration", ...] = ()  # see §2.4
    tags: tuple[str, ...] = ()  # for palette grouping/search
```

`output_schema` is the unlock for §5 (template autocomplete) and §1.4 (eliminating the hand-maintained `pipelineDataReference`).

#### 1.3.2 UI hints; a tiny, JSONSchema-compatible dialect

Today `config_schema` is JSONSchema but the frontend ignores it and uses bespoke Vue components. We adopt the [`x-ui`](https://github.com/json-editor/json-editor) convention used by JSON Forms / RJSF: keys under `x-ui` are read by a generic renderer; everything else stays standard JSONSchema and is validated server-side.

Example for a hypothetical `face_count` step:

```python
config_schema = {
    "type": "object",
    "required": ["min_count"],
    "properties": {
        "min_count": {
            "type": "integer", "minimum": 1, "default": 1,
            "x-ui": {"widget": "slider", "min": 1, "max": 10, "label": "Minimum faces"}
        },
        "prompt": {
            "type": "string",
            "x-ui": {"widget": "template-textarea", "rows": 4, "supports_template": True}
        },
        "model_id": {
            "type": "string",
            "x-ui": {"widget": "select", "options_source": "llm_models"}  # backend-registered data source
        },
        "output_key": {
            "type": "string", "default": "llm_response",
            "x-ui": {"widget": "text", "section": "advanced"}
        },
    },
}
```

Widgets to support in v1 (covers ~90% of existing step UIs): `text`, `textarea`, `template-textarea`, `template-text`, `number`, `slider`, `checkbox`, `select`, `multiselect`, `chips`, `code-json`, `cron`, `time-of-day`, `step-label-ref`. Anything not in the registry falls back to JSON editor (today's `GenericPluginConfig`).

Existing typed components remain; `stepConfigMap` entries continue to override the generic renderer. The renderer is a *fallback*, so existing custom UIs are untouched.

#### 1.3.3 Backend metadata endpoint enrichment

Extend [`/pipeline/step-types`](backend/routers/pipeline.py#L25-L42) (and the analogous filter/channel routes) to emit the new fields. The frontend already calls these in [StepConfigDialog onMounted](frontend/src/components/pipeline/StepConfigDialog.vue#L364-L397).

#### 1.3.4 Frontend generic renderer

New component `frontend/src/components/pipeline/steps/_shared/SchemaForm.vue`. It walks `config_schema.properties`, dispatches on `x-ui.widget`, and emits a config object. `stepConfigMap` learns a new shape:

```js
// Default for any step without a typed component:
genericPluginConfig = { component: SchemaForm, defaults: (meta) => meta.default_config }
```

Steps that need bespoke UX (e.g. `llm_call`, `notification`) keep their hand-written components. **No existing component needs to change.**

#### 1.3.5 Contract-enforcement tests

New tests in `backend/tests/steps/test_registry_contract.py`:

- Every registered handler has `metadata().config_schema` that is a valid JSONSchema draft 2020-12 document (use `jsonschema.Draft202012Validator.check_schema`).
- `default_config` validates against `config_schema`.
- `type_name` matches `^[a-z][a-z0-9_]*$` (already enforced in label rules; mirror here).
- `output_schema` is a valid JSONSchema (or empty).
- `icon` starts with `mdi-`.
- Categories are from the known set.

Same shape for filter and channel registries.

#### 1.3.6 Authoring CLI

`uv run --project backend python -m backend.steps.scaffold new my_step --category perception`. Generates a templated handler file + a paired test file. Uses [Jinja2](https://jinja.palletsprojects.com/) (already a transitive dep via FastAPI) or stdlib `string.Template`. ~80 LOC total. Lives under [backend/steps/_scaffold/](backend/steps/_scaffold/).

### 1.4 Eliminate hand-maintained variable reference

The `pipelineDataReference` array in [StepConfigDialog.vue:238-275](frontend/src/components/pipeline/StepConfigDialog.vue#L238-L275) becomes computed from:

- A small static list of trigger/system variables (lives in [backend/services/pipeline_data_manager.py](backend/services/pipeline_data_manager.py); exposed via new `GET /pipeline/data-keys`).
- Per-step `output_schema` from the metadata endpoint, scoped to the **current pipeline's labels** so suggestions reflect the actual `steps.<label>.outputs.*` names.

This same data feeds §5.4 autocomplete.

### 1.5 Acceptance criteria

- A new step type with a single `int` config field renders a working slider in the frontend with **zero frontend edits**.
- Removing `pipelineDataReference` from `StepConfigDialog.vue` and replacing it with a computed source produces an identical or strictly larger variable list (snapshot test).
- `make check` enforces the new contract tests.

---

## 2. Rule import / export

### 2.1 Problem

Caregivers want to share rules ("Bathroom fall detector v3") via GitHub gists, Discord, etc. Current Pydantic schemas leak DB ids (`rule_id`, `step.id`, `next_step_on_true: int`), so cross-install round-trips are impossible. There is no migration story when fields rename or move between schema versions.

### 2.2 Goal

A single self-contained JSON document (or YAML) per rule:

- Round-trips between installs.
- Survives step refactors via a **per-step-type migration chain**.
- Carries provenance (author, version, exported-at, source software version).
- Validates strictly on import; partial-fail mode skips incompatible fields with a structured warning report rather than rejecting the whole bundle.

### 2.3 Wire format

```yaml
schema_version: 1
exported_at: 2026-05-12T14:00:00Z
exported_by: "sriram@khoofia.com"
source:
  app: cognitive-companion
  app_version: 0.42.0  # backend.__version__
rule:
  name: "Bathroom fall detector"
  description: "..."
  enabled: true
  trigger_type: cron
  schedule_cron: "*/5 * * * *"
  schedule_timezone: "America/Los_Angeles"  # see §2.7
  primary_sensor_ref: { kind: "sensor", label: "bathroom_cam" }  # see §2.5
  cool_off_minutes: 5
  max_daily_triggers: 3
  max_concurrent_executions: 1
  execution_timeout_minutes: 5
  webhook_config: null
  occupancy_config: null
  telegram_trigger_config: null
contexts:
  - context_type: time_range
    config_schema_version: 1
    config: { start_time: "22:00", end_time: "06:00" }
    negate: false
steps:
  - label: scene_1
    step_type: scene_analysis
    schema_version: 1
    enabled: true
    config: { analysis_type: "objects", return_raw: false }
    branches: { on_true: null, on_false: null }
  - label: cond_1
    step_type: condition
    schema_version: 2  # bumped after the {{ }} unification (§5)
    enabled: true
    config: { expression: 'contains({{steps.scene_1.outputs.scene_description}}, "fallen")' }
    branches: { on_true: "notify_1", on_false: null }
  - label: notify_1
    step_type: notification
    schema_version: 1
    enabled: true
    config: { message: "Possible fall in bathroom", channels: ["telegram"], alert_level: "critical" }
dependencies: []
```

Notes:

- **No primary keys.** Everything cross-references by `label` (steps) or stable string ref (sensors, persons, channels).
- **Two version planes.** Bundle `schema_version` (the envelope format itself, rarely changes) and per-step `schema_version` (changes whenever a step's `config_schema` changes shape).
- **YAML preferred** for community sharing (comments, diff-friendly); JSON accepted on import. Use [PyYAML](https://pyyaml.org/) safe_load with `ruamel.yaml` if comment preservation matters. JSON is the canonical export; YAML is sugar.

### 2.4 Migration registry

Each step (and filter, channel) ships an ordered tuple of `ConfigMigration` callables:

```python
# backend/core/plugin_migrations.py
@dataclass(frozen=True)
class ConfigMigration:
    from_version: int
    to_version: int
    description: str
    apply: Callable[[dict], dict]  # pure function, no side effects

# Example in backend/steps/builtin/condition.py
@StepRegistry.register
class ConditionHandler(StepHandler):
    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="condition",
            ...,
            schema_version=2,
            migrations=(
                ConfigMigration(
                    from_version=1, to_version=2,
                    description="Unify expressions on {{ }} template syntax (see §5).",
                    apply=lambda cfg: {**cfg, "expression": _v1_to_v2_expression(cfg.get("expression", ""))},
                ),
            ),
        )
```

On import we run `migrate(config, from_version=imported, to_version=current)` per step. If any migration is missing, the importer records a structured warning and either:

- **Strict mode** (`?strict=true`): fails the whole import.
- **Lenient mode** (default, used by the UI): drops the offending step and records a warning. The caller sees a per-step report.

For *forward* compatibility (importing a rule exported from a *newer* version), we can't run the migration backwards. The contract is:

- If `imported_version > current_version` and the unknown fields are additive only, we strip unknown fields and import (with warning). This is detectable by validating the config against the current `config_schema` after dropping unknown keys.
- Otherwise we reject the step with a clear warning.

### 2.5 External references; sensors, persons, channels, models

These don't round-trip cleanly. Strategy:

- **Sensors / cameras**: export by `sensor_id` (the operator-chosen string, e.g. `"bathroom_cam"`); importer matches by id, falls back to a UI step prompting the user to remap (similar to "missing materials" in Figma component imports).
- **Persons**: export by `person_id` slug; same remap UX.
- **Channels**: export by `channel_name` (`telegram`, `eink`, etc.); these are global string identifiers, no DB id involved.
- **LLM models**: export by `model_id` (the registry's stable name). If the target install doesn't have that model, importer offers to substitute or rejects the step.

The export bundle includes a top-level `references` block listing every external reference, so the import UI can show a single "remap external references" form before committing.

```yaml
references:
  sensors: ["bathroom_cam"]
  persons: ["mom"]
  channels: ["telegram"]
  llm_models: ["gemma-3-vision"]
```

### 2.6 API surface

New endpoints in [backend/routers/rules.py](backend/routers/rules.py):

```python
GET    /rules/{id}/export                   # → application/x-yaml or application/json (Accept-driven)
POST   /rules/import                        # body: bundle; query: ?strict, ?remap (JSON of ref overrides)
POST   /rules/import/preview                # validates + returns the migration/warning report without writing
```

All gated by a new permission `rules:import` and `rules:export` (reuse `rules:write` for import, `rules:read` for export to keep `auth.yaml` lean).

Implementation lives in `backend/services/rule_serializer.py`; pure functions over Pydantic models, no DB access. The router handles the DB write + cross-reference resolution.

### 2.7 Cron timezone in exports

The current `Rule.schedule_cron` is interpreted in the install's app timezone (see [scheduler.py](backend/services/scheduler.py)). On export we capture `schedule_timezone` separately so a Pacific user's "9 AM" doesn't become "9 AM UTC" when imported by a London caregiver. On import we default to the local install's tz but offer to preserve the original; surfaced in the import preview UI.

### 2.8 Frontend UX

- **Export button** on the rule detail toolbar: downloads `<rule-name>.cc-rule.yaml`. Use Vuetify file-saver pattern.
- **Import flow**: dropzone on the rules list page → `POST /rules/import/preview` → modal showing the migration report (which steps will be migrated, dropped, or remapped) → confirm → `POST /rules/import`.
- **Conflict resolution**: rule name conflict → prompt with rename/replace/skip. The Pydantic uniqueness constraint already exists ([rules.py:50](backend/routers/rules.py#L50-L52)); reuse the `ConflictError` path.

### 2.9 Acceptance criteria

- A rule exported from install A imports cleanly on install B (different DB ids, same step types) producing semantically identical behavior on a manual `POST /rules/{id}/execute` smoke test.
- Forced migration: a v1 `condition` rule exported pre-§5 imports post-§5 with the expression rewritten in `{{ }}` form. Snapshot test.
- A bundle referencing an unknown step type imports the remaining steps and returns a warning naming the missing type. Integration test.
- Library used: **PyYAML** (already in transitive deps via uvicorn? confirm; otherwise add `ruamel.yaml`) for YAML I/O; **jsondiff** optional for nicer import-preview diffs.

---

## 3. Execution lifecycle: cancel, rerun, rich detail

### 3.1 Problem

- The Live Run tab streams pipeline_data but offers no way to **abort** a stuck or wrong execution.
- There is no **rerun** primitive; to re-test a rule you must re-trigger from scratch, losing the original trigger context.
- The Executions tab shows a dialog with the raw `pipeline_data` JSON. Users want the same rich, step-by-step timeline view they have during live run, but historical.

### 3.2 Goal

- Cancel a `running` or `waiting` execution from the UI.
- Rerun an execution: create a new `WorkflowExecution` that copies the original `TriggerContext` and re-runs all enabled steps. Optionally "from-step-N" for debugging.
- Unified execution detail view: one component renders live AND historical executions identically, fed by the same shape of data.

### 3.3 Cancel

#### 3.3.1 Backend

Already partially present; [api.js:215-220](frontend/src/services/api.js#L215-L220) calls `cancelWorkflow(id)` against `POST /workflows/{id}/cancel`. Verify the router exists (the explorer didn't surface it; if missing, add it). The cancel path should:

1. Pessimistically lock the `WorkflowExecution` row (`SELECT ... FOR UPDATE`).
2. If status is `running` or `waiting`: set `status="cancelled"`, `completed_at=now()`, `error="Cancelled by <auth.name>"`.
3. If a scheduled resume job exists, remove it via `scheduler.remove_job(f"resume-{execution_id}")`.
4. Active executions still in-flight in Python: this is the hard part; Python doesn't give you `task.cancel()` from outside the event loop process.

For (4), use a **cooperative cancellation** signal: the [PipelineExecutor](backend/services/pipeline_executor.py) checks `execution.status == "cancelled"` at the top of `_run_steps` between steps. The DB row is the source of truth; the executor reloads it. This won't kill an in-flight `llm_call` mid-request, but it stops the pipeline at the next step boundary, which is what users expect ("abort after current step").

For truly killable steps, the executor passes an `asyncio.Event` (`cancellation_token`) into long-running step handlers (`llm_call`, `scene_analysis`) and they `await` it alongside their HTTP call. v1 = cooperative-only; v2 = token-based.

Permission: `rules:execute` (the same as triggering).

#### 3.3.2 Frontend

Live Run tab toolbar gets a `<v-btn icon="mdi-stop-circle">` that calls `api.cancelWorkflow(id)` after `useConfirm()`. Disabled if `status not in ("running", "waiting")`. Snackbar via `useNotify` on success.

### 3.4 Rerun

#### 3.4.1 Backend

```python
POST /workflows/{id}/rerun
  Body: { from_step_label?: str }   # optional; defaults to first step
  Permission: rules:execute
```

Implementation:

1. Load the original execution; deserialize its `pipeline_data.trigger` into a fresh `TriggerContext`.
2. Verify the rule still exists and is enabled.
3. If `from_step_label` is set: build a partial `pipeline_data` by copying `steps.*` entries up to (and excluding) the target step. This is the **replay-from** pattern; useful when only a late LLM call needs to be retested.
4. Call `pipeline_executor.execute(rule, trigger, db, initial_pipeline_data=...)`. Add the optional kwarg to `execute()`.
5. Return the new execution id; the frontend navigates to its Live Run.

Edge case: the original execution may reference media (`trigger.media_paths`) that have since been pruned from MinIO. The executor should detect missing media at the first step that needs it and fail gracefully; same as a normal execution would.

#### 3.4.2 Frontend

Two entry points:

- Live Run tab and execution detail header: `<v-btn prepend-icon="mdi-replay">Rerun</v-btn>`.
- Per-step in the detail view: `<v-btn icon="mdi-replay" size="x-small">` on each step row → opens a confirm dialog → `POST .../rerun?from_step_label=<label>`.

### 3.5 Rich execution detail view

#### 3.5.1 Component design

Extract the current Live Run rendering into a reusable component `frontend/src/components/pipeline/ExecutionDetail.vue`. It takes a single prop `execution: WorkflowExecutionOut` and a `mode: "live" | "historical"` flag.

```vue
<ExecutionDetail :execution="exec" :mode="liveExecutionId === exec.id ? 'live' : 'historical'" />
```

Layout (mirrors [StepConfigDialog](frontend/src/components/pipeline/StepConfigDialog.vue); same shell, same look-and-feel):

- **Left**: vertical step timeline (one row per `_step_timings` entry). Each row: step icon, label, status badge, elapsed seconds. Color encodes success/failure/skipped/in-progress.
- **Right (selected step)**: tabbed view ;
  - *Inputs*: the step's resolved config (after template substitution, see §5); record this at execution time as a new `pipeline_data._step_timings[i].resolved_config` field.
  - *Outputs*: `pipeline_data.steps.<label>.outputs` formatted with collapsible JSON tree (use [vue-json-pretty](https://github.com/leezng/vue-json-pretty) or [vue-json-viewer](https://github.com/chenfengjw163/vue-json-viewer); pick by bundle size).
  - *Logs*: any per-step log lines if we add a `_step_timings[i].logs: list[str]` field (small, capped).
  - *Raw*: the existing raw-JSON view (escape hatch).
- **Top-right toolbar**: Rerun, Cancel (live only), Copy as JSON, Download bundle.

#### 3.5.2 Data shape additions to `pipeline_data._step_timings[i]`

Append (all optional, all small):

- `resolved_config: dict`; the step config after template substitution, for debuggability.
- `logs: list[str]`; bounded ring buffer (~50 lines, ~8KB total).
- `attempts: int`; for retry-aware steps in the future.
- `cancellation_observed: bool`; true if the step exited early due to cancel.

These are mutations to a dict inside `pipeline_data_json`. Use `flag_modified(execution, "pipeline_data_json")` after writing, consistent with [the existing executor pattern](backend/services/pipeline_executor.py).

#### 3.5.3 Live updates

Today's Live Run polls. Keep polling for v1 (simple, no infra). If we already have a WebSocket pipe for `pwa_realtime_ai`, route execution updates through it as a v2.

### 3.6 Acceptance criteria

- Cancelling a 10-step pipeline at step 3 leaves steps 1–3 with `success=true`, step 4+ absent, execution status `cancelled`.
- Rerun from step N produces an execution whose `steps.*` matches the original for `steps[1..N-1]` and re-executes `steps[N..]`. Snapshot test.
- The Executions tab and Live Run tab render via the same `ExecutionDetail.vue` component; confirmed by snapshot.
- The raw-JSON dialog is still reachable (as the "Raw" tab); we don't regress on the existing escape hatch.

---

## 4. Human-friendly scheduling

### 4.1 Problem

`trigger_type=cron` requires a raw cron expression. Caregivers don't speak cron. Today's hint says "interpreted in {timezone}" but provides no preview or validation. Risk: a caregiver enters `0 9 * * *` thinking 9 AM local, sees nothing fire at 9 AM London time, blames the software.

### 4.2 Goal

- A UI builder that produces a valid cron expression from human inputs (days of week, time of day, frequency).
- A live "next 5 runs" preview computed in the operator's timezone.
- Raw expression editing remains available for power users; the builder is *additive*.
- Single source of truth: the stored `schedule_cron` string. The builder is a renderer/editor over that string, not a separate data model.

### 4.3 Design

#### 4.3.1 Library choice

- Backend (validation, next-run preview): **[croniter](https://github.com/kiorky/croniter)**. APScheduler already uses it transitively.
- Frontend (human-readable rendering): **[cronstrue](https://github.com/bradymholt/cRonstrue)**; battle-tested, i18n-ready, MIT-licensed, ~30KB.
- Frontend (parsing for builder UI): roll our own thin parser (cron has 5 fields; the builder only supports a constrained subset and falls back to raw mode for anything it can't represent).

#### 4.3.2 Builder modes

The builder offers four presets that cover ~95% of caregiver use cases:

| Mode | Inputs | Resulting cron (example, local 9:30 AM) |
| --- | --- | --- |
| Daily | time of day | `30 9 * * *` |
| Weekly | days of week (checkboxes), time | `30 9 * * 1,3,5` |
| Hourly | minute of hour | `30 * * * *` |
| Every N minutes | minute interval | `*/15 * * * *` |
| Custom | raw expression | (passthrough) |

If a loaded expression doesn't fit any preset, the UI snaps to **Custom** mode and shows the raw input. No round-trip loss.

#### 4.3.3 Timezone handling

The operator timezone (from [services/timezone.js](frontend/src/services/timezone.js) `getAppTimezone()`) is the input space. The builder produces a cron expression that the backend interprets in the same timezone (the existing [scheduler.py](backend/services/scheduler.py) behavior; APScheduler is given `ZoneInfo(app.timezone)`).

We **do not** convert times to UTC in the cron string itself. Reasons:

1. DST transitions break naive UTC offsets. A "9 AM local" cron stored as "5 PM UTC" misfires twice a year.
2. APScheduler handles tz-aware cron correctly when given a `ZoneInfo`.
3. Existing rules would silently break if we changed semantics.

What we **do** store explicitly on export (§2.7) is the source timezone, so cross-install transfer is unambiguous.

The UI surfaces this: "Runs at 9:30 AM in your local time (America/Los_Angeles)". On import, the migration may need to adjust the cron string if the importing install's timezone differs and the user accepts a remap.

#### 4.3.4 Backend endpoints

```python
POST /pipeline/cron/preview
  Body: { expression: str, timezone?: str, count?: int = 5 }
  Returns: { valid: bool, error?: str, next_runs: list[ISO8601], description: str }
```

`description` is `cronstrue`-equivalent rendering done server-side (use [cron-descriptor](https://pypi.org/project/cron-descriptor/); port of cronstrue to Python; or render on the frontend and skip this field). Recommendation: render on frontend with `cronstrue`; the backend route returns only `next_runs` (croniter) and `valid`/`error`. Keeps the backend lean.

#### 4.3.5 Component

New `frontend/src/components/pipeline/CronBuilder.vue` used inside RuleDetailView's Settings tab in place of the current `<v-text-field v-model="rule.schedule_cron">`. Props: `v-model:expression`, `timezone`. Emits validation state.

Component skeleton:

```vue
<template>
  <div>
    <v-btn-toggle v-model="mode" mandatory density="compact">
      <v-btn value="daily">Daily</v-btn>
      <v-btn value="weekly">Weekly</v-btn>
      <v-btn value="hourly">Hourly</v-btn>
      <v-btn value="interval">Every N min</v-btn>
      <v-btn value="custom">Custom</v-btn>
    </v-btn-toggle>

    <component :is="modeComponent" v-model="parts" />

    <v-text-field v-model="rawExpression" label="Cron expression" readonly />
    <p class="text-caption">{{ humanReadable }} ({{ timezone }})</p>
    <p class="text-caption">Next runs: <span v-for="r in nextRuns">{{ formatDateTime(r) }}</span></p>
    <v-alert v-if="!valid" type="error">{{ validationError }}</v-alert>
  </div>
</template>
```

`humanReadable` comes from `cronstrue.toString(rawExpression)`. `nextRuns` from a debounced call to `POST /pipeline/cron/preview`.

### 4.4 Acceptance criteria

- A caregiver picks "Weekly, Mon/Wed/Fri, 9:30 AM" and the stored `schedule_cron` is `30 9 * * 1,3,5`. Snapshot test on the builder's output.
- A pre-existing rule with `*/5 * * * *` loads into "Every 5 min" preset.
- Invalid expression entered in Custom mode shows an inline error and disables the Save button.
- Next-runs preview reflects DST correctly (snapshot test around a DST boundary).

---

## 5. Template + condition unification

### 5.1 Problem

Two reference syntaxes coexist:

- Templates use `{{steps.foo.outputs.bar}}` in any string field that supports substitution. Resolution by [render_template](backend/core/template.py); dotted paths only, no functions, no logic.
- Conditions use bare `steps.foo.outputs.bar == "x"` with [ConditionEvaluator](backend/services/condition_evaluator.py); comparisons, booleans, jq-style queries via JMESPath. ConditionEvaluator *also accepts* `{{ }}` wrappers (and strips them), so the two syntaxes are already half-unified.

This produces three concrete pains:

1. Users guess wrong about which syntax applies where.
2. There is **no validation** for templates; a typo in `{{steps.scene_anaylsis_1.outputs.summary}}` (note the typo) silently leaves the literal in the rendered prompt. The LLM gets garbage.
3. There is no autocomplete in any field.

### 5.2 Goal

- One reference syntax: `{{ expr }}` everywhere. Inside the braces, `expr` is:
  - A path (`steps.foo.outputs.bar`) for substitution.
  - A JMESPath expression (`steps.foo.outputs.detections | length(@)`) for transformations.
  - A condition (`steps.foo.outputs.count > 3 and contains(steps.foo.outputs.label, "person")`) for `condition` steps.
- Server-side validation: given a step's config, identify every template expression, parse it, and either return success or a list of `{field, position, error}` records.
- Client-side autocomplete inside any field marked `supports_template`. Triggered on `{{`. Suggestions come from §1.4's metadata-driven variable list, narrowed by current pipeline labels.
- Existing rules migrated by the §2.4 migration chain at import time and once at deploy time via an Alembic data migration.

### 5.3 Design

#### 5.3.1 Single grammar

Define a tiny grammar with [Lark](https://github.com/lark-parser/lark); well-maintained, pure Python, ~200KB.

```lark
?start: expr
?expr: or_expr
?or_expr: and_expr ("or" and_expr)*
?and_expr: not_expr ("and" not_expr)*
?not_expr: "not" not_expr | comparison
?comparison: term (COMP_OP term)?
?term: STRING | NUMBER | BOOL | NULL | path | call | "(" expr ")"
path: NAME ("." NAME | "." INT)*
call: NAME "(" [expr ("," expr)*] ")"
COMP_OP: "==" | "!=" | ">=" | "<=" | ">" | "<"
NAME: /[a-z_][a-z0-9_]*/i
```

This is intentionally minimal. JMESPath queries (the `jq(...)` form today) become `call`s on a `jq` function. Everything `ConditionEvaluator` accepts today maps cleanly into this grammar; we wrap the existing implementation behind a Lark front-end so we get a real AST.

#### 5.3.2 The unified resolver

`backend/core/template.py` gets a new entrypoint:

```python
def resolve_expression(expr: str, pipeline_data: Mapping[str, Any]) -> Any:
    """Parse and evaluate a single {{ ... }} expression."""

def render_template(template: str, pipeline_data: Mapping[str, Any]) -> str:
    """Replace every {{ expr }} in `template` with str(resolve_expression(expr, ...))."""

def evaluate_condition(expr: str, pipeline_data: Mapping[str, Any]) -> bool:
    """Like resolve_expression but coerces the result to bool with a strict policy."""
```

Backwards compatibility: the existing `render_template` signature is preserved; only the implementation changes. The existing `ConditionEvaluator.evaluate` becomes a thin wrapper around `evaluate_condition`.

#### 5.3.3 Validation

```python
# backend/services/template_validator.py
@dataclass(frozen=True)
class TemplateError:
    field_path: str           # JSON pointer into the step config
    position: tuple[int, int] # (start, end) byte offsets within the field value
    severity: Literal["error", "warning"]
    code: str                 # "unknown_path" | "syntax_error" | "type_mismatch" | "unknown_step_label" | "deprecated_function"
    message: str
    suggestion: str | None = None  # e.g. "Did you mean steps.scene_analysis_1.outputs.summary?"

def validate_step_config(
    step_type: str,
    config: dict,
    rule_context: RuleValidationContext,  # known labels, step output schemas, trigger type
) -> list[TemplateError]: ...
```

`RuleValidationContext` is built from the in-flight rule's labels and each label's resolved `output_schema` (§1.3.1). For unknown labels (typo), we suggest the closest match using `difflib.get_close_matches`.

Where it's called:

- On every `PUT /rules/{id}/steps/{step_id}` and `POST /rules/{id}/steps`; server attaches validation results to the response. The frontend renders them inline. Server does NOT reject the save by default (warnings only) because partial drafts are common during editing. A new `POST /rules/{id}/validate` endpoint runs whole-rule validation for the "Lint" button.
- During rule import (§2); surfaced in the preview report.

#### 5.3.4 Frontend autocomplete

Replace the plain `v-text-field` / `v-textarea` for template-bearing fields with a CodeMirror 6-based component.

- Library: **[CodeMirror 6](https://codemirror.net/)** with `@codemirror/autocomplete`, `@codemirror/lang-javascript` (for tokenization fallback); ~50KB gzipped for our use. License MIT.
- Wrapper: `frontend/src/components/pipeline/_shared/TemplateInput.vue`. Props: `modelValue`, `multiline`, `ruleContext` (labels + output schemas).
- Autocomplete trigger: typing `{{` opens the popup, populated from the same data the StepConfigDialog variable sidebar uses.
- Lint markers: inline red squiggles for validation errors returned by the backend (debounced 400ms). The sidebar listing in StepConfigDialog still shows; the autocomplete is *in-place*.
- Tab order, accessibility: standard CodeMirror semantics; verify with screen reader pass before merge.

We adopt CodeMirror only for `template-textarea` and `template-text` widgets; plain text fields stay on `v-text-field`. Don't load CodeMirror on pages that don't need it (lazy `defineAsyncComponent`).

#### 5.3.5 Migrating the existing `condition` step

The current condition syntax `steps.foo.outputs.bar == "x"` becomes `{{ steps.foo.outputs.bar == "x" }}` after migration. The unified resolver accepts both forms during the migration window (the body of `{{ ... }}` is already a full expression). A `condition` step migration (`schema_version: 1→2`) wraps the bare expression in `{{ ... }}`. Idempotent: re-running on a v2 config is a no-op.

### 5.4 Acceptance criteria

- A pipeline with a typo in `{{steps.scene_anaylsis_1.outputs.summary}}` (typo `anaylsis`) returns a validation error pointing at byte offsets and suggesting the correct label. Integration test.
- A condition step with `count > 3` (pre-migration) and one with `{{ count > 3 }}` (post-migration) evaluate identically. Snapshot test.
- Typing `{{` in the LLM call prompt field opens autocomplete listing `trigger.*`, `system.*`, `steps.<known-label>.outputs.*`. Playwright/integration test.
- Performance: validation runs server-side in < 50ms for a 20-step rule (no LLM calls, just AST walks). Load test.

---

## 6. AI agent surface (MCP)

### 6.1 Problem

We want AI agents (Claude, Gemini, others via MCP) to be able to read existing rules, propose new ones, and create them. Today's MCP server (`backend/mcp/`) exposes read-only tools; rule authoring is human-only.

### 6.2 Goal

Three new MCP tools, gated by a new permission `rules:write_via_mcp`:

- `list_rules`; return rule summaries (name, description, enabled, trigger_type).
- `get_rule_bundle`; return the §2 export bundle for a rule, for the agent to read or template-modify.
- `import_rule_bundle`; accept an export bundle (the same wire format from §2.3) and either preview or commit, returning the same migration/warning report the UI shows.

Plus an introspection tool:

- `list_plugin_metadata`; returns the full `StepMetadata`/`FilterMetadata`/`ChannelMetadata` for every registered plugin including `config_schema`, `default_config`, `output_schema`, `ui_hints`. This is what lets an agent author a syntactically valid rule without round-tripping to the docs.

### 6.3 Design

#### 6.3.1 Tool surface

Each tool is a FastMCP `@mcp.tool()` function in `backend/mcp/tools/rules.py`. Signatures use Pydantic models for typed input/output; FastMCP serializes them to MCP-flavored JSONSchema, which is the very thing agents consume.

```python
@mcp.tool()
async def list_plugin_metadata(
    kind: Literal["step", "filter", "channel"] | None = None,
) -> list[StepMetadata | FilterMetadata | ChannelMetadata]:
    """List every registered plugin's metadata for rule authoring."""

@mcp.tool()
async def import_rule_bundle(
    bundle: RuleBundle,                # the §2.3 Pydantic model
    mode: Literal["preview", "commit"] = "preview",
    reference_overrides: dict[str, str] | None = None,
) -> ImportReport:
    """Validate and optionally commit a rule bundle. Returns the same report the UI shows."""
```

Because `RuleBundle` is the **same Pydantic model** the HTTP endpoints use, the MCP tool is free of the "two parallel schemas" trap.

#### 6.3.2 Auth

MCP tools already flow through `backend/mcp/middleware.py`. Add `rules:write_via_mcp` to `auth.yaml` and require it on the import tool. Keep it distinct from `rules:write` so admins can grant agents authoring rights without giving them full HTTP write access (least privilege).

#### 6.3.3 Discoverability

The agent's typical loop:

1. `list_plugin_metadata(kind="step")` → learns what's available.
2. Reads `config_schema` + `output_schema` to plan a pipeline.
3. Constructs a `RuleBundle` literal.
4. `import_rule_bundle(bundle, mode="preview")` → checks warnings/migrations.
5. If clean, `import_rule_bundle(bundle, mode="commit")`.

The §1.3.5 contract tests ensure the metadata an agent sees is internally consistent; bad schemas can't be merged.

### 6.4 Acceptance criteria

- An agent given only the MCP tool list and no other context can construct and import a valid 3-step rule (manual test with Claude Sonnet via SDK).
- Permission denied for an MCP client without `rules:write_via_mcp`. Integration test.
- The bundle that an agent submits must round-trip with `export_rule` to produce a byte-identical (or canonically equivalent) bundle. Property-style test.

---

## 7. Cross-cutting: testing, telemetry, rollout

### 7.1 Testing strategy

- **Contract tests** (§1.3.5) gate every plugin registration. Run as part of `make check`.
- **Migration tests**: every `ConfigMigration` has a unit test with a v(N) input and a v(N+1) expected output. Frozen test fixtures in `backend/tests/fixtures/rule_bundles/`.
- **Property tests**: use [Hypothesis](https://hypothesis.readthedocs.io/) for the template grammar; generate random valid expressions, parse them, evaluate them, assert no exceptions. Add to `make test-core`.
- **Frontend e2e**: Playwright covers the cron-builder round-trip and the autocomplete trigger. Already-existing Playwright suite gets new specs under `frontend/tests/e2e/pipeline/`.
- **Performance**: a 50-step rule must validate in < 100ms server-side; assert in CI with a perf-budget test.
- **No mocked DB**: use the existing testcontainer fixtures per [CLAUDE.md](CLAUDE.md) testing patterns.

### 7.2 Telemetry

- Log every import attempt with `bundle_schema_version`, step migration counts, warnings count. Helps us decide when to deprecate old migration paths.
- Log every cron preview call (`expression` hashed, not raw). Helps us see which presets people use.
- Log every template validation result count (`errors`, `warnings`, `0`). Helps us tune autocomplete coverage.

### 7.3 Rollout sequence

Suggested PR sequence; each lands behind a feature flag where it changes user-visible behavior:

1. **§1.3.1 + §1.3.5**: enrich metadata, add contract tests. No user-visible change.
2. **§2**: import/export. New endpoints; UI button gated by `rules:export`.
3. **§4**: cron builder. UI-only; backend cron-preview endpoint trivial.
4. **§5.3.1–§5.3.3**: unified resolver + validator, server-side only. ConditionEvaluator wraps the new path. Migration runs in Alembic data migration.
5. **§5.3.4**: CodeMirror autocomplete. Behind `features.template_autocomplete` flag for a week of dogfood.
6. **§3**: cancel/rerun + ExecutionDetail unification. Cancel and rerun ship together; ExecutionDetail can ship later as pure UI.
7. **§1.3.6 + §1.4**: scaffolding CLI + dynamic variable reference. Optional polish, no user dependency.
8. **§6**: MCP tools. Separate permission grant; safe to ship last.

### 7.4 Risk register

| Risk | Mitigation |
| --- | --- |
| Migration chain bugs corrupt configs on import. | All migrations are pure functions with unit tests; preview-mode is the default. |
| New Lark grammar regresses ConditionEvaluator behavior. | Run the existing ConditionEvaluator test suite against the new resolver as a parallel oracle for one release. |
| CodeMirror bundle bloat. | Lazy-load only on the rule edit page; measure before/after. |
| Cooperative cancellation doesn't kill stuck `llm_call`s. | Documented limitation; v2 token-based cancellation in a follow-up. |
| Agents author rules that drift from human conventions (bad labels, no descriptions). | The contract tests + a server-side linter (the same §5 validator) catch most. Add an explicit "agent-authored" provenance flag for triage. |

### 7.5 What this plan deliberately does not do

- Does not introduce a visual node-graph editor (yet). The current linear timeline + branch step is sufficient. Revisit after import/export usage data.
- Does not add a "rule marketplace" feature. Export produces a file; sharing happens via existing community channels (GitHub, Discord). A central registry is a separate, much larger project.
- Does not unify `condition` with the more general `verification` step. Keep them distinct; they're semantically different.
- Does not refactor pipeline_data into a typed object. The MutableDict-JSON approach works and the cost of refactor is high.

---

## 8. Open questions for review

1. **YAML vs JSON for export**: dual support adds ~20 LOC and helps human review. Worth it? (Recommend yes.)
2. **`rules:write_via_mcp` permission split**: necessary, or just gate MCP under existing `rules:write`? (Recommend split; least privilege.)
3. **Cron timezone on import**: silently keep source tz, or always remap to destination tz with a prompt? (Recommend prompt; surprises in scheduling are expensive.)
4. **Template grammar surface**: do we expose JMESPath functions (`length`, `keys`, `map`) by default, or whitelist a handful? (Recommend whitelist of: `length`, `contains`, `icontains`, `lower`, `upper`, `keys`, `values`. Easy to expand later.)
5. **`output_schema` enforcement**: do we *validate* step outputs against `output_schema` at runtime, or only use the schema for tooling? (Recommend tooling-only in v1; runtime validation is opt-in via a settings flag.)

---

## 9. Library inventory

| Area | Library | License | Bundle/size | Why |
| --- | --- | --- | --- | --- |
| YAML I/O | PyYAML or ruamel.yaml | MIT | n/a | Standard, no surprises. |
| Cron next-run | croniter | MIT | n/a | Already transitively present via APScheduler. |
| Cron description (FE) | cronstrue | MIT | 30KB | Mature, i18n-ready. |
| JSONSchema validation | jsonschema | MIT | n/a | Already in dep tree via FastAPI/Pydantic ecosystem. |
| Expression grammar | Lark | MIT | 200KB pure-Python | Cleaner than handwritten parser combinators. |
| Property tests | Hypothesis | MPL-2.0 | n/a | Best-in-class for grammar/migration testing. |
| FE template editor | CodeMirror 6 | MIT | 50KB gz | Standard for in-app code editing. |
| FE JSON viewer | vue-json-pretty | MIT | 15KB gz | Read-only, no Vuetify lock-in. |
| FE diff (optional) | jsondiff (Python) | MIT | n/a | Nicer import-preview diffs. |

No new transitive dependencies of concern; all are well-maintained, MIT/MPL-licensed, with mature release histories.
