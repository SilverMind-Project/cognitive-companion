# Pipeline Improvements: Review & Revised Plan

## Context

Pre-production system. All rules, steps, and executions can be wiped. The database can be recreated. The goal is **long-term maintainability, clean contracts, and high engineering standards** -- not backward compatibility with existing data.

This review judges the original plan against that bar, keeps what's good, fixes what's underspecified, and resequences for clean, incremental delivery.

---

## 1. Summary of changes from the original plan

| Concern | Original plan | This revision |
|---------|--------------|---------------|
| Trigger/rule coupling | Not addressed | **Decouple cron triggers from rules.** New `cron_triggers` table + `rule_cron_triggers` join table. A rule can have multiple cron schedules; multiple rules can share a schedule. Eliminates the need for composite cron expressions. |
| Expression grammar | Lark replaces ConditionEvaluator, dual-run for one release | Lark **is** the evaluator. No dual-run. Write once, test exhaustively. |
| JMESPath syntax | `jq("...")` function calls | **Pipe syntax** (`steps.foo.outputs \| length(@)`). Cleaner, standard JMESPath, no nested quote escaping. |
| `output_schema` | Optional, tooling-only in v1 | **Required** for all step types. Runtime-validated in dev/test. |
| Import mode | Lenient partial-import with warnings | **Strict only.** All-or-nothing within a transaction. |
| Template validation | Warnings on save, separate lint endpoint | **Reject on save.** Invalid templates don't persist. |
| Data migration | Alembic data migration for conditions | **No migration needed.** Wipe and recreate. |
| Condition migration | Migration chain rewrites v1->v2 | **No migration needed.** New format only. |
| Rerun | from-step-N with snapshot dependency | V1: from-beginning only. from-step-N is v2. |
| Cron parsing | "Roll our own thin parser" on frontend | Backend returns parsed structure. Frontend is a renderer. |
| `StepMetadata` fields | All new fields optional | `output_schema` is **required** for steps that emit data. `schema_version` added to filters and channels too. `ui_hints_version` added. Others stay optional. |
| Config validation | Handler accesses raw config dict | Executor validates config against `config_schema` before calling `execute`. |

---

## 2. New: Trigger/rule decoupling

### 2.0 Problem

The current `Rule` model has a single `trigger_type` column. A rule is either cron-triggered OR sensor-event-triggered, never both. Cron rules bypass `RulesEngine` entirely -- the Scheduler creates one APScheduler job per rule that calls `execute_periodic_rule()` directly. This creates three problems:

1. **A rule can't respond to multiple trigger sources.** "Run fall detection on every bathroom camera event AND also every 5 minutes as a safety net" is impossible.
2. **A rule can't have multiple cron schedules.** The cron builder needs composite expressions to handle "9:30 AM Mon/Wed/Fri AND 6:00 PM daily" -- and composite cron isn't a real standard.
3. **Cron rules bypass context filters.** `execute_periodic_rule()` calls `PipelineExecutor.execute()` directly. It never goes through `RulesEngine.get_matching_rules()`, so context filters (`time_range`, `day_of_week`, `person_presence`) are not evaluated for cron-triggered executions. If a caregiver sets a time_range context on a cron rule, it's silently ignored.

### 2.0.1 Design

Decouple cron schedules from rules with a proper normalized schema:

```
rules ──< rule_cron_triggers >── cron_triggers
```

```python
# backend/models/cron_trigger.py
class CronTrigger(Base, TimestampMixin):
    __tablename__ = "cron_triggers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256))  # "Weekday mornings"
    expression: Mapped[str] = mapped_column(String(128))  # "30 9 * * 1-5"
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class RuleCronTrigger(Base):
    __tablename__ = "rule_cron_triggers"
    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id"))
    cron_trigger_id: Mapped[int] = mapped_column(ForeignKey("cron_triggers.id"))
```

**Why only cron, not all trigger types:**

| Trigger type | Decouple? | Reason |
|---|---|---|
| `sensor_event` | No | Already many-to-many via `RulesEngine.get_matching_rules()`. One sensor event fans out to all matching rules. |
| `occupancy_duration` | No | Same as sensor_event -- dispatched through RulesEngine. |
| `webhook` | No | 1:1 by design. A webhook URL includes rule_id. This is a security boundary, not a limitation. |
| `telegram` | No | 1:1 by design. Commands map to specific rules. |
| `manual` | No | 1:1 by design. `POST /rules/{id}/execute`. |
| **`cron`** | **Yes** | Currently 1:1. Benefits from many-to-many: multiple schedules per rule, shared schedules across rules. |

**How this changes the Rule model:**

Remove from `Rule`:
- `trigger_type` (the `cron` value is replaced by the join table)
- `schedule_cron`
- `primary_sensor_id` (moves to individual steps that need it, or stays as a per-rule fallback)

Add to `Rule`:
- `cron_triggers: Mapped[list[CronTrigger]]` (via `rule_cron_triggers`)

`trigger_type` becomes a **derived property**: a rule with cron triggers is cron-triggered. A rule with `webhook_config` is webhook-triggered. A rule with neither is sensor-event-triggered (the default). A rule can be multiple of these.

**How this changes the Scheduler:**

The Scheduler creates one APScheduler job per `CronTrigger` (not per rule). When the job fires:
1. Query `rule_cron_triggers` for all rules associated with this cron trigger.
2. For each rule, call `RulesEngine.get_matching_rules_for_cron(rule, db)` which evaluates context filters and dependencies.
3. Execute matching rules through `PipelineExecutor`.

Cron rules now go through `RulesEngine` like everything else. Context filters work. Dependencies work. Rate limits work.

**How this changes the UI:**

- Rule detail view gets a "Cron Schedules" section: a list of cron trigger chips with add/remove.
- Add button opens a dialog with the `CronBuilder` component (phase 3).
- Existing cron triggers can be selected from a dropdown (reuse across rules) or created inline.
- The `trigger_type` dropdown is removed. Trigger capability is inferred from what's configured.

This is scoped as **Phase 0** in the revised plan because it changes the Rule model that all other phases depend on.

---

## 3. Design review: what stays, what changes

### 3.1 Plugin authoring ergonomics (§1)

**Kept as-is:**
- `x-ui` hint dialect on `config_schema`. This is the right abstraction.
- `SchemaForm.vue` as a generic renderer fallback. Custom components override it.
- Eliminating `pipelineDataReference` in favor of backend-computed data.
- Scaffolding CLI.

**Changed: `output_schema` is mandatory for data-emitting steps.**

Every step that produces data (all except `wait` and `condition`) MUST declare an `output_schema`. The contract test in `test_registry_contract.py` enforces this at CI time. In dev mode (`settings.app.dev_mode: true`), the executor validates step outputs against the schema at runtime and logs a warning on mismatch.

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

    # New -- optional with defaults
    schema_version: int = 1
    ui_hints_version: int = 1
    ui_hints: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)  # REQUIRED for data-emitting steps
    tags: tuple[str, ...] = ()
```

`output_schema` uses a subset of JSONSchema:
```python
output_schema = {
    "type": "object",
    "properties": {
        "person_name": {"type": "string", "description": "Identified person name"},
        "confidence": {"type": "number", "description": "Detection confidence 0-1"},
    },
    "required": ["person_name"],
}
```

This feeds three consumers:
1. **Contract test** verifies the step emits what it declares.
2. **`GET /pipeline/data-keys`** builds the variable reference for autocomplete.
3. **Dev-mode runtime check** catches drift during development.

**Added: `ui_hints_version` for forward-compatible UI rendering.**

If a future backend adds a new widget type (`color-picker`, `date-range`) or renames a hint property, an old frontend shouldn't crash. The `ui_hints_version` field (integer, starting at 1) lets the frontend check `meta.ui_hints_version <= FRONTEND_SUPPORTED_VERSION` and fall back to `GenericPluginConfig` for unknown versions. The version is incremented in `StepMetadata` when the set of recognized `x-ui.widget` values or their property shapes change. The `SchemaForm.vue` renderer declares its supported version as a constant.

**Changed: Config is validated before `execute`.**

The executor calls `validate_config(config, handler.metadata().config_schema)` before invoking the handler. If validation fails, the step is marked `failed` with a clear error. Handlers receive a known-valid config dict and can skip defensive `config.get("key", default)` for required fields -- the schema already guarantees they're present.

Implementation in `PipelineExecutor._execute_step`:
```python
async def _execute_step(self, step, execution, pipeline_data, trigger):
    handler = StepRegistry.get(step.step_type)
    if not handler:
        return StepResult(success=False, should_continue=False)

    meta = handler.metadata()
    config = step.config_json or {}
    try:
        jsonschema.validate(config, meta.config_schema)
    except jsonschema.ValidationError as e:
        logger.error("step_config_invalid", step_type=step.step_type, error=str(e))
        return StepResult(success=False, should_continue=False,
                          data={"error": f"Config validation failed: {e.message}"})

    return await handler.execute(step, execution, pipeline_data, trigger, self._services)
```

---

### 3.2 Rule import/export (§2)

**Kept as-is:**
- Label-based cross-references (no DB ids).
- Two version planes (bundle `schema_version` + per-step `schema_version`).
- YAML + JSON dual format. YAML for humans, JSON for agents.
- `references` block for external entity remapping.
- Cron timezone capture on export.
- Frontend import flow (dropzone -> preview -> confirm).

**Changed: Strict-only import. No lenient mode.**

If any step fails migration, any reference is unresolvable, or any config fails validation against the target step's `config_schema`, the entire import rolls back. The preview endpoint shows every issue; the user fixes them before committing.

**Changed: `ConfigMigration` is forward-looking infrastructure.**

Even though we're wiping existing data, the migration chain is still built into the plugin contract now. It costs ~20 lines of infrastructure code and prevents a future flag day when the first real migration is needed. Each handler declares an empty `migrations=()` by default.

```python
@dataclass(frozen=True)
class ConfigMigration:
    from_version: int
    to_version: int
    description: str
    apply: Callable[[dict], dict]  # pure function

def migrate_config(config: dict, migrations: tuple[ConfigMigration, ...],
                   from_version: int, to_version: int) -> dict:
    """Apply migration chain. Raises ValueError if path is incomplete."""
    current = from_version
    result = dict(config)
    migration_map = {(m.from_version, m.to_version): m for m in migrations}
    while current < to_version:
        key = (current, current + 1)
        if key not in migration_map:
            raise ValueError(f"No migration from v{current} to v{current+1}")
        result = migration_map[key].apply(result)
        current += 1
    return result
```

**Changed: Import bundle `min_app_version` is computed, not declared.**

The exporter computes `min_app_version` by taking the max of the current app version and any version that introduced a step type used in the bundle. This is checked on import; if the target install is older, the preview shows a clear "This bundle needs CC v0.43.0+ (you have v0.42.0)" message.

---

### 3.3 Execution lifecycle (§3)

**Kept as-is:**
- Cooperative cancellation (check DB status between steps).
- Cancel endpoint with pessimistic lock.
- ExecutionDetail as a shared component for live + historical.

**Changed: Backend computes an `ExecutionDetailOut` view model.**

The frontend must not know about `pipeline_data` internals (`_step_timings`, `_pipeline`, `steps.<label>.outputs`). The backend computes a typed view model:

```python
class StepTimelineEntry(BaseModel):
    label: str
    step_type: str
    icon: str
    category: str
    status: Literal["success", "failed", "skipped", "in_progress", "cancelled"]
    elapsed_seconds: float | None
    resolved_config: dict | None     # config after template substitution
    outputs: dict | None             # step result data
    logs: list[str]                  # ring buffer, max 50 lines
    error: str | None
    cancellation_observed: bool

class ExecutionDetailOut(BaseModel):
    id: int
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    rule_name: str
    trigger_type: str
    trigger_summary: str             # "Cron (every 5 min)" or "Sensor: bathroom_cam"
    timeline: list[StepTimelineEntry]
    cooloff_triggered: bool
    error: str | None
    can_cancel: bool
    can_rerun: bool
```

`GET /workflows/{id}/detail` returns this. The frontend `ExecutionDetail.vue` is a pure renderer of this model. The live run WebSocket (when added) pushes partial `ExecutionDetailOut` updates.

**Changed: Rerun v1 is from-beginning only.**

`POST /workflows/{id}/rerun` copies the original `TriggerContext` and re-executes all enabled steps. No from-step-N, no snapshot dependency. This covers the primary use case (re-test a rule after fixing its config) without the complexity of partial replay. from-step-N is a v2 feature that stores per-step pipeline_data snapshots.

**Added: Per-step timeout.**

If a step exceeds `execution_timeout_minutes / max(len(steps), 1)`, the executor marks it failed and continues. This prevents a single stuck LLM call from consuming the entire pipeline timeout. The step's `StepTimelineEntry` records `error: "Step timed out after 30s"`.

---

### 3.4 Cron builder (§4)

**Kept as-is:**
- Preset modes (daily, weekly, hourly, interval, custom).
- `croniter` backend, `cronstrue` frontend.
- Live "next 5 runs" preview.
- Timezone surfaced in the UI.

**Changed: Backend returns parsed cron structure. No frontend parser.**

`POST /pipeline/cron/preview` response gains a `parsed` field:
```json
{
  "valid": true,
  "next_runs": ["2026-05-12T09:30:00-07:00", ...],
  "parsed": {
    "minute": [30],
    "hour": [9],
    "day_of_month": ["*"],
    "month": ["*"],
    "day_of_week": [1, 3, 5]
  },
  "preset": "weekly",
  "description": "At 09:30 AM, every Monday, Wednesday, Friday"
}
```

The frontend builder reads `parsed` to determine which preset mode to show. If the expression doesn't fit any preset, it falls back to Custom mode. No parsing logic on the client.

**Added: DST safety test in CI.**

A snapshot test around a known DST boundary (e.g., `America/New_York` spring-forward 2026-03-08) asserts that "every day at 9:30 AM" produces correct next-run timestamps on both sides of the transition.

---

### 3.5 Template + condition unification (§5)

This is the most consequential change. The original plan was conservative (dual-run, lazy migration). Since we can wipe data, we can do this cleanly.

**Changed: Lark grammar IS the evaluator. No dual-run. No legacy ConditionEvaluator.**

`backend/core/template.py` is rewritten around a Lark parser. Three public functions:

```python
def parse_expression(expr: str) -> ASTNode:
    """Parse a {{ }} expression into an AST. Raises TemplateSyntaxError on failure."""

def evaluate_expression(expr: str, pipeline_data: Mapping[str, Any]) -> Any:
    """Parse and evaluate. Returns the expression's value."""

def evaluate_condition(expr: str, pipeline_data: Mapping[str, Any]) -> bool:
    """Evaluate and coerce to bool. Raises TemplateTypeError if not boolean."""

def render_template(template: str, pipeline_data: Mapping[str, Any]) -> str:
    """Replace every {{ expr }} with str(evaluate_expression(expr, ...))."""
```

The grammar covers:
- Path access: `steps.foo.outputs.bar`, `trigger.sensor_id`, `system.local_time`
- List indexing: `steps.foo.outputs.detections.0.label`
- JMESPath: `steps.foo.outputs.detections | length(@)`
- Comparisons: `==`, `!=`, `>`, `<`, `>=`, `<=`
- Boolean: `and`, `or`, `not`
- Functions: `contains()`, `icontains()`, `length()`, `lower()`, `upper()`, `keys()`, `values()`, `exists()`
- Literals: numbers, `true`, `false`, `null`, quoted strings
- Parenthesized sub-expressions

Old bare expressions (no `{{ }}`) are NOT supported. Every expression lives inside `{{ }}`. The old `condition` syntax (`steps.foo.outputs.bar == "x"` without braces) is gone.

**Why Lark over the existing recursive-descent parser:**
1. The existing `ConditionEvaluator` is 323 lines of tokenizer + parser + evaluator all interleaved. Adding new features (new functions, better error messages with positions, type checking) requires touching all three layers.
2. Lark separates grammar from interpreter. Adding a function is one line in the grammar + one method on the interpreter. Adding a comparison operator is one line in the grammar.
3. Lark gives us real parse errors with line/column positions. The existing evaluator returns `False` on parse failure and logs a warning -- silent failures are the worst kind.
4. Lark's AST can be walked for validation (does this path exist?) and autocomplete (what paths are valid at this cursor position?). The existing evaluator can't do either.

**Grammar file** (`backend/core/template_grammar.lark`):

```lark
?start: expr
?expr: or_expr
?or_expr: and_expr ("or" and_expr)*
?and_expr: not_expr ("and" not_expr)*
?not_expr: "not" not_expr -> not_op | comparison
?comparison: term (COMP_OP term)?
?term: STRING -> string
     | NUMBER -> number
     | BOOL -> boolean
     | NULL -> null
     | path -> path
     | func_call -> func_call
     | jmespath_expr -> jmespath_expr
     | "(" expr ")"

path: NAME ("." (NAME | INT))* ("|" jmespath_expr)?

func_call: NAME "(" [expr ("," expr)*] ")"

jmespath_expr: "|" /[^|}]+/  // raw JMESPath after pipe, captured as literal

COMP_OP: "==" | "!=" | ">=" | "<=" | ">" | "<"
NAME: /[a-zA-Z_][a-zA-Z0-9_]*/
INT: /[0-9]+/
STRING: /"[^"]*"/ | /'[^']*'/
NUMBER: /-?\d+(?:\.\d+)?/
BOOL: "true" | "false"
NULL: "null"

%import common.WS
%ignore WS
```

**Interpreter** (`backend/core/template_interpreter.py`):

Walks the Lark parse tree. `path` nodes resolve via the existing `resolve_path` logic (which is battle-tested and stays). `func_call` nodes dispatch to registered functions. `jmespath_expr` nodes use the existing `jmespath.search` call. `COMP_OP` nodes use the existing `_compare` logic.

This is ~150 lines of interpreter code, plus the grammar file. The existing `ConditionEvaluator` is 323 lines and deleted. Net reduction in code.

**Template validation on save:**

`PUT /rules/{id}/steps/{step_id}` validates every template-bearing field in the step config:
1. Extract all `{{ }}` expressions from every string field marked `x-ui.supports_template: true`.
2. Parse each expression with Lark.
3. For `path` nodes, verify the path resolves against the rule's known labels and their `output_schema`.
4. Return a list of `TemplateError` with byte offsets.

The server REJECTS the save if any expression has parse errors or references unknown paths. The frontend renders errors inline. No silent failures.

**`condition` step change:**

The `condition` step's `expression` field now requires `{{ }}` wrapping. The schema is:
```python
config_schema = {
    "type": "object",
    "required": ["expression"],
    "properties": {
        "expression": {
            "type": "string",
            "x-ui": {"widget": "template-textarea", "rows": 3, "supports_template": True},
        },
    },
}
```

Example: `{{ steps.scene_1.outputs.count > 3 and contains(steps.scene_1.outputs.label, "person") }}`

The `{{ }}` wrapping is what triggers autocomplete and validation. The grammar inside the braces is the same grammar used everywhere.

---

### 3.6 AI agent surface (§6)

**Kept as-is:**
- MCP tools: `list_rules`, `get_rule_bundle`, `import_rule_bundle`, `list_plugin_metadata`.
- Same Pydantic models as HTTP endpoints.
- `rules:write_via_mcp` as a distinct permission.

**Added: `list_plugin_metadata` includes `output_schema` so agents can reason about data flow between steps.** This is the key insight that lets an agent construct valid pipelines: it can see what each step produces and match it to what downstream steps reference in their templates.

---

## 4. Revised phased implementation plan

Each phase is a self-contained PR. Each phase leaves the system in a releasable state. Phases are ordered by dependency and risk.

### Phase 0: Trigger/rule decoupling (3-4 days)

**Scope:** Decouple cron triggers from rules. This phase comes first because it changes the `Rule` model that all other phases depend on.

**PR 0a: CronTrigger + RuleCronTrigger models + Alembic migration**
- New `backend/models/cron_trigger.py`: `CronTrigger` and `RuleCronTrigger` ORM models.
- `make migration` to autogenerate the schema change.
- Remove `trigger_type`, `schedule_cron` from `Rule` (or deprecate with a comment; the column gets dropped after data wipe).
- Add `cron_triggers` relationship to `Rule`.
- Update `backend/schemas/rule.py`: `RuleCreate`/`RuleUpdate` now accept `cron_trigger_ids: list[int]` instead of `schedule_cron: str | None`.

**PR 0b: Refactor RulesEngine for cron dispatch**
- Add `RulesEngine.get_matching_rules_for_cron(rule, db)` that evaluates contexts and dependencies for a single rule.
- Cron-triggered rules now go through `RulesEngine` like sensor events. Context filters work. Dependencies work. Rate limits work.
- Update `Scheduler._load_rule_jobs()`: create one APScheduler job per `CronTrigger`, not per rule. The callback queries `rule_cron_triggers`, finds associated rules, calls `RulesEngine`, executes each match.

**PR 0c: Update trigger sources**
- `WorkflowPipeline.process_event()`: remove the `trigger_type` filter from the query, or keep it but add `cron` as a valid type.
- `POST /webhooks/{rule_id}`: remove `rule.trigger_type == "webhook"` check. Any rule with a `webhook_config` is webhook-triggered.
- `TelegramTriggerService`: same pattern. Any rule with a `telegram_trigger_config` is telegram-triggered.
- `POST /rules/{id}/execute`: works for any rule. No `trigger_type == "manual"` check needed.

**PR 0d: Frontend trigger UI**
- Remove the `trigger_type` dropdown from `RuleDetailView.vue`.
- Add a "Cron Schedules" section: list of cron trigger chips with add/remove.
- Add button opens a dialog with the `CronBuilder` component (built in phase 3). For Phase 0, a simple text field for cron expression + timezone selector.
- Webhook and Telegram config sections remain on the rule form; they're independent of cron.

**Gate:** A rule with two cron triggers fires from both schedules. A rule with a cron trigger AND a webhook config fires from both. Cron-triggered rules respect context filters. `make check` passes.

---

### Phase 1: Enriched metadata + contract tests (2-3 days)

**Scope:** Extend `StepMetadata` with the new fields. Add contract tests. No behavior change.

**PR 1a: StepMetadata + FilterMetadata + ChannelMetadata contract tests**
- Add `schema_version`, `ui_hints_version`, `ui_hints`, `output_schema`, `tags` to `StepMetadata`.
- Add `schema_version` to `FilterMetadata` and `ChannelMetadata` (same migration-chain infrastructure applies).
- Every existing step handler declares its `output_schema` based on what it currently emits (read the `StepResult.data` construction in each handler).
- Add `backend/tests/steps/test_registry_contract.py` (and mirror for filters/channels):
  - Every `config_schema` is valid JSONSchema.
  - Every `default_config` validates against `config_schema`.
  - Every `output_schema` is valid JSONSchema.
  - Every data-emitting step has a non-empty `output_schema`.
  - `type_name` matches `^[a-z][a-z0-9_]*$`.
  - `icon` starts with `mdi-`.
  - `category` is from the known set.
- Add `backend/steps/_testing.py` with `assert_output_conforms_to_schema()`.
- Update existing step tests to call the assertion.

**PR 1b: Backend metadata endpoint enrichment**
- Extend `GET /pipeline/step-types` to emit `ui_hints`, `output_schema`, `tags`, `schema_version`.
- Same for `/pipeline/channel-types`, `/pipeline/filter-types`.
- New `GET /pipeline/data-keys` returns the complete variable reference (trigger vars, system vars, per-step output schemas).
- Same for filters and channels.

**Gate:** `make check` passes. All existing tests pass. Contract test runs in CI.

---

### Phase 2: Import/Export (3-4 days)

**Scope:** Self-contained rule bundles. New endpoints. Frontend import/export UI.

**PR 2a: `RuleBundle` Pydantic models**
- `backend/schemas/rule_bundle.py`: `RuleBundle`, `StepBundle`, `ContextBundle`, `ReferenceBlock`, `ExportMetadata`.
- `backend/services/rule_serializer.py`: pure functions to serialize/deserialize between `Rule` + SQLAlchemy objects and `RuleBundle`.
- Unit tests with frozen fixtures.

**PR 2b: Export endpoint**
- `GET /rules/{id}/export`. Accept header drives YAML or JSON.
- Permission: `rules:read` (reuse existing).

**PR 2c: Import endpoints**
- `POST /rules/import/preview`: validates + returns `ImportReport` without writing.
- `POST /rules/import`: commits within a single transaction. All-or-nothing.
- Permission: `rules:write` (reuse existing).
- `ImportReport` includes: per-step migration status, unknown references, validation errors, `min_app_version` check.

**PR 2d: ConfigMigration infrastructure**
- `backend/core/plugin_migrations.py`: `ConfigMigration` dataclass + `migrate_config()` pure function.
- Plumbed into the import path. All existing handlers ship with `migrations=()`.
- Unit tests for the migration runner (happy path, missing migration, vN->vN+2 gap).

**PR 2e: Frontend export button + import flow**
- Export button on rule detail toolbar. Downloads `<name>.cc-rule.yaml`.
- Import dropzone on rules list page -> preview modal -> confirm -> commit.
- Conflict resolution: name collision -> rename/replace/skip prompt.

**Gate:** Round-trip test: export from a testcontainer, import into another testcontainer, assert `POST /rules/{id}/execute` produces identical execution results.

---

### Phase 3: Cron Builder (2-3 days)

**Scope:** New CronBuilder component. Backend cron-preview endpoint. No dependency on other phases.

**PR 3a: Backend cron preview endpoint**
- `POST /pipeline/cron/preview`: `{expression, timezone?, count?}` -> `{valid, error, next_runs, parsed, preset, description}`.
- Uses `croniter` (already in dep tree via APScheduler).
- Parsed structure enables the frontend to select the right preset mode.

**PR 3b: Frontend CronBuilder**
- New `CronBuilder.vue`. Five modes: Daily, Weekly, Hourly, Interval, Custom.
- Uses `cronstrue` (npm, MIT, 30KB) for human-readable description.
- Debounced call to `/pipeline/cron/preview` for next-runs preview.
- Drop-in replacement for the `<v-text-field>` in `RuleDetailView.vue`.
- Raw expression always visible and editable (Custom mode).

**Gate:** Playwright test around a DST boundary. Playwright test: select Weekly Mon/Wed/Fri 9:30 AM, assert stored cron is `30 9 * * 1,3,5`. Load `*/5 * * * *` -> shows "Every 5 min" preset.

---

### Phase 4: Lark grammar + unified template evaluator (4-5 days)

**Scope:** Replace `ConditionEvaluator` with Lark-based evaluator. Add server-side template validation. This is the highest-risk phase; it's also the most important for long-term maintainability.

**PR 4a: Lark grammar + AST**
- `backend/core/template_grammar.lark`: the grammar file.
- `backend/core/template_ast.py`: `parse_expression()`, `ASTNode` types, `TemplateSyntaxError` with position info.
- Property tests with Hypothesis: generate random valid expressions, parse them, verify AST structure invariants.

**PR 4b: Interpreter**
- `backend/core/template_interpreter.py`: walks the Lark AST and evaluates against `pipeline_data`.
- Reuses `resolve_path` logic for path resolution. Reuses `jmespath.search` for JMESPath.
- Reuses `_compare` logic for comparison operators.
- Registers the built-in function whitelist: `contains`, `icontains`, `length`, `lower`, `upper`, `keys`, `values`, `exists`.

**PR 4c: Rewrite `render_template` + `evaluate_condition`**
- `backend/core/template.py` uses Lark for all three public functions.
- Delete `backend/services/condition_evaluator.py` (323 lines).
- Port every test from `test_condition_evaluator.py` to the new evaluator. The test cases are the spec; the implementation changes but the assertions stay identical.
- Add new test cases: parse errors with position, type coercion edge cases, nested function calls, JMESPath pipe syntax.

**PR 4d: Template validator**
- `backend/services/template_validator.py`: `validate_step_config()`.
- Extracts `{{ }}` expressions, parses each, validates paths against known labels + `output_schema`.
- Returns `list[TemplateError]` with field paths, byte offsets, and suggestions.
- Suggestions use `difflib.get_close_matches` for typo correction.

**PR 4e: Enforce on save**
- `PUT /rules/{id}/steps/{step_id}` runs template validation. 422 if errors.
- `POST /rules/{id}/validate` runs whole-rule validation (all steps, all contexts).
- `POST /rules/import` runs validation as part of the preview/commit flow.
- `condition` step config schema updated: `expression` field now expects `{{ }}` wrapping.

**PR 4f: Delete old data, run Alembic to reset**
- Truncate `pipeline_steps`, `rule_contexts`, `rules`, `workflow_executions`, `event_logs`.
- Or recreate the database. This is the clean-slate moment.

**Gate:**
- Every test in the old `test_condition_evaluator.py` passes against the new evaluator.
- Property tests with Hypothesis run 10K random expressions without crashes.
- A rule with a template typo (`steps.scene_anaylsis_1`) is rejected on save with a suggestion.
- `make check` passes.

---

### Phase 5: Execution lifecycle (3-4 days)

**Scope:** Cancel, rerun, ExecutionDetail view model, frontend unification.

**PR 5a: Cancel endpoint + cooperative cancellation**
- Add `POST /workflows/{id}/cancel` (verify existing or create).
- Pessimistic lock, set status `cancelled`, remove scheduled resume job.
- `PipelineExecutor._run_steps` checks `execution.status == "cancelled"` between steps (reload from DB).
- Frontend: cancel button in live run toolbar, `useConfirm()` guard, disabled if not `running` or `waiting`.

**PR 5b: ExecutionDetail view model + endpoint**
- `backend/schemas/workflow.py`: `ExecutionDetailOut`, `StepTimelineEntry`.
- `GET /workflows/{id}/detail` returns the view model.
- Backend computes timeline from `pipeline_data._step_timings` + `pipeline_data.steps.*`.
- Includes `resolved_config` (config after template substitution -- capture this at execution time).

**PR 5c: Capture resolved_config at execution time**
- `PipelineExecutor._run_steps` records `resolved_config` in each `_step_timings[i]` entry.
- `render_template` is called on every string config value before the step executes.
- Add `logs: list[str]` ring buffer (max 50 lines, ~8KB) to `_step_timings[i]`.

**PR 5d: Rerun endpoint (v1: from-beginning only)**
- `POST /workflows/{id}/rerun`. Copies `TriggerContext`, re-executes all steps.
- Optional `initial_pipeline_data` kwarg on `PipelineExecutor.execute()`.
- Frontend: rerun button in execution detail toolbar + live run toolbar.

**PR 5e: Frontend ExecutionDetail component**
- Extract live run rendering into `ExecutionDetail.vue`.
- Single component for live + historical. Takes `ExecutionDetailOut` as prop.
- Layout: step timeline (left) + tabbed detail (right): Inputs, Outputs, Logs, Raw.
- Raw JSON tab preserved as escape hatch.
- Per-step timeout handling (mark step as failed, continue pipeline).

**Gate:**
- Cancel a pipeline at step 3: steps 1-3 have timings, step 4+ absent, status `cancelled`.
- Rerun an execution: new execution's trigger matches original.
- ExecutionDetail renders both a live and historical execution from the same component.

---

### Phase 6: Frontend autocomplete + SchemaForm (3-4 days)

**Scope:** SchemaForm generic renderer, CodeMirror 6 autocomplete, eliminate `pipelineDataReference`, scaffolding CLI.

**PR 6a: SchemaForm generic renderer**
- New `SchemaForm.vue`. Walks `config_schema.properties`, dispatches on `x-ui.widget`.
- Widget v1 set: `text`, `textarea`, `template-textarea`, `template-text`, `number`, `slider`, `checkbox`, `select`, `multiselect`, `chips`, `code-json`, `cron`, `time-of-day`, `step-label-ref`.
- Unknown widgets fall back to `GenericPluginConfig` (today's JSON editor).
- `stepConfigMap` gets `genericPluginConfig` as default. All existing custom component entries stay; they take precedence.
- **No existing Vue component changes.**

**PR 6b: TemplateInput with CodeMirror 6**
- New `TemplateInput.vue`. Lazy-loaded (`defineAsyncComponent`).
- Uses `@codemirror/autocomplete` for the autocomplete popup.
- Trigger: typing `{{` opens suggestions. Source: `GET /pipeline/data-keys` narrowed by current pipeline labels.
- Inline lint markers: red squiggles from debounced validation (400ms).
- Plain text fields without `x-ui.supports_template` stay on `v-text-field`.

**PR 6c: Eliminate `pipelineDataReference`**
- Delete the 38-entry static array from `StepConfigDialog.vue:238-275`.
- Replace with computed data from `GET /pipeline/data-keys` + per-step `output_schema`.
- Snapshot test confirms identical or larger variable list.

**PR 6d: Scaffolding CLI**
- `python -m backend.steps.scaffold new my_step --category perception`.
- Generates: handler file, test file (failing, TDD-ready), updates `test_registry_contract.py`.
- Uses stdlib `string.Template`. ~80 LOC.

**Gate:**
- A new step type with a single `int` field renders in the frontend with zero frontend edits.
- `pipelineDataReference` is gone from `StepConfigDialog.vue`.
- Typing `{{` in an LLM call prompt opens autocomplete with correct suggestions.

---

### Phase 7: MCP agent tools (2-3 days)

**Scope:** MCP tools for rule authoring by AI agents.

**PR 7a: MCP rule tools**
- `list_rules`: rule summaries (name, description, enabled, trigger_type).
- `get_rule_bundle`: export bundle for a rule.
- `import_rule_bundle`: accept a bundle, return `ImportReport`. Preview or commit.
- `list_plugin_metadata`: all registered plugins with full metadata including `config_schema` and `output_schema`.
- Same Pydantic models as HTTP endpoints (no parallel schema trap).
- Permission: `rules:write_via_mcp` (distinct from `rules:write`).

**Gate:**
- Agent with only MCP tools constructs and imports a valid 3-step rule.
- Permission denied without `rules:write_via_mcp`.
- Export after import produces canonically equivalent bundle.

---

## 5. Testing strategy

### 5.1 Per-phase test requirements

| Phase | New test files | Type |
|-------|---------------|------|
| 0 | `test_cron_trigger.py`, `test_rules_engine_cron.py`, updates to scheduler tests | Unit + integration |
| 1 | `test_registry_contract.py`, updates to all step/filter/channel test files | Contract + unit |
| 2 | `test_rule_serializer.py`, `test_plugin_migrations.py`, `test_rule_import.py`, `test_rule_export.py` | Unit + integration |
| 3 | `test_cron_preview.py`, Playwright `cron-builder.spec.js` | Unit + e2e |
| 4 | `test_template_grammar.py`, `test_template_interpreter.py`, `test_template_validator.py`, Hypothesis property tests | Unit + property |
| 5 | `test_execution_cancel.py`, `test_execution_rerun.py`, `test_execution_detail.py` | Unit + integration |
| 6 | Playwright `autocomplete.spec.js`, snapshot test for variable reference | e2e + snapshot |
| 7 | `test_mcp_rules.py` | Integration |

### 5.2 Property tests with Hypothesis

Used in phase 4 for the expression grammar:

```python
from hypothesis import given, strategies as st

expression_atom = st.one_of(
    st.integers().map(str),
    st.floats().map(str),
    st.just("true"), st.just("false"), st.just("null"),
    st.text(min_size=1, max_size=20).map(lambda s: f'"{s}"'),
    st.text(min_size=1, max_size=20).map(lambda s: f"'{s}'"),
    st.builds(lambda parts: ".".join(parts),
              st.lists(st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]*"), min_size=1, max_size=4)),
)

@given(expression_atom)
def test_any_valid_atom_parses_without_error(expr):
    """Every generated valid atom must parse without raising TemplateSyntaxError."""
    parse_expression(expr)  # must not raise
```

### 5.3 Test invariants

- No mocked database. Use testcontainer fixtures (`db_session`, `db_factory`, `db_engine`).
- Step handler tests use `@dataclass` fakes, not `PipelineStep` ORM objects.
- Router tests use `FastAPI()` + `dependency_overrides[get_auth_context]` + `StaticPool`.
- `make check` runs contract tests + core tests + lint + strict mypy on core.
- `make check-all` adds service tests. Required for phases 2, 4, 5.

---

## 6. Library inventory

| Area | Library | License | Already in tree? |
|------|---------|---------|-----------------|
| Expression grammar | `lark` | MIT | No -- new dep |
| JSONSchema validation | `jsonschema` | MIT | Yes |
| YAML I/O | `PyYAML` | MIT | Yes (transitive) |
| Cron next-run | `croniter` | MIT | Yes (transitive via APScheduler) |
| Cron description (FE) | `cronstrue` | MIT | No -- new npm dep, 30KB |
| CodeMirror 6 (FE) | `@codemirror/autocomplete` | MIT | No -- new npm dep, 50KB gzipped |
| JMESPath | `jmespath` | MIT | Yes |
| Property tests | `hypothesis` | MPL-2.0 | No -- new dev dep |
| FE JSON viewer | `vue-json-pretty` | MIT | No -- new npm dep, 15KB |

New Python deps: `lark`, `hypothesis` (dev). No other new transitive dependencies.

---

## 7. Risk register

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Trigger decoupling breaks existing dispatch paths (scheduler, webhooks, telegram) | Medium | Each dispatch path has its own integration test. Phase 0 touches the Rule model first; all other phases build on it. |
| Lark grammar doesn't cover all existing condition expressions | Medium | Port every test from `test_condition_evaluator.py` before deleting it. Run Hypothesis property tests. |
| CodeMirror 6 bundle size bloats the rule edit page | Low | Lazy-load. Measure before/after. Set 200KB gzipped budget for the rule edit page. Fall back to `v-autocomplete` popup if over budget. |
| Cooperative cancellation doesn't kill stuck LLM calls | High | Per-step timeout ensures the pipeline doesn't hang forever. Document that in-flight HTTP calls complete but their results are discarded. |
| `output_schema` drift (step emits key not in schema) | Medium | Dev-mode runtime check warns. Contract test in CI catches missing keys. Schema update is one line in the handler file. |
| Agent-authored rules have poor labeling/conventions | Medium | Server-side lint on import catches missing descriptions, bad labels. `list_plugin_metadata` gives agents the schema they need. Add `provenance: "agent"` flag for triage. |

---

## 8. Open questions

1. **Should `output_schema` be validated at runtime in production?** Recommend dev-mode only for now. Prod logs a warning. Upgrade to hard error after a release cycle of zero warnings.

2. **Do we need `schema_version` on filters and channels too?** Yes, for the same reason as steps: when a filter's config shape changes, the migration chain needs a version to track. Same `ConfigMigration` infrastructure applies.

3. **Should the cron builder support composite expressions?** (`30 9 * * 1,3,5;0 18 * * *` -- 9:30 AM Mon/Wed/Fri AND 6:00 PM daily). This is a v2 feature. The preset modes cover 95% of caregiver use cases.

4. **Should we version the `x-ui` hint schema?** Yes. Added `ui_hints_version: int = 1` to `StepMetadata`. If a frontend sees a version it doesn't understand, it falls back to `GenericPluginConfig`. Prevents a backend upgrade from breaking an old frontend.

5. **JMESPath grammar: pipe or `jq()` function?** Pipe syntax only: `steps.foo.outputs.detections | length(@)`. Cleaner, standard JMESPath, no nested quote escaping. The Lark grammar captures raw JMESPath after the pipe as a literal token and passes it to `jmespath.search()`. No backward compat needed.

6. **Should `render_template` leave unresolved placeholders as-is (current behavior) or raise?** Current behavior leaves `{{typo}}` as the literal string "{{typo}}" in the prompt. This is a design choice for graceful degradation. But with server-side validation rejecting on save, unresolved placeholders can't exist in stored configs. The only case is runtime resolution failure (e.g., a step didn't emit a key it usually emits). For this case, keep the current behavior (leave as-is) and log a warning. The LLM sees `{{typo}}` and can ask for clarification.
