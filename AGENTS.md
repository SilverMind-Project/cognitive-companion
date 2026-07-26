# AGENTS.md

Reference for AI coding agents working in `cognitive-companion/`. `CLAUDE.md` is the short orientation file. This document is the deeper engineering reference.

The code is the source of truth. Verify symbols with `rg` before relying on old prose.

## Required local skills

Load and follow these skills from `.claude/skills/` when the work matches the scope.

| Skill | Use when | Key expectations |
| --- | --- | --- |
| `engineering-standards` | Any backend, full-stack, database, testing, logging, naming, or architecture change | Respect backend layering, use Pydantic v2, avoid `Any` for injected services, raise `AppError` subclasses, use structured logging, add focused tests |
| `front-end` | Any Vue, Vuetify, router, layout, drawer, dialog, or CSS change | Use `--cc-*` design tokens, stable layouts, real router tests, right drawer standards, no hardcoded colors |
| `data-visualization` | Charts, execution graphs, monitoring panels, spatial overlays, or data-heavy UI | Use shared ECharts components for charts, `useChartTheme`, explicit loading, empty, and error states. Vue Flow is only for the interactive pipeline canvas |
| `bff-api-design` | Any browser-visible API endpoint, BFF schema, or UI data contract | Define one Pydantic envelope, implement service logic once, expose router and MCP from the same service function when applicable, add auth and parity tests |

## Mission and scope

Cognitive Companion is a privacy-first, on-premise AI system for senior care. It ingests camera and sensor events, evaluates caregiver-authored rules, executes graph-shaped pipelines, and delivers resident or caregiver feedback through local and configured outbound channels.

The backend is also the BFF gateway for sibling services:

- `person-identification-service`
- `scene-analysis-service`
- `semantic-memory-service`
- `tts-service`
- `continuous-tracking/` services, including `rtsp-ingress`, `tracking-orchestrator`, Redis Streams, and Triton

## Runtime stack

| Layer | Choice |
| --- | --- |
| Backend | Python 3.14, FastAPI, SQLAlchemy 2.0, Pydantic 2, APScheduler |
| Database | PostgreSQL 18 with Alembic migrations |
| Frontend | Vue 3, Vuetify 3, Vite, vue-router, Vue Flow for pipeline authoring |
| Object storage | MinIO through `boto3` |
| Local AI | vLLM, llama.cpp, Ollama-compatible providers, Gemini Live, Triton embeddings |
| Package manager | `uv` for backend, npm for frontend |
| Lint and types | `ruff`; strict mypy for `backend.core`, gradual elsewhere |

Frontend requires Node.js 24.16.x. See `frontend/package.json` and `.nvmrc`.

## Repository map

```text
cognitive-companion/
├── backend/
│   ├── core/                 Foundation: config, database, auth, logging, exceptions, time, templates
│   ├── models/               SQLAlchemy ORM
│   ├── schemas/              Pydantic wire and bundle schemas
│   ├── integrations/         External and sibling-service clients
│   ├── services/             Business logic, orchestration, CTS, schedulers, read models
│   ├── steps/                Step plugin registry and built-ins
│   ├── channels/             Notification channel registry and built-ins
│   ├── filters/              Context filter registry and built-ins
│   ├── routers/              FastAPI routers
│   ├── mcp/                  MCP server and tool adapters
│   ├── websocket/            Companion and pipeline WebSocket managers
│   ├── bootstrap/            Service wiring, by phase (see bootstrap/README.md)
│   ├── tests/                Mirrors backend packages
│   └── main.py               App factory: FastAPI() creation, middleware, router includes
├── frontend/
│   └── src/
│       ├── views/admin/      Admin surfaces, including rules and executions
│       ├── components/       Pipeline, CTS, companion, charts, dashboard components
│       ├── composables/      Shared Vue state and behavior
│       └── services/         API, CTS, websocket, timezone clients
├── config/                   settings.yaml, auth.yaml, notifications.yaml, presence.yaml
├── docs/                     Internal architecture and API references
└── Makefile
```

## Commands

Run from the repository root unless noted.

```bash
# Backend development
uv run --project backend uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend development
cd frontend && npm run dev
cd frontend && npm run build

# Backend tests and gates
make test
make test-core
make test-services
make check
make check-all
make test-integration

# Lint, format, types
make lint
make lint-fix
make format
make typecheck
make typecheck-core

# Database
make init-db
make migrate
make migration
make migration-history
```

Use `backend/.venv` for one-off Python commands. Do not use system Python.

## Architecture invariants

- `backend.core` has no upward imports.
- Models do not import services or routers.
- Routers stay thin: validate input, require permission, call a service, return a schema.
- Services are constructed in `backend/bootstrap/` phase modules (orchestrated by `backend/bootstrap/lifespan.py`, called from `backend/main.py`) and accessed through `app.state`. A new service is wired in the phase matching its dependencies and added to `backend/bootstrap/README.md`'s inventory and `backend/tests/test_bootstrap_wiring.py`'s pin.
- Schema changes go through Alembic.
- Every endpoint needs `config/auth.yaml` coverage.
- Datetimes are timezone-aware UTC in storage. Display and scheduling use the configured timezone.
- Markdown files avoid em dashes.
- Required BFF upstream contracts fail closed. Do not fabricate missing required fields.

## Rules and graph pipelines

Rules store `trigger_types: list[str]`, cron trigger links, context filters, dependencies, and execution limits. Supported trigger types include `sensor_event`, `cron`, `manual`, `webhook`, `telegram`, `occupancy_duration`, `cts_window`, and `dementia_signal`.

Pipelines are directed graphs, not ordered lists.

| Model or type | Role |
| --- | --- |
| `PipelineStep` | Step type, label, config, enabled flag, order tiebreaker, `position_x`, `position_y` |
| `PipelineEdge` | Connection from `source_step_id/source_port` to `target_step_id/target_port` |
| `StepMetadata.output_ports` | Ports available in the authoring graph |
| `StepResult.output_ports` | Ports activated at runtime |
| `WorkflowExecution.pipeline_data_json["_graph"]` | Immutable graph snapshot captured at execution start |
| `WorkflowExecution.pipeline_data_json["_step_timings"]` | Runtime step timings and selected output ports |

`condition` declares `output_ports=("true", "false")`. Most other steps use `("main",)`.

`StepResult` fields are `success`, `data`, `should_continue`, `output_ports`, and `wait_until`. Do not use or reintroduce `next_step_id`.

## Execution observability

The canonical execution inspector endpoint is:

```text
GET /api/v1/workflows/{execution_id}/detail
```

It returns run metadata, `graph`, per-step `timeline`, `output_port`, skipped nodes, resolved configs, outputs, errors, and cancel or rerun flags.

`GET /api/v1/pipeline/runs` and `GET /api/v1/pipeline/runs/{execution_id}` are lightweight envelopes for live lists and dashboards. They do not include raw pipeline data, inspector timelines, logs, or resolved configs.

The admin UI has a unified `/admin/executions` surface. `/admin/workflows` and `/admin/activity` are compatibility redirects.

## Plugin registries

All registries auto-discover built-ins and contrib files at startup.

### Step types

There are 27 registered built-in step types:

`activity_detection`, `activity_session_start`, `activity_session_end`, `condition`, `daily_report`, `gate_verdict`, `guided_task_start`, `ha_action`, `home_state`, `image_crop`, `info_card`, `interactive_prompt`, `llm_call`, `media_presign`, `media_window_poll`, `notification`, `object_trend_analysis`, `person_identification`, `presence_query`, `quiz_start`, `region_presence`, `scene_analysis`, `semantic_memory_query`, `semantic_memory_write`, `signal_emit`, `verification`, `wait`.

`media_window_poll` is the single camera polling step for both CTS and reCamera sources, selected via its `source` config (`auto`, `cts`, `recamera`). The former `cts_window_poll` and `recamera_media_poll` step types have been removed. `region_presence` (DL-M03) tests person bboxes against normalized image-space regions without a model call. `signal_emit` (DL-M06) writes a CC-local signal via `SignalsService.emit()`. `media_presign` (DL-M08) resolves MinIO object names referenced in trigger or pipeline context into presigned URLs.

Every data-emitting step must declare `output_schema` in `StepMetadata`. Contract tests enforce this.

### Channels

There are 7 channel types:

`pwa_popup_text`, `pwa_realtime_ai`, `pwa_tts_announcement`, `telegram`, `eink`, `ha_speaker_tts`, `webhook`.

### Filters

There are 13 filter types:

`room`, `time_range`, `day_of_week`, `person_presence`, `person_activity`, `room_transition`, `person_movement_memory`, `scene_contains`, `scene_trend`, `home_state`, `presence_status`, `presence_dwell`, `dementia_signal`.

## Template and bundle contracts

Templates use the Lark-based `{{ }}` grammar in `backend/core/template_grammar.lark`. Bare expressions without braces are not supported. JMESPath uses pipe syntax, such as `steps.foo.outputs.detections | length(@)`.

Step config validation runs when saving a step, importing a rule bundle, and calling `POST /api/v1/rules/{rule_id}/validate`.

Rule bundles use label-based references and include graph edges plus canvas positions.

## CTS boundary

Use the shared CTS utilities:

- `backend.routers.cts_deps.cts_enabled`
- `backend.services.cts._time`
- `backend.services.cts._types`
- `backend.services.cts.signal_config`

Do not subscribe to `tracking.*` or `scene.*` streams outside `CTSRuntime`. Do not write CTS-owned tables outside `backend/services/cts/`. Do not hardcode signal kind strings.

## Frontend expectations

- Use Vuetify and the project design tokens in `frontend/src/styles/theme.css`.
- Use route records that resolve without Vue Router warnings.
- Use the established right drawer and dialog patterns.
- Use shared ECharts chart components for chart data.
- Use Vue Flow only for interactive pipeline authoring.
- Add or update Vitest coverage for route behavior, canvas behavior, and inspector state when touching those surfaces.

## Testing expectations

For backend changes, place tests under `backend/tests/<mirror_path>/test_<module>.py`.

For new or changed services and routers, cover:

- success path
- missing service or missing resource path
- at least one edge case
- permission or validation behavior when relevant

For frontend changes, run the affected Vitest specs and `npm run build` with Node.js 24.16.x.

For BFF endpoints, add auth coverage and MCP parity when the data should be available to agents.
