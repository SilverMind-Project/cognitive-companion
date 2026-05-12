# CLAUDE.md

Quick reference for Claude Code agents in `cognitive-companion/`. The full reference is [AGENTS.md](AGENTS.md); this file is the orientation pointer plus the few invariants you must hold from the first edit.

---

## What this is

Privacy-first, on-premise AI for senior care. Python 3.14 FastAPI backend, Vue 3 + Vuetify frontend, PostgreSQL 18 (shared `timescale/timescaledb-ha:pg18` instance), plugin-based per-rule pipelines. The backend is also the BFF gateway for sibling services in the monorepo: `person-identification-service`, `scene-analysis-service`, `semantic-memory-service`, `tts-service`, and the `continuous-tracking/` family.

---

## Read before editing

1. [AGENTS.md](AGENTS.md): canonical reference (architecture, plugin contracts, all 20 step types, all 7 channels, all 13 filters, CTS gateway, testing conventions, naming conventions, common tasks).
2. `backend/main.py` lifespan: source of truth for service wiring and `app.state` keys.
3. `backend/steps/base.py`: `StepHandler`, `StepMetadata`, `StepResult`, `TriggerContext`, `ServiceContainer`.
4. `config/settings.yaml`: every tunable, plus the operator timezone.
5. `.claude/skills/engineering-standards/SKILL.md`: coding standards, naming conventions, type safety, testing, anti-patterns (loaded as a skill at conversation start).

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
- **CTS surface is isolated.** Don't write CTS tables outside `services/cts/`. Don't import `_upstream_base` from non-CTS code. Don't subscribe to `tracking.*` or `scene.*` streams outside `CTSRuntime`.
- **No em-dashes in `.md` files.** Use colons, commas, semicolons.

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
        )

    async def execute(self, step, execution, pipeline_data, trigger, services) -> StepResult:
        return StepResult(data={"your_key": result})
```

`ChannelRegistry` and `FilterRegistry` follow the same shape (see AGENTS.md sections 7 and 8).

---

## Step types currently registered (20)

`llm_call`, `person_identification`, `scene_analysis`, `object_trend_analysis`, `semantic_memory_query`, `semantic_memory_write`, `presence_query`, `home_state`, `info_card`, `notification`, `ha_action`, `activity_detection`, `activity_session_start`, `activity_session_end`, `daily_report`, `verification`, `condition`, `wait`, `interactive_prompt`, `quiz_start`. Full descriptions in AGENTS.md section 6.

## Channels (7)

`pwa_popup_text`, `pwa_realtime_ai`, `pwa_tts_announcement`, `telegram`, `eink`, `ha_speaker_tts`, `webhook`. AGENTS.md section 7.

## Filters (13)

`room`, `time_range`, `day_of_week`, `person_presence`, `person_activity`, `room_transition`, `person_movement_memory`, `scene_contains`, `scene_trend`, `home_state`, `presence_status`, `presence_dwell`, `dementia_signal`. AGENTS.md section 8.

---

## Correctness expectations for every change

1. `make check` passes (lint + strict mypy on core + core tests). For service or schema changes, also `make check-all`.
2. New code has unit tests under `backend/tests/<mirror_path>/` covering success path, missing-service path, and at least one edge case. Do not mock the database; use the testcontainer fixtures.
3. Strongly-typed public surfaces. `@dataclass(frozen=True)` for results returned to callers, Pydantic for HTTP wire models. No `dict[str, Any]` leaking out of an integration client.
4. Graceful degradation. Integration clients return `None`, `[]`, or a typed zero value when upstream is disabled or unreachable; no exceptions bubble.
5. New endpoints have an `auth.yaml` entry.
6. Frontend changes pass `cd frontend && npm run build`. New step / filter types also pass `npm run test`.

---

## Testing patterns to know

- `RulesEngine(tz_name="UTC")` in tests (testcontainer stores UTC).
- For step handlers, use `@dataclass class _FakeStep`; SQLAlchemy instrumentation breaks on `__new__`-constructed `PipelineStep`.
- Pass only the `ServiceContainer` fields the step uses; the rest default to `None`.
- For routers: new `FastAPI()` + `register_exception_handlers(app)` + `app.dependency_overrides[get_auth_context]`. Use `StaticPool` so tables persist across the test connections.
- For class-level property overrides: local subclass; never `type(obj).prop = property(...)`.
- For `SignalStore`: inject the conftest `db_factory` (returns plain `Session`, not a context manager).
- HTTP is patched via `unittest.mock.patch("backend.integrations.<module>.httpx.AsyncClient")`.

---

## What NOT to do (short list)

- `print()` (use `get_logger()`); `eval()` for conditions (use `ConditionEvaluator`); `alert()` / `confirm()` in Vue (use `useNotify`, `useConfirm`); `toLocaleString()` directly (use `services/timezone.js`).
- Catch `AuthenticationError` / `PermissionDeniedError` in routers.
- Run structural migrations by hand in production.
- Add deps without updating `pyproject.toml` and running `uv lock`, or `package.json` and `npm install`.
- Import `ObjectTrendClient` (deleted; use `SemanticMemoryClient`).
- Add new callers of `services.person_tracking` or `services.activity_session_service` (deprecated; use `services.activity`).
- Import `_upstream_base` from non-CTS code.
- Hardcode timezone strings.

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
| Redis | `redis.url` | Required when `cts.enabled=true` |

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
| Condition evaluation | `backend/services/condition_evaluator.py` |
| CTS data flow | `backend/services/cts/runtime.py` and the four subscribers |
| Presence fusion | `backend/services/presence/factory.py`, `service.py`, plus `config/presence.yaml` |
| LLM model registry | `backend/integrations/llm/__init__.py` |
| Notification routing | `backend/services/notification_dispatcher.py` and `config/notifications.yaml` |
| Frontend styling | `frontend/src/styles/theme.css` and the `front-end` skill |
| Testing conventions | AGENTS.md section 16 and `engineering-standards` skill section 6 |
