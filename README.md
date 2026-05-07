# Cognitive Companion

On-premise AI for senior care. Safety monitoring and cognitive care, working together. Computer vision tracks safety and activity across the home. A personal knowledge repository keeps memories alive through narrated info cards, review-gated quizzes, and a voice Q&A interface. A natural voice companion connects everything. All inference runs locally.

> Technical reference: [AGENTS.md](AGENTS.md). AI assistant guidance: [CLAUDE.md](CLAUDE.md). Design: [cc-rag.md](cc-rag.md). User-facing docs: [silvermind-project.github.io](https://silvermind-project.github.io).

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
              │   (20 step types, plugin-based)  │
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
            (ArcFace)    (YOLO+Florence-2 (pgvectorscale
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

- **Composable per-rule pipelines.** 20 step types; add new ones as single files under `backend/steps/builtin/`.
- **Plugin architecture.** Steps, notification channels, and context filters are auto-discovered via `@StepRegistry.register` and equivalents.
- **Knowledge repository.** Caregiver-curated facts, paraphrased info cards, review-gated quizzes, and a senior-facing voice Q&A path backed by RAG (Triton embeddings + pgvector + LLM synthesis). See [cc-rag.md](cc-rag.md) for the design.
- **Multi-camera continuous tracking.** BoT-SORT + Bayesian identity resolution + dementia signal detection via `continuous-tracking/`.
- **Presence fusion.** Priority-ordered chain from bed sensor → CTS → HA device tracker → fallback. Configured in `config/presence.yaml`.
- **Person identification.** InsightFace ArcFace 512-d via `person-identification-service`.
- **Scene analysis + semantic memory.** YOLO + Florence-2 + CLIP scene understanding; pgvectorscale-backed vector search via `semantic-memory-service`.
- **Activity tracking.** Session-aware activity detection with configurable durations and `{{template}}` value substitution.
- **7 notification channels.** PWA, Telegram, e-ink, TTS, Home Assistant, webhook. Escalation and repeat policies per alert level.
- **Realtime voice.** WebSocket audio with Google Gemini Live and MCP tool calling. Voice instruction composition for per-delivery behavioural guardrails.
- **MCP server.** 27 tools at `/mcp`; subset mirrored to Gemini Live for voice interaction.
- **Visual pipeline builder.** Drag-and-drop step ordering, dynamic step palette, per-step config dialogs.
- **Role-based auth.** API keys, device keys, `fnmatch` permission patterns in `config/auth.yaml`.

---

## Prerequisites

| Component | Purpose | Notes |
| --- | --- | --- |
| NVIDIA GPU(s) | Person ID + vLLM serving | DGX Spark works well; one GPU minimum for face recognition. |
| Docker + NVIDIA Container Toolkit | Container runtime | Required for the person-ID service container. |
| PostgreSQL 18 (TimescaleDB + pgvectorscale) | Application database | Shared instance via `docker-compose.db.yml`; hosts `cognitive_companion`, `continuous_tracking`, and `semantic_memory` databases. Requires pgvector extension for knowledge embeddings. |
| Triton Inference Server | Embedding model serving | embeddinggemma-300m for knowledge repository RAG. |
| Home Assistant | Sensor integration, area discovery, media-player playback | REST API + long-lived token. |
| MinIO (or S3-compatible) | Media object storage | Pre-signed URL support required. |
| vLLM | Vision model serving | Cosmos-Reason2-8B via OpenAI-compatible API. |
| llama.cpp `llama-server` | General-purpose model serving | Gemma 4 26B (text + vision + translation). Also powers knowledge content generation and RAG answer synthesis. |
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

### 2. Start the shared PostgreSQL instance

```bash
# From the repo root, start the shared database (hosts all 3 project databases)
docker compose -f docker-compose.db.yml -p nanai up -d

# Back in cognitive-companion:
docker compose up -d postgres         # pulls in shared DB via include
make init-db                          # create DB, run migrations, seed
```

The shared database runs `timescale/timescaledb-ha:pg18` with TimescaleDB, PostGIS, pgvector, and pgvectorscale. A single instance hosts `cognitive_companion`, `continuous_tracking`, and `semantic_memory`. Development environments can use the `standalone` profile to run a self-contained Postgres: `docker compose --profile standalone up -d`.

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
├── config/          settings.yaml, auth.yaml, notifications.yaml, presence.yaml,
│                    knowledge_layouts.yaml, knowledge_voice.yaml
├── data/            Runtime media cache
├── docker-compose.yml, kubernetes/, Makefile
└── AGENTS.md, CLAUDE.md, README.md, cc-rag.md
```

---

## Configuration

YAML files in `config/` with `${ENV_VAR}` interpolation:

- `settings.yaml`: application settings (LLM models, polling intervals, MinIO, MCP tools, embedding config, knowledge repository, scene-analysis, semantic-memory, CTS, presence, image, logging).
- `auth.yaml`: API keys, device keys, fnmatch permission map.
- `notifications.yaml`: alert-level to channel routing.
- `presence.yaml`: PresenceService provider chain (priority-ordered).
- `knowledge_layouts.yaml`: info card and quiz question image layout definitions.
- `knowledge_voice.yaml`: default Gemini Live voice instructions for interactive prompts, info cards, and quizzes.

Frontend timezone is fetched at startup from `GET /api/v1/admin/app-info`. Admin UI timestamps, cron schedules, time-range filters, day-of-week filters, and daily-trigger counters all interpret `app.timezone`. DB always stores UTC.

For the full configuration surface, see [docs/guide/configuration](https://silvermind-project.github.io/guide/configuration) on the documentation portal.

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
| `backend/services/` | Business logic | Gradual mypy, dedicated test suites for `condition_evaluator`, `notification_dispatcher`, `media_processor`, `scheduler`, `workflow`, `daily_report`, `activity_session`, `activity_timeline`, `conversation_manager`, and `knowledge/` (ingestion, query, delivery, content generation, image pipeline, layout registry, voice instructions). |
| `backend/integrations/` | External clients | Typed dataclasses for results, `configured` property gates network I/O, graceful degradation on every method. |
| `backend/steps/` and friends | Plugins | Each plugin has a unit test with success path, missing-service path, and one config edge case. |

### Database

PostgreSQL 18 via `timescale/timescaledb-ha:pg18` with TimescaleDB, PostGIS, pgvector, and pgvectorscale extensions. SQLAlchemy 2.0 ORM. Schema changes go through Alembic.

```bash
make migration         # autogenerate after model edits
make migrate           # apply pending migrations
```

The shared database instance hosts three databases: `cognitive_companion`, `continuous_tracking`, and `semantic_memory`. See `docker-compose.db.yml` and `scripts/db/init-databases.sh` for the setup. Tests use a PostgreSQL testcontainer; the shared fixtures live in `backend/tests/conftest.py`.

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

## API reference

Full REST and MCP surface: [silvermind-project.github.io/api/reference](https://silvermind-project.github.io/api/reference).

---

## License

AGPL-3.0-or-later
