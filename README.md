# Cognitive Companion

[![Python](https://img.shields.io/badge/Python-3.14-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Vue.js](https://img.shields.io/badge/Vue.js-3-4FC08D?style=flat&logo=vuedotjs&logoColor=white)](https://vuejs.org)
[![Vuetify](https://img.shields.io/badge/Vuetify-3-1867C0?style=flat&logo=vuetify&logoColor=white)](https://vuetifyjs.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-316192?style=flat&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-8-DC382D?style=flat&logo=redis&logoColor=white)](https://redis.io)
[![NVIDIA](https://img.shields.io/badge/NVIDIA-GPU%20Inference-76B900?style=flat&logo=nvidia&logoColor=white)](https://developer.nvidia.com)
[![Docker](https://img.shields.io/badge/Docker-Containerised-2496ED?style=flat&logo=docker&logoColor=white)](https://docker.com)
[![uv](https://img.shields.io/badge/uv-0.11-6E40C9?style=flat&logo=astral&logoColor=white)](https://docs.astral.sh/uv)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue?style=flat)](LICENSE)

On-premise AI system for senior care: safety monitoring, activity tracking, and cognitive engagement. All inference runs locally.

The backend is a FastAPI BFF gateway for the continuous tracking, scene analysis, person identification, semantic memory, and TTS services. A Vue 3 admin UI provides camera management, a unified role-aware tracking workspace, live pipeline activity view, privacy zone configuration, rule authoring, and dementia signal dashboards. A senior-facing voice companion runs through the PWA.

BFF endpoints fail closed for required upstream contracts. Missing fields or wrong JSON shapes are returned as typed gateway errors with structured logs instead of fabricated empty arrays or placeholder objects.

**Documentation:** [silvermind-project.github.io](https://silvermind-project.github.io)

**Architecture reference:** [docs/systems-architecture.md](docs/systems-architecture.md) covers the sensors and integrations, the rules engine and trigger types, event aggregation, the plugin systems (steps, channels, filters), the PWA companion view, the Gemini Live realtime voice path, and a current bugs-and-gaps checklist.

## Architecture

```mermaid
flowchart LR
    Edge[Edge Devices] --> CC[Cognitive Companion]
    CC --> AI[AI Services]
    CC --> CTS[Continuous Tracking]
    CTS --> CC
```

The system ingests camera frames and sensor events, evaluates them against caregiver-authored rules with composable per-rule pipelines, and dispatches notifications across seven output channels. Person location state is managed by `PersonLocationService` as a single source of truth; MCP tools and BFF router endpoints read from the same service functions.

## Quick start

```bash
cp .env.example .env
docker compose -f docker-compose.db.yml -p nanai up -d  # shared Postgres
docker compose up -d
make init-db
```

See the [documentation site](https://silvermind-project.github.io) for person enrollment, pipeline configuration, and operations guides.

## Development

```bash
# Backend
uv run --project backend uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd frontend && npm install && npm run dev

# Quality gates
make check              # lint + strict mypy on core + core tests
make check-all          # adds services tests + frontend
make test-integration   # integration tests (requires Docker)
```

## License

AGPL-3.0-or-later
