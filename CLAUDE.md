# CLAUDE.md

Quick reference for Claude Code agents in `cognitive-companion/`. The full reference is [AGENTS.md](AGENTS.md).

## Start here

1. Read [docs/systems-architecture.md](docs/systems-architecture.md) for the current system shape.
2. Read [docs/api/reference.md](docs/api/reference.md) before changing BFF contracts.
3. Use `backend/main.py` as the source of truth for service wiring.
4. Use `backend/steps/base.py`, `backend/models/pipeline.py`, and `backend/schemas/workflow.py` for pipeline and execution contracts.

## Skills to load

| Skill | Use when |
| --- | --- |
| `.claude/skills/engineering-standards/SKILL.md` | Backend/full-stack architecture, database code, tests, CTS signal consumers, logging, naming, and shared contracts |
| `.claude/skills/front-end/SKILL.md` | Vue, Vuetify, router, Tracking panels, composables, layout, drawers, dialogs, CSS, and frontend tests |
| `.claude/skills/data-visualization/SKILL.md` | Shared charts, mobility trends, monitoring, execution graphs, spatial overlays, provenance, and data-heavy UI |
| `.claude/skills/bff-api-design/SKILL.md` | Browser-visible envelopes/endpoints, MCP adapters, parity tests, authorization mappings, and import boundaries |

## Current stack

- Backend: Python 3.14, FastAPI, SQLAlchemy 2.0, Pydantic 2.
- Frontend: Vue 3, Vuetify 3, Vite. Node.js 24.16.x is required.
- Database: PostgreSQL 18 with Alembic migrations.
- Storage: MinIO.
- Local AI: person ID, scene analysis, semantic memory, TTS, vLLM, llama.cpp, Gemini Live, Triton.

## Non-negotiable invariants

- `backend.core` has no upward imports.
- Services live in FastAPI lifespan and are read from `app.state`.
- Routers are thin and permission-protected.
- New endpoints need `config/auth.yaml` coverage.
- Browser-visible BFF data should use one service function and MCP parity when applicable.
- Schema changes go through Alembic.
- Datetimes are timezone-aware UTC in storage.
- Markdown files avoid em dashes.
- Do not use system Python. Use `backend/.venv` or `uv run --project backend`.

## Pipeline contract

Pipelines are directed graphs. Do not treat them as ordered step lists.

- `PipelineStep` stores step type, label, config, enabled flag, order tiebreaker, and canvas position.
- `PipelineEdge` connects `source_step_id/source_port` to `target_step_id/target_port`.
- `StepMetadata.output_ports` declares authoring ports.
- `StepResult.output_ports` declares runtime activated ports.
- `condition` emits `true` or `false`; most steps emit `main`.
- `StepResult` fields are `success`, `data`, `should_continue`, `output_ports`, and `wait_until`.
- Do not reintroduce `next_step_id`.
- An output port may fan out to multiple targets, and a step may fan in (join). The executor traverses in-degree-gated: a join runs once, after all parents; dead branches (a `condition`'s unactivated port) are skipped and the skip propagates. `build_adjacency` maps `{source: {port: [targets]}}`.
- The single-entry-node rule is execution-time only. Edge-save (`PUT /rules/{id}/edges`) uses `validate_graph(check_entry=False)` so in-progress pipelines with unwired steps stay editable; structural checks (cycles, ports, unknown steps) always run.
- `wait`/`interactive_prompt` must be on a linear segment; in a parallel branch the executor fails loud (resume cannot rebuild sibling branches).

Current built-in step types: `activity_detection`, `activity_session_start`, `activity_session_end`, `condition`, `cts_window_poll`, `daily_report`, `ha_action`, `home_state`, `image_crop`, `info_card`, `interactive_prompt`, `llm_call`, `notification`, `object_trend_analysis`, `person_identification`, `presence_query`, `quiz_start`, `recamera_media_poll`, `scene_analysis`, `semantic_memory_query`, `semantic_memory_write`, `verification`, `wait`.

Channels: `pwa_popup_text`, `pwa_realtime_ai`, `pwa_tts_announcement`, `telegram`, `eink`, `ha_speaker_tts`, `webhook`.

Filters: `room`, `time_range`, `day_of_week`, `person_presence`, `person_activity`, `room_transition`, `person_movement_memory`, `scene_contains`, `scene_trend`, `home_state`, `presence_status`, `presence_dwell`, `dementia_signal`.

## Execution observability

Use `GET /api/v1/workflows/{execution_id}/detail` for inspector data. It includes graph snapshot, timeline, skipped nodes, output ports, resolved configs, outputs, errors, and cancel or rerun flags.

Use `GET /api/v1/pipeline/runs` only for lightweight live or recent run lists. It is not the detail contract.

The admin UI surface is `/admin/executions`. `/admin/workflows` and `/admin/activity` are redirects.

## Commands

```bash
uv run --project backend uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
cd frontend && npm run dev
make check
make check-all
make test-integration
make migrate
make migration
uv run --project backend pytest backend/tests/<area>/test_<file>.py -v
```

`make check` is the fast backend gate. Use `make check-all` for service, schema, and shared infrastructure changes.
