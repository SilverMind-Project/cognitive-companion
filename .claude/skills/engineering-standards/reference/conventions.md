# Conventions: naming, typing, errors, logging, time, venv

Read before writing or reviewing any backend Python. Part of the `engineering-standards` skill; the rules summary is in `../SKILL.md`.

## Naming conventions

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
| Components | `PascalCase` in `PascalCase.vue` files | `RuleDetailView.vue`, `RoutineStepCard.vue` |
| Composables | `use<Name>.ts` for new code (existing `.js` stays until touched) | `useFaceCalibrationReview.ts`, `useNotify.js` |
| Service modules | `services/modules/<snake_case>.ts` (endpoint calls); `services/<camelCase>.js` for helpers | `face_calibration.ts`, `timezone.js` |
| Props / events | `camelCase` in `<script setup>`, `kebab-case` in templates | `:items-length`, `@update:options` |
| Ref/reactive state | `camelCase` | `const totalItems = ref(0)` |

## Type safety

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

## Error handling

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
3. **Optional integration clients return explicit zero values on failure**, never raise unexpected transport exceptions. This applies only when the endpoint is genuinely optional and the caller documents the degraded behavior, and the broad `except Exception` below is allowed only in the BLE001 allowlist paths of `backend/pyproject.toml` (`integrations/`, `channels/builtin/`, `websocket/`, `mcp/server.py`, `mcp/middleware.py`, tests); anywhere else it needs a narrower exception or a `# noqa: BLE001` with a reason ("No-silent-fallback lint rule" below). Pattern:
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
6. **Use `logger.exception()` in except blocks** (includes traceback). Use `logger.error()` for known error conditions that aren't exceptions.

### Semantic-memory writes

Semantic-memory writes go through `backend/services/scene_intel/`
(`persist_observation` / `persist_movements`, or the composed `persist` for the
analyze-then-write case). Never call the semantic-memory client's write
methods (`create_observation`, `create_movement`) from steps, subscribers, or
routers; read-side query methods may be used by query services. This is the
single write seam: one place to plug in a new writer, one degradation
behavior (a `None` memory client returns a zero-value record), and one test
surface (`backend/tests/services/scene_intel/`).

### Activity ledger

Countable/duration daily-life facts (medication, meals, TV, sleep) are recorded as
`ActivitySession` rows via the `activity_session_start`/`activity_session_end` steps, queried
via `DailyReportService` and its MCP tools. Never answer a countable question by aggregating
semantic-memory captions (DL2: typed-first, SQL aggregation, never LLM-counted recall).
Detectors ship as importable rule bundles, shadow-first.

Every ledger row carries `source` (`ActivitySourceEnum`) and `confidence` as real columns, not
metadata keys, and answers are phrased to match that evidence grade: only
`source="guided_companion"` supports claiming she completed an action. An unknown `source`
degrades to the weakest grade rather than raising, so a typo can never inflate confidence.
Full ledger architecture and the provenance table: the `daily-living` skill
(`/home/sriram/code/nanai/cognitive-companion/.claude/skills/daily-living/SKILL.md`, section 2).

## Logging

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

## Time and timezone

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

## Python virtual environment

**Always use the project venv at `backend/.venv/`; never invoke the system Python.** The Makefile targets activate it automatically. For direct invocation:

```bash
source backend/.venv/bin/activate          # interactive session
backend/.venv/bin/python -m pytest ...     # one-shot without activating
cd backend && uv sync --frozen --extra dev # sync after pyproject.toml changes
```

Running bare `python` or `pip` without the venv installs packages into the system interpreter and breaks the project's locked dependency graph.

## Common anti-patterns

### Backend

| Anti-pattern | Correct approach |
|---|---|
| `print("debug", x)` | `logger.debug("event", value=x)` |
| `from structlog import get_logger` | `from backend.core.logging import get_logger` |
| `except Exception: pass` | Log and return zero value, or re-raise as AppError |
| `dict["key"]` without check | Validate with Pydantic; `.get("key", default)` only for a documented optional field, never for required upstream data ("Error handling" rule 4 above) |
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

## No-silent-fallback lint rule

The `BLE001` (blind-except) ruff rule is enabled at `error` severity in `backend/pyproject.toml`. The documented allowlist is the only place a bare `except Exception` is permitted. Every other failure path must:

1. Raise a typed `AppError` subclass (`NotFoundError`, `ConflictError`, etc.), or
2. Return an explicit `None` / zero value with a `logger.warning()` call that names the optional degraded integration, or
3. Dead-letter the message with a Prometheus counter increment and a `logger.warning()` (for stream consumers).

Never return a fabricated `{}` or `[]` to hide a missing upstream. A missing required field is a contract violation; expose it as a typed 4xx/5xx. Only optional fields may use documented defaults, and tests must cover that degraded path.
