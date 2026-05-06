# Cognitive Companion

A privacy-first, on-premise AI system for senior care in multigenerational households.

Cognitive decline doesn't have to mean loss of independence. Cognitive Companion watches for moments where a gentle reminder might help, without automating away the daily routines that give seniors agency. Caregivers compose rules out of vision, language, and tracking primitives that run entirely on local hardware. The system understands *context*, not just motion: a person standing in the kitchen at noon means something different than at 3 AM.

> Looking for the deep technical reference? See [AGENTS.md](AGENTS.md). Working in the IDE with an AI assistant? Start with [CLAUDE.md](CLAUDE.md). For the user-facing documentation portal, see [silvermind-project.github.io](https://silvermind-project.github.io).

---

## Goals

1. **Context-aware monitoring**, not motion alerts. Frames are interpreted by vision and language models, then evaluated against caregiver rules that compose perception, reasoning, and action steps.
2. **Privacy by architecture.** All inference runs on-premise via vLLM, llama.cpp, and the sibling AI services. Camera frames are stored in your own MinIO and never leave your network unless you configure an outbound channel.
3. **Senior agency first.** The system suggests and reminds rather than acting. A lunch reminder is a reminder, not a robot.
4. **Multigenerational by default.** Built for a household where a senior lives with family who want to help but cannot watch all day. Caregiver alerts go out by Telegram or webhook; the senior interacts via voice, popup, e-ink display, and TTS.
5. **Extensible by drop-in.** Pipeline steps, notification channels, and context filters are auto-discovered Python files. Adding one is a single module, not a fork.

---

## Architecture at a glance

```text
            ┌─────────── Edge devices ───────────┐
            │  reCamera (HTTP push)              │
            │  reTerminal (e-ink + button)       │
            │  Home Assistant sensors (poll)     │
            │  RTSP cameras → continuous-tracking│
            └──────────────────┬─────────────────┘
                               │
                               ▼
              ┌──────────────────────────────────┐
              │   Cognitive Companion (FastAPI)  │
              │                                  │
              │  EventAggregator → RulesEngine   │
              │              ↓ matched rules     │
              │       PipelineExecutor           │
              │   (19 step types, plugin-based)  │
              │              ↓                   │
              │       NotificationDispatcher     │
              │   (7 channels, plugin-based)     │
              │                                  │
              │  CTSRuntime (Redis Streams)      │
              │  PresenceService (fused)         │
              │  MCP server (FastMCP, /mcp)      │
              │  WebSocket audio (Gemini Live)   │
              └────┬──────────┬──────────┬───────┘
                   │          │          │
                   ▼          ▼          ▼
            person-id    scene-analysis  semantic-memory
            service       service          service
            (ArcFace)    (YOLO+Florence-2 (pgvector
                          +CLIP)            observations,
                                            movements,
                                            trends)
                   │
                   ▼
            tts-service (svara / fish_speech / edge_tts)

            continuous-tracking/  (separate monorepo path)
            ├── rtsp-ingress (Go)        ─► go2rtc + motion gate + MinIO
            ├── tracking-orchestrator    ─► YOLO26L + SOLIDER-REID + RTMPose
            │                               + BoT-SORT + Bayesian identity
            │                               + dementia signal worker
            └── Redis Streams ──► CC subscribers
                tracking.events / tracking.revisions / tracking.signals
```

Camera and sensor frames are batched by the **EventAggregator** (configurable window, batch size, per-sensor cooldown) and matched against rules whose context filters, dependencies, and rate limits pass. Each matching rule's pipeline executes independently, with every step logged to `EventLog` and `WorkflowExecution` for audit. Notifications fan out to whichever channels `notifications.yaml` and the rule's `notification` step request.

When `cts.enabled` is true, the **continuous-tracking-service** runs alongside CC. It pulls RTSP streams, tracks individuals with BoT-SORT and a Bayesian identity resolver, and publishes high-level dementia signals (pacing, sundowning, bathroom anomalies, nighttime movement, prolonged stillness, unexplained absence) to Redis Streams. CC subscribes via `CTSRuntime`, persists the signals, fuses location into `PresenceService`, and exposes everything through admin views, MCP tools, and a `dementia_signal` rule filter.

---

## Key features

- **Composable per-rule pipelines.** Each rule defines its own ordered `PipelineStep` rows. 19 built-in step types: `llm_call`, `person_identification`, `scene_analysis`, `semantic_memory_query`, `semantic_memory_write`, `object_trend_analysis`, `presence_query`, `home_state`, `tracking_query` (deprecated), `notification`, `ha_action`, `activity_detection`, `activity_session_start`, `activity_session_end`, `daily_report`, `verification`, `condition`, `wait`, `interactive_prompt`. Add new types by dropping a file under `backend/steps/builtin/` or `backend/steps/contrib/`.
- **Six trigger types.** `sensor_event` (camera or HA sensor), `cron`, `manual`, `webhook` (HMAC-validated), `telegram` (bot command, fail-closed chat-ID whitelist), `occupancy_duration` (presence sensor occupied >= N minutes).
- **Unified LLM step (`llm_call`).** Picks a model from `llm.models` in `settings.yaml` by `model_id`. Supports vision (image attachment), structured JSON via `guided_json` (vLLM) or prompt injection (llama.cpp), sensor-ordered image assembly for inter-frame analysis, and hallucination retry. Replaces the legacy `vision_analysis`, `logic_reasoning`, and `translation` steps.
- **Multi-camera continuous tracking.** Optional integration with `continuous-tracking/`. Multi-camera person re-identification, room-level dwell, dementia-relevant signal detection, soft-revisable identity assignments, and a CTS BFF surface (cameras, calibration, privacy zones, adjacency, signals, keyframes, identity corrections, presence) under `/api/v1/cts/*`.
- **Whole-house presence fusion.** `PresenceService` reads a priority chain in `config/presence.yaml`: night anchor (bed sensor + light state) → HA bed sensor → CTS location → HA device tracker → stale fallback → unknown sentinel. Drives the `presence_query` and `home_state` steps and the `presence_status` / `presence_dwell` / `home_state` filters.
- **Person identification + camera topology.** Face recognition via the `person-identification-service` (InsightFace, ArcFace 512-d). Per-camera `movement_map` config translates raw motion direction into semantic transitions (entering / exiting / approaching / stationary). The `room_transition` filter gates rules on doorway behaviour.
- **Scene analysis + semantic memory.** The `scene_analysis` step calls the `scene-analysis-service` (YOLO11x + Florence-2-large + CLIP ViT-L/14). The `semantic_memory_write` and `semantic_memory_query` steps persist and recall observations and movements via the `semantic-memory-service` (PostgreSQL + pgvector). The `scene_contains` filter gates rules on "object or hazard observed in this room within N minutes".
- **Activity tracking.** `activity_detection`, `activity_session_start`/`end` (duration-aware), `verification` (database query), `daily_report` (end-of-day wellness rollup with optional LLM summary). All values support `{{template}}` syntax. `capture_scene_description: true` saves the upstream VLM output alongside the activity for full audit.
- **Multi-channel notifications.** 7 channels: `pwa_popup_text`, `pwa_realtime_ai`, `pwa_tts_announcement`, `telegram`, `eink`, `ha_speaker_tts`, `webhook`. Each supports per-step template overrides; e-ink notifications support per-rule template selection and expiry.
- **E-ink display pipeline.** Per-device active image with template editor (background image + text regions), automatic expiry, and SHA-256 hash-based refresh suppression to avoid disruptive pixel cycles when content is unchanged.
- **Realtime voice companion.** WebSocket audio streaming with Google Gemini Live, voice tool calling via the MCP registry, transcript actor delineation (orchestrator prompts hidden from the senior's UI), background-noise high-pass filtering on the frontend.
- **MCP tool server.** FastMCP at `/mcp` with 24 tools including 5 semantic-memory read tools (`get_recent_scene_objects`, `get_scene_observations`, `get_person_movements`, `get_room_trend`, `search_similar_scenes`). A subset is mirrored to Gemini Live for voice tool calling.
- **Plugin systems.** Three auto-discovered registries (steps, channels, filters). Each plugin is one file with a class decorated by `@*Registry.register`.
- **Visual pipeline builder** in the admin UI: drag-and-drop step ordering, step type palette loaded dynamically from `GET /api/v1/pipeline/step-types`, per-step config dialog, structured filter dialogs in `RuleDetailView`.
- **Role-based auth.** API keys, hardware device keys (8-char alphanumeric), and `fnmatch` permission patterns under `config/auth.yaml`. Hardware sensors defined under `auth.device_keys` are auto-upserted at startup.
- **Outbound webhooks** for triggering external systems from a `notification` step, plus per-rule **inbound webhooks** with HMAC-validated secrets.

---

## Prerequisites

| Component | Purpose | Notes |
| --- | --- | --- |
| NVIDIA GPU(s) | Person ID + vLLM serving | DGX Spark works well; one GPU minimum for face recognition. |
| Docker + NVIDIA Container Toolkit | Container runtime | Required for the person-ID service container. |
| PostgreSQL 17 | Application database | Docker Compose ships one; or point at an external server. |
| Home Assistant | Sensor integration, area discovery, media-player playback | REST API + long-lived token. |
| MinIO (or S3-compatible) | Media object storage | Pre-signed URL support required. |
| vLLM | Vision model serving | Cosmos-Reason2-8B via OpenAI-compatible API. |
| llama.cpp `llama-server` | General-purpose model serving | Gemma 4 26B (text + vision + translation). |
| Python 3.12, Node 18+ | Runtimes | Backend and frontend. |

Optional but recommended:

| Component | Purpose |
| --- | --- |
| `tts-service` | TTS announcements via PWA stream or HA media players. |
| `scene-analysis-service` | YOLO + Florence-2 + CLIP for richer scene context. |
| `semantic-memory-service` | Observation, movement, and trend memory; powers `scene_contains` and the memory steps. |
| `continuous-tracking/` | Multi-camera tracking and dementia-signal generation. |
| Telegram bot | Caregiver alerts and command triggers. |
| Google Gemini API | Realtime voice companion. |

---

## Quick start

### 1. Configure

```bash
cp .env.example .env
# Edit .env with service URLs and API keys
```

Review `config/settings.yaml` for application behaviour (event aggregation, LLM models, polling intervals, CTS feature flag). The single source of truth for the operator timezone is `app.timezone`.

### 2. Start PostgreSQL

```bash
docker compose up -d postgres
make init-db                         # create DB, run migrations, seed
```

Or point at an external Postgres by setting the `POSTGRES_*` env vars in `.env`.

### 3. Start the person identification service

```bash
cd ../person-identification-service
docker compose up -d
```

### 4. Bring up the rest

```bash
docker compose up -d
```

This starts the backend on port 8000 and the frontend on port 80. Open the admin UI at `http://<host>/admin` and:

1. Set your admin API key.
2. Sync rooms and sensors from Home Assistant (or create them manually).
3. Register household members under **Members and Enrollment**, then enroll faces by uploading 5-10 reference photos per person directly from the UI.
4. Build rules using the visual pipeline builder.

### 5. Enable continuous tracking (optional)

```yaml
# cognitive-companion/config/settings.yaml
cts:
  enabled: true
```

Then bring up the CTS services per [continuous-tracking/README.md](../continuous-tracking/README.md). The CC backend will start the three Redis Streams subscribers and expose CTS admin views (`/admin/cts/*`).

### 6. Local development without Docker

```bash
# Backend
cd backend
uv sync --extra gemini
cd ..
uv run --directory backend uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd frontend
npm install
npm run dev
```

---

## Project structure

See [AGENTS.md section 3](AGENTS.md#3-repository-layout) for the deep view. Top-level shape:

```text
cognitive-companion/
├── backend/         FastAPI app (core, models, schemas, services, integrations,
│                    steps, channels, filters, routers, mcp, websocket, alembic, tests)
├── frontend/        Vue 3 + Vuetify admin console + senior-facing companion UI
├── config/          settings.yaml, auth.yaml, notifications.yaml, presence.yaml
├── data/            Runtime media cache
├── docker-compose.yml, kubernetes/, Makefile
└── AGENTS.md, CLAUDE.md, README.md
```

---

## Configuration

YAML files in `config/` with `${ENV_VAR}` interpolation:

- `settings.yaml`: application settings (LLM models, polling intervals, MinIO, MCP tools, scene-analysis, semantic-memory, CTS, presence, image, logging).
- `auth.yaml`: API keys, device keys, fnmatch permission map.
- `notifications.yaml`: alert-level to channel routing.
- `presence.yaml`: PresenceService provider chain (priority-ordered).

Frontend timezone is fetched at startup from `GET /api/v1/admin/app-info`. Admin UI timestamps, cron schedules, time-range filters, day-of-week filters, and daily-trigger counters all interpret `app.timezone`. DB always stores UTC.

For the full configuration surface, see [docs/guide/configuration](https://silvermind-project.github.io/guide/configuration) on the documentation portal.

---

## Real-world examples

The pipeline builder is most useful when you can see what a complete rule looks like. The documentation portal hosts worked examples for each of the scenarios below; this section sketches the shape so you know they exist.

| Scenario | Trigger | Filters | Pipeline shape |
| --- | --- | --- | --- |
| Stove-caution reminder when only grandma is home | `sensor_event` (kitchen camera) | `room: Kitchen` + `person_presence: grandma` + `person_presence: NOT others` | `scene_analysis` → `condition` (stove on) → `notification` (`pwa_tts_announcement`) |
| Lunch eaten + send images to caretaker | `cron` (every 10 min, 12:00-14:00) | `time_range` + `person_presence: grandma in Kitchen` | `llm_call` (vision, image_source=both, since_minutes=30) → `condition` (lunch_observed) → `activity_detection` (`meal_lunch`) → `notification` (`telegram`) |
| Lunch reminder if missed by 14:00 | `cron` (14:00 daily) | none | `verification` (no `meal_lunch` since 11:00) → `notification` (`telegram` to caregivers + `pwa_tts_announcement` and `eink` to grandma) |
| Unknown person enters when grandma is alone | `sensor_event` (entry camera) | `home_state: grandma at home` + `person_presence: NOT others` | `person_identification` → `condition` (unknown identity present) → `notification` (`telegram` emergency) |
| Pacing detection (CTS) | `dementia_signal` (kind=pacing) | `time_range`, `person_presence: grandma at home` | `presence_query` → `condition` (sustained signal) → `notification` (`telegram` + `pwa_tts_announcement`) |
| Sundowning escalation (CTS) | `dementia_signal` (kind=sundowning_index) | `time_range: 17:00-22:00` | `notification` (`pwa_realtime_ai` to gently engage) → `wait 10 min` → `verification` → `notification` (`telegram` if persists) |
| Bathroom anomaly with caregiver suppression | `dementia_signal` (kind=bathroom_dwell_anomaly) | `dementia_signal: not acknowledged within 30m` | `notification` (`telegram`) |

The full worked examples (with config JSON and screenshots) are in the [Real-world examples](https://silvermind-project.github.io/features/pipeline#real-world-examples) section of the docs portal, plus a dedicated [Continuous tracking](https://silvermind-project.github.io/features/continuous-tracking) page.

---

## Development

### Backend

```bash
cd backend
uv sync --extra dev --extra gemini

# Lint, format, types, tests
make lint
make format
make typecheck-core    # strict mypy on backend.core
make typecheck         # full backend tree
make test              # full backend test suite
make test-core         # backend.core only (~113 tests)
make test-services     # backend.services only

# Coverage
make coverage          # core, terminal output
make coverage-services
make coverage-html     # HTML report under ./htmlcov

# Pre-commit gates
make check             # lint + typecheck-core + test-core (fast)
make check-all         # adds test-services
```

`make check` is the gate every PR must pass. `make check-all` is required for any change that touches `backend/services/` or shared infrastructure.

### Frontend

```bash
cd frontend
npm install
npm run dev            # Vite dev server with HMR
npm run build          # production build
npm run test           # spec suite under src/views/admin/__tests__
```

### Quality bar by layer

| Layer | What it owns | Standard |
| --- | --- | --- |
| `backend/core/` | Settings, Database, KeyStore, BoundLogger, exceptions, template, time helpers | Strict mypy (`disallow_untyped_defs=true`), ~98% branch coverage, ~113 tests, no upward imports. |
| `backend/services/` | Business logic | Gradual mypy, dedicated test suites for `condition_evaluator`, `notification_dispatcher`, `media_processor`, `rag`, `scheduler`, `workflow`, `daily_report`, `activity_session`, `activity_timeline`, `conversation_manager`. |
| `backend/integrations/` | External clients | Typed dataclasses for results, `configured` property gates network I/O, graceful degradation on every method. |
| `backend/steps/` and friends | Plugins | Each plugin has a unit test with success path, missing-service path, and one config edge case. |

### Database

PostgreSQL 17 with SQLAlchemy 2.0 ORM. Schema changes go through Alembic.

```bash
make migration         # autogenerate after model edits
make migrate           # apply pending migrations
```

Tests use a PostgreSQL testcontainer; the shared fixtures live in `backend/tests/conftest.py`.

### Plugin system in 60 seconds

Add a step:

```python
# backend/steps/builtin/your_step.py
from backend.steps import StepRegistry
from backend.steps.base import StepHandler, StepMetadata, StepResult

@StepRegistry.register
class YourStep(StepHandler):
    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="your_step",
            display_name="Your Step",
            category="action",
            icon="mdi-star",
            description="Does the thing.",
            config_schema={"type": "object", "properties": {}},
            default_config={},
        )

    async def execute(self, step, execution, pipeline_data, trigger, services):
        return StepResult(data={"your_key": "value"})
```

The step shows up in the StepPalette automatically. For a custom config form, add a `<template v-if="localStep.step_type === 'your_step'">` block in `frontend/src/components/pipeline/StepConfigDialog.vue`. Add a unit test under `backend/tests/steps/test_your_step.py`.

The same pattern works for notification channels (`backend/channels/builtin/`) and context filters (`backend/filters/builtin/`).

---

## Testing patterns to know

- `RulesEngine(tz_name="UTC")` in tests; the testcontainer stores UTC.
- Step handler tests use `@dataclass class _FakeStep` instead of `PipelineStep` (SQLAlchemy instrumentation breaks on `__new__`-constructed mapped objects).
- Pass only the `ServiceContainer` fields the step uses; the rest default to `None`.
- For routers: new `FastAPI()` + `register_exception_handlers(app)` + `app.dependency_overrides[get_auth_context]`. Use `StaticPool` so tables persist across the test connections.
- HTTP is patched via `unittest.mock.patch("backend.integrations.<module>.httpx.AsyncClient")`. No real network.
- Do not mock the database. Use the testcontainer fixtures.

---

## API reference

The full REST and MCP surface lives at [silvermind-project.github.io/api/reference](https://silvermind-project.github.io/api/reference). Highlights:

- `GET /api/v1/health`: unauthenticated liveness probe.
- `GET /api/v1/pipeline/step-types`, `/channel-types`, `/filter-types`, `/llm-models`: dynamic metadata for the visual pipeline builder.
- `POST /api/v1/rules`, `/rules/{id}/steps`, `/rules/{id}/contexts`, `/rules/{id}/dependencies`: rule and pipeline CRUD.
- `POST /api/v1/webhooks/{rule_id}`: trigger a webhook-enabled rule (HMAC required).
- `POST /api/v1/device/recamera`, `/device/reterminal`: hardware device endpoints (device-key auth).
- `GET /api/v1/image/active`: per-device e-ink image with refresh suppression.
- `GET /api/v1/cts/*`: BFF surface for cameras, calibration, signals, keyframes, identity corrections, presence (gated by `cts.enabled`).
- `POST /mcp`: streamable-HTTP MCP transport.

---

## License

AGPL-3.0-or-later
