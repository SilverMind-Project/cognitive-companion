# AGENTS.md

Guide for AI coding agents working on this codebase.

## Project Overview

Cognitive Companion v2 is a privacy-first AI system for senior care. It processes camera and sensor events through composable rule-based pipelines (vision, logic, translation, conditions, waits) and dispatches notifications across multiple channels. Each rule defines its own ordered pipeline steps. The system runs entirely on-premise.

**Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic 2.0, APScheduler, structlog
**Frontend**: Vue 3, Vuetify 3, Vite, Pinia
**Database**: SQLite (WAL mode via SQLAlchemy)
**LLM Providers**: vLLM (vision/translation), Ollama (logic), Google Gemini (realtime voice)
**Object Storage**: MinIO (S3-compatible, via boto3)

## Project Layout

```
backend/
  core/
    config.py              # YAML config loader with ${ENV_VAR} interpolation
    auth.py                # API key resolution, permission checking (fnmatch)
    database.py            # SQLAlchemy engine, session factory, init_db()
    exceptions.py          # AuthenticationError, PermissionDeniedError, NotFoundError, ConflictError
    logging.py             # structlog setup, get_logger()
  models/
    __init__.py            # Re-exports all models -- import here to register with Base
    sensor.py              # Sensor (camera, presence, button, light)
    room.py                # Room grouping
    rule.py                # Rule, RuleContext, RuleDependency
    pipeline.py            # PipelineStep, WorkflowExecution, STEP_TYPES
    event.py               # EventLog (pipeline execution audit trail, links to WorkflowExecution)
    alert.py               # EmergencyAlert
    person.py              # HouseholdMember, PersonSighting, PersonLocationState, PersonLocationHistory, PersonActivity
    conversation.py        # ConversationSession, ConversationTurn
    media_cache.py         # MediaCache (presigned URL tracking)
    image_state.py         # ActiveImageState (per-device eInk display state)
    image_template.py      # ImageTemplate (template definitions with regions)
  schemas/                 # Pydantic models mirroring ORM models (*Create, *Update, *Out)
    rule.py                # Rule schemas
    workflow.py            # WorkflowExecution schemas
    activity.py            # PersonActivity schemas
    image.py               # Image template and render schemas
    event.py, person.py, room.py, sensor.py, alert.py
  services/
    pipeline_executor.py   # Core composable pipeline executor (TriggerContext, StepResult, PipelineExecutor)
    condition_evaluator.py # Safe recursive-descent expression evaluator for condition steps
    event_aggregator.py    # Batches per-sensor events, manages media lifecycle
    rules_engine.py        # Rule matching: context + dependency + rate-limit checks
    person_tracking.py     # Fuses camera detections with HA presence sensors
    sensor_polling.py      # Polls Home Assistant entities on interval
    notification_dispatcher.py  # Routes alerts to channels by level
    conversation_manager.py     # Conversation history with TTL
    media_processor.py     # Image/video processing
    rag.py                 # Optional RAG service
    scheduler.py           # APScheduler job setup
  integrations/
    homeassistant.py       # HA REST API client
    minio_client.py        # S3/MinIO wrapper (boto3)
    telegram.py            # Telegram bot client
    tts.py                 # Text-to-speech client
    eink_renderer.py       # Internal PIL-based eink display renderer
    person_id_client.py    # HTTP client for person identification service
    llm/
      base.py              # LLMProvider abstract base
      vllm.py              # vLLM provider (vision, translation)
      ollama.py            # Ollama provider (logic)
      gemini_live.py       # Google Gemini Live (realtime audio)
  mcp/
    server.py              # MCPToolRegistry: read-only tools for AI agents
  routers/                 # FastAPI route handlers (one file per domain)
    rules.py               # Rule CRUD + pipeline step management
    workflows.py           # Workflow execution endpoints (list, detail, cancel)
    activities.py          # PersonActivity endpoints
    events.py, sensors.py, rooms.py, persons.py, alerts.py, etc.
  websocket/
    connection_manager.py  # WebSocket tracking, broadcast, prompt queue
    audio_handler.py       # Audio streaming with Gemini Live
  main.py                  # App factory, lifespan, service wiring -- START HERE

frontend/src/
  views/                   # Vue 3 pages (CompanionView, AdminView + admin/ sub-views)
    admin/
      RuleDetailView.vue   # Rule editor with pipeline step builder
      ActivitiesView.vue   # PersonActivity list/filter
      WorkflowsView.vue    # Workflow execution monitor
      EInkTemplatesView.vue  # E-Ink template editor
      DashboardView.vue, EventsView.vue, RulesView.vue, etc.
  components/
    pipeline/
      PipelineBuilder.vue  # Drag-and-drop step ordering, icon mapping per step type
      StepCard.vue         # Single step display with status
      StepPalette.vue      # Available step types to add
      StepConfigDialog.vue # Per-step-type config forms
    eink/
      BoundingBoxCanvas.vue  # Canvas overlay for region placement
      RegionEditor.vue       # Region property editor
  services/api.js          # API client with auth header injection
  services/WebSocketClient.js  # WebSocket client
  router/index.js          # Route definitions

person-identification-service/
  app/services/
    image_annotator.py     # Bounding box drawing with OpenCV

config/
  settings.yaml            # Application settings (${ENV_VAR} interpolation)
  auth.yaml                # API keys, device keys, permission map
  notifications.yaml       # Alert level -> channel routing
```

## Architecture Patterns

### Pipeline Execution

Rules have composable pipeline steps executed in sequence by `PipelineExecutor`. This replaces any fixed linear pipeline -- each rule defines its own ordered steps via the `PipelineStep` model.

**Key types**:

- `PipelineStep` (model) -- one step in a rule's pipeline. Has `order`, `step_type`, `config_json`, optional branching fields.
- `WorkflowExecution` (model) -- tracks a single run of a rule's pipeline, including paused/waiting state.
- `TriggerContext` (dataclass) -- carries trigger metadata (sensor_id, room_name, media_paths, trigger_type).
- `StepResult` (dataclass) -- carries step output (success, data dict, should_continue, optional next_step_id or wait_until).

**Data flow**: Pipeline data accumulates across steps. Each step receives the current `pipeline_data` dict and returns a `StepResult`. The executor merges `result.data` into `pipeline_data` before proceeding to the next step.

**Condition steps** use `ConditionEvaluator` -- a recursive-descent parser that evaluates expressions like `person_detections.count > 0 and exists(translation)` against pipeline data. Condition steps may branch via `next_step_on_true` / `next_step_on_false` on `PipelineStep`.

**Wait steps** persist execution state to the `WorkflowExecution` table (status="waiting", resume_at set). The scheduler resumes execution via an APScheduler `DateTrigger`. A `SchedulerBridge` abstraction is injected into `PipelineExecutor` to decouple wait/resume scheduling.

**Step types** are defined in `STEP_TYPES` tuple in `backend/models/pipeline.py`: person_identification, vision_analysis, logic_reasoning, translation, notification, ha_action, activity_detection, wait, condition, verification. Each has a corresponding `_step_<type>` handler method in `PipelineExecutor`.

Step type details:

- `activity_detection`: A pure setter step. Reads activity data from `pipeline_data` (typically produced by an upstream `logic_reasoning` step) and records it to the `PersonActivity` table. Does not run its own LLM prompts.
- `verification`: A database query step. Queries the `PersonActivity` table to verify household member activities within configured time windows. Does not capture images or run LLM calls.
- `logic_reasoning`: Sends a prompt to the logic LLM provider. Supports a `response_format` config option with values: `"default"`, `"activity_detection"`, `"custom"`.

**Wiring**: `PipelineExecutor` is instantiated in the lifespan in `backend/main.py` and attached to `app.state`.

### Service Injection

Services are instantiated in the FastAPI lifespan (`backend/main.py`) and attached to `app.state`. Routers access them via `request.app.state.<service>`. Do NOT instantiate services inside routers or import them at module level in router files.

```python
# In a router:
pipeline_executor = request.app.state.pipeline_executor
```

### Configuration

YAML files in `config/` with `${ENV_VAR}` interpolation. Access any value with dot-notation:

```python
from backend.core.config import settings
url = settings.get("person_id.url")
interval = settings.get("homeassistant.poll_interval_seconds", 30)
```

The config is loaded once at import time and reloaded in the lifespan. If you add a new config section, add it to `config/settings.yaml` -- the loader handles it automatically.

### Database

SQLAlchemy 2.0 ORM with a session factory. All models inherit from `Base` defined in `backend/core/database.py`.

```python
from backend.core.database import get_session
db = get_session()
try:
    # queries
finally:
    db.close()
```

For schema changes: **delete `data/cognitive_companion.db` and restart**. Tables are auto-created from the ORM models. There are no migrations.

### Authentication

API keys resolve from (in order): `X-API-Key` header, `?api_key` query param, `device_key` in JSON body.

Permission checking uses fnmatch patterns defined in `config/auth.yaml`. The `require_permission()` dependency handles this automatically when applied to a router.

### Error Handling

Raise custom exceptions from `backend/core/exceptions.py`:

- `AuthenticationError` -> 401
- `PermissionDeniedError` -> 403
- `NotFoundError` -> 404
- `ConflictError` -> 409

Global exception handlers in `register_exception_handlers()` convert these to HTTP responses. Do NOT catch these in routers -- let them propagate.

### Logging

Use structlog via `get_logger()`. Never use `print()`.

```python
from backend.core.logging import get_logger
logger = get_logger(__name__)
logger.info("event_processed", sensor_id=sid, rule=rule.name)
```

## Key Files to Read First

| File | Why |
|------|-----|
| `backend/main.py` | Lifespan wires all services -- shows how everything connects |
| `backend/services/pipeline_executor.py` | The composable pipeline executor (TriggerContext, StepResult, step handlers) |
| `backend/services/condition_evaluator.py` | Safe expression evaluator for condition steps |
| `backend/models/pipeline.py` | PipelineStep, WorkflowExecution, STEP_TYPES |
| `backend/services/event_aggregator.py` | How sensor events are batched and media is managed |
| `backend/services/rules_engine.py` | How rules are matched (contexts, dependencies, rate limits) |
| `backend/core/config.py` | How YAML config and env vars work |
| `backend/core/auth.py` | How API keys and permissions work |
| `person-identification-service/app/services/image_annotator.py` | Bounding box annotation with OpenCV |
| `config/settings.yaml` | All available configuration options |
| `config/auth.yaml` | Permission model definition |

## Common Tasks

### Adding a New Pipeline Step Type

A pipeline step flows through **4 files** (2 backend, 2 frontend). The pipeline executor passes a shared `pipeline_data` dict from step to step. Each handler reads upstream results from it and merges its own output back in via `StepResult(data={...})`.

#### 1. Backend Model: `backend/models/pipeline.py`

Add the type string to the `STEP_TYPES` tuple. This is informational only (the `step_type` column is a free-form string), but it documents the valid set:

```python
STEP_TYPES = (
    ...,
    "your_new_type",
)
```

#### 2. Backend Handler: `backend/services/pipeline_executor.py`

Add a handler method and register it in the dispatch dict inside `_execute_step()`:

```python
# In the handlers dict (~line 338):
handlers = {
    ...,
    "your_new_type": self._step_your_new_type,
}

# Handler method:
async def _step_your_new_type(
    self,
    step: PipelineStep,
    execution: WorkflowExecution,
    pipeline_data: dict,
    trigger: TriggerContext,
) -> StepResult:
    config = step.config_json or {}
    # Read from pipeline_data (upstream results) and config (step settings).
    # ...
    return StepResult(data={"your_key": result})
    # Keys in data={} are merged into pipeline_data for downstream steps.
```

Key types: `TriggerContext` carries trigger metadata (sensor_id, room_name, media_paths). `StepResult` fields: `success`, `data` (merged into pipeline_data), `should_continue`, `next_step_id` (for branching), `wait_until` (for delayed resume).

#### 3. Frontend Step Palette: `frontend/src/components/pipeline/StepPalette.vue`

Add an entry to the `groups` array in the appropriate category (Perception, Reasoning, Action, or Flow):

```javascript
{ type: "your_new_type", label: "Your Label", icon: "mdi-icon-name" },
```

#### 4. Frontend Config Dialog: `frontend/src/components/pipeline/StepConfigDialog.vue`

Three additions in this file:

**(a)** Add a `<template v-if>` block with Vuetify form fields for the step's config:

```html
<template v-if="localStep.step_type === 'your_new_type'">
  <v-text-field v-model="cfg.some_field" label="Some Field" variant="outlined" />
</template>
```

**(b)** Add default values to the `defaults` object:

```javascript
your_new_type: {
  some_field: "",
},
```

**(c)** If your config uses arrays stored as comma-separated strings (see `target_persons` pattern), add normalization in the `watch` callback and the `save()` function.

#### 5. Test

Delete `data/cognitive_companion.db`, restart the backend, create a rule, add your new step, configure it, and trigger the pipeline.

### Adding a New Context Filter Type

1. Add a handler in `rules_engine.py` `_matches_context()` method
2. Update the `RuleContext` docstring in `backend/models/rule.py` with the new type and its config schema
3. Add form support in `frontend/src/views/admin/RuleDetailView.vue`

### Adding a New API Endpoint

1. Create or edit a router file in `backend/routers/`
2. Add Pydantic request/response schemas in `backend/schemas/`
3. Register the router in `backend/main.py` (`app.include_router(...)`)
4. Add permission patterns for the new endpoint in `config/auth.yaml`

### Adding a New Database Model

1. Define the model in `backend/models/` (inherit from `Base`)
2. Import it in `backend/models/__init__.py` and add to `__all__`
3. Delete `data/cognitive_companion.db` -- tables are auto-created on restart

### Adding a New Service

1. Create the service class in `backend/services/`
2. Instantiate it in the lifespan function in `backend/main.py`
3. Attach to `app.state` so routers can access it

### Adding a New MCP Tool

1. Add a `_tool_<name>` method to `MCPToolRegistry` in `backend/mcp/server.py`
2. Add the tool definition to `_build_tool_definitions()` in the same file
3. Add the tool name to `config/settings.yaml` under `mcp.tools`

### Adding a New Notification Channel

1. Create an integration client in `backend/integrations/`
2. Register it in `NotificationDispatcher` (`backend/services/notification_dispatcher.py`)
3. Add channel configuration in `config/notifications.yaml`

### Working with E-Ink Displays

**Render pipeline flow:**

1. A pipeline's notification step triggers with `"eink"` in channels
2. `NotificationDispatcher` calls `EInkRenderer.render(text, template, sensor_ids)`
3. `EInkRenderer` resolves the template (DB or filesystem), renders text into regions via PIL, saves per-device PNGs
4. ESPHome devices poll `GET /api/v1/image/active` with their device key, receiving their specific image

**Adding a new eink device:**

1. Add a device key entry in `config/auth.yaml` with `image:read` permission and a `sensor_id`
2. Create a sensor with `sensor_type: "eink"` via the admin UI or API
3. The device will be automatically included when `sensor_ids=None` (default targeting)

### Adding a New LLM Provider

1. Implement the `LLMProvider` interface from `backend/integrations/llm/base.py`
2. Register it in `backend/integrations/llm/__init__.py` (`get_provider()`)
3. Add config in `config/settings.yaml` under the appropriate `llm.*` section

## Key Model Reference

### Rule (backend/models/rule.py)

Fields: `id`, `name`, `description`, `enabled`, `trigger_type` (sensor_event | cron | manual), `schedule_cron`, `primary_sensor_id`, `cool_off_minutes`, `max_daily_triggers`, `created_at`, `updated_at`.

Relationships: `steps` (list of PipelineStep, ordered by `order`), `contexts` (list of RuleContext), `dependencies` (list of RuleDependency).

Note: Rules no longer have `prompts_json`, `notification_config_json`, `additional_camera_ids_json`, or `VerificationStep`. All pipeline behavior is defined via composable `PipelineStep` records.

### PipelineStep (backend/models/pipeline.py)

Fields: `id`, `rule_id`, `order`, `step_type`, `label`, `config_json`, `enabled`, `next_step_on_true`, `next_step_on_false`.

### EventLog (backend/models/event.py)

Fields: `id`, `timestamp`, `rule_id`, `rule_name`, `sensor_id`, `room_name`, `trigger_type`, `media_paths_json`, `pipeline_data_json`, `status`, `workflow_execution_id`.

### PersonActivity (backend/models/person.py)

Fields: `id`, `person_id`, `activity_type`, `room_id`, `room_name`, `detected_at`, `confidence`, `source_event_id`, `metadata_json`.

Uses a GET/SET pattern across pipeline steps:

- **SET**: The `activity_detection` step reads activity data from `pipeline_data` (produced by `logic_reasoning`) and writes to the `PersonActivity` table.
- **GET**: The `verification` step queries the `PersonActivity` table based on its `conditions` config (person, activity type, time window).

### ImageTemplate (backend/models/image_template.py)

Fields: `id`, `name`, `description`, `width`, `height`, `image_filename`, `font_filename`, `regions_json`, `is_default`, `created_at`, `updated_at`.

`regions_json` is a list of region dicts, each with: `name`, `x`, `y`, `width`, `height`, `font_size_max`, `font_size_min`, `align`, `bg_color`, `text_color`.

### ActiveImageState (backend/models/image_state.py)

Fields: `id`, `sensor_id` (unique), `template_id`, `rendered_text`, `expires_at`, `created_at`, `updated_at`.

One row per eink display device. Links a sensor to its current rendered state and template.

## Code Style

- **Python**: ruff with `E`, `F`, `I`, `W` rules. 100-char line length. Target Python 3.11.
- **Frontend**: Vue 3 Composition API (`<script setup>`), Vuetify 3 components.
- **Documentation**: no em-dashes (—) in any `.md` file. Use colons, periods, semicolons, or commas instead. For `**Bold** — desc` patterns, use `**Bold**: desc` or `**Bold.** Desc`. Em-dashes read as AI-generated; write like a technical writer at Apple or Google.
- Prefer `async`/`await` for all I/O operations.
- Use structlog for logging, never `print()`.
- Follow existing patterns in the codebase rather than introducing new abstractions.

## Testing

- Backend: `pytest` + `pytest-asyncio` (configured in `pyproject.toml`)
- When writing tests, place them in `tests/` mirroring the `backend/` directory structure
- Run with: `pytest`

## External Services

| Service | Env Var | Used For |
|---------|---------|----------|
| Vision (Cosmos Reason2) | `VISION_MODEL_URL` | Vision analysis |
| Translation (TranslateGemma) | `TRANSLATE_MODEL_URL` | Language translation |
| Logic (Gemma3) | `LOGIC_MODEL_URL` | Logic reasoning |
| Gemini | `GEMINI_API_KEY` | Real-time voice conversations |
| Home Assistant | `HOME_ASSISTANT_URL`, `HOME_ASSISTANT_TOKEN` | Sensor polling, announcements, area discovery |
| MinIO | `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` | Media object storage |
| Person ID Service | `PERSON_ID_SERVICE_URL` | Face recognition + motion detection |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CAREGIVER_CHAT_ID` | Alert notifications |
| TTS | `TTS_API_URL` | Text-to-speech announcements |

## Do NOT

- **Run migrations** -- delete `data/cognitive_companion.db` and restart instead
- **Use `print()`** -- use `structlog` via `get_logger()`
- **Instantiate services in routers** -- access them from `request.app.state`
- **Add dependencies without updating `pyproject.toml`** (backend) or `package.json` (frontend)
- **Skip permission checks** -- all new endpoints need entries in `config/auth.yaml`
- **Catch `AuthenticationError` or `PermissionDeniedError` in routers** -- let global handlers deal with them
- **Store secrets in config files** -- use `${ENV_VAR}` interpolation
- **Hardcode pipeline step order** -- use `PipelineStep` model with `order` field; each rule defines its own steps
- **Use `eval()` for condition expressions** -- use `ConditionEvaluator` (recursive-descent parser)
- **Use lazy imports for required dependencies** -- all imports at top of file (PEP 8). Exception: optional deps (e.g. `google-genai`) may use guarded lazy imports with a comment explaining why
- **Use `alert()` or `confirm()` in Vue views** -- use the `useNotify` and `useConfirm` composables from `frontend/src/composables/`
- **Swallow errors silently** -- bare `catch {}` blocks must log via `console.error` (frontend) or `logger.error` (backend)
