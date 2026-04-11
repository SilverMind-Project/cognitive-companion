# AGENTS.md

Guide for AI coding agents working on this codebase.

## Project Overview

Cognitive Companion v2 is a privacy-first AI system for senior care. It processes camera and sensor events through composable rule-based pipelines (vision, logic, translation, conditions, waits) and dispatches notifications across multiple channels. Each rule defines its own ordered pipeline steps. The system runs entirely on-premise.

**Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic 2.0, APScheduler, stdlib logging
**Frontend**: Vue 3, Vuetify 3, Vite, Pinia
**Database**: SQLite (WAL mode via SQLAlchemy)
**LLM Providers**: vLLM (vision/translation, OpenAI-compatible), llama.cpp llama-server (OpenAI-compatible, e.g. Gemma 4 26B at 192.168.1.31:8100), Ollama (logic, gemma3:4b), Google Gemini (realtime voice)
**Object Storage**: MinIO (S3-compatible, via boto3)

## Project Layout

```text
backend/
  core/                    # Foundational layer — see "Core layer" section below.
    __init__.py            # Re-exports the public surface: Settings, Database, KeyStore, AuthContext, get_logger, …
    config.py              # Settings class + ${ENV_VAR} interpolated YAML loader; module-level ``settings`` singleton
    database.py            # Database class wrapping engine + session factory; ``init_db`` / ``get_db`` / ``get_session`` facade
    auth.py                # KeyStore (pure lookup) + FastAPI deps: ``get_auth_context`` / ``require_permission``
    exceptions.py          # AppError hierarchy + ``register_exception_handlers``
    logging.py             # BoundLogger + ``setup_logging`` / ``get_logger``
    template.py            # ``{{dotted.path}}`` renderer for pipeline prompts
  steps/                   # Step plugin system
    base.py                # StepHandler ABC, StepMetadata, StepResult, TriggerContext, ServiceContainer
    __init__.py            # StepRegistry singleton + auto-discovery
    builtin/               # 10 built-in step handlers (one file each)
  channels/                # Notification channel plugin system
    base.py                # NotificationChannel ABC, ChannelMetadata
    __init__.py            # ChannelRegistry singleton + auto-discovery
    builtin/               # PWA Popup Text, Telegram, eInk, HA Speaker TTS, PWA Realtime AI, PWA TTS Announcement channel plugins
  filters/                 # Context filter plugin system
    base.py                # ContextFilter ABC, FilterMetadata
    __init__.py            # FilterRegistry singleton + auto-discovery
    builtin/               # Room, time_range, day_of_week, person_presence, person_activity filters
  models/
    __init__.py            # Re-exports all models -- import here to register with Base
    sensor.py              # Sensor (camera, presence, button, light, media_player, eink, generic)
    room.py                # Room grouping
    rule.py                # Rule, RuleContext, RuleDependency (+ webhook_config, occupancy_config)
    pipeline.py            # PipelineStep, WorkflowExecution
    event.py               # EventLog (pipeline execution audit trail, links to WorkflowExecution)
    alert.py               # EmergencyAlert
    person.py              # HouseholdMember, PersonSighting, PersonLocationState, PersonLocationHistory, PersonActivity
    conversation.py        # ConversationSession, ConversationTurn
    media_cache.py         # MediaCache (presigned URL tracking)
    image_state.py         # ActiveImageState (per-device eInk display state)
    image_template.py      # ImageTemplate (template definitions with regions)
  schemas/                 # Pydantic models mirroring ORM models (*Create, *Update, *Out)
    rule.py                # Rule schemas (includes webhook_config)
    workflow.py            # WorkflowExecution schemas
    activity.py            # PersonActivity schemas
    image.py               # Image template and render schemas
    event.py, person.py, room.py, sensor.py, alert.py
  services/
    pipeline_executor.py   # Step orchestrator (dispatches to StepRegistry, uses ServiceContainer)
    condition_evaluator.py # Safe recursive-descent expression evaluator for condition steps
    event_aggregator.py    # Batches per-sensor events, manages media lifecycle
    rules_engine.py        # Rule matching: context via FilterRegistry + dependency + rate-limit checks
    person_tracking.py     # Fuses camera detections with HA presence sensors
    sensor_polling.py      # Polls HA presence sensors, tracks occupancy durations, fires occupancy_duration rules
    notification_dispatcher.py  # Routes alerts to channels via ChannelRegistry
    conversation_manager.py     # Conversation history with TTL
    media_processor.py     # Image/video processing
    rag.py                 # Optional RAG service
    scheduler.py           # APScheduler job setup
  integrations/
    homeassistant.py       # HA REST API client
    minio_client.py        # S3/MinIO wrapper (boto3)
    telegram.py            # Telegram bot client
    tts.py                 # Text-to-speech client (batch + streaming via AudioStream)
    eink_renderer.py       # Internal PIL-based eink display renderer
    person_id_client.py    # HTTP client for person identification service
    llm/
      base.py              # LLMProvider abstract base + RealtimeLLMProvider
      chain.py             # LLMProviderChain (fallback) + LLMProviderPool (load balancing)
      openai_compat.py     # OpenAICompatibleProvider -- /v1/chat/completions (vLLM, llama.cpp, etc.)
      vllm.py              # Legacy VLLMVisionProvider + VLLMTranslationProvider (used by old steps)
      ollama.py            # OllamaProvider -- /api/chat (used by old logic_reasoning step + registry)
      gemini_live.py       # Google Gemini Live (realtime audio)
      __init__.py          # LLMModelConfig, LLMModelRegistry (named model registry for llm_call step)
                           # + get_provider() / get_llm_provider() for legacy steps
  mcp/
    server.py              # FastMCP tool definitions with auto-generated schemas
    gemini_adapter.py      # Bridges MCP tools to Gemini Live function calling
    middleware.py           # ASGI auth middleware for /mcp endpoint
  routers/                 # FastAPI route handlers (one file per domain)
    rules.py               # Rule CRUD + pipeline step management
    pipeline.py            # Step type, channel type, filter type, llm-models metadata endpoints
    ha_sync.py             # HA sync: rooms, sensors (with room_id), media_player entities; GET /ha/media-players, GET /ha/entities
    webhooks.py            # Webhook trigger endpoint with HMAC validation
    workflows.py           # Workflow execution endpoints (list, detail, cancel)
    activities.py          # PersonActivity endpoints
    persons.py             # HouseholdMember CRUD + enrollment proxy (list/enroll/delete via person-ID service)
    media.py                 # GET /media/buffer -- per-camera aggregator state (flushed images + pending count)
    events.py, sensors.py, rooms.py, alerts.py, etc.
  websocket/
    connection_manager.py  # WebSocket tracking, broadcast, prompt queue
    audio_handler.py       # Audio streaming with Gemini Live
  main.py                  # App factory, lifespan, plugin discovery, service wiring -- START HERE

frontend/src/
  views/                   # Vue 3 pages (CompanionView, AdminView + admin/ sub-views)
    AdminView.vue          # Admin layout with grouped sidebar nav (Automation, Infrastructure, People)
    CompanionView.vue      # Senior care voice UI with connection status indicator
    admin/
      DashboardView.vue    # System stats, health checks, person locations, occupancy, alerts
      RuleDetailView.vue   # Rule editor: sensor/room/person autocomplete, structured context filter dialogs
      PersonsView.vue      # Member management + face enrollment UI (photo upload, enrollment status)
      ActivitiesView.vue   # PersonActivity list/filter
      WorkflowsView.vue    # Workflow execution monitor
      EInkTemplatesView.vue  # E-Ink template editor
      CameraMediaView.vue     # Per-camera media buffer: flushed images (with lightbox), pending count, cooldown, auto-refresh, sort
      EventsView.vue, RulesView.vue, SensorsView.vue, RoomsView.vue, AlertsView.vue
  components/
    pipeline/
      PipelineBuilder.vue  # Drag-and-drop step ordering, icon mapping per step type
      StepCard.vue         # Single step display with status
      StepPalette.vue      # Dynamic step types loaded from GET /pipeline/step-types
      StepConfigDialog.vue # Per-step-type config forms with person/sensor multi-select dropdowns
    companion/             # Widget system for CompanionView
      WidgetRegistry.js    # Widget registration, lookup, enable/disable
      VoiceWidget.vue      # Audio recording with pulse/glow animations per state
      TranscriptWidget.vue # Chat-bubble conversation display with timestamps
      AlertWidget.vue      # Emergency alert overlay
      index.js             # Built-in widget registration
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

Rules have composable pipeline steps executed in sequence by `PipelineExecutor`. Each rule defines its own ordered steps via the `PipelineStep` model.

**Plugin architecture**: Step handlers are self-contained plugins in `backend/steps/builtin/` (one file per type). Each plugin is a class inheriting `StepHandler` from `backend/steps/base.py`, decorated with `@StepRegistry.register`. The registry auto-discovers plugins at startup via `StepRegistry.discover()`.

**Key types** (all in `backend/steps/base.py`):

- `StepHandler` (ABC) -- base class for step plugins. Requires `metadata()` classmethod and `execute()` async method.
- `StepMetadata` (dataclass) -- step name, description, icon, config JSONSchema.
- `StepResult` (dataclass) -- step output: success, data dict, should_continue, optional next_step_id or wait_until.
- `TriggerContext` (dataclass) -- trigger metadata: sensor_id, room_name, media_paths, trigger_type, webhook_payload.
- `ServiceContainer` (dataclass) -- holds all shared services (LLM providers, HA client, DB session factory, etc.) passed to step handlers.

**Data flow**: Pipeline data accumulates across steps. Each step receives the current `pipeline_data` dict and returns a `StepResult`. The executor merges `result.data` into `pipeline_data` before proceeding to the next step. At initialization, `PipelineExecutor` injects a localized `system` object including `system.local_time`, `system.local_date`, `system.local_day_of_week`, and `system.timezone` ensuring downstream steps (like prompts or notifications) have localized time awareness.

**Rate Limiting & Cool-Off**: The `EventLog.status` relies on the execution outcome to determine rate limiting. If a pipeline concludes but no actions were taken, it registers as `ignored` avoiding cool-off triggers. Built-in terminal steps (`notification`, `activity_detection`, `ha_action`, and conditionally `condition`) accept a `trigger_cooloff` generic boolean explicitly forcing the execution status to `completed` upon success.

**Condition steps** use `ConditionEvaluator` -- a recursive-descent parser that evaluates expressions like `person_detections.count > 0 and exists(translation)` against pipeline data. Condition steps may branch via `next_step_on_true` / `next_step_on_false` on `PipelineStep`.

**Wait steps** persist execution state to the `WorkflowExecution` table (status="waiting", resume_at set). The scheduler resumes execution via an APScheduler `DateTrigger`. A `SchedulerBridge` abstraction is injected into `PipelineExecutor` to decouple wait/resume scheduling.

**Built-in step types**: llm_call, person_identification, vision_analysis, logic_reasoning, translation, notification, ha_action, activity_detection, wait, condition, verification. Each lives in its own file under `backend/steps/builtin/`.

Step type details:

- `llm_call`: Unified LLM step. Selects a model by `model_id` from `LLMModelRegistry` (loaded from `llm.models` in settings.yaml). Supports vision (image attachment), JSON schema enforcement (`response_format`: `"text"`, `"json_schema"`, `"json_free"`), `special_instructions` prepended to the prompt, context key inclusion, and hallucination retry. Key config: `model_id`, `prompt`, `include_context`, `image_source` (`"none"`, `"trigger"`, `"additional"`, `"both"`), `additional_sensor_ids`, `sort_by_sensor_then_time` (groups images by sensor order then chronologically within each -- enables inter-frame analysis), `images_per_sensor`, `max_images`, `image_time_filter`, `response_format`, `response_json_schema`, `output_key` (defaults to `"llm_response"`; set to `"logic_response"` / `"vision_response"` / `"translation"` for downstream step compatibility), `hallucination_marker`. Uses `services.llm_model_registry` from `ServiceContainer`.
- `activity_detection`: Records a single activity to the `PersonActivity` table. Config fields: `activity_type` (required), `person_id` (optional), `room_name` (optional), `confidence` (accepts a fixed number or `{{template}}` syntax, defaults to `0.8`). All fields support `{{template}}` syntax. `person_id` defaults to `"unknown"` when empty. `room_name` defaults to the trigger room when empty. Use multiple steps to record multiple activities. **Scene capture**: set `capture_scene_description: true` to store the upstream vision analysis output (default key: `vision_response`) in `metadata_json.scene_description` -- gives each activity record an auditable explanation of *why* it was detected. Use `scene_description_key` to read from a different pipeline key. `metadata_extra` accepts an optional JSON string (template-supported) merged into `metadata_json` for arbitrary extra fields.
- `verification`: A database query step. Queries the `PersonActivity` table to verify activities within configured time windows. Each condition has `activity_type` (required), optional `person_id` (template-enabled, empty = any person), optional `room_name` (template-enabled, empty = any room), time window (`within_minutes` or `window_start`/`window_end`), and `min_confidence`. Does not capture images or run LLM calls.
- `vision_analysis`: Instructs the vision LLM (hardwired to `services.vision_provider`). Prefer `llm_call` for new pipelines. Supports `image_source` (`"trigger"`, `"additional"`, `"both"`), `additional_sensor_ids`, `additional_room_names`, `image_time_filter`, structured JSON output via `response_format`/`response_schema`/`response_json_schema`.
- `logic_reasoning`: Sends a prompt to the logic LLM provider (hardwired to `services.logic_provider`). Prefer `llm_call` for new pipelines. Supports `response_format` (`"default"`, `"activity_detection"`, `"custom"`), `response_schema`, `response_json_schema`.
- `translation`: Translates text (hardwired to `services.translation_provider`). Prefer `llm_call` for new pipelines. Accepts `special_instructions` and `hallucination_marker` for Tenacity retry.
- `notification`: Formats and delivers alerts using `notifications.yaml` mappings. Has advanced template overriding support per-channel (`telegram_template`, `ha_speaker_tts_template`, `eink_template`, `webhook_template`, `pwa_popup_text_template`, `pwa_realtime_ai_template`) that gracefully degrade to the unified `message_template` format. The `pwa_tts_announcement` channel reuses `ha_speaker_tts_template` since both feed the same TTS engine. Supports `eink_template_id` for selecting an image template and `eink_expiry_minutes` for setting expiry duration.

**Wiring**: `PipelineExecutor` is instantiated in the lifespan in `backend/main.py` and attached to `app.state`. It receives a `ServiceContainer` with all shared services.

### Notification Channels

Notification channels are plugins in `backend/channels/builtin/`. Each channel inherits `NotificationChannel` from `backend/channels/base.py` and is registered via `@ChannelRegistry.register`. Built-in channels are: `pwa_popup_text` (UI text popups), `telegram`, `eink` (e-ink display images), `ha_speaker_tts` (smart speaker audio via HA), `pwa_tts_announcement` (TTS audio streamed to PWA), `pwa_realtime_ai` (interactive Gemini Live voice), and `webhook` (outbound HTTP POST).

The `NotificationDispatcher` iterates over matched channels from the registry to deliver alerts. Per-step channel overrides (via the `channels` field in notification step config), as well as direct endpoints like `webhook_url`, take precedence over the defaults in `notifications.yaml`.

**HA Speaker TTS channel flow:** `HASpeakerTTSChannel.send()` calls `TTSClient.generate_and_upload()` to produce an MP3 and upload it to MinIO, obtaining a presigned URL. It then calls `HomeAssistantClient.play_audio(url, entity_id)` to play the audio on the configured `media_player` entity. The entity ID comes from `ha_media_player` in the notification step's `config_json` (defaults to `media_player.living_room_speaker`). `NotificationDispatcher` passes `minio_client` and `ha_client` via `DispatchServices` so no integration clients are imported inside the channel plugin.

**PWA TTS Announcement channel flow:** `PWATTSAnnouncementChannel` delivers audio directly to connected PWA clients via WebSocket, bypassing MinIO and HA entirely. Two modes are supported:

- **Stream mode** (default): Calls `TTSClient.stream_audio()` which opens a streaming HTTP connection to the TTS service. The channel broadcasts a `stream_start` JSON message (with `sample_rate`), then forwards each PCM chunk as a binary WebSocket frame via `ConnectionManager.broadcast_bytes()`, then sends a `stream_end` JSON message. The frontend accumulates all PCM chunks until `stream_end`, then plays the complete audio as a single buffer via the Web Audio API. This full-buffering strategy avoids audible gaps when the TTS service cannot sustain real-time inference speeds. On `stream_start`, the playback timeline is reset to prevent stale scheduling from previous announcements.
- **File mode**: Broadcasts a JSON message containing an `audio_url` for the frontend to play via the HTML5 Audio API.

`TTSClient.stream_audio()` returns an `AudioStream` dataclass wrapping an async iterator of bytes chunks plus a `sample_rate` field. The underlying httpx streaming connection is cleaned up when the iterator is fully consumed.

`ConnectionManager.broadcast_bytes()` sends raw bytes to all connected WebSocket clients, mirroring the pattern of `broadcast()` for JSON payloads including stale connection cleanup.

**Transcript actor delineation (pwa_realtime_ai):** When the orchestrator sends a backend prompt to the Gemini Live session, it is tagged as an orchestrator turn. The prompt text is **not** sent to the frontend transcript: only the agent's spoken response appears (as `source: "assistant"`). This ensures the senior sees a clean conversation without internal system nudges. Three actors are tracked in the conversation log: `user` (senior speech), `assistant` (agent response), and `orchestrator` (system-initiated prompts, hidden from UI).

**WebSocket connection lifecycle:** The frontend connects to `/ws/audio` on page load and holds the connection open for push notifications (alerts, reminders) even before the user taps the mic. The backend lazily opens a Gemini Live session only when the first audio chunk, text message, or orchestrator prompt arrives in `_client_to_backend`. After each Gemini session ends, the backend waits for fresh activity before reconnecting. No keepalive messages are sent to Gemini; idle sessions are allowed to expire naturally.

A continuous `prompt-bridge` task (started in `_run_backend_loop`) transfers orchestrator prompts from `ConnectionManager.prompt_queue` into `_client_to_backend` throughout the WebSocket connection's lifetime, so a queued reminder wakes the lazy-connect wait even if the user has never spoken.

**Background noise filtering (frontend):** `AudioVisualizer.vue` applies a 150 Hz high-pass `BiquadFilter` before the VAD analyser and PCM processor, removing fan and AC hum (50-120 Hz) at the signal level. The 2.5-second ambient calibration runs on the filtered signal. The "speaking" state change is emitted only when the `recording` prop is `true`, so the status pill never shows "You're speaking" due to background noise while the mic button has not been tapped.

### Context Filters

Context filters are plugins in `backend/filters/builtin/`. Each filter inherits `ContextFilter` from `backend/filters/base.py` and is registered via `@FilterRegistry.register`. The `RulesEngine._matches_context()` method delegates to `FilterRegistry.get(context_type).evaluate()`.

**Negation:** Each `RuleContext` has a `negate` boolean column. When `True`, the filter result is inverted  -  e.g., a room filter with `negate=True` means "NOT in this room". Within a context_type group, contexts are ORed; across groups, they are ANDed. Negation applies per-context before the OR grouping.

### Face Enrollment Proxy

The backend proxies face enrollment requests to the person-ID service so the admin UI can manage enrollment without direct access to the face recognition service.

**Endpoints** (in `backend/routers/persons.py`):

- `GET /persons/enrolled` -- list all enrolled members from the person-ID service
- `POST /persons/{person_id}/enroll` -- upload reference photos (multipart `files` + `name` field), proxied to the person-ID service via `PersonIDClient.enroll()`
- `GET /persons/{person_id}/enrollment` -- get enrollment details (embedding count, created date)
- `DELETE /persons/{person_id}/enrollment` -- remove face enrollment data

The `PersonIDClient` at `backend/integrations/person_id_client.py` handles all communication with the person-ID service.

### Webhook Triggers

Rules can be triggered via `POST /webhooks/{rule_id}` with an `X-Webhook-Secret` header. The webhook endpoint validates the secret via HMAC comparison against the rule's `webhook_config.secret`. Secrets are generated via `POST /webhooks/{rule_id}/generate-secret`.

### Telegram Command Triggers

Rules with `trigger_type="telegram"` are fired when a matching Telegram command arrives. The `TelegramTriggerService` (`backend/services/telegram_trigger.py`) polls the Bot API on a scheduler interval (default every 5 seconds, configurable via `notifications.telegram.trigger_poll_interval_seconds`). Only started when `telegram_client.configured` is true.

`Rule.telegram_trigger_config` fields:

- `command` (str): command to match, e.g. `"/medication"`. Case-insensitive. Omit to match any command.
- `allowed_chat_ids` (list): whitelist of Telegram chat IDs. Empty = any chat allowed.
- `respond_with_ack` (bool, default `true`): send a brief reply confirming the rule was triggered.

The Telegram message is available in `pipeline_data["trigger_input"]` with keys `command`, `args`, `text`, `chat_id`, `from_user` -- identical structure to webhook payload so downstream steps referencing `{{trigger_input.*}}` work the same way. `TriggerContext.trigger_type` is `"telegram"`. Dispatch path is identical to webhook triggers; only the delivery channel differs.

### LLM Subsystem

The LLM subsystem (`backend/integrations/llm/`) has two independent layers:

**Named model registry** (`LLMModelRegistry`, loaded from `llm.models` in settings.yaml): used by the `llm_call` step. Each entry declares `id`, `name`, `api_type` (`openai` or `ollama`), `base_url`, `model`, `capabilities` (list of `text`/`vision`/`translation`), `guided_decoding` (bool), `max_tokens`, `timeout`, and `max_retries`. The registry lazily constructs and caches provider instances. `app.state.llm_model_registry` is a `LLMModelRegistry` instance. `GET /api/v1/pipeline/llm-models` exposes model metadata for the frontend step config UI.

**`OpenAICompatibleProvider`** (`openai_compat.py`): handles all `/v1/chat/completions` servers (vLLM, llama.cpp llama-server, etc.). Supports images (base64 inline), two JSON enforcement modes (`guided_json` payload field for vLLM when `guided_decoding=True`; schema injected as prompt text otherwise), and hallucination retry via tenacity.

**Legacy per-role providers** (used by `vision_analysis`, `logic_reasoning`, `translation` steps): configured under `llm.vision`, `llm.logic`, `llm.translation` in settings.yaml. Each supports three deployment modes:

- **Simple**: single provider (default)
- **Chain**: primary provider with fallback providers and configurable retry count
- **Pool**: round-robin load balancing across multiple providers

`EventAggregator.query_media_by_sensor(sensor_ids_ordered, images_per_sensor, max_images, ...)` returns images grouped by sensor in the specified order, sorted chronologically within each group. Used by `llm_call` when `sort_by_sensor_then_time=True` to produce a temporally coherent sequence for inter-frame analysis.

### Service Injection

Services are instantiated in the FastAPI lifespan (`backend/main.py`) and attached to `app.state`. Routers access them via `request.app.state.<service>`. Do NOT instantiate services inside routers or import them at module level in router files.

```python
# In a router:
pipeline_executor = request.app.state.pipeline_executor
```

### Configuration

YAML files in `config/` with `${ENV_VAR}` interpolation, exposed through the
`Settings` class. Access any value with dot-notation via the module singleton:

```python
from backend.core.config import settings
url = settings.get("person_id.url")
interval = settings.get("homeassistant.poll_interval_seconds", 30)
```

The config is loaded lazily on first access and reloaded in the lifespan. If
you add a new config section, add it to `config/settings.yaml` — the loader
handles it automatically.

In tests, construct a `Settings` object directly to avoid touching the disk:

```python
from backend.core.config import Settings
s = Settings.from_dict({"llm": {"model": "fake"}})
assert s.get("llm.model") == "fake"
```

### Database

SQLAlchemy 2.0 ORM wrapped by the `Database` class, which owns the engine and
session factory. All models inherit from `Base` defined in
`backend/core/database.py`. Application code uses the module-level facade:

```python
from backend.core.database import get_session
db = get_session()
try:
    # queries
finally:
    db.close()
```

For schema changes: **delete `data/cognitive_companion.db` and restart**. Tables
are auto-created from the ORM models. There are no migrations.

In tests, construct an isolated `Database` directly — no global reset needed:

```python
from backend.core.database import Database
db = Database("sqlite:///:memory:")
sess = db.session()
```

### Authentication

API keys resolve from (in order): `X-API-Key` header, `?api_key` query param,
`device_key` in JSON body. Resolution and permission checking live in the
pure `KeyStore` class; the module-level `get_auth_context` / `require_permission`
dependencies wrap a lazily-built default `KeyStore` sourced from the current
`Settings`. Call `invalidate_lookup_cache()` after reloading settings to pick
up rotated keys without a restart.

Permission checking uses fnmatch patterns defined in `config/auth.yaml`. The
`require_permission()` dependency handles this automatically when applied to a
router.

In tests, hand-construct a `KeyStore` with in-memory data:

```python
from backend.core.auth import KeyStore
ks = KeyStore(api_keys=[{"key": "K1", "name": "admin", "permissions": ["*"]}])
assert ks.resolve("K1").name == "admin"
```

**Device key sensor upsert:** At startup, `_upsert_device_key_sensors()` in `backend/main.py` reads every entry under `auth.device_keys` (from `config/auth.yaml`) and upserts a `Sensor` record using the entry's `sensor_id` as the primary key. `device_type` maps to `sensor_type` via `_DEVICE_TYPE_TO_SENSOR_TYPE` (`recamera` -> `camera`, `reterminal` -> `eink`). This ensures hardware devices are immediately visible in the sensors API without a manual create step. The upsert is idempotent: existing sensors get their name and sensor_type refreshed.

**reCamera payload format:** The reCamera device posts a JSON object with the following structure. The device key is passed as the `?api_key=` query parameter (not in the body).

```json
{
  "code": 0,
  "data": {
    "image": "<base64-encoded JPEG>",
    "labels": ["person"],
    "boxes": [[x1, y1, x2, y2, score, class_id]],
    "count": 287,
    "perf": [[model_id, preprocess_ms, inference_ms]],
    "resolution": [1280, 720]
  },
  "name": "invoke",
  "type": 1
}
```

`data.image` is the JPEG image. `data.labels` contains the object class names detected by the on-device YOLO11 model and drives per-camera label filtering.

**Per-camera configuration (`config/settings.yaml`):** The `cameras` section accepts per-sensor options keyed by `sensor_id`:

```yaml
cameras:
  recamera_kitchen:
    rotate: 90           # clockwise rotation before MinIO upload (90, 180, 270)
    label_filter:
      labels: ["person"] # required labels from payload.data.labels
      mode: "any"        # "any" (default) or "all"
```

- `rotate`: applies a clockwise PIL rotation to the decoded JPEG before uploading. Useful when cameras are mounted at an angle.
- `label_filter`: drops the image (returns `{"status": "filtered"}`) when the detected labels do not satisfy the filter. `mode: "any"` requires at least one label to match; `mode: "all"` requires every configured label to be present. Omitting `label_filter` passes all images through.

### Error Handling

Raise custom exceptions from `backend/core/exceptions.py`:

- `AuthenticationError` -> 401
- `PermissionDeniedError` -> 403
- `NotFoundError` -> 404
- `ConflictError` -> 409

Global exception handlers in `register_exception_handlers()` convert these to HTTP responses. Do NOT catch these in routers -- let them propagate.

### Logging

Use `get_logger()` from `backend.core.logging`. Never use `print()`. The logger
wraps the Python stdlib `logging` module and accepts keyword context arguments
that are appended to the log line as `key=value` pairs.

```python
from backend.core.logging import get_logger
logger = get_logger(__name__)
logger.info("event_processed", sensor_id=sid, rule=rule.name)
# output: "event_processed sensor_id=cam1 rule=Motion Alert"
```

## Key Files to Read First

| File | Why |
| ---- | --- |
| `backend/main.py` | Lifespan wires all services, plugin discovery -- shows how everything connects |
| `backend/steps/base.py` | StepHandler ABC, StepResult, TriggerContext, ServiceContainer -- core plugin types |
| `backend/steps/__init__.py` | StepRegistry -- how step plugins are discovered and dispatched |
| `backend/services/pipeline_executor.py` | Orchestrates step execution via StepRegistry |
| `backend/services/condition_evaluator.py` | Safe expression evaluator for condition steps |
| `backend/channels/__init__.py` | ChannelRegistry -- notification channel plugin discovery |
| `backend/filters/__init__.py` | FilterRegistry -- context filter plugin discovery |
| `backend/models/pipeline.py` | PipelineStep, WorkflowExecution models |
| `backend/services/event_aggregator.py` | How sensor events are batched and media is managed |
| `backend/services/rules_engine.py` | How rules are matched (filters, dependencies, rate limits) |
| `backend/core/config.py` | How YAML config and env vars work |
| `config/settings.yaml` | All available configuration options |

## Common Tasks

### Adding a New Pipeline Step Type

Create a single file in `backend/steps/builtin/` (or `backend/steps/contrib/` for third-party plugins). The registry auto-discovers it at startup.

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
            name="Your Step",
            description="What this step does",
            icon="mdi-icon-name",
            config_schema={
                "some_field": {"type": "string", "default": "", "description": "Field description"},
            },
        )

    async def execute(self, step, execution, pipeline_data, trigger, services) -> StepResult:
        config = step.config_json or {}
        # Read from pipeline_data (upstream results) and config (step settings).
        # Access shared services via `services` (ServiceContainer).
        return StepResult(data={"your_key": result})
```

1. **That's it.** The step appears automatically in the frontend StepPalette (loaded via `GET /pipeline/step-types`) and gets a generic JSON config editor in StepConfigDialog. For a custom config form, add a `<template v-if>` block in `StepConfigDialog.vue`.

Key types (all in `backend/steps/base.py`): `TriggerContext` carries trigger metadata  -  `trigger_type` (`"sensor_event"`, `"cron"`, `"manual"`, `"webhook"`, `"occupancy_duration"`), `sensor_id`, `room_name`, `media_paths`, `webhook_payload`, and `occupancy_duration_minutes` (set for `occupancy_duration` triggers). `StepResult` fields: `success`, `data` (merged into pipeline_data), `should_continue`, `next_step_id` (for branching), `wait_until` (for delayed resume). `ServiceContainer` holds LLM providers, HA client, DB session factory, and other shared services.

### Adding a New Context Filter Type

Create a single file in `backend/filters/builtin/` (or `backend/filters/contrib/`):

```python
# backend/filters/builtin/your_filter.py
from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata

@FilterRegistry.register
class YourFilter(ContextFilter):
    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(
            context_type="your_filter",
            name="Your Filter",
            description="What this filter checks",
            config_schema={"field": {"type": "string"}},
        )

    def evaluate(self, config: dict, trigger_context) -> bool:
        return config.get("field") == trigger_context.some_value
```

1. The filter is auto-discovered and used by `RulesEngine._matches_context()` when a rule has a context with `context_type="your_filter"`.
1. Add form support in `frontend/src/views/admin/RuleDetailView.vue` for the filter's config fields.

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

1. Add a `@_register` decorated async function in `backend/mcp/server.py`. Type hints on parameters auto-generate JSON schemas.
2. Add the tool name to `config/settings.yaml` under `mcp.tools`
3. If the tool should be available in voice conversations, also add it to `mcp.gemini_tools`

### Adding a New Notification Channel

Create a single file in `backend/channels/builtin/` (or `backend/channels/contrib/`):

```python
# backend/channels/builtin/your_channel.py
from backend.channels import ChannelRegistry
from backend.channels.base import NotificationChannel, ChannelMetadata

@ChannelRegistry.register
class YourChannel(NotificationChannel):
    @classmethod
    def metadata(cls) -> ChannelMetadata:
        return ChannelMetadata(
            channel_type="your_channel",
            name="Your Channel",
            description="Where notifications go",
        )

    async def send(self, message: str, level: str, services) -> bool:
        # Use services to access integration clients.
        return True
```

1. The channel is auto-discovered and available in `NotificationDispatcher`.
1. Add channel configuration in `config/notifications.yaml` to route alert levels to the new channel.

### Working with E-Ink Displays

**Render pipeline flow:**

1. A pipeline's notification step triggers with `"eink"` in channels
2. `NotificationDispatcher` calls `EInkRenderer.render(text, template, sensor_ids)`
3. `EInkRenderer` resolves the template (DB or filesystem), renders text into regions via PIL, saves per-device PNGs
4. ESPHome devices poll `GET /api/v1/image/active` with their device key, receiving their specific image

**Adding a new eink device:**

1. Add a device key entry in `config/auth.yaml` with `image:read` permission and a `sensor_id`
2. The sensor is auto-upserted at startup via `_upsert_device_key_sensors()` (`sensor_type: "eink"` for `device_type: "reterminal"`)
3. The device will be automatically included when `sensor_ids=None` (default targeting)

### Home Assistant Sensor Sync

`POST /ha/sync/sensors` imports entities from HA areas into the local `sensors` table. Supported domains: `sensor`, `binary_sensor`, and `media_player`. The `sensor_type` is inferred from the entity name (presence, light, distance) or entity domain (media_player). The sensor's `room_id` is set (or updated) on every sync run so that room reassignments in HA are always reflected locally.

Two read endpoints support the frontend pipeline config UI:

- `GET /ha/media-players`: lists all `media_player.*` entities from HA (for TTS media player dropdown)
- `GET /ha/entities?domain=<domain>`: lists entities for a specific HA domain (for ha_action entity_id dropdown)

### Adding a New LLM Provider

1. Implement the `LLMProvider` interface from `backend/integrations/llm/base.py`
2. Register it via `register_provider(name, provider)` in `backend/integrations/llm/__init__.py`
3. Add config in `config/settings.yaml` under the appropriate `llm.*` section
4. Optionally configure as part of a chain (fallback) or pool (load balancing) in `settings.yaml`

## Key Model Reference

### Rule (backend/models/rule.py)

Fields: `id`, `name`, `description`, `enabled`, `trigger_type` (sensor_event | cron | manual | webhook | occupancy_duration), `schedule_cron`, `primary_sensor_id`, `cool_off_minutes`, `max_daily_triggers`, `webhook_config` (JSON: `{secret, created_at}`), `occupancy_config` (JSON: `{min_minutes: int}` -- used with `occupancy_duration` trigger type), `created_at`, `updated_at`.

Relationships: `steps` (list of PipelineStep, ordered by `order`), `contexts` (list of RuleContext), `dependencies` (list of RuleDependency).

**occupancy_duration trigger**: `SensorPollingService` queries all enabled rules with `trigger_type = "occupancy_duration"` on each polling cycle. When a sensor identified by `primary_sensor_id` has been continuously occupied for ≥ `occupancy_config.min_minutes`, the service fires the rule via `WorkflowPipeline.process_event()`. The actual elapsed duration is passed as `TriggerContext.occupancy_duration_minutes`. All existing context filters (room, time_range, person_presence, etc.) and rate limits apply normally.

Note: Rules no longer have `prompts_json`, `notification_config_json`, `additional_camera_ids_json`, or `VerificationStep`. All pipeline behavior is defined via composable `PipelineStep` records.

### PipelineStep (backend/models/pipeline.py)

Fields: `id`, `rule_id`, `order`, `step_type`, `label`, `config_json`, `enabled`, `next_step_on_true`, `next_step_on_false`.

### EventLog (backend/models/event.py)

Fields: `id`, `timestamp`, `rule_id`, `rule_name`, `sensor_id`, `room_name`, `trigger_type`, `media_paths_json`, `pipeline_data_json`, `status`, `workflow_execution_id`.

### PersonActivity (backend/models/person.py)

Fields: `id`, `person_id`, `activity_type`, `room_id`, `room_name`, `detected_at`, `confidence`, `source_event_id`, `metadata_json`.

Uses a GET/SET pattern across pipeline steps:

- **SET**: The `activity_detection` step writes a single activity to the `PersonActivity` table. All config fields support `{{template}}` syntax so values can be fixed strings or resolved from upstream step output.
- **GET**: The `verification` step queries the `PersonActivity` table based on its `conditions` config (person, activity type, time window).

### ImageTemplate (backend/models/image_template.py)

Fields: `id`, `name`, `description`, `width`, `height`, `image_filename`, `font_filename`, `regions_json`, `is_default`, `created_at`, `updated_at`.

`regions_json` is a list of region dicts, each with: `name`, `x`, `y`, `width`, `height`, `font_size_max`, `font_size_min`, `align`, `bg_color`, `text_color`.

### ActiveImageState (backend/models/image_state.py)

Fields: `id`, `sensor_id` (unique), `template_id`, `rendered_text`, `expires_at`, `created_at`, `updated_at`.

One row per eink display device. Links a sensor to its current rendered state and template.

## Code Style

- **Python**: ruff with `E`, `F`, `I`, `W`, `UP`, `B`, `SIM`, `RUF`, `PIE`, `PT`, `C4`, `T20` rules. mypy for type checking with `enable_error_code = ["import"]`. 100-char line length. Target Python 3.11. Package management via uv with a lockfile (`uv.lock`).
- **Frontend**: Vue 3 Composition API (`<script setup>`), Vuetify 3 components.
- **Documentation**: no em-dashes ( - ) in any `.md` file. Use colons, periods, semicolons, or commas instead. For `**Bold**  -  desc` patterns, use `**Bold**: desc` or `**Bold.** Desc`. Em-dashes read as AI-generated; write like a technical writer at Apple or Google.
- Prefer `async`/`await` for all I/O operations.
- Use structlog for logging, never `print()`.
- Follow existing patterns in the codebase rather than introducing new abstractions.

## Testing

- Backend: `pytest` + `pytest-asyncio` + `pytest-cov` (configured in `pyproject.toml`)
- Place tests in `backend/tests/` mirroring the `backend/` structure (e.g., `tests/services/test_rules_engine.py`)
- `backend/tests/conftest.py` provides `db_engine`, `db_session`, and `db_factory` fixtures backed by an in-memory SQLite instance
- `backend/tests/core/` holds the `backend.core` test suite (113 tests, ~98% branch coverage) — the primary reference for how the core layer expects to be consumed
- Use `RulesEngine(tz_name="UTC")` in tests to avoid timezone-mismatch when comparing timestamps stored as UTC strings in SQLite
- Run with: `uv run pytest` or, from the repo root, any of the Makefile targets:
  - `make test` -- full backend suite
  - `make test-core` -- only `backend.core`
  - `make test-services` -- only `backend.services`
  - `make coverage` -- `backend.core` with branch coverage
  - `make coverage-services` -- `backend.services` with branch coverage
  - `make coverage-html` -- writes `./htmlcov/index.html`
  - `make typecheck-core` -- strict mypy against `backend.core` (`disallow_untyped_defs=true`)
  - `make check` -- lint + typecheck-core + test-core (fast pre-commit gate)
  - `make check-all` -- lint + typecheck-core + test-core + test-services
- Run linters: `./scripts/lint.sh` (ruff + mypy), `./scripts/lint.sh --fix`, or `make lint` / `make lint-fix`

### Core layer invariants

`backend/core/` is the foundational layer; every other backend package depends
on it. Three invariants must hold:

1. **No dependencies on higher-level packages.** Modules in `backend.core` must
   not import from `backend.services`, `backend.routers`, `backend.channels`,
   `backend.steps`, etc. `backend.models` may only be imported lazily inside
   `Database.create_all` so that `Base.metadata` is populated before DDL.
2. **No framework imports except FastAPI leaves.** Only `auth.py` and
   `exceptions.register_exception_handlers` may touch FastAPI types. `config`,
   `logging`, `template`, `database`, and the rest of `exceptions` must be
   usable in contexts where FastAPI is not imported.
3. **Testability first.** Every stateful module-level singleton is a thin
   facade over a class (`Settings`, `Database`, `KeyStore`, `BoundLogger`) that
   can be constructed directly in a test with no global reset.

These are enforced by convention and by the `backend.core.*` mypy override in
`pyproject.toml`, which applies `disallow_untyped_defs=true` to this package
only.

### Services layer test suite

`backend/tests/services/` holds 177 tests covering the services layer.
Seven modules have dedicated test files with high branch coverage:

| Module | Test file | Coverage |
| ------ | --------- | -------- |
| `condition_evaluator.py` | `test_condition_evaluator.py` | 97% |
| `conversation_manager.py` | `test_conversation_manager.py` | 100% |
| `media_processor.py` | `test_media_processor.py` | 100% |
| `notification_dispatcher.py` | `test_notification_dispatcher.py` | 100% |
| `rag.py` | `test_rag.py` | 100% |
| `scheduler.py` | `test_scheduler.py` | 89% |
| `workflow.py` | `test_workflow.py` | 97% |

The `scheduler.py` module was refactored to lift module-level globals into a
`Scheduler` class. The module-level facade (`setup_scheduler`,
`_pipeline_executor`) is preserved for backward compatibility with
`backend/main.py` and `backend/mcp/server.py`.

Tests use the shared `db_engine`, `db_session`, and `db_factory` fixtures from
`backend/tests/conftest.py`. Media processor and notification dispatcher tests
mock external dependencies (ffmpeg, channel registry) via `monkeypatch`.

## External Services

| Service | Env Var | Used For |
| ------- | ------- | -------- |
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
- **Add dependencies without updating `pyproject.toml` and running `uv lock`** (backend) or `package.json` (frontend)
- **Skip permission checks** -- all new endpoints need entries in `config/auth.yaml`
- **Catch `AuthenticationError` or `PermissionDeniedError` in routers** -- let global handlers deal with them
- **Store secrets in config files** -- use `${ENV_VAR}` interpolation
- **Hardcode pipeline step order** -- use `PipelineStep` model with `order` field; each rule defines its own steps
- **Use `eval()` for condition expressions** -- use `ConditionEvaluator` (recursive-descent parser)
- **Use lazy imports for required dependencies** -- all imports at top of file (PEP 8). Exception: optional deps (e.g. `google-genai`) may use guarded lazy imports with a comment explaining why
- **Use `alert()` or `confirm()` in Vue views** -- use the `useNotify` and `useConfirm` composables from `frontend/src/composables/`
- **Swallow errors silently** -- bare `catch {}` blocks must log via `console.error` (frontend) or `logger.error` (backend)

## Timezone Conventions

The operator timezone is set once in `config/settings.yaml` under `app.timezone` (IANA format, e.g. `"America/New_York"`). Every layer of the stack must respect this convention.

### Backend rules

| Concern | Rule |
| ------- | ---- |
| Database storage | All timestamps stored as naive UTC (SQLite has no real tz support). Use `datetime.now(UTC)` for current time. |
| Timezone source | Always read from `settings.get("app.timezone", "UTC")`. Never hardcode a timezone. |
| ZoneInfo | Use `from zoneinfo import ZoneInfo` (stdlib, Python 3.9+). Never use `pytz`. |
| Local time for display | `datetime.now(ZoneInfo(tz_name))` when local wall-clock time is needed (pipeline context, MCP `get_local_datetime`). |
| UTC comparison from local | `local_dt.astimezone(UTC).replace(tzinfo=None)` to produce a naive UTC value for SQLite queries. |
| Daily rate-limit window | Use local midnight: `now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC).replace(tzinfo=None)`. |
| Cron scheduling (APScheduler) | Pass `timezone=ZoneInfo(settings.get("app.timezone", "UTC"))` to every `CronTrigger.from_crontab()` call. APScheduler handles DST transitions automatically. |
| Context filters (`time_range`, `day_of_week`) | The `now` datetime passed into `evaluate()` must be in the app timezone; `RulesEngine` ensures this. |

### Frontend rules

| Concern | Rule |
| ------- | ---- |
| Timezone source | Fetched at app startup from `GET /api/v1/admin/app-info` and stored in `frontend/src/services/timezone.js`. |
| Displaying timestamps | Import `formatDateTime`, `formatDateTimeShort`, etc. from `services/timezone.js`. Never call `toLocaleString()` / `toLocaleDateString()` / `toLocaleTimeString()` directly. |
| DST | `Intl.DateTimeFormat` with an IANA `timeZone` option handles DST automatically. |
| User time inputs | Time and cron inputs are in the operator timezone. Show `getAppTimezone()` as a hint next to every time input. |
| Converting HH:MM to UTC for the backend | Use `localHHMMToUTCISO(timeStr)` from `services/timezone.js`. |
| Converting UTC ISO to HH:MM for display | Use `isoToLocalHHMM(iso)` from `services/timezone.js`. |

### Timezone testing

- Use `RulesEngine(tz_name="UTC")` in unit tests so timestamp comparisons are consistent with the naive-UTC values in the in-memory SQLite test DB.
- Write dedicated tests for non-UTC timezones (e.g. `"America/New_York"`) to cover DST edge cases. See `TestTimezoneAwareLimits` and `TestTimeRangeContextFilter` in `backend/tests/services/test_rules_engine.py`.
- Scheduler timezone tests should patch `backend.services.scheduler.settings.get` and assert that the resulting `CronTrigger.timezone` matches the configured value.
