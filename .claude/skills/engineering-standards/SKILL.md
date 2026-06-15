---
name: engineering-standards
description: "Use when changing Cognitive Companion backend or full-stack architecture, database code, tests, logging, naming, error handling, CTS consumers, or shared contracts."
---

# Engineering Standards

Production-quality standards for every agent working in `cognitive-companion`. This skill applies to all backend and full-stack changes. Frontend-specific UI patterns live in the `front-end` skill; this skill covers code quality, testing, naming, error handling, and architecture.

---

## 1. Naming conventions

### Python files

| What | Convention | Example |
|---|---|---|
| Modules | `snake_case` | `pipeline_executor.py`, `scene_analysis_client.py` |
| Packages | `snake_case` (no plurals unless it's a collection package) | `services/`, `steps/`, `routers/` |
| Test files | `test_<module>.py` mirrors source path | `tests/steps/test_scene_analysis.py` |

### Python symbols

| What | Convention | Example |
|---|---|---|
| Classes | `PascalCase` | `PipelineExecutor`, `SceneAnalysisHandler` |
| Functions / methods | `snake_case` | `get_matching_rules()`, `build_initial_pipeline_data()` |
| Private helpers | `_leading_underscore` | `_check_contexts()`, `_format()` |
| Constants (module-level) | `UPPER_SNAKE_CASE` | `MAX_RETRIES`, `BASE_DELAY`, `DEFAULT_CONFIG_DIR` |
| Variables | `snake_case` | `engine`, `tz_name` |
| FastAPI routers | `router` (module-level) | `router = APIRouter(prefix="/rules")` |

### Database columns

- SQLAlchemy columns: `snake_case` (ORM maps to snake_case Python attrs).
- PostgreSQL columns: `snake_case` (Alembic generates them from ORM models).
- Foreign keys: `<related_table>_id` (singular).
- Boolean columns: `is_<adjective>` or `has_<noun>` (e.g., `is_enabled`, `has_ended`).
- Timestamps: `<event>_at` (e.g., `created_at`, `resume_at`, `completed_at`).

### Frontend (Vue)

| What | Convention | Example |
|---|---|---|
| Components | `PascalCase` in `PascalCase.vue` files | `RuleDetailView.vue`, `StepCard.vue` |
| Composables | `use<Name>.js` | `useNotify.js`, `useConfirm.js` |
| Service modules | `camelCase.js` | `api.js`, `timezone.js` |
| Props / events | `camelCase` in `<script setup>`, `kebab-case` in templates | `:items-length`, `@update:options` |
| Ref/reactive state | `camelCase` | `const totalItems = ref(0)` |

---

## 2. Code organization

### Backend layering (strict dependency direction)

```text
core/            Zero upward imports. No services, routers, steps, channels, filters.
models/          ORM models. Can import from core/.
schemas/         Pydantic wire models. Can import from core/, models/.
integrations/    External clients (HTTP, HA, MinIO). Can import from core/.
services/        Business logic. Orchestrates integrations + models.
steps/channels/filters/  Plugin systems. Import from core/, models/, integrations/.
routers/         FastAPI route handlers. Thin: validate input, call service, return schema.
mcp/             MCP tool server. Same constraints as routers.
main.py          App factory + lifespan. Only place services are constructed.
```

**Cut-point rule:** If you find yourself importing from a layer to the right of your current layer, you have a circular dependency risk. Restructure.

### Module size

- Keep modules under 500 lines. When a module exceeds this, split by concern.
- Step handlers, channel handlers, and filter handlers are each one file per type (this is enforced by the plugin auto-discovery pattern).
- Routers are one file per domain. Don't put multiple unrelated resource groups in one router.

### Import style

```python
from __future__ import annotations  # always first

import <stdlib>
from collections.abc import ...     # not typing.List/Dict/etc.

import <third_party>

from backend.core.<module> import ...
from backend.models.<module> import ...
from backend.<layer>.<module> import ...
```

- Use `from __future__ import annotations` in every `.py` file.
- Group imports: stdlib, third-party, application. One blank line between groups.
- No relative imports. Always use the full `backend.` path.
- No `import *` outside of `__init__.py` re-export blocks.

---

## 3. Type safety

### Mandatory typing

- Every public function/method signature has type annotations on parameters and return.
- Private helpers should be annotated but `mypy` won't fail on unannotated internals outside `backend.core/`.
- `backend.core/` uses `disallow_untyped_defs = true` (strict mypy). Every function there must be fully typed, including private helpers.

### Use the right type

| Scenario | Type |
|---|---|
| Nullable scalar | `str \| None`, not `Optional[str]` (PEP 604 union syntax) |
| Dict with string keys | `dict[str, Any]` (precise key type) |
| Callable | `Callable` or `Callable[[int], str]` from `collections.abc` |
| Immutable result to callers | `@dataclass(frozen=True)` |
| JSON-able wire data | Pydantic model (`BaseModel`) |
| ORM object | SQLAlchemy model (`Base` subclass) |

### Pydantic specifics

- `BaseModel.model_config = {"extra": "forbid"}` for all Create/Update schemas. This catches typos in the frontend silently sending unknown fields.
- Use `model_dump()` not `.dict()` (Pydantic v2).
- Validation errors are automatically handled by FastAPI; don't catch `ValidationError` in routers.

### Dataclass specifics

- Results returned to callers use `@dataclass(frozen=True)`.
- Optional fields default to `None`.
- Use `field(default_factory=list)` for mutable defaults (never `[]`).
- Do not subclass SQLAlchemy models with dataclasses; use standalone dataclasses.

---

## 4. Error handling

### The AppError hierarchy

```python
from backend.core.exceptions import (
    AppError,           # base, status_code=500
    AuthenticationError, # 401
    PermissionDeniedError, # 403
    NotFoundError,      # 404: NotFoundError("Rule", rule_id)
    ConflictError,      # 409
    ValidationError,    # 422
)
```

### Rules

1. **Raise AppError subclasses from services and routers.** The global handler in `core/exceptions.py` converts them to JSON.
2. **Never catch AppError subclasses in routers.** Let them bubble to the handler.
3. **Optional integration clients return explicit zero values on failure**, never raise unexpected transport exceptions. This applies only when the endpoint is genuinely optional and the caller documents the degraded behavior. Pattern:
   ```python
   async def analyze(self, ...) -> SceneAnalyzeResult | None:
       try:
           ...
       except Exception:
           logger.exception("scene_analysis_failed")
           return None
   ```
4. **Required BFF upstream contracts fail closed.** If a browser-visible BFF endpoint depends on an upstream envelope field, validate that field at the router/client boundary. Missing required fields, wrong shapes, and upstream 5xx responses are contract failures: log with context and return a typed 502/503. Do not use `.get("required_field", [])` or fabricate display data to keep the UI quiet.
5. **Log with context before raising.** The exception handler doesn't log:
   ```python
   logger.warning("rule_not_found", rule_id=rule_id)
   raise NotFoundError("Rule", rule_id)
   ```
5. **Use `logger.exception()` in except blocks** (includes traceback). Use `logger.error()` for known error conditions that aren't exceptions.

---

## 5. Logging

```python
from backend.core.logging import get_logger
logger = get_logger(__name__)

# Structured: event name first, then key=value pairs
logger.info("rule_matched", rule_id=r.id, sensor_id=s.id)
logger.warning("slow_step", step_type=name, elapsed_seconds=elapsed)
logger.exception("pipeline_failed", execution_id=exec_id)  # includes traceback
```

- Never `print()`. Never `logging.getLogger()` directly (use `get_logger()`).
- Never `from structlog import get_logger`. The project replaced structlog with a stdlib-based
  ``BoundLogger`` in `backend/core/logging.py` that accepts the same keyword-context API.
  Always import ``get_logger`` from ``backend.core.logging``.
- Never printf-style `%s` or `.format()`. Always `key=value` kwargs.
- Event names are `snake_case` short strings describing what happened.
- Every integration call that can fail should log at least one event (success or failure).

---

## 6. Testing standards

### Test location and naming

```
backend/tests/<mirror_path>/test_<module>.py
```

- Test files mirror the source tree exactly.
- One test file per source module.
- Test function names: `test_<what>_<condition>_<expected>`. Examples:
  - `test_execute_with_valid_config_returns_success`
  - `test_analyze_when_service_disabled_returns_none`
  - `test_matches_with_cooloff_active_returns_empty_list`

### Test structure (Arrange-Act-Assert)

```python
async def test_execute_with_person_detected_returns_identification():
    # Arrange
    handler = SceneAnalysisHandler()
    step = _make_step({"min_confidence": 0.7})
    services = _make_services(scene_analysis_client=_mock_client())
    trigger = _make_trigger(media_paths=[_MINIO_URL])

    # Act
    result = await handler.execute(step, _FakeExecution(), {}, trigger, services)

    # Assert
    assert result.success is True
    assert result.data.get("detections") == []
```

Keep blank lines between the three blocks.

### Required test cases

Every new public class/function must have tests covering:

1. **Success path**: normal inputs, expected output.
2. **Missing service path**: what happens when an optional service is `None`.
3. **Edge case**: empty input, boundary value, unusual config.

Step handlers, channels, and filters each need all three.

### Fixtures

- Use the conftest fixtures (`db_session`, `db_factory`, `db_engine`). Do not create your own database setups.
- `db_engine` is the session-scoped PostgreSQL/TimescaleDB engine, `db_session` is the per-test SQLAlchemy session, and `db_factory` creates independent sessions that callers must close. The autouse `_truncate_tables` fixture cleans database state after tests that request `db_session` or `db_factory`.
- Test timestamps must be timezone-aware UTC, for example `datetime(2026, 6, 12, tzinfo=UTC)` or `datetime.now(UTC)`. Naive datetimes can compare differently from PostgreSQL `timestamptz` values and create false failures.
- Use `Settings.from_dict({...})` instead of touching config files.
- Use `@dataclass class _FakeStep` instead of constructing `PipelineStep` (SQLAlchemy instrumentation breaks on `__new__`).
- Use `RulesEngine(tz_name="UTC")` to align with testcontainer UTC values.
- Patch HTTP at `unittest.mock.patch("backend.integrations.<module>.httpx.AsyncClient")`.

### Envelope and authorization tests

Browser-visible envelope changes require an MCP/BFF parity test whenever an MCP tool exposes the same concept. Use the existing patterns in:

- `backend/tests/integrations/test_mcp_bff_parity.py` for person-location and heatmap reads.
- `backend/tests/integrations/test_gait_mcp_bff_parity.py` for a domain-specific envelope.
- `backend/tests/routers/test_signals_feed.py` for direct router/service/MCP parity.
- `backend/tests/mcp/test_signal_ack_parity.py` for a mutation.

Every new or changed endpoint also needs an authorization coverage check against `config/auth.yaml`: verify the permission token exists under `permission_map`, verify the intended role includes that token or concrete route pattern, and add a focused route test proving unauthorized access is rejected. There is no generic route-to-auth coverage test today, so do not assume `make check` discovers a missing mapping automatically.

Follow the complete recipe in `/home/sriram/code/nanai/cognitive-companion/.claude/skills/bff-api-design/SKILL.md`; do not duplicate router and MCP business logic in tests.

### What not to do in tests

- Never mock the database. Use testcontainer fixtures.
- Never mutate class-level state with `type(obj).prop = ...`. Use a local subclass.
- Never call external services (no real HTTP, no real MinIO, no real Redis).

### Test quality signals

- A test that doesn't assert anything is broken.
- A test with more mocks than lines of arrange code is testing implementation, not behavior.
- A test that depends on execution order is fragile. Every test sets up its own state.

### Injectable clocks for time-based logic

Any component that computes monotonic deadlines, token refills, cooldowns, or
time windows must accept a `time_fn` dependency. Default it to
`time.monotonic`, `datetime.now`, or another production clock appropriate to the
domain. Tests advance a fake clock and must not sleep to exercise time-based
behavior.

`PerCameraRateLimiter` and `CooldownTracker` in
`backend.services.aggregation` are the reference implementations.

---

## 7. Database patterns

### Session management

```python
from backend.core.database import get_session

db = get_session()
try:
    rule = db.query(Rule).filter(Rule.id == rule_id).first()
finally:
    db.close()
```

- Always close sessions explicitly. The context-manager form of `get_session()` is fine for single-use.
- In services, accept `db: Session` as a parameter. The caller owns lifecycle.
- In routers, use `Depends(get_db)` for the request-scoped session.

### Migrations

- All schema changes go through Alembic: `make migration` then `make migrate`.
- `Base.metadata.create_all()` is for tests and dev only.
- Review autogenerated migrations before committing. Alembic can miss renames and type changes.
- **Pre-release lifecycle:** A single squashed baseline `0001_baseline.py` contains the complete
  schema. Changes are folded directly into the baseline. Existing dev databases must be dropped
  and recreated; `alembic_version` holds stale entries from any prior chain.
- **Post-release lifecycle:** Each atomic change gets its own `NNNN_description.py`. The
  `downgrade()` must exactly reverse `upgrade()`. The baseline `downgrade()` stays a no-op.
- Verify no schema drift after folding: `alembic check` against live models.
- **CTS (tracking-orchestrator)** uses a custom `MigrationRunner` with raw `.up.sql`/`.down.sql`
  files; Alembic is not used there. The same pre-release/post-release lifecycle applies.

### Query conventions

- Use SQLAlchemy 2.0-style queries: `db.query(Model).filter(...)`.
- Use `.options(joinedload(...))` for eager loading relationships.
- Use `func.count()` for pagination totals.
- Filter conditions should be explicit column comparisons, never raw SQL strings.

---

## 8. Security

### Secrets and config

- Secrets live in env vars, never in YAML. Use `${ENV_VAR}` interpolation in config files.
- Validate secrets load at startup. Missing required env vars should fail fast.
- Never log secrets, tokens, or API keys. Mask them in log output.

### Authentication and authorization

- Every new endpoint must have an `auth.yaml` permission entry.
- Use `require_permission("METHOD /path")` on every route.
- Keys resolve from `X-API-Key` header, `?api_key` query param, or `device_key` in body.

### Input validation

- All input passes through Pydantic schemas (`extra="forbid"`).
- Validate string lengths and numeric ranges explicitly in schemas.
- Template rendering (Jinja2) must not execute arbitrary Python. The `render_template()` helper uses sandboxed evaluation.

---

## Consuming a new CTS signal kind

The producer-side recipe is `/home/sriram/code/nanai/continuous-tracking/.claude/skills/cts-signals/SKILL.md`. On the CC side, start with a grep inventory rather than assuming signal kinds have one registry:

```bash
grep -rn "stillness_anomaly" backend/ frontend/ \
  --include='*.py' --include='*.js' --include='*.ts' --include='*.vue' -l
grep -rn "signal_kind\|signal_type\|knownSignalKinds" backend/ frontend/ \
  --include='*.py' --include='*.js' --include='*.ts' --include='*.vue'
```

Check each of these touchpoints:

| Touchpoint | Current location and rule |
|---|---|
| Protobuf subscriber validation | `backend/services/cts/subscriber.py::_PROTO_KIND_TO_STR`. A protobuf enum not mapped here is rejected by `decode`; add the enum-to-string mapping and a decode/persist round-trip test |
| Alert profiles | `backend/services/cts/signal_config.py` and any profile controls in `frontend/src/views/admin/PersonsView.vue` |
| Pydantic enums or Literals | Search `backend/schemas/`; current signal envelopes use `str`, but any future `Literal` must be extended |
| Rule filter choices | `backend/filters/builtin/dementia_signal.py` and `frontend/src/components/pipeline/steps/index.js` |
| Narrative and feed | `backend/services/cts/signal_narratives.py`, `backend/services/signals/feed.py`, and `backend/schemas/cts_envelopes.py` |
| Frontend labels/icons | Search kind arrays/maps in Tracking, signal, keyframe, profile, and rule views; add i18n entries if that surface uses i18n |

**Forward-compatibility rule.** Unknown string kinds already stored or returned by an API must render generically, not crash. Backend fallbacks convert `my_future_kind` to a human-readable label in `SignalsFeedService` and `DementiaSignalEnvelope.from_dict`. Frontend surfaces use underscore-to-space labels and must use a generic icon or severity icon when a kind-specific icon map misses. Never index a map and then call a method on the possibly missing value.

Required tests for a new kind:

1. Subscriber protobuf decode and persistence round trip in `backend/tests/services/test_dementia_signal_subscriber.py`.
2. `dementia_signal` filter match and non-match in `backend/tests/filters/test_dementia_signal_filter.py`.
3. Unified feed or envelope rendering in `backend/tests/services/signals/test_feed.py` or the nearest feed test.
4. Frontend kind label/icon plus unknown-kind fallback under `frontend/tests/`.
5. MCP/BFF parity and `config/auth.yaml` coverage if an envelope or endpoint changes.

## 9. Plugin development

### Adding a step, channel, or filter

Three rules apply to all plugin types:

1. **Single file, no wiring.** Drop a file into the `builtin/` directory. The `@*Registry.register` decorator handles discovery.
2. **Metadata is mandatory.** `StepMetadata`, `ChannelMetadata`, or `FilterMetadata` must be complete: display name, description, icon (for steps), config schema, default config.
3. **Zero-config by default.** `default_config` must produce a working handler without any user overrides.

When consolidating handlers whose `step_type` values are already stored, keep
one canonical handler and register thin alias subclasses for the legacy names.
Alias subclasses override only `metadata()` and inherit `execute()`. The
`media_window_poll` handler and its `cts_window_poll` and
`recamera_media_poll` aliases are the canonical example.

### Step handler contract

```python
@StepRegistry.register
class YourStepHandler(StepHandler):
    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="your_step",          # snake_case, unique across all steps
            display_name="Your Step",       # human-readable
            category="action",              # perception | reasoning | action | state | flow
            icon="mdi-star",
            description="What this does.",
            config_schema={"type": "object", "properties": {}},  # JSONSchema
            default_config={},
        )

    async def execute(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
        services: ServiceContainer,
    ) -> StepResult:
        return StepResult(data={"output_key": value})
```

- Access only the `ServiceContainer` fields your step uses. Don't reference fields that might be `None` without checking.
- Return `StepResult(success=True, data={...})` on success.
- Return `StepResult(success=False, data={"error": "..."})` on expected failure.
- Let unexpected exceptions bubble; `PipelineExecutor` handles them.

### Pipeline DAG execution contract

Pipelines are directed graphs, not ordered lists. A single output port may
**fan out** to multiple target steps, and a step may **fan in** (join) from
multiple parents. There is no unique constraint on `(source_step_id, source_port)`.

- `build_adjacency(edges)` returns `{source_step_id: {source_port: [target_step_id, ...]}}` (targets are a list, in edge-insertion order). Anything consuming adjacency must iterate the list, never index a single target.
- The executor (`_run_steps`) is **in-degree gated**, not a plain BFS. Each outgoing edge resolves as *live* (the source activated that port) or *dead* (the source took another branch). A node runs once all incoming edges are resolved and at least one is live; a node whose incoming edges are all dead is **skipped**, and the skip propagates to its descendants. A join therefore runs exactly once, after every parent. The only step that produces dead edges today is `condition` (it emits `true` xor `false`); every other step emits `main`.
- `wait` / `interactive_prompt` inside a **parallel branch** is not supported: pausing serializes the run and resume only rebuilds work downstream of the paused step, so a sibling branch would be silently dropped. The executor detects this (`abandoned = run_set - resolved - descendants(waiting_step)`) and **fails loudly** with a `ValidationError` rather than losing a branch. Keep waits on a linear segment. (Resuming all branches across a wait is a future enhancement; persist the traversal frontier if you implement it.)

**Authoring-time vs execution-time graph validation.** `validate_graph(..., check_entry=...)` separates the two. The "exactly one entry node" rule is an *execution* invariant, enforced by the executor, rule import, and the read-only `GET /rules/{id}/validate` endpoint (which surfaces it as a non-blocking `graph_errors` warning). The edge-save endpoint (`PUT /rules/{id}/edges`) passes `check_entry=False`, because a pipeline under construction routinely has unwired steps (multiple entry nodes) and must remain editable. Structural checks (unknown step refs, invalid ports, cycles) always run. Never re-add the entry-count check to the edge-save path; it makes incremental editing and edge deletion 422.

---

## 10. API design

### Router conventions

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.exceptions import NotFoundError
from backend.schemas.resource import ResourceCreate, ResourceOut, ResourceUpdate

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("", response_model=list[ResourceOut])
def list_resources(
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("resources:read")),
):
    return db.query(Resource).order_by(Resource.name).all()
```

- Use `response_model` on every route.
- Use plural nouns for collection routes (`/resources`), singular with id for item routes (`/resources/{resource_id}`).
- POST returns `status_code=201`.
- Auth is always the last Depends (underscore-prefixed if unused in body).
- Router tags match the resource name.

### Pagination

List endpoints that can grow must support server-side pagination:

```python
@router.get("", response_model=ResourceListOut)
def list_resources(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("resources:read")),
):
    total = db.query(func.count(Resource.id)).scalar()
    items = db.query(Resource).order_by(Resource.name).offset(offset).limit(limit).all()
    return {"items": items, "total": total}
```

The response schema must include `total: int`:
```python
class ResourceListOut(BaseModel):
    items: list[ResourceOut]
    total: int
```

---

## 11. Time and timezone

```python
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

# DB storage: always UTC
created_at = datetime.now(UTC)

# Local wall-clock: from settings
tz = ZoneInfo(settings.get("app.timezone", "America/New_York"))
local_now = datetime.now(tz)

# Converting local to UTC for queries
utc_boundary = local_dt.astimezone(UTC)
```

- Single source of truth: `app.timezone` in `config/settings.yaml`.
- Database stores UTC. All `TIMESTAMPTZ` columns.
- Schedule with APScheduler `CronTrigger(timezone=ZoneInfo(tz_name))`.
- Daily counters reset at local midnight, computed in UTC for DB queries.
- Frontend: use `services/timezone.js` helpers, never `toLocaleString()` directly.

---

## 12. Frontend standards

Covered in detail by the `front-end` skill. Key cross-cutting rules:

- Design tokens from `theme.css` (`--cc-*` variables), no hardcoded colors.
- Server-side pagination on all data tables (`:items-length`, `:page`, `@update:options`).
- `useNotify()` / `useConfirm()` for user feedback, never `alert()` / `confirm()`.
- API calls go through `services/api.js` with contract validation.
- `cd frontend && npm run build` must pass before marking work complete.

---

## 13. Python virtual environment

**Always use the project venv at `backend/.venv/`; never invoke the system Python.** The Makefile targets activate it automatically. For direct invocation:

```bash
source backend/.venv/bin/activate          # interactive session
backend/.venv/bin/python -m pytest ...     # one-shot without activating
cd backend && uv sync --frozen --extra dev # sync after pyproject.toml changes
```

Running bare `python` or `pip` without the venv installs packages into the system interpreter and breaks the project's locked dependency graph.

---

## 14. Pre-commit checklist

Before opening a PR, verify:

### Backend
- [ ] `make check` passes (lint + strict mypy on core + core tests)
- [ ] If services/schemas changed: `make check-all` passes
- [ ] New public code has tests under `backend/tests/<mirror_path>/`
- [ ] Tests cover: success path, missing-service path, at least one edge case
- [ ] New endpoints have `auth.yaml` permission entries
- [ ] Schema changes use Alembic (`make migration` + reviewed autogenerated file)
- [ ] No `print()`, no `eval()`, no hardcoded timezone strings
- [ ] Integration clients return zero values on failure (graceful degradation)
- [ ] Pydantic schemas use `extra="forbid"` (Create/Update)
- [ ] `make typecheck` passes on all changed modules

### Frontend
- [ ] `cd frontend && npm run build` passes
- [ ] `npm audit --audit-level=high` reports no vulnerabilities
- [ ] No hardcoded colors or `rgba()` values
- [ ] Server-side pagination on data tables
- [ ] Filter changes reset page to 1
- [ ] API methods registered in `contracts.js`

### General
- [ ] No print/output statements left in
- [ ] No commented-out code blocks
- [ ] No em-dashes in `.md` files (use colons, commas, semicolons)
- [ ] Commit messages describe the "why"

---

## 15. Common anti-patterns

### Backend

| Anti-pattern | Correct approach |
|---|---|
| `print("debug", x)` | `logger.debug("event", value=x)` |
| `from structlog import get_logger` | `from backend.core.logging import get_logger` |
| `except Exception: pass` | Log and return zero value, or re-raise as AppError |
| `dict["key"]` without check | `dict.get("key", default)` or validate with Pydantic |
| `str(datetime.now())` | `datetime.now(UTC).isoformat()` |
| Instantiating services in routers | `request.app.state.<service>` |
| `from typing import Dict, List` | Use built-in `dict`, `list` (Python 3.9+) |
| `Optional[str]` | Use `str \| None` |
| Catching `AppError` in router | Let the global handler convert it |
| `time.sleep()` in async code | `await asyncio.sleep()` |
| Hardcoded config paths | Use `settings.get("dotted.key")` |
| `getattr(request.app.state, "name", None)` | Use typed `Depends(get_*)` from `backend.routers.dependencies`, or direct access `request.app.state.name` with a type annotation |
| `getattr(services, "field", None)` | Use direct attribute access `services.field` (all `ServiceContainer` fields default to `None`) |
| `Any` in `ServiceContainer` fields | Use concrete types with `TYPE_CHECKING` imports |
| `Any` in filter/channel `services` param | Use `ServiceContainer \| None` |

### Frontend

| Anti-pattern | Correct approach |
|---|---|
| `alert("done")` | `notify.success("Done.")` |
| `document.querySelector(...)` in Vue | Use `ref()` and template refs |
| Inline styles with hex colors | Design tokens from `theme.css` |
| `v-if` on large blocks with `v-for` children | Use `<template v-if>` wrapper |

---

## 15b. Router service access

### The typed dependency pattern

Every service on ``app.state`` is set in `backend/main.py` (to a concrete instance or ``None``).
Routers MUST use one of two patterns to access them; never ``getattr`` with a string key.

**Pattern 1: Required service (503 when unavailable).** Use a typed ``Depends`` from
`backend/routers/dependencies.py`:

```python
from backend.routers.dependencies import get_orchestrator_client

@router.get("/data")
async def get_data(
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    return await client.get_data()
```

**Pattern 2: Optional service (graceful degradation).** Use direct attribute access
with an explicit type annotation:

```python
@router.get("/data")
async def get_data(request: Request) -> dict:
    svc: SomeService | None = request.app.state.some_service
    if svc is None:
        return {"status": "unavailable"}
    return await svc.get_data()
```

**Never do this:**

```python
# BANNED: string-keyed getattr, no type safety, silent None on typos
client = getattr(request.app.state, "orchestrator_client", None)

# BANNED: creating a new client per request, services live in the lifespan
def _get_client() -> OrchestratorClient:
    return OrchestratorClient()

# BANNED: Any-typed helper that hides the actual type
def _get_client(request: Request) -> Any:
    return getattr(request.app.state, "orchestrator_client", None)
```

### Adding a new dependency

1. Ensure the service is set on ``app.state`` in ``backend/main.py`` (set to ``None`` in
   every branch so the attribute always exists).
2. Add a typed ``get_<name>`` callable in ``backend/routers/dependencies.py``.
3. Import and use ``Depends(get_<name>)`` in routers.

---

## 16. When to abstract

- **Three similar blocks** is the threshold. Two is coincidence; three is pattern.
- Extract a helper function when the same logic appears in 3+ places.
- Extract a component when the same UI pattern appears in 3+ views.
- Extract a base class when 3+ handlers share the same lifecycle steps.
- Don't abstract for "future use." The codebase already has a plugin system for that.

### Public contract minimality

A shared function, composable, service, or component exposes one canonical name
per value. Do not widen a provider API with same-value aliases to satisfy a
consumer's local naming preference.

```js
// WRONG: two public names for one value
return { theme: chartTheme, chartTheme }

// RIGHT: one canonical provider name
return { chartTheme }

// Adapt at the consumer boundary when a local rename is genuinely useful
const { chartTheme: theme } = useChartTheme()
```

Before changing a shared return shape:

1. Read the provider implementation and its contract test.
2. Inventory production consumers, tests, and skill examples with `rg`.
3. Distinguish provider field names from downstream prop or wire names. A
   `theme` prop does not require the provider to expose a field named `theme`.
4. Fix a drifting consumer or mock before expanding the provider contract.

Aliases are allowed only for an external or persisted compatibility contract,
such as stored step type names or public API fields. Document the compatibility
reason, keep one canonical implementation, add a deprecation/removal plan when
possible, and test both names. Convenience aliases without compatibility
evidence are prohibited.

### Theme-isolation boundary (sanctioned pattern)

When a feature requires an alternate rendering of an existing component (not just a style change, but a different component tree), extract the themed variant into a dedicated folder and swap it at the render seam with a single `v-if`. The primary component stays unchanged.

Reference: `components/marauders/` contains all Marauder's Map themed variants. Primary components (`CTSFloorPlanView.vue`, etc.) each have one `v-if` at the render seam. This lets themed code be maintained or removed without touching the primary app.

Rules for this pattern:

- One `v-if` per seam. If a seam needs more than one branch, the themed component absorbs the branching internally.
- The themed variant consumes the same data path and composables as the primary component. It introduces no new fetches or BFF contracts.
- All theme-specific files live in a single named folder (e.g., `components/marauders/`, `styles/marauders.css`, `assets/marauders/`).

For spatial components that use rough.js or other procedural sketch generators, see the front-end skill's "rough.js and procedural sketch generators" section for the required seed and memoization rules.

## 20. MCP and BFF single-service-layer rule (D6)

Any data exposed to the Vue UI through a FastAPI router must be exposed to MCP tools by reading the **same service function**. MCP tools contain no query logic of their own; they call service methods and adapt the result with `envelope_to_mcp()` or similar adapters.

Enforcement:
- Import-linter contract: `backend.mcp` may not import from `backend.models` or any repository module directly. Run `make import-lint` to verify.
- Smoke tests in `backend/tests/mcp/` assert that the tool registry resolves every registered tool name to a callable.
- When a service response envelope changes, both the router and the MCP tool reflect the change automatically because they share the same service call.

Violation pattern to avoid:

```python
# WRONG: MCP tool queries DB directly, diverges from router
@_register
async def get_person_location(person_id: str) -> dict:
    db = get_session()
    row = db.query(PersonLocationState).filter(...).first()
    return {"room": row.room_name}

# RIGHT: MCP tool calls the same service the router calls
@_register
async def get_person_location(person_id: str) -> dict:
    svc: PersonLocationService = request.app.state.person_location_service
    loc = await svc.get_current_location(person_id)
    return envelope_to_mcp(PersonLocationEnvelope.from_current_location(loc))
```

## 21. Unified envelope pattern

Location, occupancy, signal, and person-summary responses each have one Pydantic v2 envelope defined in `backend/schemas/cts_envelopes.py`. These fields are **always present and always server-computed**:

| Field | Type | Rule |
|-------|------|------|
| `confidence` | float | From the presence provider or identity resolver |
| `quality` | float | PH `mean_quality` from the CTS wire |
| `staleness_seconds` | int | Computed from `last_observed_at` at response time |
| `source` | str | Canonical provenance badge: `observation`, `transition`, `manual_override`, `ph_continuation` |

The frontend renders these fields via `CcProvenanceBadge`; it never computes them client-side (design rule D5).

The envelope is a **strict superset** of prior response shapes: every legacy field is present with the same name. New fields are added; nothing is renamed or removed until every consumer migrates.

## 22. No-silent-fallback lint rule

The `BLE001` (blind-except) ruff rule is enabled at `error` severity in `backend/pyproject.toml`. The documented allowlist is the only place a bare `except Exception` is permitted. Every other failure path must:

1. Raise a typed `AppError` subclass (`NotFoundError`, `ConflictError`, etc.), or
2. Return an explicit `None` / zero value with a `logger.warning()` call that names the optional degraded integration, or
3. Dead-letter the message with a Prometheus counter increment and a `logger.warning()` (for stream consumers).

Never return a fabricated `{}` or `[]` to hide a missing upstream. A missing required field is a contract violation; expose it as a typed 4xx/5xx. Only optional fields may use documented defaults, and tests must cover that degraded path.

---

## 17. CTS-specific standards

These apply to all code under `backend/services/cts/`, `backend/routers/cts*.py`, and `backend/websocket/connection_manager.py`.

### 16.1 Shared utilities (do not duplicate)

Three files are the single authoritative source for previously-duplicated functions:

| Utility | Import from | Replaces |
| --- | --- | --- |
| `ns_to_iso()` | `backend.services.cts._time` | 4 identical copies across subscriber files |
| `parse_ts()` | `backend.services.cts._time` | 3 divergent copies across service files |
| `ensure_aware()` | `backend.services.cts._time` | 1 copy in source_authority |
| `cts_enabled()` | `backend.routers.cts_deps` | 8 identical copies across router files |
| Aggregation primitives | `backend.services.aggregation` | Per-camera token buckets, cooldown math, and uniform buffer-state snapshots |

If you need one of these, import it. Never redefine it.
Import `PerCameraRateLimiter`, `CooldownTracker`, and `CameraBufferState` from
`backend.services.aggregation`; do not reimplement per-camera token buckets or
cooldown deadline math.

### 16.2 Protocol-based dependency injection

CTS subscribers and services accept their dependencies through `__init__`. Use the protocol types from `backend.services.cts._types`, never `Any`:

```python
from backend.services.cts._types import ConnectionManager, PipelineExecutor, DBSessionFactory

class TrackingEventSubscriber(StreamConsumer[dict[str, Any]]):
    def __init__(
        self,
        redis_url: str,
        consumer_id: str,
        writer: LocationWriter,
        ws_manager: ConnectionManager | None = None,      # not Any
        pipeline: PipelineExecutor | None = None,          # not Any
    ) -> None:
        ...
```

`DBSessionFactory` is `Callable[[], Session]`. Use it for `db_factory` parameters.

### 16.3 StreamConsumer contract

All four CTS subscribers extend `StreamConsumer[T]`. The `decode()` and `handle()` signatures must match the base class exactly. The `decode` parameter `fields` uses `dict[bytes | str, bytes | str]` because Redis returns bytes keys and values when `decode_responses=False`.

### 16.4 CTS isolation

- CTS tables (`dementia_signals`, `cts_cameras`) are written only inside `services/cts/`.
- **R2:** The four CTS filters (`room`, `room_transition`, `person_presence`, `scene_trend`) were migrated to `PersonLocationService` as the single source of truth (`presence_segments` / `location_observations`). The `person_location_state` and `person_location_history` tables are **deprecated CC-side tables** (not CTS tables): `PersonLocationService` is the SSOT and reads from `presence_segments`. No new code may read or write the deprecated tables from filters or steps. The deprecated tables still exist pending provider migration; they will be dropped in a follow-up milestone. Do not reintroduce reads of these tables in filters or steps.
- `_upstream_base` is imported only by CTS integration clients (`ingress_admin_client`, `tracking_orchestrator_client`).
- Redis Stream subscriptions (`tracking.events`, `tracking.revisions`, `tracking.signals`, `scene.samples`) are created only inside `CTSRuntime`.
- All browser and MCP traffic to `rtsp-ingress` or `tracking-orchestrator` goes through CC routers. No direct access.
- The `CtsEventBucketizer` (in-memory per-camera recent-frame buffer) is built by `CTSRuntime` and fed by `TrackingEventSubscriber.ingest` from the `tracking.events` stream (no new stream, no DB read, so it respects the isolation boundary). It reaches the canonical `media_window_poll` step and its `cts_window_poll` alias via `ServiceContainer.bucketizer`, injected **after** CTS bootstrap through the `PipelineExecutor.bucketizer` property (the executor is constructed before `CTSRuntime`; `main.py` sets `pipeline_executor.bucketizer = cts_runtime.bucketizer`). This is the same post-construction injection pattern as `_scheduler`. Steps read it via typed direct access (`services.bucketizer`), never `getattr`.

### 16.5 Per-camera image rate limiting

- Rate limiting gates images only. CTS metadata remains full fidelity for trigger evaluation, location state, live views, and summaries.
- Mark CTS frames with `image_eligible`; image consumers filter to eligible frames before per-rule downsampling.
- Count every rate-limit rejection in `cc_aggregator_images_dropped_total`. Drops must never be silent.
- Apply `sample_period_s` after the aggregator ceiling. Effective image rate is the minimum of the system ceiling and rule intent.
- Keep CTS frame references in memory. Never persist CTS-owned frame references to `MediaCache`.
- Cognitive Companion deletes only its own reCamera objects. It never deletes CTS-owned MinIO objects.

### 16.6 WebSocket security

- The `/ws/cts` WebSocket reads the API key from `sec-websocket-protocol` header, not from a query parameter.
- Frame image URLs (`GET /api/v1/cts/frames/{key}`) use query-param auth as a known limitation (browser `<img>` tags cannot set headers).
- Nginx uses `location ^~ /api/` and `location ^~ /ws` to prevent regex static-cache locations from stealing proxied URLs.

---

## 18. Frontend composables

Extract duplicated view logic into composables under `frontend/src/composables/`. Existing shared composables include:

| Composable | Replaces |
| --- | --- |
| `useCtsSeverity.js` | `severityColor()` / `severityIcon()` duplicated across 3 views |
| `useFormatRelative.js` | `formatRelative()` duplicated across 2 views |
| `useCtsWebSocket.js` | Ad-hoc WebSocket lifecycle with no reconnection; adds 3-second exponential backoff |
| `usePHList.js` | PH list fetch, pagination, WS update handling |
| `usePHDetail.js` | PH detail fetch (observations, trail, co-present) with `Promise.allSettled` |
| `usePHCorrection.js` | PH correction/merge/split mutations with notify injection |
| `usePresenceTimeline.js` | Presence timeline fetch, dwell totals, WS live update, active segment timer |
| `useWorldSnapshot.js` | World snapshot WS subscription, PH marker map, 30s trail buffer, inferred rooms |

### Required composable shape: `{ state, actions }`

**All composables that manage server state must return a `{ state, actions }` object.** This is the project standard, modelled on `useCtsWebSocket.js`.

```js
export function useMyResource() {
  const state = reactive({
    items: [],
    total: 0,
    loading: false,
    error: null,
    page: 1,
    itemsPerPage: 20,
  })

  async function fetchItems() { ... }
  function onPageOptions({ page, itemsPerPage }) { ... }

  return {
    state,
    actions: { fetchItems, onPageOptions },
  }
}
```

**Never return flat named refs from a composable** (`return { items, total, loading, fetchItems }`). The `{ state, actions }` shape:
- Makes destructuring explicit: `const { state, actions } = useMyResource()`
- Groups reactive data vs. functions clearly
- Prevents naming collisions when multiple composables are used in the same view
- Makes it obvious in the template what is state (`state.items`) vs. an action (`actions.fetchItems()`)

**Rules:**
- All reactive data (refs, reactive objects) lives under `state`
- All functions (fetch, setFilter, onPageOptions, handlers) live under `actions`
- Each returned value has one canonical key. Do not return the same ref,
  computed, object, or function under multiple names.
- WS subscriptions are wired inside the composable body (not in the view)
- Cleanup (timers, WS unsubscribe) uses `onUnmounted()` inside the composable
- Composables never call `useNotify()` internally; they accept a `notify` callback if feedback is needed, or they export an `error` state field and let the view decide how to show it. Exception: `usePHCorrection.js` injects `useNotify()` directly since correction feedback is always immediate.

Use design tokens (`var(--cc-*)`) or Vuetify theme colors for all CSS color values. Never hardcode hex values like `'#4CAF50'` or `'#fff'` in templates.

---

## 19. CTS integration design principles

### Severity-transition contract

The orchestrator's hysteresis guarantees idempotent DB rows but does not guarantee idempotent alerts. The CC must enforce the consumer side of the contract:

- **New `signal_id`** (first time seen): actionable. Persist, fire pipeline event, allow notifications.
- **Same `signal_id`, higher severity**: actionable escalation. Update row, fire pipeline event with `action="escalation"`.
- **Same `signal_id`, equal or lower severity**: update row only. Do not fire pipeline events. Do not re-alert caregivers.

`SignalStore.upsert()` enforces this contract. The `DementiaSignalSubscriber.handle()` method gates pipeline event firing on the `action` returned by upsert. The `DementiaSignalFilter` should honor this as a second line of defense.

### Algorithm version tracking

Every signal carries `algorithm_version` from the orchestrator. The CC persists this value and surfaces it in `CTSSignalsView`. The `get_24h_summary` and `list_recent` endpoints should allow filtering out signals from stale detector generations.

### Signal identity across services

The orchestrator computes deterministic signal IDs via UUID5. The CC stores these as `signal_id` on the `DementiaSignal` model. This is the cross-service identity for deduplication. Do not use the auto-increment `id` for dedup logic.

### Proto evolution

Additive proto fields (new tag numbers) are wire-compatible. The CC subscriber uses `message.algorithm_version if message.algorithm_version else None` to gracefully handle old orchestrators that do not set the field. Regenerate bindings in both repos after every proto change via `make proto-py` from the continuous-tracking repo.

### CTS WebSocket payload rule

**All WebSocket broadcasts must use `Pydantic model.model_dump(mode="json")`**, never manual dict literals. This prevents the payload schema drifting from the Pydantic definition without a type error.

```python
# CORRECT
from backend.schemas.cts_ph_ws import PHUpdateEvent

event = PHUpdateEvent(ph_id=..., ...)
await self._ws_manager.broadcast(event.model_dump(mode="json"))

# WRONG: raw dict will silently drift from the schema
await self._ws_manager.broadcast({
    "type": "cts_ph_update",
    "ph_id": ph_id,
    ...
})
```

WS event schemas live in a dedicated module named `backend/schemas/<domain>_ws.py`. The module for PH events is `backend/schemas/cts_ph_ws.py`. Never define WS event schemas inside a router file.

### CTS WebSocket debounce rule

High-frequency WS events (those driven by every tracking frame) must be debounced server-side per entity. The pattern:

```python
async def _schedule_broadcast(self, entity_id: str, event: BaseModel) -> None:
    self._pending[entity_id] = event
    existing = self._debounce_tasks.get(entity_id)
    if existing and not existing.done():
        existing.cancel()
    task = asyncio.create_task(self._delayed_broadcast(entity_id))
    task.add_done_callback(lambda t: self._debounce_tasks.pop(entity_id, None))
    self._debounce_tasks[entity_id] = task

async def _delayed_broadcast(self, entity_id: str) -> None:
    await asyncio.sleep(self._debounce_interval)  # 0.200s for PH updates
    event = self._pending.pop(entity_id, None)
    if event is not None and self._ws_manager is not None:
        await self._ws_manager.broadcast(event.model_dump(mode="json"))
```

Always cancel and await pending debounce tasks in `stop()`.

### CTS router pattern

All CTS routers follow the same pattern:
1. Import `cts_enabled` from `backend.routers.cts_deps`.
2. All routes have `dependencies=[Depends(cts_enabled)]`.
3. Proxy requests through the typed client (`OrchestratorClient` or `IngressAdminClient`), never raw `httpx`.
4. Return 503 when the upstream client is not available; return 502 on upstream errors.

### Testing CTS services

- `SignalStore` tests use the conftest `db_factory` that returns a plain `Session`. Never use context-manager form.
- `DementiaSignalSubscriber` tests test `decode()` and `handle()` directly. No real Redis required.
- The severity-transition logic must be tested with three cases: new signal_id, same signal_id with escalation, same signal_id with equal severity. Assert pipeline event firing only in the first two cases.

---

## 23. Supply-chain security

### Toolchain versions (as of 2026-06-01)

| Component | Required minimum | Rationale |
| --- | --- | --- |
| Node.js | 24.16.0 LTS (Krypton), enforced by `frontend/.nvmrc`, `frontend/package.json` engines, and `frontend/Dockerfile` | Node 24 is the latest active LTS; Node 20 is EOL. Keep local, CI, and Docker builds on the same latest LTS patch. |
| Vite | 8.x | Node 24 LTS supported; Rolldown bundler, faster cold starts |
| ECharts | 6.x with vue-echarts 8.x | Tree-shaking API unchanged; vue-echarts 8 requires ECharts 6 |
| Vuetify | 3.12+ (v3 stable branch) | Vuetify 4 is a ground-up rewrite; v3 remains maintained |
| Python | 3.14 | Minimum is set in `requires-python` in `pyproject.toml` |
| redis-py | 8.0 | Minimum floor raised; RESP3 types in 8.x require the `type: ignore[index,assignment]` note in `stream_consumer.py` |
| pillow | 12.0 | Multiple CVEs patched between 10 and 12 |
| pyjwt | 2.13 | RSA/ECDSA bundled; `[cryptography]` extra dropped |

### Lock-file discipline

- `frontend/package-lock.json` is committed and used in CI via `npm ci` (never `npm install`).
- `backend/uv.lock` is committed and used in CI via `uv sync --frozen --extra dev`.
- Neither lock file is edited by hand. Update the lock with `npm install` (frontend) or `uv lock --upgrade` (backend), then commit the change.
- When the Node latest LTS patch changes, update `frontend/.nvmrc`, `frontend/package.json` engines, `frontend/Dockerfile`, and `frontend/package-lock.json` together. Verify with `nvm use $(cat frontend/.nvmrc)`, `npm run build`, `npm run test -- --reporter=dot`, and `npm audit --audit-level=high`.

### Dependency scanning

- Run `npm audit --audit-level=high` before every PR; this is in the pre-commit checklist.
- For Python: `uv pip list --outdated --python backend/.venv` shows drift from the lock.
- Recommended CI gate: add `pip-audit` (PyPI) or `osv-scanner` (multi-ecosystem) as a CI step that fails on critical/high CVEs.
- Automated PRs: add a Dependabot config at `.github/dependabot.yml` targeting both `npm` (frontend) and `pip` (backend/pyproject.toml) on a weekly schedule.

### Integrity hygiene

- Prefer `--save-exact` (or `--save-exact` equivalent) for packages directly handling auth, crypto, or serialization to prevent accidental float to a vulnerable patch.
- Never use `npm install <package>` in CI. Use `npm ci` which validates the lockfile hash.
- For the Python side: `uv sync --frozen` aborts if the lock is out of date with `pyproject.toml`, which prevents silent drift.

### Third-party git sources

The `triton-shared` package is sourced directly from a GitHub repo via `[tool.uv.sources]`. This bypasses PyPI release signing. Before updating the pinned commit, verify the commit is on the expected branch and review the diff.
