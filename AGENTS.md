# AGENTS.md

Reference for AI coding agents working in `cognitive-companion/`. This document is the canonical, deep guide. `CLAUDE.md` is a tight pointer aimed at the same audience; `README.md` is human-facing.

If a fact appears here, it traces to a file in this tree at the time of writing. Verify before relying on it: `git log` is authoritative for "what changed", and `grep` against `backend/` is authoritative for "what exists".

---

## 1. Mission and scope

Cognitive Companion is a privacy-first, on-premise AI system for senior care. It ingests camera and sensor events, evaluates them against caregiver-authored rules, and dispatches gentle reminders and caregiver alerts through a plug-in pipeline.

Three things make this codebase non-trivial:

1. **Plugin registries.** Pipeline steps, notification channels, and context filters are auto-discovered classes. Adding a new one is a single file in the right directory.
2. **Composable per-rule pipelines.** Each rule defines its own ordered sequence of `PipelineStep` rows. The same step type can behave very differently across rules via per-step `config_json`.
3. **Strongly-typed service injection.** CTS-injected services use structural `Protocol` classes from `backend/services/cts/_types.py`. Never pass `Any` for `ws_manager`, `pipeline`, `minio_client`, or `db_factory`. Shared utilities (`_time.py`, `cts_deps.py`) replace duplicated functions; import them, don't redefine them.
4. **Multi-service architecture.** The backend depends on seven sibling services: `person-identification-service` (face ID), `scene-analysis-service` (YOLO + Florence-2 + CLIP), `semantic-memory-service` (pgvectorscale observations and movements), `tts-service` (TTS), and the `continuous-tracking/` family (multi-camera tracking + dementia signals via Redis Streams: `tracking-orchestrator`, `rtsp-ingress`, Triton Inference Server, Redis). Cognitive Companion is the BFF gateway for all browser and MCP traffic into those services.

---

## 2. Tech stack

| Layer | Choice |
| --- | --- |
| Backend | Python 3.14, FastAPI, SQLAlchemy 2.0, Pydantic 2, APScheduler, stdlib logging via `BoundLogger` |
| Database | PostgreSQL 18 via `timescale/timescaledb-ha:pg18` (shared instance with `continuous_tracking`, `semantic_memory`); Alembic migrations; DB `cognitive_companion` owns all tables |
| Frontend | Vue 3 (Composition API, `<script setup>`), Vuetify 3, Vite, vue-router |
| Object storage | MinIO (S3-compatible) via `boto3` |
| LLM serving | vLLM and llama.cpp `llama-server` (OpenAI-compatible `/v1/chat/completions`); Ollama; Google Gemini Live for realtime audio |
| Package manager | `uv` (`backend/uv.lock` is committed) |
| Lint and types | `ruff`; `mypy` strict on `backend.core`, gradual elsewhere |

---

## 3. Repository layout

```text
cognitive-companion/
├── backend/
│   ├── core/                   Foundational layer (Settings, Database, KeyStore, exceptions, logging, template, template_grammar, template_ast, template_interpreter, plugin_migrations, time helpers)
│   ├── models/                 SQLAlchemy ORM (Rule, PipelineStep, WorkflowExecution, EventLog, Sensor, Room, HouseholdMember, PersonSighting, PersonLocationState/History, PersonActivity, MediaCache, ImageTemplate, ActiveImageState, ConversationSession, EmergencyAlert, CtsCamera, DementiaSignal, InteractiveResponse, ...)
│   ├── schemas/                Pydantic *Create / *Update / *Out mirrors of the ORM models
│   ├── steps/                  Pipeline-step plugin system
│   │   ├── base.py             StepHandler ABC, StepMetadata, StepResult, TriggerContext, ServiceContainer
│   │   ├── _helpers.py         Shared helpers (resolve_person_id, etc.)
│   │   ├── __init__.py         StepRegistry singleton + auto-discovery
│   │   └── builtin/            20 built-in step files (see section 6)
│   ├── channels/               Notification-channel plugin system
│   │   ├── base.py, __init__.py
│   │   └── builtin/            8 built-in channel files for 7 channel types (see section 7)
│   ├── filters/                Rule-context filter plugin system
│   │   ├── base.py, __init__.py
│   │   └── builtin/            13 built-in filters (see section 8)
│   ├── services/               Business logic
│   │   ├── pipeline_executor.py    Orchestrates step execution via StepRegistry
│   │   ├── workflow.py             Per-event entry point: rules engine + executor
│   │   ├── rules_engine.py         Rule matching: filters + dependencies + rate limits
│   │   ├── rule_serializer.py          Rule import/export: Rule ↔ RuleBundle serialization
│   │   ├── event_aggregator.py     Frame batching, per-sensor cooldown, MinIO lifecycle
│   │   ├── sensor_polling.py       HA presence polling + occupancy_duration triggers
│   │   ├── person_tracking.py      Camera-detection + HA presence fusion (DEPRECATED, prefer services.activity)
│   │   ├── notification_dispatcher.py  Multi-channel delivery via ChannelRegistry
│   │   ├── conversation_manager.py     Conversation history with TTL
│   │   ├── media_processor.py          Image/video helpers
│   │   ├── rag.py                       Optional RAG lookup
│   │   ├── template_validator.py         Lark-based template validation for step configs
│   │   ├── scheduler.py                 APScheduler wrapper + SchedulerBridge
│   │   ├── camera_topology.py           infer_room_transition() + RoomTransition dataclass
│   │   ├── activity_session.py          Open/close duration sessions (DEPRECATED, prefer services.activity)
│   │   ├── activity_timeline.py         Activity timeline reads
│   │   ├── activity/                    ActivityService (replaces person_tracking + activity_session for new code)
│   │   ├── daily_report.py              End-of-day wellness report writer
│   │   ├── interactive_response.py      Pending-prompt persistence + scheduler hooks
│   │   ├── memory_query/                MemoryQueryService (semantic-memory cache + read API)
│   │   ├── scene_intel/                 SceneIntelService (scene_analysis + semantic_memory composition)
│   │   ├── presence/                    PresenceService (Block 1-3 provider chain: night anchor + HA bed sensor + CTS location + HA device tracker + stale fallback)
│   │   ├── signals/                     SignalsService (CTS dementia signal reads)
│   │   ├── telegram_trigger.py          Telegram command-to-rule polling
│   │   └── cts/                         CTS subscribers + writers: runtime, stream_consumer, _time (shared time utils), _types (protocols), tracking_event_subscriber, identity_revision_subscriber, subscriber (dementia_signal), scene_sample_subscriber, location_writer, location_repository, identity_rewriter, signal_store, source_authority, metrics
│   ├── integrations/           External clients
│   │   ├── homeassistant.py, ha_state_cache.py, telegram.py, tts.py, minio_client.py
│   │   ├── eink_renderer.py            Internal PIL-based eink renderer
│   │   ├── person_id_client.py         Face-recognition microservice client
│   │   ├── scene_analysis_client.py    YOLO+Florence-2+CLIP client (HttpUpstreamClient)
│   │   ├── semantic_memory_client.py   Observations, movements, trends client (HttpUpstreamClient)
│   │   ├── ingress_admin_client.py     CTS rtsp-ingress proxy (mTLS + EdDSA JWT)
│   │   ├── tracking_orchestrator_client.py  CTS tracking-orchestrator proxy (mTLS + EdDSA JWT)
│   │   ├── _http_base.py               Shared LAN HTTP base
│   │   ├── _upstream_base.py           CTS-only mTLS + JWT base
│   │   ├── llm/                        LLM providers (OpenAICompatibleProvider, OllamaProvider, GeminiLiveProvider, LLMProviderChain, LLMProviderPool, LLMModelRegistry)
│   │   └── proto/                      Generated protobuf bindings (committed)
│   ├── routers/                FastAPI route handlers (one file per domain). 30 routers including 10 CTS routers (cts, cts_cameras, cts_calibration, cts_dashboard, cts_identity, cts_keyframes, cts_live, cts_presence, cts_signals)
│   ├── mcp/                    FastMCP tool server, Gemini tool adapter, ASGI auth middleware
│   ├── websocket/              Connection manager, audio handler (Gemini Live)
│   ├── alembic/                Alembic migrations (linear chain on PostgreSQL)
│   ├── assets/                 Fonts and eInk template images
│   ├── tests/                  Mirrors backend/ layout: core/, services/, steps/, channels/, filters/, routers/, integrations/, mcp/, schemas/, models/, websocket/, integration/, e2e/, fixtures/
│   ├── pyproject.toml, uv.lock
│   └── main.py                 App factory, lifespan (the wiring source-of-truth)
├── frontend/
│   └── src/
│       ├── views/CompanionView.vue                Senior-facing voice UI
│       └── views/admin/                            25 admin views (Dashboard, Rules, RuleDetail, Sensors, Rooms, Events, Alerts, Persons, PersonTimeline, Activities, DailyReports, Workflows, EInkTemplates, CameraMedia, InteractiveResponses, plus 10 CTS views)
│       ├── components/pipeline/                    PipelineBuilder, StepCard, StepConfigDialog, StepPalette, CronBuilder, ExecutionDetail, steps/_shared/SchemaForm
│       ├── components/companion/                   Widget registry (VoiceWidget, TranscriptWidget, AlertWidget)
│       ├── components/cts/                         PresenceStatusChip, PresenceWidget
│       ├── components/eink/                        BoundingBoxCanvas, RegionEditor
│       ├── components/person/                      PersonTimeline, DailyReportCard
│       ├── composables/useNotify.js, useConfirm.js, useCtsSeverity.js, useFormatRelative.js, useCtsWebSocket.js, useIdentityColor.js
│       └── services/api.js, cts.js, timezone.js, WebSocketClient.js, contracts.js
├── config/
│   ├── settings.yaml           Application settings (single source of truth for the operator timezone in app.timezone)
│   ├── auth.yaml               API keys, device keys, fnmatch permission map
│   ├── notifications.yaml      Alert-level to channel routing
│   └── presence.yaml           PresenceService provider chain (priority-ordered)
├── data/                       Runtime media cache
├── docker-compose.yml (includes ../docker-compose.db.yml for shared Postgres)
└── Makefile                    See section 4
```

---

## 4. Commands

Run from the repository root unless noted.

```bash
# Backend (development)
uv run --project backend uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (development)
cd frontend && npm run dev          # http://localhost:5173
cd frontend && npm run build        # production build

# Tests
make test                           # full backend suite
make test-core                      # backend.core only
make test-services                  # backend.services only

# Coverage
make coverage                       # core, terminal output
make coverage-services              # services, terminal output
make coverage-html                  # writes htmlcov/index.html

# Lint, format, type check
make lint                           # ruff check
make lint-fix                       # ruff check --fix
make format                         # ruff format
make typecheck                      # mypy on the full backend tree
make typecheck-core                 # strict mypy on backend.core only

# Pre-commit gates
make check                          # lint + typecheck-core + test-core (fast)
make check-all                      # adds test-services

# Database
make init-db                        # create DB + run migrations + seed
make migrate                        # apply pending migrations
make migration                      # autogenerate new migration after model edits
make migration-history

# Docker
docker compose -f ../docker-compose.db.yml -p nanai up -d  # shared DB first
docker compose up -d                # backend (8000) + frontend (80)
docker compose build --no-cache
```

`make check` must pass before opening a PR. `make check-all` is the gate for any change that touches `backend/services/` or shared infrastructure.

---

## 5. Architecture

### 5.1 Backend layering

```text
backend/core/          Foundational layer (no upward imports)
backend/models/        ORM
backend/schemas/       Pydantic wire models
backend/integrations/  External clients
backend/services/      Business logic
backend/steps/, channels/, filters/   Plugin systems
backend/routers/       FastAPI route handlers
backend/mcp/           MCP tool server
backend/websocket/     WS connection + audio handlers
backend/main.py        App factory + lifespan (wiring)
```

**`backend.core` invariant.** No imports from services, routers, steps, channels, or filters. Models import is only via `Database.create_all` (lazy). FastAPI types appear only in `auth.py` and `exceptions.register_exception_handlers`. Strict `disallow_untyped_defs = true` via per-package mypy override.

### 5.2 Service injection

Services are constructed in the FastAPI lifespan (`backend/main.py`) and stashed on `app.state`. Routers read them through `request.app.state.<name>`; never instantiate a service in a router.

```python
@router.get("/some-path")
async def endpoint(request: Request, auth = Depends(require_permission("GET /some-path"))):
    executor = request.app.state.pipeline_executor
```

The `ServiceContainer` dataclass in `backend/steps/base.py` is the bag passed to every step handler. Current fields:

```text
db_factory, person_id_client, notification_dispatcher, ha_client,
event_aggregator, scheduler, llm_model_registry, ha_state_cache,
presence, scene_analysis_client, daily_report_service, semantic_memory_client,
interactive_response_service, memory_query, scene_intel, activity, signals,
knowledge_ingestion, knowledge_query, content_generation, knowledge_delivery,
layout_registry, voice_instruction_config, embedding_client, image_renderer,
person_tracking (DEPRECATED), activity_session_service (DEPRECATED)
```

Steps must request only what they use. The deprecated fields stay until the migration to `ActivityService` is complete; do not introduce new callers.

### 5.3 Plugin systems

All three registries follow the same pattern:

| Registry | Base class | Discovery | Add by |
| --- | --- | --- | --- |
| `StepRegistry` | `StepHandler` | scans `backend/steps/builtin` and `backend/steps/contrib` at startup | dropping a Python file with a `@StepRegistry.register` class |
| `ChannelRegistry` | `NotificationChannel` | scans `backend/channels/builtin` and `backend/channels/contrib` | same pattern with `@ChannelRegistry.register` |
| `FilterRegistry` | `ContextFilter` | scans `backend/filters/builtin` and `backend/filters/contrib` | same pattern with `@FilterRegistry.register` |

Lifespan calls `StepRegistry.discover() / ChannelRegistry.discover() / FilterRegistry.discover()` once at startup. Adding a plugin requires zero changes outside its own file.

### 5.4 Step handler contract

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
            description="What this step does.",
            config_schema={...},     # JSONSchema; consumed by the frontend StepConfigDialog
            default_config={...},
        )

    async def execute(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
        services: ServiceContainer,
    ) -> StepResult:
        config = step.config_json or {}
        ...
        return StepResult(data={"your_key": result})
```

`StepResult` fields: `success`, `data` (merged into `pipeline_data`), `should_continue`, `next_step_id` (branching), `wait_until` (delayed resume).

`TriggerContext.trigger_type` values: `sensor_event`, `cron`, `manual`, `webhook`, `telegram`, `occupancy_duration`, `dementia_signal`, `resume`.

### 5.5 Pipeline data accumulation

`PipelineExecutor` initializes `pipeline_data` with a localized `system` object (`local_time`, `local_date`, `local_day_of_week`, `timezone`) using `app.timezone` from settings, then merges every successful step's `result.data` into the dict before invoking the next step. Templates use `{{dotted.path}}` resolved by `backend.core.template.render_template`.

### 5.6 Cool-off and rate limits

`EventLog.status` drives rule cool-off. A pipeline that completes without producing a terminal action records `status = "ignored"`, which does not consume the cool-off window. Steps that should consume it set `_cooloff_triggered: true` in their `data`:

| Step | Default `trigger_cooloff` |
| --- | --- |
| `notification` | `true` |
| `ha_action` | `true` |
| `activity_detection` | `true` |
| `condition` | `false` (only fires on `true` branch when enabled) |

`Rule.cool_off_minutes` and `Rule.max_daily_triggers` are enforced in `RulesEngine.matches()`. Daily counters reset at local midnight in `app.timezone`.

### 5.7 Database

PostgreSQL 18 via `timescale/timescaledb-ha:pg18` (shared instance with `continuous_tracking`, `semantic_memory`). The shared database host, port, user, password, and name come from `CC_DB_USER`, `CC_DB_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB` env vars. `Database` class in `backend/core/database.py` owns the engine and session factory.

```python
from backend.core.database import get_session
db = get_session()
try:
    ...
finally:
    db.close()
```

Schema changes use Alembic (`make migrate`, `make migration`). `Database.create_all()` is for tests and dev only.

In tests, construct `Database` directly:

```python
from backend.core.database import Database
db = Database("postgresql+psycopg://cc_user:pass@localhost:5432/cognitive_companion")
sess = db.session()
```

The shared `db_engine`, `db_session`, and `db_factory` fixtures in `backend/tests/conftest.py` start a PostgreSQL testcontainer and are reused across the suite.

### 5.8 Configuration

YAML in `config/` with `${ENV_VAR}` interpolation. Access via the singleton:

```python
from backend.core.config import settings
url = settings.get("person_id.url")
interval = settings.get("homeassistant.poll_interval_seconds", 30)
```

In tests, `Settings.from_dict({...})` constructs without disk access. The lifespan calls `settings.reload()` and then `invalidate_lookup_cache()` so the auth `KeyStore` rebuilds against the freshly loaded config.

### 5.9 Authentication and authorization

Keys resolve from `X-API-Key` header, `?api_key` query param, or `device_key` in the JSON body. Permission patterns are `fnmatch` strings against `METHOD /path` declared in `config/auth.yaml`. Every new endpoint needs an entry there.

```python
from backend.core.auth import require_permission

@router.get("/things")
async def endpoint(auth = Depends(require_permission("GET /things"))):
    ...
```

In router tests, override `get_auth_context` (not `require_permission`):

```python
app.dependency_overrides[get_auth_context] = lambda: AuthContext(
    key="x", name="tester", permissions=["*"]
)
```

`require_permission` is a factory returning a closure; overriding the factory has no effect on previously-built closures.

**Hardware device upsert.** At startup, `_upsert_device_key_sensors()` reads every entry under `auth.device_keys` and upserts a `Sensor` row using the entry's `sensor_id`. `device_type: "recamera"` maps to `sensor_type: "camera"`; `device_type: "reterminal"` maps to `sensor_type: "eink"`.

### 5.10 Logging

```python
from backend.core.logging import get_logger
logger = get_logger(__name__)
logger.info("event_processed", sensor_id=sid, rule=rule.name)
```

Always pass keyword context. Never `print()`. Never printf-style.

### 5.11 Error handling

`backend/core/exceptions.py` exports the `AppError` hierarchy:

| Exception | Status |
| --- | --- |
| `AuthenticationError` | 401 |
| `PermissionDeniedError` | 403 |
| `NotFoundError` | 404 |
| `ConflictError` | 409 |
| `ValidationError` | 422 |

Routers must not catch these. The global handlers registered by `register_exception_handlers()` convert them. Tests must call `register_exception_handlers(app)` on every test FastAPI app or `NotFoundError` returns 500.

### 5.12 Timezone

`app.timezone` in `config/settings.yaml` (IANA, e.g. `America/New_York`) is the single source of truth.

| Concern | Rule |
| --- | --- |
| DB storage | UTC-aware, `TIMESTAMPTZ`. Use `datetime.now(UTC)`. |
| Source | Always `settings.get("app.timezone", "UTC")`. Never hardcode. |
| Library | `from zoneinfo import ZoneInfo` (stdlib). Never `pytz`. |
| Local wall-clock | `datetime.now(ZoneInfo(tz_name))`. |
| UTC for queries | `local_dt.astimezone(UTC)`. |
| Cron | Pass `timezone=ZoneInfo(tz_name)` to every `CronTrigger.from_crontab()`. APScheduler handles DST. |
| Daily counters | Reset at local midnight: `now.replace(hour=0, ..., tzinfo=tz).astimezone(UTC)`. |
| Filters | The `now` argument passed into `evaluate()` is already in app timezone; `RulesEngine` ensures this. |

Frontend timezone: fetched once from `GET /api/v1/admin/app-info` and stored in `services/timezone.js`. Never `toLocaleString()` directly; use the `formatDateTime*` helpers and `localHHMMToUTCISO` / `isoToLocalHHMM` for inputs.

In tests, use `RulesEngine(tz_name="UTC")` to keep timestamp comparisons aligned with the UTC values in the testcontainer.

### 5.13 Naming conventions

**Files and packages.** `snake_case` for modules, packages, and test files. Test files mirror their source: `backend/tests/<path>/test_<module>.py`.

**Python symbols.** `PascalCase` for classes; `snake_case` for functions, methods, variables; `UPPER_SNAKE_CASE` for module-level constants; `_leading_underscore` for private helpers.

**Database columns.** `snake_case` in both ORM and PostgreSQL. Foreign keys: `<table>_id`. Booleans: `is_<adj>` or `has_<noun>`. Timestamps: `<event>_at` (e.g. `created_at`, `resume_at`).

**Pydantic schemas.** `*Create`, `*Update`, `*Out` suffixes mirroring the ORM model name (e.g. `RuleCreate`, `RuleOut`). List wrappers: `*ListOut` with `items: list[FooOut]` and `total: int`.

**Vue components.** `PascalCase` files and component names (e.g. `RuleDetailView.vue`). Composables: `use<Name>.js`. Props are `camelCase` in `<script setup>`, `kebab-case` in templates.

---

## 6. Built-in pipeline step types

20 step files under `backend/steps/builtin/`. Categories drive the StepPalette grouping in the admin UI.

| Type name | File | Category | Notes |
| --- | --- | --- | --- |
| `llm_call` | `llm_call.py` | reasoning | Unified LLM step. Selects a model from `LLMModelRegistry` by `model_id`. Supports `image_source` (`none`, `trigger`, `additional`, `both`), `additional_sensor_ids`, `sort_by_sensor_then_time`, `images_per_sensor`, `max_images`, `image_time_filter`, JSON output (`response_format` text or json_schema, `response_json_schema`), hallucination retry, `output_key` (default `llm_response`). |
| `person_identification` | `person_identification.py` | perception | Calls `person_id_client`. Records sightings. With `write_movements_to_memory: true`, also persists camera-topology room transitions to semantic memory. |
| `scene_analysis` | `scene_analysis.py` | perception | Calls `scene_analysis_client`. Returns YOLO detections, Florence-2 description, CLIP embedding, hazard alerts. With `write_to_memory: true`, also persists an observation to semantic memory and emits `scene_memory_observation_id`. |
| `object_trend_analysis` | `object_trend_analysis.py` | perception | Displayed as "Room Trend Query". Queries `semantic_memory_client` for room-level trend state (clutter score, persistent/novel objects, anomaly severity). |
| `semantic_memory_query` | `semantic_memory_query.py` | perception | Composes a compact LLM-ready summary of recent observations and object presence in a room. Output key default `memory_context`. |
| `semantic_memory_write` | `semantic_memory_write.py` | state | Persists scene observations and movements (typically produced upstream by `scene_analysis` or `person_identification`) to semantic memory. |
| `presence_query` | `presence_query.py` | perception | Reads the fused `PresenceService`. Emits a structured snapshot under `output_key` and flat keys (`presence_status`, `presence_room_name`, `presence_dwell_minutes`, `presence_at_home`, `presence_asleep`, `presence_away`). Also fetches recent dementia signals when `services.signals` is wired. |

| `home_state` | `home_state.py` | perception | Thin wrapper around `presence_query` that emits four boolean flags only: `<key>_at_home`, `<key>_asleep`, `<key>_away`, `<key>_state_unknown`. |
| `info_card` | `info_card.py` | action | Delivers a curated info card to the senior via PWA popup, e-ink display, or both. Loads an approved `InfoCard` by ID, resolves image slots, and dispatches through `KnowledgeDeliveryService`. Supports per-delivery voice instruction override. |
| `quiz_start` | `quiz_start.py` | flow | Starts an interactive quiz session via the companion PWA. Loads an approved `Quiz` by ID, creates a `QuizSession`, supports question randomization, per-senior dedupe (skip if completed within N hours), session timeout, and voice instruction override. |
| `notification` | `notification.py` | action | Formats and dispatches across channels using `notifications.yaml` mappings, with per-channel template overrides (`telegram_template`, `ha_speaker_tts_template`, `eink_template`, `webhook_template`, `pwa_popup_text_template`, `pwa_realtime_ai_template`). The `pwa_tts_announcement` channel reuses `ha_speaker_tts_template`. Selects an eink template via `eink_template_id` and expiry via `eink_expiry_minutes`. |
| `ha_action` | `ha_action.py` | action | Calls a Home Assistant service. |
| `activity_detection` | `activity_detection.py` | state | Records a single `PersonActivity`. All fields support `{{template}}` syntax. Setting `capture_scene_description: true` saves the upstream vision output (`scene_description_key`, default `vision_response`) into `metadata_json.scene_description`. `metadata_extra` accepts a templated JSON string for arbitrary extra metadata. |
| `activity_session_start` | `activity_session_start.py` | action | Opens a duration-aware session via `ActivitySessionService`. Idempotent (reuses an open session of the same kind for the same person). |
| `activity_session_end` | `activity_session_end.py` | action | Closes an open session, optionally recording a `PersonActivity` with `duration_minutes`. |
| `daily_report` | `daily_report.py` | action | Aggregates sleep, meals, medication, bathroom, door, exercise, and location into a `DailyReport` row with wellness scoring. Designed for cron-triggered end-of-day rules. |
| `verification` | `verification.py` | state | Queries `PersonActivity` to verify activities within a time window. No images, no LLMs. |
| `condition` | `condition.py` | reasoning | Evaluates a safe expression via the Lark-based `evaluate_condition()`. Branches via `next_step_on_true` / `next_step_on_false`. |
| `wait` | `wait.py` | flow | Persists `WorkflowExecution.status = waiting`, sets `resume_at`, and returns. Scheduler resumes via APScheduler `DateTrigger` and the injected `SchedulerBridge`. |
| `interactive_prompt` | `interactive_prompt.py` | flow | Asks the senior a question (popup or voice) and waits for the answer with a timeout. Wires to `InteractiveResponseService` which persists the pending response and resumes the workflow when the answer arrives or the timeout expires. |

`logic_reasoning`, `translation`, and `vision_analysis` step types were removed in v0.6; use `llm_call` with the appropriate `output_key` and `model_id`. `info_card` and `quiz_start` were added in v0.6.9 to support knowledge repository delivery through the pipeline.

---

## 7. Built-in notification channels

8 files under `backend/channels/builtin/` implementing 7 channel types (each file declares a `channel_name` consumed by `notifications.yaml`).

| `channel_name` | File | Notes |
| --- | --- | --- |
| `pwa_popup_text` | `websocket.py` | Text popup pushed over WebSocket to the senior's PWA. Broadcasts structured JSON payloads; frontend renders as snackbar toasts or persistent dialogs. |
| `pwa_realtime_ai` | `realtime_voice.py` | Queues an interactive voice prompt on the active Gemini Live session (transcript actor: `orchestrator`, hidden from the senior's UI). Two-way: the AI speaks then listens. |
| `pwa_tts_announcement` | `announcement.py` | TTS audio streamed directly to PWA clients via WebSocket as PCM chunks; full-buffer playback on the frontend to avoid gaps. Also supports pre-rendered file mode. |
| `telegram` | `telegram.py` | Caregiver chat alerts via Telegram Bot API. Supports text, single photo, media groups, and per-rule target overrides. |
| `eink` | `eink.py` | Renders an image via the internal `EInkRenderer` and updates `ActiveImageState`. Supports per-device targeting, template selection, and expiry. |
| `ha_speaker_tts` | `tts.py` | Generates audio via `TTSClient`, uploads to MinIO, calls `media_player.play_media` on the configured HA entity (`ha_media_player` in step config; defaults to `media_player.living_room_speaker`). Wakes the speaker before playback. |
| `webhook` | `webhook.py` | Outbound HTTP POST with JSON payload and configurable templating. |

`NotificationDispatcher` accepts a `DispatchServices` bundle containing `minio_client`, `ha_client`, `tts_client`, `ws_manager`, and `image_renderer` so channels never import integration clients directly.

---

## 8. Built-in context filters

13 files under `backend/filters/builtin/`. Each declares a `filter_type` used in `RuleContext.context_type`. Within a `context_type` group, contexts are OR-ed; across groups, AND-ed. Each `RuleContext` has a `negate` flag inverting the filter result.

| `filter_type` | Description |
| --- | --- |
| `room` | Trigger room name match. |
| `time_range` | Wall-clock window in `app.timezone` (HH:MM start, HH:MM end). |
| `day_of_week` | Day-of-week match in `app.timezone`. |
| `person_presence` | "Person is in this room" gate. v2 supports `use_semantic_memory: true` to corroborate via `SemanticMemoryClient.get_transitions`. |
| `person_activity` | Activity recorded for a person within `within_minutes`. |
| `room_transition` | `PersonLocationHistory` query for `direction_semantic` (entering, exiting, approaching_exit, entering_depth, stationary) plus optional `from_room_name` / `to_room_name`. |
| `person_movement_memory` | Same idea as `room_transition` but reads from semantic memory. |
| `scene_contains` | Object label or hazard flag observed in the room within `within_minutes`. Reads `SemanticMemoryClient.get_recent_objects` and `search_observations`. |
| `scene_trend` | Trend severity gate (info, warning, critical) on a room. |
| `home_state` | Filter version of the `home_state` step: home, asleep, away, state_unknown. |
| `presence_status` | Specific `PresenceStatus` value match. |
| `presence_dwell` | Person has dwelled in a room at least `min_dwell_minutes`. |
| `dementia_signal` | CTS signal kind, severity, person IDs, time-of-day window, and acknowledgement cooldown gate. When evaluated from a `dementia_signal` trigger, `sensor` is the event dict (not a SQLAlchemy object); sensor-dependent filters (`room`, `room_transition`, `person_movement_memory`) are skipped automatically by `get_matching_rules_for_event`. |

When a filter needs services (semantic memory, presence, signals), it accesses them through the `services: ServiceContainer | None` keyword passed by `RulesEngine`. Filters that don't need services accept `services=None` and ignore it.

---

## 9. Workflow lifecycle

Triggers are decoupled from rules via `Rule.trigger_types: list[str]` (JSON column). Cron schedules live in a separate `CronTrigger` table with a many-to-many join (`rule_cron_triggers`). A rule can respond to multiple trigger types simultaneously.

```text
edge device  ─►  routers/device.py      ─►  EventAggregator
                                              │
                                              ▼
HA poll      ─►  SensorPollingService   ─►  WorkflowPipeline.process_event
webhook      ─►  routers/webhooks.py    ─►  ▼
telegram cmd ─►  TelegramTriggerService ─►  RulesEngine.matches(rules, ctx)
                                              │
                                              ▼
cron tick    ─►  Scheduler              ─►  for each CronTrigger: find linked rules
  (one job per CronTrigger,                  via rule_cron_triggers → RulesEngine checks
   not per rule)                              contexts, dependencies, rate limits
                                              │
                                              ▼
                                            WorkflowExecution row + EventLog row
                                              │
                                              ▼
                                   step-by-step via StepRegistry.dispatch(step.step_type)
                                              │
                                              ▼
                                   on `wait`: status="waiting", resume_at set; SchedulerBridge schedules a DateTrigger
                                              │
                                              ▼
                                   on `interactive_prompt`: pending row in InteractiveResponse; resumes via the response API
                                              │
                                              ▼
                                   `notification` step → NotificationDispatcher → ChannelRegistry plugins
```

The executor checks `execution.status == "cancelled"` between steps (cooperative cancellation). A per-step timeout (60s default) prevents stuck LLM calls from hanging the pipeline indefinitely. Step timings are recorded in `pipeline_data_json._step_timings` with labels, elapsed seconds, and success/failure status.

`WorkflowExecution` uses optimistic locking (`version` column). `PipelineExecutor` retries on version conflicts with exponential backoff. Status transitions (cancel, timeout) use pessimistic locking (`SELECT ... FOR UPDATE`).

`WorkflowExecution` uses optimistic locking (`version` column). `PipelineExecutor` retries on version conflicts with exponential backoff.

---

## 10. CTS (Continuous Tracking System) integration

CTS lives in `../continuous-tracking/`. Cognitive Companion is the BFF: all browser and MCP traffic reaches the `tracking-orchestrator` and `rtsp-ingress` services only through the CC backend.

### 10.1 Feature flag

`cts.enabled` in `config/settings.yaml`. When false, every CTS router returns `404 {"code": "cts.disabled"}` and the lifespan does not start any CTS subscribers.

### 10.2 CTS shared utilities

Before editing any CTS code, know these four files:

| File | Purpose | Rule |
| --- | --- | --- |
| `backend/routers/cts_deps.py` | `cts_enabled()` | Import it; never redefine `_cts_enabled()` in a router. |
| `backend/services/cts/_time.py` | `ns_to_iso()`, `parse_ts()`, `ensure_aware()` | Import them; never duplicate these helpers in a subscriber or service. |
| `backend/services/cts/_types.py` | `ConnectionManager`, `PipelineExecutor`, `MinioClient`, `SceneAnalysisClient`, `SemanticMemoryClient` protocols + `DBSessionFactory` type alias | Use these protocol types for injected service parameters. Never `Any`. |
| `backend/services/cts/signal_config.py` | `ALL_SIGNAL_KINDS`, `is_signal_enabled(cfg, kind, severity)`, `default_config_for_profile(profile)` | Import from here when checking per-person signal dispatch. Never hardcode the 7 kind strings inline. |

### 10.3 CTS routers (9 files)

| Router | Endpoints |
| --- | --- |
| `cts.py` | `GET /cts/status`, `GET /cts/features`, `GET /cts/frames/{key}` |
| `cts_cameras.py` | CRUD, `test-connect`, `snapshot`, `health`, `reload` (proxies via `IngressAdminClient`) |
| `cts_calibration.py` | OpenCV RANSAC homography fit, privacy zones, adjacency graph |
| `cts_signals.py` | List, ack, unacknowledged, summary, trend (read from `SignalStore`) |
| `cts_keyframes.py` | List, get, retain (proxies via `OrchestratorClient`) |
| `cts_dashboard.py` | Signals + trajectory + dwell summary aggregates |
| `cts_identity.py` | Global tracks, identity corrections, merges, revision log |
| `cts_presence.py` | Read/reload `presence.yaml`, `GET /cts/{person_id}` snapshot |
| `cts_live.py` | `WS /ws/cts` live tracking stream |\n| `cts_trajectory.py` | Proxy `GET /api/v1/cts/trajectory/recent` from orchestrator |

All handlers call `cts_enabled()` (imported from `backend.routers.cts_deps`) and return 404 + `{"code": "cts.disabled"}` when off.

### 10.4 CTS runtime

`backend/services/cts/runtime.py` is `CTSRuntime`, started in the lifespan when `cts.enabled` is `true`. It owns four subscribers (Redis Streams consumer groups) and a `LocationWriter`:

| Subscriber | Stream | Effect |
| --- | --- | --- |
| `TrackingEventSubscriber` | `tracking.events` | Updates `PersonLocationState` and writes `PersonLocationHistory` via `LocationWriter` and `SourceAuthority` (CTS-precedence lock for `cts.lock_seconds`). Broadcasts `cts_live_frame` WebSocket messages for the live view. |
| `IdentityRevisionSubscriber` | `tracking.revisions` | Soft-deletes superseded `PersonLocationHistory` rows via `IdentityRewriter` and inserts the corrected entries. |
| `DementiaSignalSubscriber` | `tracking.signals` | Persists `DementiaSignal` rows via `SignalStore.upsert()`. Before calling `pipeline.fire_event`, checks `HouseholdMember.cts_alert_config` for the person via `is_signal_enabled()` (`backend/services/cts/signal_config.py`). If the kind or severity is disabled for that person, the signal is stored but no pipeline event is fired. |
| `SceneSampleSubscriber` | `scene.samples` | Decodes tagged keyframe `SceneSample` proto messages, pulls JPEG from MinIO, runs scene analysis (YOLO + Florence-2 + CLIP + hazards), and persists observations to semantic memory. |

`StreamConsumer` (in `stream_consumer.py`) is the shared base class: consumer-group creation, `XAUTOCLAIM` reclaim, bounded semaphore, graceful shutdown. All four subscribers decode protobuf-encoded messages from the `backend/integrations/proto/continuoustracking/v1/` package, compiled from `.proto` sources in the `continuous-tracking/` repository.

`SignalStore` reads use `db = self._db_factory(); try / finally db.close()`; never the context-manager form, because the conftest `db_factory` returns a plain `Session`.

### 10.5 Identities and presence

`PresenceService` (Block 3 chain in `config/presence.yaml`): provider order is `night_anchor`, `ha_bed_sensor`, `cts_location`, `ha_device_tracker`, plus stale fallback / unknown sentinel. Build with `services/presence/factory.py`. The `PresenceQueryHandler` step + `presence_status` / `presence_dwell` / `home_state` filters read this service.

### 10.6 Per-person CTS alert configuration

`HouseholdMember.cts_alert_config` is a nullable JSONB column (migration `0012_cts_alert_config`) that controls which dementia signal kinds and minimum severity a person receives. `NULL` means all kinds at `info` severity (permissive default).

```python
# Shape of cts_alert_config
{
    "enabled_kinds": ["absence", "nighttime_movement", "stillness_anomaly"],
    "min_severity": "info"   # "info" | "warning" | "emergency"
}
```

Three built-in profiles (from `signal_config.py`):

| Profile | `enabled_kinds` |
| --- | --- |
| `senior` | All 7 kinds |
| `adult` | `absence`, `nighttime_movement`, `stillness_anomaly` |
| `guest` | `absence` only |

**Three-layer enforcement:**

1. **Subscriber dispatch gate** (`DementiaSignalSubscriber._is_dispatch_enabled`): signals are always persisted to DB for history, but `pipeline.fire_event` is only called when `is_signal_enabled(member.cts_alert_config, kind, severity)` returns `True`.
2. **API read filter** (`cts_signals.py:_filter_by_person_config`): `GET /cts/signals` and `GET /cts/signals/unacknowledged` load all household member configs in one query and filter the response list, keeping the Alerts UI quiet.
3. **Pipeline rule gate** (`RulesEngine.get_matching_rules_for_event`): rules with `trigger_type="dementia_signal"` receive an event dict (not a `Sensor` ORM object). Sensor-dependent filters (`room`, `room_transition`, `person_movement_memory`) are skipped; other filters including `dementia_signal` are evaluated normally.

`PipelineExecutor.fire_event(source, kind, payload)` calls `rules_engine.get_matching_rules_for_event(event, kind, db)` and executes each matched rule through the normal `PipelineExecutor.execute` path. `rules_engine` is injected at construction time from `backend/main.py`.

The enrollment dialog in `PersonsView.vue` captures the alert profile (`Senior / Adult / Presence only / Custom`) when creating or editing a household member. Profile picker maps to `cts_alert_config` via `onProfileChange()` and is stored through the `HouseholdMemberCreate` / `HouseholdMemberUpdate` schemas.

### 10.7 Don't

- Don't write to CTS tables (`dementia_signals`, `cts_cameras`, etc.) outside the `services/cts/` package.
- Don't import `_upstream_base` from non-CTS code (it does mTLS + EdDSA service JWTs; LAN clients use `_http_base`).
- Don't subscribe to `tracking.*` or `scene.*` streams outside `CTSRuntime`.
- Don't bypass the BFF: there is no path from the browser or MCP to `rtsp-ingress` or `tracking-orchestrator` except through CC routers.
- Don't duplicate `_cts_enabled()`, `_ns_to_iso()`, or `_parse_ts()`. Import from the shared modules.
- Don't use `Any` for CTS-injected service parameters. Use the protocols in `backend/services.cts._types`.
- Don't hardcode the 7 signal kind strings anywhere outside `signal_config.py`. Import `ALL_SIGNAL_KINDS` from there.

---

## 11. LLM subsystem

```text
backend/integrations/llm/
├── base.py            LLMProvider ABC + RealtimeLLMProvider
├── openai_compat.py   OpenAICompatibleProvider for /v1/chat/completions (vLLM, llama.cpp)
├── ollama.py          OllamaProvider for /api/chat
├── gemini_live.py     GeminiLiveProvider for realtime audio
├── chain.py           LLMProviderChain (failover) + LLMProviderPool (round-robin)
└── __init__.py        LLMModelConfig, LLMModelRegistry, get_provider helpers
```

`LLMModelRegistry` is loaded from `llm.models` in `settings.yaml` and exposed as `app.state.llm_model_registry`. The `llm_call` step picks a model by `model_id`. Each entry declares `id`, `name`, `api_type` (`openai` or `ollama`), `base_url`, `model`, `capabilities` (`text` / `vision` / `translation`), `guided_decoding`, `max_tokens`, `timeout`.

For vLLM, `guided_decoding=true` sends the JSON schema as the `guided_json` request field. For llama.cpp, set `guided_decoding=false` and the schema is appended to the prompt.

`GET /api/v1/pipeline/llm-models` returns the registry metadata for the StepConfigDialog dropdown.

---

## 12. MCP

`backend/mcp/server.py` defines the FastMCP tool registry. Each tool is an `@_register` async function; type hints auto-generate JSON schemas. The registry currently holds 39 tools including: presence and location tools (`get_person_locations`, `get_person_location`, `get_tracking_status`), CTS signal tools (`get_recent_dementia_signals`), room and sensor tools (`get_rooms`, `get_sensors`, `get_room_occupancy`), scene and semantic memory tools (`get_recent_scene_objects`, `get_scene_observations`, `get_person_movements`, `get_room_trend`, `search_similar_scenes`), knowledge repository tools (`query_knowledge_base`, `get_current_quiz_question`, `submit_quiz_answer`, `complete_quiz_session`), rule-authoring tools (`list_rules`, `list_plugin_metadata`, `get_rule_bundle`, `import_rule_bundle`), and others. The authoritative list is in `mcp.tools` in `settings.yaml`. A subset is mirrored to Gemini Live in `mcp.gemini_tools`.

MCP tools and BFF router endpoints share one service layer (D6): a tool calls a service method and adapts the result; it never queries a repository directly. Import-linter contracts enforce that `backend.mcp` may not import from `backend.models` directly.

The rule-authoring MCP tools enable AI agents to read, create, and import rules:
- `list_rules()`: returns rule summaries (name, description, enabled, trigger_types)
- `list_plugin_metadata(kind)`: returns full metadata (config_schema, output_schema, default_config) for every registered step, filter, or channel, so agents can construct syntactically valid pipelines
- `get_rule_bundle(rule_id)`: exports a rule as a portable `RuleBundle` dict
- `import_rule_bundle(bundle, mode)`: validates (`mode="preview"`) or commits (`mode="commit"`) a bundle, returning the same `ImportReport` the UI shows

Auth is enforced by the ASGI middleware in `backend/mcp/middleware.py`. Permission patterns under `mcp_readonly` cover `GET /mcp*` and `POST /mcp*`.

`backend/mcp/gemini_adapter.py` bridges MCP tools to Gemini Live function calling. Backend-authored prompts dispatched through the `pwa_realtime_ai` channel are tagged as `orchestrator` turns and excluded from the senior's transcript.

---

## 13. Camera topology

Per-sensor `movement_map` in `Sensor.config_json`:

```yaml
movement_map:
  left-to-right: entering
  right-to-left: exiting
  towards-camera: approaching_exit
  away-from-camera: entering_depth
  stationary: stationary
```

`infer_room_transition()` in `services/camera_topology.py` reads this and returns a frozen `RoomTransition`. The `room_transition` filter queries `PersonLocationHistory`; the `person_movement_memory` filter queries the equivalent rows in semantic memory.

---

## 14. E-ink display pipeline

1. A pipeline's `notification` step includes `eink` in channels.
2. `NotificationDispatcher` calls `EInkRenderer.render(text, template, sensor_ids)`.
3. The renderer resolves the template (DB or filesystem), renders text into regions via PIL, saves per-device PNGs, updates `ActiveImageState`.
4. Devices poll `GET /api/v1/image/active` with their device key.

Refresh suppression: on each poll, the endpoint computes a SHA-256 of the PNG it would serve. If it matches `last_served_hash` and `last_served_at` is within `image.refresh_window_minutes` (default 60), it returns `204 No Content` and the device skips its disruptive full-pixel refresh. Set `refresh_window_minutes: 0` to disable.

---

## 15. Webhook and Telegram triggers

Webhook: `POST /webhooks/{rule_id}` with `X-Webhook-Secret`. HMAC-checked against `Rule.webhook_config.secret`. Generate or rotate the secret via `POST /webhooks/{rule_id}/generate-secret`.

Telegram command: rules with `trigger_type="telegram"` are matched by `TelegramTriggerService` polling the Bot API on a scheduler interval (`notifications.telegram.trigger_poll_interval_seconds`, default 5s). Started only when `telegram_client.configured`. `Rule.telegram_trigger_config`:

| Field | Meaning |
| --- | --- |
| `command` | e.g. `/medication`. Case-insensitive. Omit to match any command. |
| `allowed_chat_ids` | Per-rule whitelist. Falls back to `notifications.telegram.trigger_allowed_chat_ids`. **Empty or absent = BLOCKED (fail-closed).** |
| `respond_with_ack` | Default true; sends a one-line ack. |

The Telegram message is exposed as `pipeline_data["trigger_input"]` with `command`, `args`, `text`, `chat_id`, `from_user`. `TriggerContext.trigger_type` is `"telegram"`.

---

## 16. Testing conventions

Framework: `pytest` + `pytest-asyncio` (`asyncio_mode = "auto"`). Tests mirror `backend/` layout (`backend/tests/services/test_rules_engine.py`, etc.).

Fixtures (`backend/tests/conftest.py`): `db_engine`, `db_session`, `db_factory`, all backed by a PostgreSQL testcontainer. Do not mock the DB; mocks let migration drift through.

| What you are testing | Pattern |
| --- | --- |
| Step handler | `@dataclass class _FakeStep` instead of `PipelineStep`. SQLAlchemy instrumentation breaks when you set mapped attributes on objects created with `__new__`. Call `assert_output_conforms_to_schema(handler, result)` from `backend/steps/_testing.py`. |
| Plugin contract | `test_registry_contract.py` validates every registered handler's config_schema, default_config, output_schema, naming conventions, and icon. Run as part of `make check`. |
| Expression grammar | `test_template_grammar.py` covers parsing, evaluation, functions, and template rendering. Use `parse_expression()` and `_eval()` for unit tests of specific AST nodes. |
| `ServiceContainer` | Pass only the fields the step uses; everything else defaults to `None`. |
| Router | New `FastAPI()` + `register_exception_handlers(app)` + `app.dependency_overrides[get_auth_context]`. Use `StaticPool` so tables persist across the test connections. |
| Class-level property | Local subclass; never `type(obj).prop = property(...)`. Class mutation leaks. |
| Filter | `RulesEngine(tz_name="UTC")` to keep timestamp comparisons aligned with the testcontainer's UTC values. |
| `SignalStore` | Inject the conftest `db_factory` (returns plain `Session`). |
| `DementiaSignalSubscriber` | Test `decode()` and `handle()` directly; no real Redis. For dispatch suppression tests, insert a `HouseholdMember` with `cts_alert_config` using `db_factory` and pass it to the subscriber constructor. |
| `DementiaSignalFilter` | `db_session` fixture for cooldown tests; `db=None` for non-cooldown. |
| Integration | Tests under `backend/tests/integration/` use mocked HTTP via `unittest.mock.patch("backend.integrations.<module>.httpx.AsyncClient")`. |

`make check` is the fast pre-commit gate. `make check-all` adds `backend.services` and is the gate for service or shared-infra changes. Frontend has a small spec set under `frontend/src/views/admin/__tests__/`.

### 16.1 Code review checklist

Every code change must pass these gates. Check off each item before opening a PR.

**Gate 1: Automated checks**

- [ ] `make check` passes (lint + strict mypy on core + core tests)
- [ ] `make check-all` passes if services or schemas changed
- [ ] `make typecheck` passes on every module touched
- [ ] `cd frontend && npm run build` passes (frontend changes only)
- [ ] `cd frontend && npm run test` passes (new step/filter types only)

**Gate 2: Test coverage**

- [ ] New public classes, methods, and endpoints have mirrored tests under `backend/tests/<mirror_path>/`
- [ ] Step handlers, channels, and filters each have: success path, missing-service path, and at least one config-edge-case test
- [ ] New step handlers call `assert_output_conforms_to_schema(handler, result)` in their tests
- [ ] New step handlers are enumerated in `test_registry_contract.py`
- [ ] Tests follow Arrange-Act-Assert structure with blank lines between blocks
- [ ] No mocks for the database (use testcontainer fixtures)

**Gate 3: Types and boundaries**

- [ ] Results returned to callers use `@dataclass(frozen=True)` or Pydantic models, not raw dicts
- [ ] No `dict[str, Any]` leaking out of integration clients (use typed return values)
- [ ] Pydantic Create/Update schemas use `model_config = {"extra": "forbid"}`
- [ ] No `Optional[str]` (use `str | None` per PEP 604)

**Gate 4: Data integrity**

- [ ] External datetimes pass through `backend.core.time.normalize_utc_datetime()` before storage
- [ ] Outbound datetimes serialize with `.astimezone(UTC).isoformat()`
- [ ] Schema changes use Alembic (`make migration`); autogenerated migration reviewed by hand
- [ ] No `print()`, no `eval()` for conditions (use `evaluate_condition()` from `backend.core.template`)

**Gate 5: Security and config**

- [ ] Every new endpoint has an `auth.yaml` permission entry
- [ ] Secrets use `${ENV_VAR}` interpolation in YAML, never inlined
- [ ] No secrets logged (no `logger.info("key", secret=api_key)`)

**Gate 6: Resilience**

- [ ] Integration clients return `None`, `[]`, or typed zero values when upstream is disabled or unreachable
- [ ] No exceptions bubble from integration clients
- [ ] Every integration call has at least one structured log event (success or failure)

### 16.2 Iterating during development

Run the targeted slice instead of the full suite:

```bash
uv run --project backend pytest backend/tests/steps/test_<your_step>.py -v
uv run --project backend pytest backend/tests/services/test_<your_service>.py -v
uv run --project backend pytest backend/tests/routers/test_<your_router>.py -v
```

Use `uv run --project backend ruff check backend/<changed_path>` for a fast lint pre-check before `make check`. Use `make typecheck` (full tree) only after the slice is green.

---

## 17. Common tasks

### 17.1 Add a pipeline step type

Use the scaffolding CLI for boilerplate:

```bash
uv run --project backend python -m backend.steps._scaffold new your_step --category action
```

This generates `backend/steps/builtin/your_step.py` and `backend/tests/steps/test_your_step.py`.

Or write manually:

```python
# backend/steps/builtin/your_step.py
from backend.steps import StepRegistry
from backend.steps.base import StepHandler, StepMetadata, StepResult

@StepRegistry.register
class YourStepHandler(StepHandler):
    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="your_step",
            display_name="Your Step",
            category="action",
            icon="mdi-star",
            description="What this does.",
            config_schema={"type": "object", "properties": {...}},
            default_config={...},
            # New fields:
            output_schema={              # REQUIRED for data-emitting steps
                "type": "object",
                "properties": {
                    "your_key": {"type": "string", "description": "Result value"},
                },
            },
        )

    async def execute(self, step, execution, pipeline_data, trigger, services) -> StepResult:
        return StepResult(data={"your_key": "value"})
```

The step appears in the StepPalette via `GET /pipeline/step-types`. For a custom config form, use the `x-ui` hints in `config_schema` (consumed by `SchemaForm.vue`), or add a `<template v-if>` block in the step config dialog.

Every step handler test must call `assert_output_conforms_to_schema(handler, result)` from `backend/steps/_testing.py`.

### 17.2 Add a notification channel

```python
# backend/channels/builtin/your_channel.py
from backend.channels import ChannelRegistry
from backend.channels.base import NotificationChannel, ChannelMetadata

@ChannelRegistry.register
class YourChannel(NotificationChannel):
    @classmethod
    def metadata(cls) -> ChannelMetadata:
        return ChannelMetadata(channel_name="your_channel", display_name="Your Channel", description="...")

    async def send(self, message, alert_level, room_name, services, **kwargs) -> bool:
        return True
```

Add the channel to `config/notifications.yaml` for routing.

### 17.3 Add a context filter

```python
# backend/filters/builtin/your_filter.py
from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata

@FilterRegistry.register
class YourFilter(ContextFilter):
    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(filter_type="your_filter", display_name="Your Filter", description="...", config_schema={...})

    def evaluate(self, config, sensor, now, db=None, *, services=None) -> bool:
        return True
```

Add a form template in `frontend/src/views/admin/RuleDetailView.vue` for the new filter's config fields. Negation is handled by `RulesEngine`; filters do not need to.

### 17.4 Add an API endpoint

1. Edit or create a router in `backend/routers/`.
2. Add or extend Pydantic schemas in `backend/schemas/`.
3. Register the router in `backend/main.py` (`create_app`).
4. Add permission patterns in `config/auth.yaml`.
5. Add router tests under `backend/tests/routers/` following the override pattern in section 16.

### 17.5 Add a database model

1. Define under `backend/models/` (subclass `Base`).
2. Re-export in `backend/models/__init__.py` (so `Base.metadata` is populated).
3. `make migration` to autogenerate, review the file, then `make migrate`.

### 17.6 Add an MCP tool

1. Add an `@_register` async function in `backend/mcp/server.py` with full type hints.
2. Add the tool name to `mcp.tools` in `config/settings.yaml`.
3. If voice-callable, also add it to `mcp.gemini_tools`.
4. Add a test under `backend/tests/mcp/`.

### 17.7 Add an LLM model

Append a new entry to `llm.models` in `config/settings.yaml`. The unified `llm_call` step picks it by `id`. Optionally use `LLMProviderChain` or `LLMProviderPool` to compose multiple `base_url`s into a failover chain or a round-robin pool.

---

## 18. External services

| Service | Env var | Required |
| --- | --- | --- |
| PostgreSQL (shared) | `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Required. |
| Person Identification Service | `PERSON_ID_SERVICE_URL` | Face recognition. |
| Scene Analysis Service | `SCENE_ANALYSIS_URL` (settings.yaml) | Optional. YOLO + Florence-2 + CLIP. |
| Semantic Memory Service | `SEMANTIC_MEMORY_URL` (settings.yaml) | Optional. Observations, movements, trends. |
| TTS Service | `TTS_API_URL` | Optional but recommended for audible reminders. |
| Home Assistant | `HOME_ASSISTANT_URL`, `HOME_ASSISTANT_TOKEN` | Sensor polling, area discovery, media-player playback. |
| MinIO | `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` | Required. |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CAREGIVER_CHAT_ID` | Optional. |
| Google Gemini | `GEMINI_API_KEY` | Optional. Required only for the realtime voice companion. |
| vLLM (vision) | `VISION_MODEL_URL` | Required for vision steps. |
| llama.cpp (reasoning) | `GEMMA_MODEL_URL` (or `LOGIC_MODEL_URL`) | Required for general reasoning. |
| Triton Inference Server | `embedding.tokenizer_path`, `embedding.service_url` (settings.yaml) | Required for knowledge repository RAG embeddings. |
| Tracking Orchestrator | `TRACKING_ORCHESTRATOR_URL` (+ `cts.upstream.tracking_orchestrator`) | Required when `cts.enabled=true`. |
| RTSP Ingress | `CTS_INGRESS_URL` (+ `cts.upstream.rtsp_ingress`) | Required when `cts.enabled=true`. |
| Redis | `redis.url` (settings.yaml) | Required when `cts.enabled=true`. |

---

## 19. What NOT to do

**Logging and console.**
- Do not use `print()`. Use `get_logger()`.
- Do not use printf-style `%s` or `.format()` in log calls. Use `key=value` kwargs.

**Error handling.**
- Do not catch `AuthenticationError` or `PermissionDeniedError` in routers.
- Do not use `eval()` for conditions. Use `evaluate_condition()` from `backend.core.template` (Lark-based grammar).
- Do not use bare condition expressions without `{{ }}` wrapping. The old `ConditionEvaluator` has been deleted.
- Do not access `self._pipeline_executor._services` from other services. Use the public `PipelineExecutor.event_aggregator` property.
- Do not use bare `except:` or `except Exception: pass`. Log and return a zero value or re-raise as AppError.

**Architecture and layering.**
- Do not instantiate services in routers. Read from `request.app.state`.
- Do not import `_upstream_base` from non-CTS code.
- Do not write to CTS tables (`dementia_signals`, `cts_cameras`) outside `services/cts/`.
- Do not add new callers of the deprecated `services.person_tracking` or `services.activity_session_service`. Use `services.activity` (`ActivityService`).
- Do not import `ObjectTrendClient` or `backend.integrations.object_trend_client`. Use `SemanticMemoryClient` from `backend.integrations.semantic_memory_client`.
- Do not duplicate `_cts_enabled()`, `_ns_to_iso()`, or `_parse_ts()`. Import from `backend.routers.cts_deps` or `backend.services.cts._time`.
- Do not use `Any` for injected service parameters in CTS code. Use the protocol types in `backend.services.cts._types`.
- Do not hardcode `'#4CAF50'`, `'#FFC107'`, or `'#fff'` in Vue templates. Use `var(--cc-*)` design tokens or Vuetify theme colors.
- Do not duplicate `severityColor` or `formatRelative` in views. Import from `frontend/src/composables/`.

**Database.**
- Do not run structural migrations by hand in production. Always use Alembic via `make migrate`.

**Config and secrets.**
- Do not store secrets in YAML config. Use `${ENV_VAR}`.
- Do not hardcode timezone strings. Use `settings.get("app.timezone")`.
- Do not hardcode pipeline ordering. Each rule defines its own `PipelineStep` rows.

**Dependencies.**
- Do not add a runtime dependency without updating `pyproject.toml` and running `uv lock` (or `package.json` + `npm install` for the frontend).
- Do not use lazy imports for required deps (PEP 8). Optional deps (e.g. `google-genai`) may use guarded lazy imports with a comment.

**Frontend.**
- Do not use `alert()` or `confirm()` in Vue. Use the `useNotify` and `useConfirm` composables.
- Do not call `toLocaleString()`/`toLocaleDateString()`/`toLocaleTimeString()` directly. Use `services/timezone.js`.

**Tests.**
- Do not mutate a class-level property in tests with `type(obj).prop = property(...)`. Use a local subclass.
- Do not mock the database. Use the testcontainer fixtures (`db_session`, `db_factory`, `db_engine`).

**Documentation.**
- Do not write em-dashes ( -- ) in `.md` files. Use colons, commas, semicolons.

---

## 20. Where to look when stuck

| You want to ... | Read |
| --- | --- |
| Understand startup wiring | `backend/main.py` (lifespan) |
| Add a step type | `backend/steps/base.py`, an existing builtin like `backend/steps/builtin/scene_analysis.py`, run `python -m backend.steps._scaffold new` |
| Trace a rule firing | `backend/services/workflow.py` then `rules_engine.py` then `pipeline_executor.py` |
| Debug a condition / expression | `backend/core/template_grammar.lark` (grammar), `template_ast.py` (parser), `template_interpreter.py` (evaluator) |
| Understand trigger dispatch | `backend/services/scheduler.py` (cron via CronTrigger), `backend/services/rules_engine.py` (sensor/occupancy), `backend/models/cron_trigger.py` (schema) |
| Export or import rules | `backend/services/rule_serializer.py`, `backend/schemas/rule_bundle.py`, `backend/core/plugin_migrations.py` |
| Understand CTS data flow | `backend/services/cts/runtime.py`, then the four subscribers, then `services/cts/location_writer.py` |
| Understand presence fusion | `backend/services/presence/factory.py`, `service.py`, `anchor_rules.py`, plus `config/presence.yaml` |
| Add an external HTTP client | `backend/integrations/_http_base.py` (LAN) or `_upstream_base.py` (CTS only) |
| Understand knowledge surface | `cc-rag.md` (design), `backend/services/knowledge/` (services), `backend/routers/knowledge*.py` (REST) |
| Understand voice delivery | `backend/websocket/audio_handler.py`, `backend/services/knowledge/delivery_service.py` |
| Debug embedding issues | `backend/integrations/triton_embedding_client.py`, `triton-shared/triton_shared/models/embedder.py` |
| Understand knowledge repository | `cc-rag.md` (design), `backend/services/knowledge/` (services), `backend/routers/knowledge.py`, `info_cards.py`, `quizzes.py` (REST) |
| Understand info card / quiz pipeline steps | `backend/steps/builtin/info_card.py`, `backend/steps/builtin/quiz_start.py` |
| Understand MCP rule authoring | `backend/mcp/server.py` (list_plugin_metadata, get_rule_bundle, import_rule_bundle) |
| Find the canonical config | `config/settings.yaml` (loaded fresh on every lifespan) |

---

## 21. Knowledge repository operator runbook

### 21.1. Triton embedding model rollover

The embedding model (`embeddinggemma-300m`) runs on Triton Inference Server.
To upgrade or replace it:

1. **Deploy the new model** to the Triton model repository at the path
   configured in `settings.yaml` (`embedding.tokenizer_path`). The model
   directory must contain:
   ```
   embeddinggemma-300m/
       config.pbtxt
       1/model.onnx
       1/tokenizer.json
   ```

2. **Verify the embedding dimension.** If the new model outputs a different
   dimension (e.g. 512 instead of 768):
   - Update `settings.yaml` → `embedding.dim` to the new value.
   - Create a new Alembic migration that runs:
     ```sql
     ALTER TABLE knowledge_document_chunks ALTER COLUMN embedding TYPE VECTOR(N);
     ```
     where N is the new dimension.
   - Drop and recreate the DiskANN index:
     ```sql
     DROP INDEX IF EXISTS knowledge_chunks_embedding_diskann;
     CREATE INDEX knowledge_chunks_embedding_diskann
         ON knowledge_document_chunks
         USING diskann (embedding vector_cosine_ops);
     ```
   - Re-embed all documents: call `POST /api/v1/knowledge/documents/{id}/reembed`
     for every document in `approved` or `chunked` status. A script at
     `scripts/reembed_all.py` can batch this.

3. **Verify the model is ready** before restarting CC:
   ```bash
   curl http://triton.nanai.khoofia.com:8001/v2/models/embeddinggemma-300m/ready
   ```
   Expected response: `200 OK`.

4. **Monitor the re-embed job.** CC has a scheduler job
   (`knowledge_reembed_retry`) that retries documents stuck in `uploaded`
   status every 10 minutes. Check logs for `chunk_embed_complete` and
   `reembed_stuck_complete` events.

### 21.2. Embedding similarity threshold calibration

The `knowledge.min_similarity` setting (default 0.55) controls the cosine
similarity floor for RAG answers. If seniors are getting too many "I don't
know" responses, lower it. If answers are inaccurate, raise it.

A calibration notebook at `scripts/calibrate_similarity.py` embeds a set
of test queries against known documents and reports the similarity
distribution. Run it after model changes:
```bash
uv run python scripts/calibrate_similarity.py
```

### 21.3. Voice instruction debugging

Voice instructions follow the 3-layer composition rule (section 6.5 of
`cc-rag.md`): step override → resource column → yaml default → base only.

To debug what instruction is active:
- Check the `voice_instruction` column on `info_cards` or `quizzes`.
- Check the step's `config_json.voice_instruction` in `pipeline_steps`.
- Check `config/knowledge_voice.yaml` for the per-type default.
- Check `config/settings.yaml` → `llm.realtime.system_instruction` for
  the base instruction.
- Structured logs emit `ws_voice_instruction_changed` when the handler
  reconnects with a new instruction.

### 21.4. pgvector index maintenance

The DiskANN index on `knowledge_document_chunks.embedding` requires
periodic reindexing after large bulk inserts. The `pgvectorscale`
extension handles this automatically for incremental inserts, but
after importing >1000 documents:

```sql
REINDEX INDEX CONCURRENTLY knowledge_chunks_embedding_diskann;
```

This is non-blocking and can run during normal operation.

### 21.5. MinIO orphan reconciliation

Image cleanup follows the DB-first, MinIO-second contract (section 6.5.5
of `cc-rag.md`). A nightly reconciler script compares MinIO prefixes
against DB rows:

```bash
uv run python scripts/scrub_minio_orphans.py
```

Run this after any incident where MinIO cleanup partially failed (check
logs for `image_purge_partial` events). The `pending_image_purges` gauge
on the admin metrics surface shows unreconciled prefixes.
