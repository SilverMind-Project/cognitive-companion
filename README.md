# Cognitive Companion

A privacy-first, on-premise AI system for senior care in multigenerational households.

Cognitive decline doesn't have to mean loss of independence. Cognitive Companion watches for situations where a gentle reminder might help -- without automating away the daily routines that give seniors agency. Rules are written in natural language and evaluated by vision and language models running entirely on-premise, so the system understands *context* rather than triggering on rigid conditions.

## Architecture

```text
 Edge Devices                         AI Pipeline                              Outputs
 ───────────                         ───────────                              ───────

 reCamera ──┐                    ┌─► Person ID Service   ──┐
            │    ┌────────────┐  │   (InsightFace/ArcFace) │
 WebSocket ─┼──► │   Event    │──┤                         ├─► Rules Engine
            │    │ Aggregator │  │   ┌──────────────────┐  │   (context/deps/rate-limit)
 HA Sensors─┘    └────────────┘  ├─► │ Vision LLM       │  │        │
                   MinIO ◄───────┘   │ (Cosmos Reason2) │──┘        ▼
                  (media)            └──────────────────┘    ┌─────────────┐
                                           │                 │  Logic LLM  │
                                           ▼                 │  (Gemma3)   │
                                  ┌────────────────┐         └──────┬──────┘
                                  │ Translation    │                │
                                  │(TranslateGemma)|◄───────────────┘
                                  └────────┬───────┘
                                           │
                ┌──────────────────────────┼──────────────────────────┐
                ▼              ▼           ▼           ▼              ▼
           WebSocket      Telegram     eInk Display   TTS      Home Assistant
           (frontend)     (caregiver)  (reTerminal)  (speaker) (actions + announce)

 ┌──────────────────────────────────────────────────────────────────────────────┐
 │  Admin Console (Vue 3 + Vuetify)       MCP Tool Server (AI agent access)     │
 │  Companion Voice UI (Gemini Live)      APScheduler (cron rules, polling)     │
 └──────────────────────────────────────────────────────────────────────────────┘
```

Each rule defines a **composable pipeline** -- an ordered sequence of steps executed by the `PipelineExecutor`. Rather than a fixed linear chain, administrators configure exactly which steps run and in what order, including conditional branching and wait/resume for multi-stage workflows. Sensor events are batched by the **Event Aggregator** (configurable window, batch size, cooldown), then matched against rules whose context filters, dependencies, and rate limits all pass. Each matched rule's pipeline executes independently, with every step logged for auditability.

## Key Features

- **Natural-language rules** with context filters (room, time-of-day, day-of-week, person presence, person activity) and inter-rule dependencies
- **Composable pipeline steps** -- 10 step types that can be assembled in any order per rule:
  `person_identification`, `vision_analysis`, `logic_reasoning`, `translation`, `notification`, `ha_action`, `activity_detection`, `wait`, `condition`, `verification`
- **Person identification** via ArcFace embeddings -- GPU-accelerated, no fine-tuning required, just enrollment
- **Annotated person identification images** with bounding boxes and name labels returned inline
- **Activity tracking** -- detect and record person activities (eating, sleeping, taking medication) as pipeline outputs for use as context filters in downstream rules
- **Motion direction detection** at doorways (left/right, towards/away from camera)
- **Whole-house location tracking** fusing camera detections with Home Assistant presence sensors
- **Home Assistant actions** as first-class pipeline steps (call any HA service from a rule)
- **Wait/resume for multi-stage workflows** -- pause a pipeline, resume on a timer or external trigger
- **Conditional branching** -- evaluate expressions against pipeline data to fork execution paths
- **Visual pipeline builder** in the admin UI for drag-and-drop step assembly
- **Real-time voice** conversations via Google Gemini Live with WebSocket audio streaming
- **Multi-channel notifications**: WebSocket, Telegram, eInk display, TTS, Home Assistant announcements
- **MCP tool server** exposing read-only tools (plus rule triggering) for AI agent integration
- **Role-based authentication** with API keys, device keys, and fnmatch permission patterns
- **Event aggregation** with configurable batching, windowing, and per-sensor cooldown
- **Tamil language support** for feedback delivery and voice interaction

## Prerequisites

| Component | Purpose | Notes |
|-----------|---------|-------|
| **NVIDIA GPUs** | Person-ID service + vLLM serving | DGX Spark |
| **Docker** + NVIDIA Container Toolkit | Container runtime | For person-ID service |
| **Home Assistant** | Sensor integration, audio playback, actions | REST API + long-lived token |
| **MinIO** (or S3-compatible) | Media object storage | Pre-signed URL support required |
| **vLLM** | Vision + translation model serving | Cosmos-Reason2-8B, TranslateGemma-12b |
| **Ollama** | Logic reasoning model | gemma3:4b |
| **Python 3.11+** | Backend runtime | 3.12 recommended |
| **Node.js 18+** | Frontend build | For admin console |

Optional:

| Component | Purpose |
|-----------|---------|
| Telegram Bot | Caregiver alert notifications |
| Google Gemini API | Real-time voice conversations |
| TTS service | Text-to-speech announcements |

## Quick Start

### 1. Configure

```bash
cp .env.example .env
# Edit .env with your service URLs and API keys
```

Review `config/settings.yaml` for application behavior (event aggregation, LLM models, polling intervals). See [Configuration](#configuration) for details.

### 2. Start the Person Identification Service

The face recognition service runs as a standalone GPU-accelerated container. See [`../person-identification-service/README.md`](../person-identification-service/README.md) for full setup and enrollment instructions.

```bash
cd ../person-identification-service
docker compose up -d
```

### 3. Start with Docker Compose

```bash
cp .env.example .env
# Edit .env with your service URLs and API keys
docker compose up -d
```

This starts the backend (port 8000) and frontend (port 80).

### 4. Local Development (without Docker)

**Backend:**

```bash
pip install -e ".[gemini]"
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev          # Development server at http://localhost:5173
npm run build        # Production build
```

### 5. Initial Setup

1. Open the admin console at `http://localhost:5173/admin`
2. Set your admin API key
3. Create rooms and register sensors
4. Enroll household members in the person-ID service (see its README)
5. Register members in the admin console under **Persons**
6. Create rules and assemble their pipeline steps using the visual builder

## Project Structure

```text
cognitive-companion/
├── backend/
│   ├── core/                   # Config loader, auth, database, exceptions, logging
│   ├── models/
│   │   ├── rule.py             # Rule, RuleContext, RuleDependency
│   │   ├── pipeline.py         # PipelineStep, WorkflowExecution
│   │   ├── person.py           # HouseholdMember, PersonSighting, PersonActivity
│   │   ├── event.py            # EventLog
│   │   ├── alert.py            # Alert
│   │   └── ...                 # Room, Sensor, Conversation, etc.
│   ├── schemas/
│   │   ├── rule.py             # Rule + PipelineStep request/response schemas
│   │   ├── workflow.py         # WorkflowExecution schemas
│   │   ├── activity.py         # PersonActivity schemas
│   │   └── ...                 # Alert, Event, Person, Room, Sensor schemas
│   ├── services/
│   │   ├── pipeline_executor.py    # Composable step executor with wait/resume
│   │   ├── condition_evaluator.py  # Safe expression parser for condition steps
│   │   ├── rules_engine.py         # Context matching, dependency checks, rate limits
│   │   ├── event_aggregator.py     # Frame batching and cooldown
│   │   ├── person_tracking.py      # Location fusion (camera + HA sensors)
│   │   ├── notification_dispatcher.py  # Multi-channel alert routing
│   │   ├── workflow.py             # Workflow orchestration
│   │   └── ...                     # Scheduler, sensor polling, media, RAG
│   ├── integrations/           # External clients (HA, MinIO, Telegram, TTS, LLMs)
│   │   └── llm/                # LLM provider implementations (vLLM, Ollama, Gemini)
│   ├── routers/
│   │   ├── rules.py            # Rule CRUD + pipeline step endpoints
│   │   ├── workflows.py        # Workflow execution list/detail/cancel
│   │   ├── activities.py       # Person activity log
│   │   └── ...                 # Alerts, events, persons, sensors, rooms, etc.
│   ├── mcp/                    # MCP tool registry and server
│   ├── websocket/              # WebSocket connection manager and audio handler
│   ├── assets/                 # Fonts and eInk display templates
│   └── main.py                 # App factory, lifespan, service wiring
├── frontend/
│   └── src/
│       ├── views/
│       │   ├── admin/
│       │   │   ├── DashboardView.vue
│       │   │   ├── RulesView.vue
│       │   │   ├── RuleDetailView.vue    # Per-rule pipeline builder + config
│       │   │   ├── ActivitiesView.vue    # Person activity log
│       │   │   ├── WorkflowsView.vue     # Workflow execution monitor
│       │   │   ├── PersonsView.vue
│       │   │   ├── SensorsView.vue
│       │   │   ├── RoomsView.vue
│       │   │   ├── EventsView.vue
│       │   │   └── AlertsView.vue
│       │   └── CompanionView.vue
│       ├── components/
│       │   └── pipeline/
│       │       ├── PipelineBuilder.vue    # Visual drag-and-drop step editor
│       │       ├── StepCard.vue           # Individual step display
│       │       ├── StepConfigDialog.vue   # Step-type-specific config form
│       │       └── StepPalette.vue        # Available step types for adding
│       ├── services/           # API client, WebSocket client
│       ├── router/             # Vue Router configuration
│       └── stores/             # Pinia state management
├── config/
│   ├── settings.yaml           # Application settings
│   ├── auth.yaml               # API keys, device keys, permissions
│   └── notifications.yaml      # Alert routing and escalation
├── data/                       # Runtime data (SQLite DB, media cache)
├── docker-compose.yml          # Compose file (backend + frontend)
├── pyproject.toml              # Python dependencies and tooling
└── .env.example                # Environment variable template
```

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `VISION_MODEL_URL` | Vision model endpoint — Cosmos Reason2 (OpenAI-compatible) |
| `TRANSLATE_MODEL_URL` | Translation model endpoint — TranslateGemma (OpenAI-compatible) |
| `LOGIC_MODEL_URL` | Logic/reasoning model endpoint — Gemma3 (OpenAI-compatible) |
| `GEMINI_API_KEY` | Google Gemini API key (real-time voice) |
| `TTS_API_URL` | Text-to-speech service endpoint |
| `HOME_ASSISTANT_URL` | Home Assistant base URL |
| `HOME_ASSISTANT_TOKEN` | HA long-lived access token |
| `MINIO_ENDPOINT` | MinIO / S3-compatible endpoint |
| `MINIO_ACCESS_KEY` | MinIO access key |
| `MINIO_SECRET_KEY` | MinIO secret key |
| `PERSON_ID_SERVICE_URL` | Person identification service URL |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CAREGIVER_CHAT_ID` | Caregiver Telegram chat ID |
| `CC_ADMIN_API_KEY` | Admin API key |
| `CC_CAREGIVER_API_KEY` | Caregiver API key (read-only + alerts) |
| `CC_MCP_API_KEY` | MCP/AI agent API key (read-only) |

All variables are interpolated into YAML config files using `${ENV_VAR}` syntax.

### settings.yaml

| Section | Controls |
|---------|----------|
| `app` | Name, version, timezone, debug mode |
| `server` | Host and port binding |
| `cors` | Allowed origins |
| `database` | SQLite database URL |
| `llm` | Vision, logic, translation, and realtime LLM provider configs |
| `tts` | TTS voice and speed |
| `homeassistant` | HA URL, token, polling interval, bathroom time limit |
| `minio` | Object storage credentials and presigned URL expiry |
| `event_aggregator` | Batch size, window, cooldown, media retention |
| `conversation` | History TTL and max turns per session |
| `websocket` | Max connections, audio backend, lazy connect |
| `mcp` | Enabled tools list |
| `person_id` | Person-ID service URL, confidence threshold, motion detection |
| `person_tracking` | Location stale timeout, HA propagation toggle |
| `rag` | Optional RAG index configuration |
| `image` | eInk template and font paths |
| `logging` | Log level |

### auth.yaml

Authentication uses a role-based model:

1. **API keys** are defined with a name and one or more permission roles
2. **Device keys** are 8-character uppercase alphanumeric strings for hardware that can't set HTTP headers
3. **Permission map** translates role names to endpoint patterns using `fnmatch` syntax

```yaml
# Example: caregiver can read everything and take alert actions
caregiver:
  - "GET /api/v1/*"
  - "POST /api/v1/alerts/*/action"
```

Keys are resolved from: `X-API-Key` header, `?api_key` query param, or `device_key` in JSON body.

### notifications.yaml

Maps alert levels to notification channels with escalation:

| Level | Default Channels | Escalation |
|-------|-----------------|------------|
| `emergency` | WebSocket, Telegram, eInk, TTS, HA | Every 5 min, 3x repeat |
| `warning` | WebSocket, Telegram, eInk | Every 10 min |
| `info` | WebSocket only | None |
| `reminder` | WebSocket, TTS, eInk | None |

## LLM Pipeline

Rules no longer use a fixed linear pipeline. Instead, each rule defines a **composable sequence of pipeline steps** stored in the database and executed by the `PipelineExecutor`. Steps share a `pipeline_data` dictionary that accumulates results as execution progresses.

### Pipeline Step Types

| Step Type | Purpose |
|-----------|---------|
| `person_identification` | Run face recognition on media frames; record sightings and update location |
| `vision_analysis` | Send media + prompt to the vision LLM (Cosmos Reason2) |
| `logic_reasoning` | Evaluate vision output with the logic LLM (Gemma3); decide whether to act. Supports configurable `response_format` for different output schemas (default, activity_detection, custom). |
| `translation` | Translate text to a target language (TranslateGemma) |
| `notification` | Dispatch an alert to configured channels based on alert level |
| `ha_action` | Call a Home Assistant service (turn on lights, lock doors, etc.) |
| `activity_detection` | Record activities from pipeline data to the PersonActivity table. Pair with a preceding `logic_reasoning` step (with `response_format: activity_detection`) for LLM analysis. |
| `wait` | Pause execution for a configured duration; resume automatically via scheduler |
| `condition` | Evaluate an expression against pipeline data; branch to different steps |
| `verification` | Query the PersonActivity database to verify whether household members completed (or did not complete) specific activities within a time window. |

### Condition Expressions

Condition steps use a safe expression evaluator (no `eval()`) that supports path access, comparisons, boolean operators, and built-in functions:

```text
person_detections.count > 0
logic_response.is_notification_needed == true
exists(translation) and not contains(vision_response, "empty")
```

### Example Pipeline Configurations

**Camera monitoring rule** -- the classic detect-analyze-notify chain:

```text
person_identification --> vision_analysis --> logic_reasoning --> translation --> notification
```

**Lunch reminder** -- detect the person, analyze activity with LLM, record it, wait, then verify and remind:

```text
vision_analysis --> logic_reasoning (response_format: activity_detection) --> activity_detection --> wait (30 min) --> verification --> notification
```

**Light monitor** -- analyze, decide, notify caregiver, wait for response, then verify and act:

```text
vision_analysis --> logic_reasoning --> notification --> wait (5 min) --> verification --> ha_action
```

Each step stores its configuration (prompts, HA service calls, wait durations, condition expressions) in a per-step `config_json` field, so the same step type can behave differently across rules.

### Workflow Execution

When a rule's pipeline is triggered, a `WorkflowExecution` record tracks progress:

- **Status**: `running`, `waiting`, `completed`, `failed`, `cancelled`
- **Current step**: which step the executor is on (or paused at)
- **Pipeline data**: the accumulated output dictionary from all completed steps
- **Resume**: `wait` steps set a `resume_at` timestamp; the scheduler picks them back up

All intermediate results are persisted in `pipeline_data_json` on both the `WorkflowExecution` and the `EventLog` for debugging and auditability.

## API Reference

All endpoints are under `/api/v1/` and require authentication.

### Rooms

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/rooms` | List all rooms |
| `POST` | `/rooms` | Create a room |
| `PUT` | `/rooms/{id}` | Update a room |
| `DELETE` | `/rooms/{id}` | Delete a room |

### Sensors

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/sensors` | List sensors (filter by `room_id`, `sensor_type`, `source`) |
| `POST` | `/sensors` | Register a sensor |
| `PUT` | `/sensors/{id}` | Update a sensor |
| `DELETE` | `/sensors/{id}` | Delete a sensor |

### Rules

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/rules` | List all rules |
| `POST` | `/rules` | Create a rule |
| `GET` | `/rules/{id}` | Get a rule with its pipeline steps, contexts, and dependencies |
| `PUT` | `/rules/{id}` | Update a rule |
| `DELETE` | `/rules/{id}` | Delete a rule and its pipeline steps |
| `POST` | `/rules/{id}/execute` | Manually trigger a rule's pipeline (returns execution ID) |

Rule fields: `name`, `description`, `enabled`, `trigger_type` (sensor_event / cron / manual), `primary_sensor_id`, `schedule_cron`, `cool_off_minutes`, `max_daily_triggers`.

#### Pipeline Steps

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/rules/{id}/steps` | List pipeline steps for a rule (ordered) |
| `POST` | `/rules/{id}/steps` | Add a step (auto-assigned to end of sequence) |
| `PUT` | `/rules/{id}/steps/{step_id}` | Update a step's type, config, label, or enabled flag |
| `DELETE` | `/rules/{id}/steps/{step_id}` | Remove a step (remaining steps re-ordered) |
| `PUT` | `/rules/{id}/steps/reorder` | Bulk reorder steps by passing `[{id, order}, ...]` |

#### Contexts and Dependencies

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/rules/{id}/contexts` | List context filters |
| `POST` | `/rules/{id}/contexts` | Add a context filter (room, time_range, day_of_week, person_presence, person_activity) |
| `DELETE` | `/rules/{id}/contexts/{ctx_id}` | Remove a context filter |
| `GET` | `/rules/{id}/dependencies` | List rule dependencies |
| `POST` | `/rules/{id}/dependencies` | Add a dependency on another rule |
| `DELETE` | `/rules/{id}/dependencies/{dep_id}` | Remove a dependency |

### Workflows

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/workflows` | List workflow executions (filter by `rule_id`, `status`, `limit`) |
| `GET` | `/workflows/{id}` | Get execution detail with full pipeline data |
| `POST` | `/workflows/{id}/cancel` | Cancel a running or waiting execution |

### Activities

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/activities` | List detected person activities (filter by `person_id`, `activity_type`, `room_name`) |

### Alerts

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/alerts` | List alerts (filter by `resolved`, `room_name`, `alert_type`) |
| `GET` | `/alerts/{id}` | Get a single alert |
| `POST` | `/alerts/{id}/action` | Dismiss or request assistance for an alert |

### Events

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/events` | List event logs (filter by `rule_name`, `status`, `limit`) |

### Persons

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/persons` | List all household members |
| `POST` | `/persons` | Register a new member |
| `GET` | `/persons/locations` | Current location of all tracked members |
| `GET` | `/persons/{id}` | Get member details |
| `PATCH` | `/persons/{id}` | Update a member |
| `DELETE` | `/persons/{id}` | Remove a member and their data |
| `GET` | `/persons/{id}/location` | Current location of a specific member |
| `GET` | `/persons/{id}/history` | Location timeline (`?hours=24`) |
| `GET` | `/persons/{id}/sightings` | Recent camera sightings (`?limit=20`) |

### Device

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/device/recamera` | Upload image from reCamera (device key auth) |
| `POST` | `/device/reterminal` | reTerminal button/command endpoint |

### Image (eInk Display)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/image/active` | Get the currently active eInk image |
| `POST` | `/image/render` | Render a new notification image |
| `POST` | `/image/reset` | Reset to default template |

### Occupancy

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/occupancy` | Room occupancy from presence sensors |

### MCP

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/mcp/tools` | List available MCP tools |
| `POST` | `/mcp/tools/{name}` | Execute an MCP tool |

### Home Assistant Sync

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ha/sync/rooms` | Import rooms (areas) from Home Assistant |
| `POST` | `/ha/sync/sensors` | Import sensors from Home Assistant areas |

### Other

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check (no auth required) |
| `WS` | `/ws` | WebSocket for audio streaming and notifications |
| `GET` | `/admin/config` | Inspect active configuration |

## Person Identification and Tracking

Person identification runs as a [companion microservice](../person-identification-service/) using InsightFace (buffalo_l model pack) with ArcFace 512-dimensional embeddings.

**Enrollment**: Provide 5-10 reference photos per person via the person-ID service API. No model fine-tuning is needed -- ArcFace generalizes from pretrained weights.

**Identification**: The backend sends batched frames to `POST /api/v1/identify-batch`. The service returns per-frame face detections with identity, confidence, and bounding boxes.

**Annotated images**: When the `include_annotated_image` flag is set in a `person_identification` pipeline step's config, the person-ID service returns a copy of each frame with bounding boxes and name labels drawn over detected faces. These annotated images are stored in pipeline data and can be forwarded to downstream notification steps for visual confirmation.

**Motion Detection**: Cross-frame centroid tracking classifies movement direction (left-to-right, right-to-left, towards-camera, away-from-camera, stationary). Door-mounted cameras can use this to infer entering vs. leaving.

**Location Tracking**: The `PersonTrackingService` fuses camera detections with Home Assistant presence sensors to maintain per-person location state. When a person's room changes, a history entry is created. For rooms without cameras (e.g., bathrooms), HA presence sensor activations are correlated with the most recent camera sighting to infer who is present.

**Home Assistant Propagation**: Person locations are pushed to HA `input_text` helpers (`input_text.cc_{person_id}_location`) for use in automations and dashboards.

## E-Ink Display Pipeline

The system renders notification images for color e-ink displays (800x480 reTerminal). Each device gets its own active image. ESPHome-based devices poll a static URL to fetch their current image.

### Per-Device Image Serving

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/image/active` | Serve the active image for the authenticated device (`sensor_id` derived from device key) |
| `GET` | `/image/active/{sensor_id}` | Serve the active image for a specific sensor (admin use) |

Images fall back to a default template when the active image is expired or missing.

### Image Templates

Templates define background images with configurable text regions (bounding boxes). Regions specify where rendered text is placed on the background.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/image/templates` | List all templates |
| `POST` | `/image/templates` | Create a template (multipart upload with image + metadata) |
| `PUT` | `/image/templates/{id}` | Update regions or metadata |
| `DELETE` | `/image/templates/{id}` | Remove a template |

### Rendering

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/image/render` | Render text onto a template for target devices |
| `POST` | `/image/preview` | Preview a render without saving (returns PNG) |
| `POST` | `/image/reset` | Reset a device's display to the default template |

### Pipeline Integration

The `notification` step in composable pipelines supports an `eink_targets` config field to target specific displays. When `eink` is included in the notification channels, the `NotificationDispatcher` renders alert images automatically for the specified targets.

### Frontend Template Editor

Available at `/admin/eink-templates`. Upload background images, draw text regions with bounding boxes, select fonts, and preview renders before saving.

## MCP Integration

The [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) server exposes tools that AI agents can discover and call to query system state and trigger actions.

**Available tools:**

| Tool | Description |
|------|-------------|
| `get_rooms` | List all configured rooms |
| `get_sensors` | List sensors (filter by room, type) |
| `get_room_occupancy` | Current occupancy from presence sensors |
| `get_recent_images` | Recent camera images for a sensor |
| `get_light_level` | Illuminance from a HA sensor |
| `get_alerts` | Recent emergency alerts |
| `get_event_logs` | Rule execution event logs |
| `get_rules` | Configured automation rules |
| `get_conversation_history` | Recent conversation turns |
| `get_person_locations` | Current location of all tracked members |
| `get_person_sightings` | Camera sighting history for a person |
| `get_person_activities` | Recent detected activities for a person (eating, sleeping, etc.) |
| `get_workflow_executions` | Recent pipeline workflow executions (filter by rule, status) |
| `get_rule_pipeline` | Pipeline step definitions for a specific rule |
| `trigger_rule` | Manually trigger a rule's pipeline execution |

Agents authenticate with the MCP API key. Tool discovery is via `GET /api/v1/mcp/tools`, execution via `POST /api/v1/mcp/tools/{name}`.

## Frontend

The admin console is a Vue 3 + Vuetify 3 single-page application with Material Design components.

**Admin views** (`/admin`):

| View | Purpose |
|------|---------|
| Dashboard | System stats, person locations, room occupancy, recent alerts |
| Rules | CRUD rules with trigger type, sensor binding, and rate-limit settings |
| Rule Detail | Per-rule pipeline builder with drag-and-drop step assembly, step config dialogs, and reordering |
| Sensors | Manage camera and presence sensors |
| Rooms | Manage rooms and HA area mappings |
| Events | Browse rule execution logs with pipeline data inspection |
| Alerts | View and resolve emergency alerts |
| Persons | Manage household members, view locations, history, and sightings |
| Activities | Browse detected person activities with filters by person, type, and room |
| Workflows | Monitor workflow executions, inspect pipeline state, cancel running/waiting workflows |

**Pipeline builder components** (`frontend/src/components/pipeline/`):

| Component | Purpose |
|-----------|---------|
| `PipelineBuilder.vue` | Visual editor showing the ordered step list with drag-to-reorder |
| `StepCard.vue` | Displays a single step's type, label, and enabled state |
| `StepConfigDialog.vue` | Step-type-specific configuration form (prompts, HA services, wait durations, conditions) |
| `StepPalette.vue` | Sidebar listing available step types for adding to the pipeline |

**Companion view** (`/`): Voice interaction interface using WebSocket audio streaming with Google Gemini Live.

## Hardware Integration

### Seeed reCamera

Compact Linux camera that captures images and uploads via `POST /api/v1/device/recamera`. Authenticates with an 8-character device key in the JSON body. Images are passed to the event aggregator for batching.

### Seeed reTerminal

Linux SBC with a 5" touchscreen and built-in eInk display. Fetches rendered notification images from `GET /api/v1/image/{id}`. Reports button presses via `POST /api/v1/device/reterminal`.

### Home Assistant Sensors

The backend polls Home Assistant entities at a configurable interval (default: 30s). Supported sensor types:

- **Presence** sensors (binary PIR/mmWave) for room occupancy
- **Light** sensors (illuminance) for context-aware rules
- **Media players** for TTS announcements

## Development

### Backend

```bash
pip install -e ".[dev,gemini]"
ruff check backend/             # Lint
ruff format backend/            # Format
pytest                          # Tests (when available)
```

### Frontend Dev Server

```bash
cd frontend
npm install
npm run dev                     # Dev server with HMR
npm run build                   # Production build
```

### Database

SQLite with SQLAlchemy 2.0. Tables are auto-created on startup. For schema changes, delete `data/cognitive_companion.db` and restart -- there are no migrations.

### Extending the Pipeline

Adding a new pipeline step type touches 4 files. The pipeline executor passes a shared `pipeline_data` dictionary from step to step. Each handler reads upstream results and merges its own output back in.

1. **Backend model.** Add the type string to `STEP_TYPES` in `backend/models/pipeline.py`.
2. **Backend handler.** Add an `async def _step_<name>()` method in `backend/services/pipeline_executor.py` and register it in the `handlers` dict inside `_execute_step()`.
3. **Frontend palette.** Add `{ type, label, icon }` to the `groups` array in `frontend/src/components/pipeline/StepPalette.vue`.
4. **Frontend config form.** Add a `<template v-if>` block + defaults entry in `frontend/src/components/pipeline/StepConfigDialog.vue`.

See the full guide with code examples in [AGENTS.md](AGENTS.md#adding-a-new-pipeline-step-type).

## Roadmap

Proposed features and integration pathways for future development.

### Home Assistant Webhook Triggers

**Problem**: HA automations can't trigger CC pipelines because communication is one-way (CC polls HA, never the reverse).

**Design**: Per-rule `webhook_id` + `webhook_secret` fields. A new `POST /api/v1/webhook/{webhook_id}?secret=...` endpoint accepts a JSON body that becomes `pipeline_data["trigger_input"]`. Bypasses API key auth via per-rule webhook secrets. HA automations call the webhook URL to trigger pipelines with custom parameters.

### Enhanced Pipeline Triggers with Input Parameters

**Problem**: The `trigger_rule` MCP tool and manual execute endpoint accept no input parameters.

**Design**: Add `input_params: dict` to `TriggerContext`. Modify `POST /rules/{id}/execute` and the MCP `trigger_rule` tool to accept an `input_params` JSON body. Parameters become available in `pipeline_data["trigger_input"]` for downstream steps. Use case: an external AI agent triggers a reminder pipeline with a custom message.

### Gemini Live Tool Calling

**Problem**: The voice agent can only converse. It can't look up information or take actions mid-conversation.

**Design**: Extend `GeminiLiveProvider.build_config()` to include tool definitions built from the MCP registry. Add RAG as a `lookup_knowledge` tool. In the audio session handler, detect `FunctionCall` parts from Gemini responses, route to the appropriate MCP tool or RAG service, and send `FunctionResponse` back. All execution is client-side, so no public endpoint is needed. The voice agent could say "Let me check where grandma is" → call `get_person_locations` → respond with the result.

### Pipeline Templates / Presets

**Problem**: Creating pipelines from scratch is complex for new users.

**Design**: JSON fixtures file with preset pipeline definitions (Camera Alert, Periodic Check, Medication Reminder). A `GET /rules/templates` endpoint lists presets, and `POST /rules/from-template` creates a rule from one. "Use Template" button in the rule creation dialog.

### Activity Timeline

**Problem**: `PersonActivity` records exist but there is no timeline visualization.

**Design**: A `GET /persons/{id}/timeline?date=YYYY-MM-DD` endpoint merging activities, sightings, and alerts into a unified chronological view. Frontend `v-timeline` component in the person detail drawer.

## License

AGPL-3.0-or-later
