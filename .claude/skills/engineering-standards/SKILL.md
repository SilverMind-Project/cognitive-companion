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
3. **Integration clients return zero values on failure**, never raise. Pattern:
   ```python
   async def analyze(self, ...) -> SceneAnalyzeResult | None:
       try:
           ...
       except Exception:
           logger.exception("scene_analysis_failed")
           return None
   ```
4. **Log with context before raising.** The exception handler doesn't log:
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
- Use `Settings.from_dict({...})` instead of touching config files.
- Use `@dataclass class _FakeStep` instead of constructing `PipelineStep` (SQLAlchemy instrumentation breaks on `__new__`).
- Use `RulesEngine(tz_name="UTC")` to align with testcontainer UTC values.
- Patch HTTP at `unittest.mock.patch("backend.integrations.<module>.httpx.AsyncClient")`.

### What not to do in tests

- Never mock the database. Use testcontainer fixtures.
- Never mutate class-level state with `type(obj).prop = ...`. Use a local subclass.
- Never call external services (no real HTTP, no real MinIO, no real Redis).

### Test quality signals

- A test that doesn't assert anything is broken.
- A test with more mocks than lines of arrange code is testing implementation, not behavior.
- A test that depends on execution order is fragile. Every test sets up its own state.

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

## 9. Plugin development

### Adding a step, channel, or filter

Three rules apply to all plugin types:

1. **Single file, no wiring.** Drop a file into the `builtin/` directory. The `@*Registry.register` decorator handles discovery.
2. **Metadata is mandatory.** `StepMetadata`, `ChannelMetadata`, or `FilterMetadata` must be complete: display name, description, icon (for steps), config schema, default config.
3. **Zero-config by default.** `default_config` must produce a working handler without any user overrides.

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

## 13. Pre-commit checklist

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

## 14. Common anti-patterns

### Backend

| Anti-pattern | Correct approach |
|---|---|
| `print("debug", x)` | `logger.debug("event", value=x)` |
| `except Exception: pass` | Log and return zero value, or re-raise as AppError |
| `dict["key"]` without check | `dict.get("key", default)` or validate with Pydantic |
| `str(datetime.now())` | `datetime.now(UTC).isoformat()` |
| Instantiating services in routers | `request.app.state.<service>` |
| `from typing import Dict, List` | Use built-in `dict`, `list` (Python 3.9+) |
| `Optional[str]` | Use `str \| None` |
| Catching `AppError` in router | Let the global handler convert it |
| `time.sleep()` in async code | `await asyncio.sleep()` |
| Hardcoded config paths | Use `settings.get("dotted.key")` |

### Frontend

| Anti-pattern | Correct approach |
|---|---|
| `alert("done")` | `notify.success("Done.")` |
| `document.querySelector(...)` in Vue | Use `ref()` and template refs |
| Inline styles with hex colors | Design tokens from `theme.css` |
| `v-if` on large blocks with `v-for` children | Use `<template v-if>` wrapper |

---

## 15. When to abstract

- **Three similar blocks** is the threshold. Two is coincidence; three is pattern.
- Extract a helper function when the same logic appears in 3+ places.
- Extract a component when the same UI pattern appears in 3+ views.
- Extract a base class when 3+ handlers share the same lifecycle steps.
- Don't abstract for "future use." The codebase already has a plugin system for that.
