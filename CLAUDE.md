# Cognitive Companion — Claude guidance

Privacy-first, on-premise AI system for senior care. Python 3.12 FastAPI backend, Vue 3 + Vuetify frontend, SQLite database, plugin-based pipeline execution.

---

## Commands

```bash
# Run backend (development)
uv run --project backend uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Run frontend (development)
cd frontend && npm run dev          # http://localhost:5173
cd frontend && npm run build        # production build

# Run all backend tests
make test                           # or: uv run --project backend pytest backend/tests

# Run targeted test suites
make test-core                      # backend/core only
make test-services                  # backend/services only

# Coverage
make coverage                       # core layer (terminal)
make coverage-services              # services layer (terminal)
make coverage-html                  # writes htmlcov/index.html

# Lint / format
make lint                           # ruff check (no fixes)
make lint-fix                       # ruff check --fix
make format                         # ruff format

# Type checking
make typecheck-core                 # strict mypy on backend.core only
make typecheck                      # full backend tree

# Pre-commit gate (fast)
make check                          # lint + typecheck-core + test-core
make check-all                      # lint + typecheck-core + test (all)

# Docker
docker compose up -d                # backend (8000) + frontend (80)
docker compose build --no-cache     # rebuild images
```

---

## Architecture

### Backend layers

```
backend/core/          Foundational layer — no upward dependencies
backend/models/        SQLAlchemy ORM models
backend/schemas/       Pydantic request/response models
backend/services/      Business logic
backend/steps/         Pipeline step plugin system
backend/channels/      Notification channel plugin system
backend/filters/       Context filter plugin system
backend/integrations/  External service clients (HA, MinIO, Telegram, TTS, LLMs)
backend/routers/       FastAPI route handlers
backend/mcp/           MCP tool server (official SDK)
backend/websocket/     WebSocket connection + audio handler
backend/main.py        App factory, lifespan, plugin discovery, service wiring
```

**core/ invariant**: `backend.core` has zero upward dependencies. It must not import from services, routers, steps, channels, or filters.

### Service injection

Services are instantiated in the FastAPI lifespan (`backend/main.py`) and attached to `app.state`. Routers access them through `request.app.state.<service>`. Never instantiate services inside routers.

```python
# In a router:
executor = request.app.state.pipeline_executor
```

### Plugin systems

Three auto-discovered plugin registries, each following the same pattern:

**StepRegistry** (`backend/steps/`)
- Add a file to `backend/steps/builtin/` or `backend/steps/contrib/`
- Class inherits `StepHandler`, decorated with `@StepRegistry.register`
- Implement `metadata()` classmethod and `execute()` async method
- Auto-discovered at startup via `StepRegistry.discover()`

**ChannelRegistry** (`backend/channels/`)
- Same pattern; inherits `NotificationChannel`, `@ChannelRegistry.register`

**FilterRegistry** (`backend/filters/`)
- Same pattern; inherits `ContextFilter`, `@FilterRegistry.register`
- Current filters: `room`, `time_range`, `day_of_week`, `person_presence`, `person_activity`, `room_transition`, `scene_trend`, `dementia_signal`

### Step handler contract

```python
@StepRegistry.register
class YourStepHandler(StepHandler):
    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="your_step",
            display_name="Your Step",
            category="perception",   # perception | reasoning | action | flow
            icon="mdi-icon-name",
            description="What this step does.",
            config_schema={...},
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
        # Read from pipeline_data (upstream results) and config (step settings).
        # Access shared services via services.{client}.
        return StepResult(data={"your_key": result})
```

`ServiceContainer` fields (in `backend/steps/base.py`): `db_factory`, `ha_client`, `minio_client`, `telegram_client`, `tts_client`, `ws_manager`, `notification_dispatcher`, `person_tracking`, `person_id_client`, `scene_analysis_client`, `llm_model_registry`, `rag_lookup`, `eink_renderer`, `event_aggregator`, `activity_session_service`, `activity_timeline_service`, `daily_report_service`, `object_trend_client`.

---

## Database

SQLAlchemy 2.0 ORM, SQLite (WAL mode). `Database` class in `backend/core/database.py` owns the engine and session factory.

**No migrations.** For schema changes:
- New tables or dropped columns: delete `data/cognitive_companion.db` and restart. Tables are auto-created from ORM models.
- New nullable columns on existing tables: add an `ALTER TABLE ... ADD COLUMN` statement to `_COLUMN_MIGRATIONS` in `backend/core/database.py`. `Database.create_all()` runs these at startup.

**Session usage:**

```python
from backend.core.database import get_session
db = get_session()
try:
    # queries
finally:
    db.close()
```

**In tests**, construct an isolated `Database` directly:

```python
from backend.core.database import Database
db = Database("sqlite:///:memory:")
sess = db.session()
```

---

## Configuration

YAML files in `config/` with `${ENV_VAR}` interpolation:

```python
from backend.core.config import settings
url = settings.get("person_id.url")
interval = settings.get("homeassistant.poll_interval_seconds", 30)
```

**In tests**, construct directly without touching disk:

```python
from backend.core.config import Settings
s = Settings.from_dict({"llm": {"model": "fake"}})
```

Key config files:
- `config/settings.yaml` — all application settings
- `config/auth.yaml` — API keys, device keys, fnmatch permission map
- `config/notifications.yaml` — alert level to channel routing

---

## Authentication

Keys resolved from `X-API-Key` header, `?api_key` query param, or `device_key` in JSON body. Permissions use fnmatch patterns from `config/auth.yaml`. Every new endpoint needs entries in `auth.yaml`.

```python
from backend.core.auth import require_permission
@router.get("/path")
async def endpoint(auth = Depends(require_permission("GET /path"))):
    ...
```

---

## Logging

```python
from backend.core.logging import get_logger
logger = get_logger(__name__)
logger.info("event_processed", sensor_id=sid, rule=rule.name)
# output: "event_processed sensor_id=cam1 rule=Motion Alert"
```

Always use keyword arguments for context. Never use `print()`. Never use printf-style `logger.info("msg %s", value)`.

---

## Error handling

Raise from `backend/core/exceptions.py`:
- `AuthenticationError` → 401
- `PermissionDeniedError` → 403
- `NotFoundError` → 404
- `ConflictError` → 409

Do not catch these in routers. Let global handlers in `register_exception_handlers()` convert them.

---

## Testing

- Framework: `pytest` + `pytest-asyncio` (asyncio_mode = "auto" — all `async def` test methods run without decoration)
- Fixtures: `db_engine`, `db_session`, `db_factory` in `backend/tests/conftest.py` (in-memory SQLite)
- Structure: mirrors `backend/` (e.g., `backend/tests/services/test_rules_engine.py`)
- Run: `make test` or `uv run --project backend pytest backend/tests`

**Key conventions:**

- Use `RulesEngine(tz_name="UTC")` in tests to avoid timezone mismatches with naive-UTC values in the in-memory SQLite DB.
- Do not mock the database — use the in-memory fixture. Mocking DB leads to integration gaps.
- For step handler tests: use `@dataclass class _FakeStep` instead of `PipelineStep`. SQLAlchemy instrumentation breaks when you set mapped attributes on objects created with `__new__`.
- For `ServiceContainer`: pass only the fields your step uses. The rest default to `None`.
- When overriding a class-level property in tests, use a local subclass — never `type(obj).prop = property(...)`. Class mutation leaks between test instances.
- For router tests, override `get_auth_context` (not `require_permission`): `app.dependency_overrides[get_auth_context] = lambda: AuthContext(key="x", name="tester", permissions=["*"])`. `require_permission` is a factory returning a closure; overriding the factory has no effect.
- For router tests with SQLite in-memory: use `poolclass=StaticPool` from `sqlalchemy.pool`. Without it, SQLAlchemy may open new connections (each a fresh empty DB), so tables created by `create_all` vanish.
- Always call `register_exception_handlers(app)` on every test `FastAPI()` instance. Bare apps lack the CC handlers; `NotFoundError` and `ConflictError` produce 500s instead of 404/409.

---

## Timezone

Single source of truth: `app.timezone` in `config/settings.yaml` (IANA format, e.g. `"America/New_York"`).

| Concern | Rule |
|---------|------|
| Database storage | All timestamps stored as naive UTC. Use `datetime.now(UTC)`. |
| Timezone source | Always `settings.get("app.timezone", "UTC")`. Never hardcode. |
| ZoneInfo | `from zoneinfo import ZoneInfo` (stdlib). Never `pytz`. |
| Local time | `datetime.now(ZoneInfo(tz_name))` for wall-clock values. |
| UTC comparison from local | `local_dt.astimezone(UTC).replace(tzinfo=None)` for SQLite queries. |
| Cron scheduling | Pass `timezone=ZoneInfo(tz_name)` to every `CronTrigger.from_crontab()`. |
| Context filters | `now` passed to `evaluate()` must already be in app timezone. `RulesEngine` ensures this. |

Frontend timezone: fetched at startup from `GET /api/v1/admin/app-info`, stored in `frontend/src/services/timezone.js`. Never call `toLocaleString()` directly.

---

## Pipeline step types (current)

Registered step types (13 total, each with its own file in `backend/steps/builtin/`):

| Type | File | Category |
|------|------|----------|
| `llm_call` | `llm_call.py` | reasoning |
| `person_identification` | `person_identification.py` | perception |
| `scene_analysis` | `scene_analysis.py` | perception |
| `notification` | `notification.py` | action |
| `ha_action` | `ha_action.py` | action |
| `activity_detection` | `activity_detection.py` | action |
| `activity_session_start` | `activity_session_start.py` | action |
| `activity_session_end` | `activity_session_end.py` | action |
| `daily_report` | `daily_report.py` | action |
| `object_trend_analysis` | `object_trend_analysis.py` | perception |
| `verification` | `verification.py` | reasoning |
| `condition` | `condition.py` | flow |
| `wait` | `wait.py` | flow |

Note: `logic_reasoning`, `translation`, and `vision_analysis` step types were removed; use `llm_call` with the appropriate `output_key` instead.

---

## Key integrations

| Client | File | Notes |
|--------|------|-------|
| `HomeAssistantClient` | `integrations/homeassistant.py` | REST API + long-lived token |
| `PersonIDClient` | `integrations/person_id_client.py` | Face recognition microservice |
| `SceneAnalysisClient` | `integrations/scene_analysis_client.py` | YOLO+Florence-2+CLIP microservice; `enabled` gates all calls |
| `MinioClient` | `integrations/minio_client.py` | S3-compatible media storage |
| `TelegramClient` | `integrations/telegram.py` | Caregiver alerts + command triggers |
| `TTSClient` | `integrations/tts.py` | Batch + streaming TTS |
| `EInkRenderer` | `integrations/eink_renderer.py` | PIL-based e-ink image renderer |
| `IngressAdminClient` | `integrations/cts_ingress.py` | CTS ingress proxy: snapshot, health, reload, RTSP test |
| `OrchestratorClient` | `integrations/cts_orchestrator.py` | CTS orchestrator: homography, privacy zones, adjacency, status, keyframes |

LLM providers live in `integrations/llm/`:
- `OpenAICompatibleProvider` — `/v1/chat/completions` (vLLM, llama.cpp)
- `OllamaProvider` — `/api/chat`
- `GeminiLiveProvider` — realtime audio streaming
- `LLMProviderChain` — failover; `LLMProviderPool` — round-robin load balancing
- `LLMModelRegistry` — named model registry used by the `llm_call` step

---

## Camera topology

Per-sensor movement map in `Sensor.config_json`:

```yaml
movement_map:
  left-to-right: entering
  right-to-left: exiting
  towards-camera: approaching_exit
  away-from-camera: entering_depth
  stationary: stationary
```

`infer_room_transition()` in `backend/services/camera_topology.py` reads this map and returns a frozen `RoomTransition` dataclass. The `RoomTransitionFilter` (`backend/filters/builtin/room_transition.py`) queries `PersonLocationHistory` for transitions matching a configured `semantic` and optional room names.

---

## CTS (Continuous Tracking System) Integration

The CTS gateway is a BFF proxy layer for the `tracking-orchestrator` and `rtsp-ingress` microservices. All browser and MCP traffic reaches CTS services only through this backend. Feature-flag gated: `cts.enabled` in `config/settings.yaml`.

### Services and modules

| Module | Purpose |
|--------|---------|
| `services/cts/signal_store.py` | `SignalStore`: async persistence and read API for `DementiaSignal` ORM rows. All methods use `db = self._db_factory(); try/finally db.close()` — never `with self._db_factory() as db:`. |
| `services/cts/subscriber.py` | `DementiaSignalSubscriber`: Redis Streams consumer for `tracking.signals` (consumer group `cognitive-companion-signals`). Decodes JSON, validates required fields, persists via `SignalStore`, fires pipeline events. |
| `services/cts/stream_consumer.py` | `StreamConsumer` base class: consumer-group creation, XAUTOCLAIM reclaim, bounded semaphore, graceful shutdown. Reused by all CTS subscribers. |
| `filters/builtin/dementia_signal.py` | `DementiaSignalFilter`: rule-engine context filter. Matches on signal kind, person ID, severity (0.0-1.0 mapped from info/warning/emergency), time-of-day window, and cooldown (queries `DementiaSignal.acknowledged_at`). |
| `models/cts_signal.py` | `DementiaSignal` ORM model. |
| `models/cts_camera.py` | `CtsCamera` ORM model. |
| `integrations/cts_ingress.py` | `IngressAdminClient`: RTSP test, snapshot, health, reload. |
| `integrations/tracking_orchestrator_client.py` | `OrchestratorClient`: homography, privacy zones, adjacency, calibration status, keyframe list/get/retain. |

### CTS routers

| Router | Endpoints | Notes |
|--------|-----------|-------|
| `routers/cts.py` | `GET /cts/status`, `GET /cts/features` | Feature-flag status |
| `routers/cts_cameras.py` | 9 endpoints: CRUD, test-connect, snapshot, health, reload | Proxies to `IngressAdminClient` |
| `routers/cts_calibration.py` | 6 endpoints: homography, privacy zones, adjacency | OpenCV RANSAC homography fit |
| `routers/cts_signals.py` | 5 endpoints: list, ack, unacknowledged, summary, trend | Reads from `SignalStore` |
| `routers/cts_keyframes.py` | 3 endpoints: list, get, retain | Proxies to `OrchestratorClient` |

All handlers call `_cts_enabled()` first and return 404 + `{"code": "cts.disabled"}` when off.

### Lifecycle wiring

`DementiaSignalSubscriber` is started in `main.py` lifespan inside the `if settings.get("cts.enabled")` block. It is stopped (`.stop()` + task cancel) in the shutdown block. The subscriber is accessible at `app.state.dementia_signal_subscriber`.

### CTS-specific test conventions

- `SignalStore` tests: inject `db_factory` from the conftest `db_factory` fixture (returns a plain `Session`).
- Router tests: override `_get_signal_store` dependency directly with a `SignalStore` backed by an in-memory `StaticPool` engine.
- `DementiaSignalSubscriber` tests: no real Redis needed — test `decode()` and `handle()` directly.
- `DementiaSignalFilter` tests: use `db_session` fixture for cooldown tests; pass `db=None` for non-cooldown tests.

---

## What NOT to do

- Run structural migrations. Delete `data/cognitive_companion.db` and restart instead.
- Use `print()`. Use `get_logger()`.
- Instantiate services inside routers. Access them from `request.app.state`.
- Add dependencies without updating `pyproject.toml` and running `uv lock` (backend) or `package.json` (frontend).
- Skip permission checks. All new endpoints need entries in `config/auth.yaml`.
- Catch `AuthenticationError` or `PermissionDeniedError` in routers.
- Store secrets in config files. Use `${ENV_VAR}` interpolation.
- Use `eval()` for condition expressions. Use `ConditionEvaluator`.
- Use lazy imports for required dependencies (PEP 8). Exception: optional deps (e.g. `google-genai`) may use guarded lazy imports with a comment.
- Use `alert()` or `confirm()` in Vue. Use the `useNotify` and `useConfirm` composables.
- Swallow errors silently. Log with `console.error` (frontend) or `logger.error` (backend).
- Write em-dashes ( -- ) in `.md` files. Use colons, commas, or semicolons instead.
- Call `toLocaleString()` directly in frontend code. Use `services/timezone.js` helpers.
- Mutate a class-level property in tests with `type(obj).prop = property(...)`. Use local subclasses.

---

## External services

| Service | Env var(s) | Required |
|---------|-----------|----------|
| Person ID Service | `PERSON_ID_SERVICE_URL` | For face recognition |
| vLLM (Cosmos Reason2) | `VISION_MODEL_URL` | For vision analysis |
| llama.cpp server (Gemma 4) | `LOGIC_MODEL_URL` | For reasoning |
| Google Gemini | `GEMINI_API_KEY` | For realtime voice |
| Home Assistant | `HOME_ASSISTANT_URL`, `HOME_ASSISTANT_TOKEN` | Sensor polling + actions |
| MinIO | `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` | Media storage |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CAREGIVER_CHAT_ID` | Alert notifications |
| TTS service | `TTS_API_URL` | Voice announcements |
| Scene Analysis Service | `SAS_BASE_URL` (in settings.yaml) | YOLO+Florence-2+CLIP; optional |
