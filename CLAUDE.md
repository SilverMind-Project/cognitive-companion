# CLAUDE.md

Quick reference for Claude Code agents in `cognitive-companion/`. The full reference is [AGENTS.md](AGENTS.md); this file is the orientation pointer plus the few invariants you must hold from the first edit.

**Engineering standards are non-negotiable.** The `.claude/skills/engineering-standards/SKILL.md` skill is loaded at conversation start. Follow it. No hacks, no short-term fixes, no `Any`-typed injected services, no duplicated utility functions. Write code as if it will be reviewed by a senior engineer at Google or Facebook.

---

## What this is

Privacy-first, on-premise AI for senior care. Python 3.14 FastAPI backend, Vue 3 + Vuetify frontend, PostgreSQL 18 (shared `timescale/timescaledb-ha:pg18` instance), plugin-based per-rule pipelines. The backend is also the BFF gateway for sibling services in the monorepo: `person-identification-service`, `scene-analysis-service`, `semantic-memory-service`, `tts-service`, and the `continuous-tracking/` family.

---

## Read before editing

1. [AGENTS.md](AGENTS.md): canonical reference (architecture, plugin contracts, all 20 step types, all 7 channels, all 13 filters, CTS gateway, per-person signal config, testing conventions, naming conventions, common tasks).
2. `backend/main.py` lifespan: source of truth for service wiring and `app.state` keys.
3. `backend/steps/base.py`: `StepHandler`, `StepMetadata`, `StepResult`, `TriggerContext`, `ServiceContainer`.
4. `config/settings.yaml`: every tunable, plus the operator timezone.
5. `.claude/skills/engineering-standards/SKILL.md`: coding standards, naming conventions, type safety, testing, anti-patterns (loaded as a skill at conversation start).
6. `backend/services/cts/_types.py`: protocol definitions for CTS-injected services. Use these, not `Any`.
7. `backend/services/cts/_time.py`: shared time utilities (`ns_to_iso`, `parse_ts`, `ensure_aware`). Never duplicate these.
8. `backend/routers/cts_deps.py`: shared `cts_enabled()` dependency. Import it; don't redefine it.
9. `backend/services/cts/signal_config.py`: `ALL_SIGNAL_KINDS`, `is_signal_enabled(cfg, kind, severity)`, `default_config_for_profile(profile)`. Import from here; never hardcode the 7 kind strings inline.

---

## Commands

```bash
# Backend dev
uv run --project backend uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend dev
cd frontend && npm run dev          # http://localhost:5173

# Test gates (run before any PR)
make check                          # lint + strict mypy on core + core tests
make check-all                      # adds backend.services tests

# Targeted iteration
make test-core / make test-services
uv run --project backend pytest backend/tests/<area>/test_<file>.py -v

# Coverage / typing / lint
make coverage / make coverage-html / make typecheck / make typecheck-core / make lint / make lint-fix / make format

# Database
make init-db / make migrate / make migration / make migration-history

# Docker
docker compose up -d

# Scaffold a new step type
uv run --project backend python -m backend.steps._scaffold new <type_name> --category <category>
```

`make check` is the fast pre-commit gate. `make check-all` is required for service or schema changes.

---

## Non-negotiable invariants

- **`backend.core` has zero upward dependencies.** No imports from `services`, `routers`, `steps`, `channels`, or `filters`. Strict mypy applies to this package only.
- **Services live in the lifespan, not in routers.** Use `request.app.state.<name>`. Never instantiate inside a router.
- **Plugin systems are auto-discovered.** Add a single file under `backend/steps/builtin/`, `backend/channels/builtin/`, or `backend/filters/builtin/` with the appropriate `@*Registry.register` decorator. No manual wiring.
- **Composable per-rule pipelines.** Pipeline behaviour lives in `PipelineStep.config_json`, not in code branching by rule name.
- **Single timezone source.** `app.timezone` in `config/settings.yaml` is the truth. DB stores UTC; display and scheduling use `ZoneInfo(tz)` from stdlib. Frontend uses `services/timezone.js` (never `toLocaleString()`).
- **Schema changes go through Alembic.** `make migration` then `make migrate`. `Database.create_all()` is for tests and dev only.
- **Permissions are mandatory.** Every endpoint needs an `auth.yaml` entry. Tests override `get_auth_context`, not `require_permission`.
- **Datetimes are timezone-aware.** Use `datetime.now(UTC)`. External datetimes pass through `backend.core.time.normalize_utc_datetime()`.
- **Shared PostgreSQL.** The database host, port, user, password, and name come from `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` env vars. The shared `timescale/timescaledb-ha:pg18` instance hosts three databases: `cognitive_companion`, `continuous_tracking`, `semantic_memory`. Dev: `docker compose --profile standalone up -d` for a self-contained Postgres, or use the shared `docker-compose.db.yml` via `include`.
- **CTS surface is isolated.** Don't write CTS tables outside `services/cts/`. Don't import `_upstream_base` from non-CTS code. Don't subscribe to `tracking.*` or `scene.*` streams outside `CTSRuntime`. Don't duplicate `_cts_enabled()` — import from `backend.routers.cts_deps`. Don't duplicate `ns_to_iso` or `parse_ts` — import from `backend.services.cts._time`. Use protocol types from `backend.services.cts._types` for injected service parameters; never `Any`. Don't hardcode signal kind strings — import `ALL_SIGNAL_KINDS` from `backend.services.cts.signal_config`.
- **No em-dashes in `.md` files.** Use colons, commas, semicolons.
- **Template expressions use `{{ }}` syntax everywhere.** The Lark-based grammar in `backend/core/template_grammar.lark` is the single evaluator. Bare expressions (no braces) are not supported. JMESPath uses pipe syntax: `steps.foo.outputs.detections | length(@)`.
- **Plugins declare their output schema.** Every data-emitting step handler must include `output_schema` in its `StepMetadata`. The contract tests in `backend/tests/steps/test_registry_contract.py` enforce this.
- **Config is validated at save time.** Template expressions are checked server-side on step save via `backend/services/template_validator.py`. Invalid `{{ }}` references are rejected with HTTP 422. Template validation also runs during rule import and via `POST /rules/{id}/validate`.

---

## Plugin contract (the 30-second version)

```python
@StepRegistry.register
class YourStepHandler(StepHandler):
    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="your_step",
            display_name="Your Step",
            category="perception",   # perception | reasoning | action | state | flow
            icon="mdi-icon-name",
            description="...",
            config_schema={...},
            default_config={...},
            # New fields (all optional with defaults):
            schema_version=1,
            ui_hints_version=1,
            ui_hints={},            # x-ui widget hints for SchemaForm
            output_schema={},        # JSONSchema for step outputs (REQUIRED for data-emitting steps)
            tags=(),                # for palette grouping/search
        )

    async def execute(self, step, execution, pipeline_data, trigger, services) -> StepResult:
        return StepResult(data={"your_key": result})
```

`ChannelRegistry` and `FilterRegistry` follow the same shape (see AGENTS.md sections 7 and 8). Both support `schema_version` for migration chains.

---

## Step types currently registered (20)

`llm_call`, `person_identification`, `scene_analysis`, `object_trend_analysis`, `semantic_memory_query`, `semantic_memory_write`, `presence_query`, `home_state`, `info_card`, `notification`, `ha_action`, `activity_detection`, `activity_session_start`, `activity_session_end`, `daily_report`, `verification`, `condition`, `wait`, `interactive_prompt`, `quiz_start`. Full descriptions in AGENTS.md section 6.

## Channels (7)

`pwa_popup_text`, `pwa_realtime_ai`, `pwa_tts_announcement`, `telegram`, `eink`, `ha_speaker_tts`, `webhook`. AGENTS.md section 7.

## Filters (13)

`room`, `time_range`, `day_of_week`, `person_presence`, `person_activity`, `room_transition`, `person_movement_memory`, `scene_contains`, `scene_trend`, `home_state`, `presence_status`, `presence_dwell`, `dementia_signal`. AGENTS.md section 8.

---

## Trigger architecture

Triggers are decoupled from rules. A `Rule` stores `trigger_types: list[str]` (JSON column, default `["sensor_event"]`). Cron schedules are managed through a separate `CronTrigger` model with a many-to-many join table (`rule_cron_triggers`).

| Trigger type | Mechanism |
|---|---|
| `sensor_event` | RulesEngine queries all rules with `trigger_types` containing `"sensor_event"` |
| `cron` | Scheduler creates one APScheduler job per `CronTrigger` row. On fire, queries `rule_cron_triggers` for linked rules and dispatches each through `RulesEngine` (context filters, dependencies, rate limits all apply) |
| `webhook` | `POST /webhooks/{rule_id}`; rule must have `"webhook"` in `trigger_types` and a configured secret |
| `telegram` | `TelegramTriggerService` polls for commands, matches rules with `"telegram"` in `trigger_types` |
| `manual` | `POST /rules/{id}/execute`; works for any enabled rule |
| `occupancy_duration` | RulesEngine with `trigger_type="occupancy_duration"` filter |
| `dementia_signal` | `DementiaSignalSubscriber` calls `PipelineExecutor.fire_event` after dispatch gate; `get_matching_rules_for_event` runs rules with `trigger_types` containing `"dementia_signal"`. Event is a dict, not a Sensor ORM object; sensor-dependent filters are skipped. |

A rule can respond to multiple trigger types simultaneously (e.g., both cron and sensor_event).

---

## Expression grammar

All `{{ }}` template expressions use a Lark-based grammar defined in `backend/core/template_grammar.lark`. The grammar supports:

- **Path access:** `steps.foo.outputs.bar`, `trigger.sensor_id`, `system.local_time`
- **List indexing:** `steps.foo.outputs.detections.0.label`
- **JMESPath pipes:** `steps.foo.outputs.detections | length(@)`
- **Comparisons:** `==`, `!=`, `>`, `<`, `>=`, `<=`
- **Boolean:** `and`, `or`, `not`
- **Functions:** `contains()`, `icontains()`, `length()`, `lower()`, `upper()`, `keys()`, `values()`, `exists()`
- **Literals:** numbers, `true`, `false`, `null`, quoted strings

The old `ConditionEvaluator` in `backend/services/condition_evaluator.py` has been deleted. The Lark interpreter in `backend/core/template_interpreter.py` is the single evaluator for both template substitution and condition evaluation.

For simple dotted paths (no operators), `render_template` uses a fast regex + `resolve_path` shortcut. Everything else goes through the Lark parser.

---

## Import/export

Rules can be exported to portable YAML/JSON bundles and imported across installations.

- **Export:** `GET /rules/{id}/export` returns a `RuleBundle` with label-based cross-references (no DB ids)
- **Import:** `POST /rules/import/preview` validates without writing; `POST /rules/import` commits within a transaction
- **ConfigMigration:** Each plugin can declare migration chains in its metadata via `ConfigMigration` dataclasses
- **Schema:** `backend/schemas/rule_bundle.py`, serializer in `backend/services/rule_serializer.py`

---

## Correctness expectations for every change

1. `make check` passes (lint + strict mypy on core + core tests). For service or schema changes, also `make check-all`.
2. New code has unit tests under `backend/tests/<mirror_path>/` covering success path, missing-service path, and at least one edge case. Do not mock the database; use the testcontainer fixtures.
3. Strongly-typed public surfaces. `@dataclass(frozen=True)` for results returned to callers, Pydantic for HTTP wire models. No `dict[str, Any]` leaking out of an integration client.
4. Graceful degradation. Integration clients return `None`, `[]`, or a typed zero value when upstream is disabled or unreachable; no exceptions bubble.
5. New endpoints have an `auth.yaml` entry.
6. Frontend changes pass `cd frontend && npm run build`. New step / filter types also pass `npm run test`.
7. **New:** Plugin contract tests pass. Every config_schema is valid JSONSchema, every default_config validates against it, every data-emitting step has a non-empty `output_schema`.

---

## Testing patterns to know

- `RulesEngine(tz_name="UTC")` in tests (testcontainer stores UTC).
- For step handlers, use `@dataclass class _FakeStep`; SQLAlchemy instrumentation breaks on `__new__`-constructed `PipelineStep`.
- Pass only the `ServiceContainer` fields the step uses; the rest default to `None`.
- For routers: new `FastAPI()` + `register_exception_handlers(app)` + `app.dependency_overrides[get_auth_context]`. Use `StaticPool` so tables persist across the test connections.
- For class-level property overrides: local subclass; never `type(obj).prop = property(...)`.
- For `SignalStore`: inject the conftest `db_factory` (returns plain `Session`, not a context manager).
- HTTP is patched via `unittest.mock.patch("backend.integrations.<module>.httpx.AsyncClient")`.
- For expression grammar tests: use `backend.core.template_ast.parse_expression()` and `backend.core.template_interpreter._eval()`. For template tests: `render_template()`.
- For migration tests: frozen fixtures in `backend/tests/fixtures/rule_bundles/`.
- **New:** Use `backend/steps/_testing.assert_output_conforms_to_schema()` in step handler tests to verify output schema compliance.

---

## What NOT to do (short list)

- `print()` (use `get_logger()`); `eval()` for conditions (use Lark grammar via `evaluate_condition()`); `alert()` / `confirm()` in Vue (use `useNotify`, `useConfirm`); `toLocaleString()` directly (use `services/timezone.js`).
- Catch `AuthenticationError` / `PermissionDeniedError` in routers.
- Run structural migrations by hand in production.
- Add deps without updating `pyproject.toml` and running `uv lock`, or `package.json` and `npm install`.
- Import `ObjectTrendClient` (deleted; use `SemanticMemoryClient`).
- Add new callers of `services.person_tracking` or `services.activity_session_service` (deprecated; use `services.activity`).
- Import `_upstream_base` from non-CTS code.
- Hardcode timezone strings.
- Use bare condition expressions without `{{ }}` wrapping (the old syntax is not supported).
- Access `self._pipeline_executor._services` from Scheduler (use the public `event_aggregator` property).

Full do-not list: AGENTS.md section 19.

---

## External services

| Service | Env var | Required |
| --- | --- | --- |
| PostgreSQL (shared) | `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Required |
| Person Identification | `PERSON_ID_SERVICE_URL` | Face recognition |
| Scene Analysis | `SCENE_ANALYSIS_URL` | Optional |
| Semantic Memory | `SEMANTIC_MEMORY_URL` | Optional |
| Home Assistant | `HOME_ASSISTANT_URL`, `HOME_ASSISTANT_TOKEN` | Sensors + actions |
| MinIO | `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` | Required |
| TTS | `TTS_API_URL` | Optional |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CAREGIVER_CHAT_ID` | Optional |
| Google Gemini | `GEMINI_API_KEY` | Optional (realtime voice) |
| vLLM (vision) | `VISION_MODEL_URL` | Required for vision |
| llama.cpp (reasoning) | `GEMMA_MODEL_URL` (or `LOGIC_MODEL_URL`) | Required for reasoning |
| Triton Inference Server | (settings.yaml embedding section) | Required for knowledge RAG |
| Tracking Orchestrator | `TRACKING_ORCHESTRATOR_URL` (+ `cts.upstream.tracking_orchestrator`) | Required when `cts.enabled=true` |
| RTSP Ingress | `CTS_INGRESS_URL` (+ `cts.upstream.rtsp_ingress`) | Required when `cts.enabled=true` |
| Redis | `REDIS_URL` (env var, mapped to `redis.url` in settings.yaml) | Required when `cts.enabled=true` |

---

## Agent skills

This project loads two skills at conversation start. Read them before making frontend or backend changes:

- **`engineering-standards`** (`.claude/skills/engineering-standards/SKILL.md`): naming conventions, type safety, error handling, testing standards, database patterns, plugin development, API design, security, anti-patterns, pre-commit checklist.
- **`front-end`** (`.claude/skills/front-end/SKILL.md`): design tokens, frosted-glass system, page layout pattern, dialog pattern, server-side pagination, form patterns, API contracts, composables, common mistakes.

---

## Where to look when stuck

| Goal | File |
| --- | --- |
| Startup wiring | `backend/main.py` (lifespan) |
| Step plugin contract | `backend/steps/base.py` |
| Trace a rule firing | `backend/services/workflow.py` → `rules_engine.py` → `pipeline_executor.py` |
| Condition / expression evaluation | `backend/core/template_grammar.lark` → `template_ast.py` → `template_interpreter.py` |
| Template rendering | `backend/core/template.py` |
| CTS data flow | `backend/services/cts/runtime.py` and the four subscribers (tracking_event, identity_revision, dementia_signal, scene_sample) |
| CTS shared utilities | `backend/services/cts/_time.py` (time), `backend/services/cts/_types.py` (protocols), `backend/routers/cts_deps.py` (router deps), `backend/services/cts/signal_config.py` (per-person alert config + kind list) |
| CTS stream consumer base | `backend/services/cts/stream_consumer.py` |
| Presence fusion | `backend/services/presence/factory.py`, `service.py`, plus `config/presence.yaml` |
| LLM model registry | `backend/integrations/llm/__init__.py` |
| Notification routing | `backend/services/notification_dispatcher.py` and `config/notifications.yaml` |
| Trigger dispatch | `backend/services/scheduler.py` (cron), `backend/services/rules_engine.py` (sensor/occupancy/dementia_signal via `get_matching_rules_for_event`) |
| Per-person CTS alert config | `backend/services/cts/signal_config.py`, `HouseholdMember.cts_alert_config`, migration `0012_cts_alert_config` |
| Import/export | `backend/services/rule_serializer.py`, `backend/schemas/rule_bundle.py` |
| Plugin migrations | `backend/core/plugin_migrations.py` |
| Cron expression handling | `backend/routers/pipeline.py` (preview endpoint), `frontend/src/components/pipeline/CronBuilder.vue` |
| Template validation | `backend/services/template_validator.py`, `backend/routers/rules.py` (validate endpoint) |
| Variable reference / data keys | `backend/routers/pipeline.py` (`GET /pipeline/data-keys`) |
| Frontend generic step renderer | `frontend/src/components/pipeline/steps/_shared/SchemaForm.vue` |
| Frontend styling | `frontend/src/styles/theme.css` and the `front-end` skill |
| Frontend CTS composables | `frontend/src/composables/useCtsSeverity.js`, `useFormatRelative.js`, `useCtsWebSocket.js`, `useIdentityColor.js` |
| Testing conventions | AGENTS.md section 16 and `engineering-standards` skill section 6 |
