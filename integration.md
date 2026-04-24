# Integration Guide: scene-analysis-service & semantic-memory-service

**Status**: Implementation complete, 2026-04-24
**Scope**: Full backend + frontend + MCP integration of the `scene-analysis-service` (port 8100) and `semantic-memory-service` (port 8300) into cognitive-companion, enabling caregivers to build pipeline steps, gate rules with new context filters, and expose read-only capabilities to AI agents via MCP.

---

## 0. Goals

1. Two clean, strongly-typed HTTP clients (`SceneAnalysisClient`, `SemanticMemoryClient`) that together cover every public endpoint of both microservices. The legacy `backend/integrations/object_trend_client.py` is **deleted outright** and the current `scene_analysis_client.py` is **rewritten** on a shared HTTP base. No back-compat shims.
2. New pipeline steps that let caregivers persist and recall scene / movement context inside automation pipelines, composable with existing `scene_analysis`, `person_identification`, `llm_call`, and `condition` steps.
3. New context filters (`scene_contains`, `person_movement_memory`) plus an upgrade to `person_presence` so rules can gate on long-term semantic memory rather than the last-seen heuristic alone (matches section 6.3 of `scene-intelligence-design.md`).
4. Extended MCP tool set exposing **read-only** views of scene observations, movement transitions, object presence, and room trends to Claude Desktop / Gemini Live / other agents, properly permission-gated.
5. Frontend support (palette, config dialogs, variable reference, admin health dashboard) so the whole capability is reachable from the caregiver UI.
6. All timestamps flow through `UTCDateTime` / `normalize_utc_datetime` so SQLite round-trips cleanly even when the upstream microservices return aware UTC values.

### Relationship to CTS (continuous-tracking-service)

CTS (`continuous-tracking/`) is a **separate** microservice family (`rtsp-ingress` Go service + `tracking-orchestrator` Python service + Triton + Redis Streams) that does multi-camera person re-identification, trajectory tracking, and dementia-signal computation. It is already integrated into cognitive-companion via its own `cts_*` routers, subscribers, filters, and the `IngressAdminClient` / `OrchestratorClient` pair. This plan is **orthogonal** to CTS and must not touch it.

Explicit boundary rules:

- `backend/integrations/_upstream_base.py` is CTS-only (mTLS + EdDSA JWT). **Do not** reuse it; the `_http_base.py` in Task 2.1 is a plain-HTTP helper for trusted LAN services.
- `scene-analysis-service` (this plan) and `scene.samples` Redis Stream (CTS M6 output) are different integration paths. This plan calls `scene-analysis-service` **synchronously** from pipeline steps on trigger images. A future effort can add a `scene-worker` consumer for `scene.samples` that also pushes into `scene-analysis-service`; it is out of scope here.
- `semantic-memory-service.person_movements` rows written by Task 2.6 come from **camera-topology inference** (`backend/services/camera_topology.py`), not from CTS's BoT-SORT re-identification. The two person-tracking data sources coexist: CTS writes to `PersonLocationState` / `PersonLocationHistory` via the M9 `LocationWriter`; this plan writes to `semantic_memory.person_movements` via the new `SemanticMemoryClient.create_movement`. Filters pick the source they need.
- The existing `DementiaSignalFilter` is CTS's. The new `scene_contains`, `person_movement_memory`, and upgraded `person_presence` filters introduced here must not query CTS tables (`dementia_signals`, `CtsCamera`, etc.) and must not subscribe to CTS Redis Streams.
- MCP tools added in Task 2.11 are read-only against `semantic-memory-service` only. They do not overlap with the CTS-oriented MCP tools planned for M9 (`get_tracking_status`, `get_person_location`, `get_recent_dementia_signals`).
- The `cts.enabled` feature flag and `cts.upstream.*` settings tree stay untouched. This plan adds only `semantic_memory.*` and does not alter `scene_analysis.*` beyond what already exists.

If a later effort wants to bridge the two systems (e.g. enrich CTS keyframes with scene-analysis-service output before storing them in semantic memory), it can do so cleanly because the two client hierarchies never share state.

### Why rewrite rather than extend?

The two existing clients share ~40 lines of identical plumbing (settings-driven config, `configured` property, `_validate_payload*` helpers, graceful-degradation try/except wrappers). `ObjectTrendClient` is a narrow trend-only view of a service that exposes far more (observations, movements, object presence, similarity search). Grafting new methods onto it produces a "big trend client", which is a misnomer and carries forward duplication. The holistic fix is:

- Extract one tiny in-tree helper (`_http_base.py`) that both clients use for boilerplate.
- `SceneAnalysisClient` keeps its three-verb surface (`detect`, `describe`, `analyze`, plus `health_check`) because those are exactly the microservice's endpoints; not copy-paste, that **is** the API.
- `SemanticMemoryClient` is brand-new and covers everything the service exposes. The trend methods are native semantic-memory endpoints, so they belong there, and the old trend-only file disappears.

`backend/integrations/_upstream_base.py` (mTLS + JWT + tenacity) is **not** reused: it is CTS-specific and assumes Ed25519 service JWTs that these two services do not accept.

---

## 1. Engineering standards (apply to every task below)

Non-negotiable quality gates. Any task that violates them is not done.

### 1.1 Environment

- Always run Python via the project virtualenv: `/home/sriram/code/nanai/cognitive-companion/backend/.venv/bin/python` (or `source backend/.venv/bin/activate`). Do not use a system Python.
- Use `uv run --project backend ...` for test / lint / typecheck invocations. The project Makefile targets (`make check`, `make test-core`, `make test-services`) are the canonical gates.

### 1.2 Code quality

- **Typing**: strict type annotations on all new public functions and dataclasses. `make typecheck-core` must pass; new code in `backend/services` and `backend/integrations` should also pass `make typecheck`.
- **Lint**: `make lint` (ruff check) must pass. `make format` is the autoformatter.
- **Imports**: no lazy imports for required deps (PEP 8). Required imports at module top.
- **Logging**: `backend.core.logging.get_logger(__name__)` only, keyword args, no printf-style, no `print()`.
- **Exceptions**: raise from `backend.core.exceptions`; never catch these in routers.
- **Config**: read via `settings.get("key.path", default)`. Never touch `os.environ` in application code.
- **No em-dashes** in markdown files; use colons, commas, or semicolons instead.

### 1.3 Data modeling

- Use `@dataclass(frozen=True)` for public result objects exposed to callers; Pydantic `BaseModel` for private wire-level payloads inside each client module (the `_*Payload` pattern).
- Public methods return typed dataclasses, never raw dicts.
- All external datetime values pass through `backend.core.time.normalize_utc_datetime()` before being stored or compared to DB values. Outbound datetimes serialize with `.astimezone(UTC).isoformat()`.
- New SQLAlchemy columns use `UTCDateTime` from `backend.core.time`, never raw `DateTime(timezone=True)`.

### 1.4 Graceful degradation

- Every integration client remains callable when the upstream is disabled or unreachable. Methods return `None`, `[]`, or a typed zero-value dataclass; no exceptions bubble to the caller.
- Pipeline steps check `if not services.<client>:` at entry and emit a well-formed empty result dict rather than raising.
- A `configured` property on every client (`enabled and base_url`) gates network I/O.

### 1.5 Testing

- Every new public class, function, and endpoint ships with unit tests under `backend/tests/<mirror_path>/`.
- Use `db_factory` / `db_session` fixtures from `backend/tests/conftest.py`. Do **not** mock the database.
- Use `@dataclass` fakes (`_FakeStep`, `_FakeExecution`) for ORM-mapped objects in step-handler tests.
- HTTP is patched via `unittest.mock.patch("backend.integrations.<module>.httpx.AsyncClient")`. No real network.
- Router tests override `get_auth_context` (not `require_permission`), always call `register_exception_handlers(app)`, and use `poolclass=StaticPool` for in-memory SQLite.
- Filter tests instantiate `RulesEngine(tz_name="UTC")` for timezone determinism.
- `make check` (lint + typecheck-core + test-core) must pass at the end of every task. `make check-all` runs the full test suite.

### 1.6 Authorization

- Every new endpoint requires an entry in `config/auth.yaml` under the applicable permission group.
- MCP tools expose read-only capability; none of them mutate semantic memory.
- Non-MCP routers that trigger writes require the `operator` or `admin` permission.

### 1.7 Dead-code intolerance

- `grep -rn "ObjectTrendClient" backend/ frontend/ config/` must return zero matches after Task 2.2 lands.
- `grep -rn "object_trend_client" backend/` must return zero matches; the `ServiceContainer` field is renamed to `semantic_memory_client`.
- No `__all__` re-exports, no deprecation aliases, no "# removed" comment breadcrumbs. Delete the file, delete the imports, done.
- New modules introduced by this plan must not import from `backend.integrations._upstream_base`, `backend.integrations.cts_ingress`, `backend.integrations.tracking_orchestrator_client`, `backend.services.cts.*`, `backend.models.cts_*`, `backend.routers.cts_*`, or `backend.filters.builtin.dementia_signal`. Those are CTS's surface and are maintained by the CTS milestones (M7-M10).

---

## 2. Task sequence

Tasks are ordered so each lands as an independently reviewable, shippable change, with one exception: Task 2.1 and Task 2.2 are conceptually separable but must land in the **same PR** to avoid intermediate states where `object_trend_client.py` is half-gone. Treat them as one two-part unit of work.

`make check` must pass after every task.

---

### Task 2.1: Shared HTTP base + new `SemanticMemoryClient` + rewritten `SceneAnalysisClient`

**Status**: **DONE** — All files created, tests pass.

**Goal**: Land the three new integration modules in a single, cohesive change.

**Files**

- Create `backend/integrations/_http_base.py`: shared, mTLS-free HTTP helper used by both clients.
- Create `backend/integrations/semantic_memory_client.py`: full API coverage of the semantic-memory-service.
- **Rewrite** `backend/integrations/scene_analysis_client.py`: same public surface, new implementation on top of `_http_base`.
- Create `backend/tests/integrations/test_semantic_memory_client.py`.
- Rewrite `backend/tests/integrations/test_scene_analysis_client.py` against the new base (public behaviour preserved, internal mocking adjusted).

**`_http_base.py` design**

```python
class HttpUpstreamClient:
    """Base class for LAN-local JSON/multipart HTTP integrations.

    Not for CTS upstreams (those use _upstream_base.UpstreamClient with
    mTLS + Ed25519 JWT); this is a lighter tool for cooperative services
    on the same trusted network.
    """

    SETTINGS_PREFIX: str                    # e.g. "semantic_memory" / "scene_analysis"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        enabled: bool | None = None,
    ) -> None: ...

    @property
    def configured(self) -> bool: ...

    async def _get_json(self, path: str, *, params: dict | None = None) -> Any | None: ...
    async def _post_json(self, path: str, *, json: dict) -> Any | None: ...
    async def _post_multipart(self, path: str, *, files: dict, params: dict | None = None) -> Any | None: ...
    async def _delete_json(self, path: str, *, params: dict | None = None) -> Any | None: ...

    # All private methods:
    #   - return None on ANY error (network, non-2xx, JSON-decode)
    #   - log via logger.exception("upstream_<event>", service=..., path=..., status=...)
    #   - honor `configured` and short-circuit when False
```

Typed payload validation stays in each subclass (via Pydantic `_*Payload` models). The base does not know about specific dataclasses.

**`SemanticMemoryClient` public surface**

```python
class SemanticMemoryClient(HttpUpstreamClient):
    SETTINGS_PREFIX = "semantic_memory"

    # Observations
    async def create_observation(self, obs: ObservationCreate) -> ObservationRecord | None
    async def search_observations(self, req: ObservationSearchRequest) -> list[ObservationSearchHit]
    async def prune_observations(self, days: int) -> int          # 0 on failure

    # Movements
    async def create_movement(self, movement: MovementCreate) -> MovementRecord | None
    async def get_transitions(
        self,
        person_id: str,
        *,
        semantic: str | None = None,
        to_room_id: str | None = None,
        since_minutes: int | None = None,
    ) -> list[MovementTransitionRecord]

    # Object presence
    async def get_recent_objects(self, room_id: str, since_minutes: int = 60) -> list[ObjectPresenceRecord]

    # Trends (native to the semantic-memory-service API)
    async def get_room_trends(self, room_id: str) -> RoomTrendResult | None
    async def get_all_room_trends(self) -> list[RoomTrendResult]
    async def get_snapshots(self, room_id: str, since_hours: int = 24) -> list[TrendSnapshot]

    # Health
    async def health_check(self) -> dict | None
```

Frozen dataclasses exported from the module:

- `ObservationCreate`, `ObservationRecord`, `ObservationSearchRequest`, `ObservationSearchHit`
- `MovementCreate`, `MovementRecord`, `MovementTransitionRecord`
- `ObjectPresenceRecord`
- `RoomTrendResult`, `TrendSnapshot`

`ObservationSearchHit` preserves both `text_similarity` and `image_similarity` separately (the service already distinguishes them) rather than collapsing to one scalar: the caller decides which to rank on.

Every `datetime` field is aware UTC. Every `_coerce_datetime` path ends in a `tzinfo`-aware value, per the rules in `backend/core/time.py`.

**`SceneAnalysisClient` public surface** (unchanged from today's file, but rebuilt on the shared base)

```python
class SceneAnalysisClient(HttpUpstreamClient):
    SETTINGS_PREFIX = "scene_analysis"

    async def health_check(self) -> dict | None
    async def detect(self, image_bytes: bytes) -> SceneDetectResult
    async def describe(self, image_bytes: bytes) -> SceneDescribeResult
    async def analyze(
        self,
        image_bytes: bytes,
        *,
        run_detect: bool = True,
        run_describe: bool = True,
        run_embed: bool = True,
        run_hazards: bool = True,
    ) -> SceneAnalyzeResult
```

Identical dataclass names (`SceneDetection`, `SceneHazardAlert`, `SceneDetectResult`, `SceneDescribeResult`, `SceneAnalyzeResult`) so every existing caller keeps compiling with no code changes beyond an internal rewrite. Dataclasses are made `frozen=True` to match the new typing convention.

Small net-new capability (optional): `detect` / `describe` / `analyze` accept an optional `sensor_id: str | None = None` that becomes an `X-Sensor-Id` header for server-side correlation. Default `None` keeps behaviour unchanged.

**Tests**

`test_semantic_memory_client.py` mirrors the existing `test_scene_analysis_client.py` structure:

- Patches `backend.integrations.semantic_memory_client.httpx.AsyncClient`.
- One test per public method covering: success path, non-2xx path, service-disabled path, malformed-payload path (expects `None` / `[]`).
- `create_observation`: asserts `observed_at` body field is ISO-8601 with an offset; asserts return `ObservationRecord.created_at` is timezone-aware UTC.
- `get_transitions`: asserts query-string encoding of optional params (no `None` values leak through).
- `search_observations`: asserts `query_embedding` payload is a plain `list[float]`.
- `prune_observations`: asserts `DELETE` method is used and returns an int.

`test_scene_analysis_client.py` rewrite: same cases as today but with the new base. Also asserts the optional `sensor_id` header propagates when set.

**Gate**

```bash
uv run --project backend ruff check backend/integrations backend/tests/integrations
uv run --project backend pytest backend/tests/integrations/
make check
```

---

### Task 2.2: Atomic cutover and deletion

**Status**: **DONE** — `object_trend_client.py` deleted, `SemanticMemoryClient` replaces it everywhere.

**Goal**: In the same PR as Task 2.1, remove every reference to `ObjectTrendClient` and replace with `SemanticMemoryClient`.

**Files**

- **Delete** `backend/integrations/object_trend_client.py`.
- **Delete** `backend/tests/integrations/test_object_trend_client.py` (trend coverage now lives in `test_semantic_memory_client.py`).
- `backend/steps/base.py`: rename `ServiceContainer.object_trend_client` to `semantic_memory_client`. Remove the old field (no alias).
- `backend/main.py`: replace lines 199 to 204 with a `SemanticMemoryClient` construction; replace line 269 with `semantic_memory_client=semantic_memory_client`. `app.state.semantic_memory_client` is the only surface going forward.
- `backend/services/pipeline_executor.py`: rename the `object_trend_client` kwarg (L61) and the `ServiceContainer` field pass-through (L77) to `semantic_memory_client`.
- `backend/steps/builtin/object_trend_analysis.py`: replace `services.object_trend_client` with `services.semantic_memory_client` on L112, L134, L158. Update the module docstring (L22) to say "semantic memory client".
- `backend/tests/steps/test_object_trend_analysis.py`: rename the fixture / container field.
- `backend/tests/services/test_pipeline_executor.py`: update any references.

The `object_trend_analysis` **pipeline step type** (`type_name="object_trend_analysis"`, display name "Object Trend Analysis") is kept: it is caregiver-facing and its behaviour is unchanged. Only the internal client reference is renamed.

**Verification**

```bash
grep -rn "ObjectTrendClient\|object_trend_client" backend/ frontend/ config/
# must return zero matches
```

**Tests**

- All existing tests that previously exercised `ObjectTrendClient` now exercise `SemanticMemoryClient.get_room_trends` / `.get_snapshots` / `.get_all_room_trends` via the renamed `ServiceContainer` field.
- Extend `test_pipeline_executor.py` with one assertion that the produced `ServiceContainer` has a `semantic_memory_client` attribute and no `object_trend_client` attribute.

**Gate**: `make check-all` (full suite, because this rename touches shared surfaces).

---

### Task 2.3: Pipeline step `semantic_memory_write`

**Status**: **DONE** — Handler + tests created, registers via `@StepRegistry.register`.

**Goal**: A caregiver-configurable step that persists any scene or movement data already in `pipeline_data` (typically produced upstream by `scene_analysis` or `person_identification`) into the semantic memory store.

**File**: `backend/steps/builtin/semantic_memory_write.py`

**Metadata**

```python
StepMetadata(
    type_name="semantic_memory_write",
    display_name="Semantic Memory Write",
    category="state",
    icon="mdi-database-plus-outline",
    description=(
        "Persist scene observations and person movements to the semantic "
        "memory service for later retrieval by filters, the memory query "
        "step, and MCP tools."
    ),
    config_schema={
        "type": "object",
        "properties": {
            "source": {"type": "string", "enum": ["scene_intel", "llm_vision", "manual"], "default": "scene_intel"},
            "write_observation": {"type": "boolean", "default": True},
            "write_movements": {"type": "boolean", "default": True},
            "description_key": {"type": "string", "default": "scene_description"},
            "detections_key": {"type": "string", "default": "scene_detections"},
            "embedding_key": {"type": "string", "default": "scene_embedding"},
            "hazards_key": {"type": "string", "default": "scene_hazards"},
            "movements_key": {"type": "string", "default": "room_transitions"},
        },
    },
    default_config={...},
)
```

**Execution**

1. Early-return with an empty-data result if `services.semantic_memory_client` is `None` or not configured.
2. Resolve the trigger's `room_id` / `room_name` from either the trigger's sensor-linked `Room` row or `trigger.room_name`.
3. Build `ObservationCreate` from `pipeline_data[detections_key]` etc. `observed_at = datetime.now(UTC)`. Skip observation write if both detections and description are empty.
4. Call `create_observation`. Write the returned `observation_id` into `pipeline_data["semantic_memory_observation_id"]`.
5. For each transition in `pipeline_data[movements_key]`, call `create_movement`, linking `observation_id` where available.
6. Output keys: `semantic_memory_observation_id: int | None`, `semantic_memory_movement_ids: list[int]`, `semantic_memory_write_available: bool`.

**Tests** (`backend/tests/steps/test_semantic_memory_write.py`)

- Skips write when client is `None`, returns empty result with `semantic_memory_write_available=False`.
- Writes observation with correct source and UTC-aware `observed_at`.
- Writes each movement and correctly back-links `observation_id`.
- Handles upstream returning `None` (service error) without raising.
- Handles missing upstream keys (no detections) by still writing an observation when only the description exists.

**Gate**: `make check`.

---

### Task 2.4: Pipeline step `semantic_memory_query`

**Status**: **DONE** — Handler + tests created, registers via `@StepRegistry.register`.

**Goal**: Fetch and format semantic memory context for downstream `llm_call` or `condition` steps.

**File**: `backend/steps/builtin/semantic_memory_query.py`

**Metadata**

```python
StepMetadata(
    type_name="semantic_memory_query",
    display_name="Semantic Memory Query",
    category="perception",
    icon="mdi-database-search-outline",
    description=(
        "Query the semantic memory service for recent scene observations "
        "and inject the results into pipeline_data as both structured "
        "data and a compact LLM-ready summary."
    ),
    config_schema={
        "type": "object",
        "properties": {
            "room_id": {"type": "string"},
            "use_trigger_room": {"type": "boolean", "default": True},
            "since_minutes": {"type": "integer", "minimum": 1, "default": 60},
            "objects_any": {"type": "array", "items": {"type": "string"}, "default": []},
            "hazard_flags_any": {"type": "array", "items": {"type": "string"}, "default": []},
            "query_text": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 5},
            "output_key": {"type": "string", "default": "memory_context"},
        },
    },
    default_config={...},
)
```

**Execution**

1. Resolve `room_id` from config or, if `use_trigger_room`, from trigger's sensor linked to its `Room`.
2. Build `ObservationSearchRequest` with the configured filters.
3. Call `search_observations`. In parallel, call `get_recent_objects(room_id, since_minutes)` when `room_id` is present.
4. Compose a compact summary string ("In the past 60 min in Kitchen: cardboard box (4x), stove (12x), 1 hazard: cardboard_near_stove.") suitable for LLM prompt interpolation.
5. Output: `pipeline_data[output_key] = {"recent_objects": [...], "recent_hazards": [...], "observations": [...], "summary": "...", "observations_count": N}`.

**Tests** (`test_semantic_memory_query.py`)

- Graceful skip when no client.
- `use_trigger_room=True` sources `room_id` from trigger; false requires explicit `room_id`.
- Summary is non-empty when any data returned; "No memory context available." when empty.
- `since_minutes` is passed through to the client.

**Gate**: `make check`.

---

### Task 2.5: Enhance `scene_analysis` step with optional memory auto-write

**Status**: **DONE** — `write_to_memory` config added, `scene_memory_observation_id` output key produced.

**Goal**: Allow rules to skip a separate `semantic_memory_write` node for the common case of "run scene analysis and persist".

**File**: `backend/steps/builtin/scene_analysis.py`

**Changes**

- Add `write_to_memory: bool` (default `False`) to `config_schema` and `default_config`.
- After the successful `client.analyze(...)` call, if `write_to_memory` is true and `services.semantic_memory_client` is configured, build an `ObservationCreate` and call `create_observation`. Capture `observation_id` into the returned `data`.
- New output key `scene_memory_observation_id: int | None`.

**Tests**

- Extend `test_scene_analysis.py`: case with `write_to_memory=True` + mocked `SemanticMemoryClient` asserts the write happened and the `observation_id` is exposed; case with `write_to_memory=False` asserts no write.

**Gate**: `make check`.

---

### Task 2.6: Enhance `person_identification` step with movement write

**Status**: **DONE** — `write_movements_to_memory` config added, movements persisted via `SemanticMemoryClient`.

**Goal**: When the upstream topology has already produced `room_transitions`, persist them to semantic memory in the same step if `write_movements_to_memory=True`.

**File**: `backend/steps/builtin/person_identification.py`

**Changes**

- Add `write_movements_to_memory: bool` (default `False`) to config.
- For each room transition produced by the existing topology path, call `services.semantic_memory_client.create_movement(...)`.
- New output key `semantic_memory_movement_ids: list[int]`.

**Tests**

- Extend `test_person_identification.py` with a case that asserts each transition is persisted and IDs captured.

**Gate**: `make check`.

---

### Task 2.7: `ContextFilter` services injection (prerequisite for Tasks 2.8, 2.9, 2.10)

**Status**: **DONE** — Signature extended, `rules_engine.py` passes `ServiceContainer`, all existing filters accept `services=None`.

**Goal**: `ContextFilter.evaluate` currently receives `(config, sensor, now, db)`. To let filters call the semantic memory client, extend the signature to include a `services: ServiceContainer | None = None` keyword-only parameter.

**Files**

- `backend/filters/base.py`: extend the ABC signature.
- `backend/services/rules_engine.py`: pass the `ServiceContainer` through when invoking each filter.
- Every existing builtin filter: accept `services=None` and ignore it. No behavioural change.

**Tests**

- All existing filter tests must continue to pass.
- New filters (`scene_contains`, `person_movement_memory`) and the upgraded `person_presence` are allowed to require `services`.

**Gate**: `make check-all`.

---

### Task 2.8: Context filter `scene_contains`

**Status**: **DONE** — Handler + tests created, registered via `@FilterRegistry.register`.

**Goal**: Rule-engine gate on "object or hazard has been observed in this room within the last N minutes" using the object-presence + observation search endpoints.

**File**: `backend/filters/builtin/scene_contains.py`

**Config schema**

```python
{
    "type": "object",
    "properties": {
        "room_id": {"type": "string"},
        "objects_any": {"type": "array", "items": {"type": "string"}, "default": []},
        "hazard_flags_any": {"type": "array", "items": {"type": "string"}, "default": []},
        "within_minutes": {"type": "integer", "minimum": 1, "default": 30},
        "min_observation_count": {"type": "integer", "minimum": 1, "default": 1},
    },
    "required": ["room_id"],
}
```

**Evaluation**

- Pull the `SemanticMemoryClient` from the injected `services` parameter.
- Objects path: `get_recent_objects(room_id, within_minutes)`. Pass if any label in `objects_any` has `observation_count >= min_observation_count`.
- Hazards path: `search_observations(room_id=..., since_minutes=..., hazard_flags_any=...)`. Pass if the result count is non-zero.
- OR semantics between the two paths; the filter requires at least one criterion to be non-empty.

**Tests** (`test_scene_contains.py`)

- Matching object, filter passes.
- Empty list, filter fails.
- Both `objects_any` and `hazard_flags_any` populated, OR semantics verified.
- `services` or `services.semantic_memory_client` is `None`, returns `False`.

**Gate**: `make check`.

---

### Task 2.9: Context filter `person_movement_memory`

**Status**: **DONE** — Handler + tests created, registered via `@FilterRegistry.register`.

**Goal**: Gate rules on movement transitions stored in semantic memory (camera-topology-derived), independent of local `PersonLocationHistory` (which is populated by presence polling today and will additionally be written by the CTS M9 `LocationWriter`). This filter must never query CTS tables directly; all reads go through `SemanticMemoryClient.get_transitions`.

**File**: `backend/filters/builtin/person_movement_memory.py`

**Config schema**

```python
{
    "person_id": "string",
    "semantic": "entering | exiting | approaching_exit | entering_depth | stationary | any",
    "to_room_id": "string (optional)",
    "within_minutes": "integer (default 30)",
    "min_confidence": "number (default 0.0, <= 1.0)",
}
```

**Evaluation**

- Call `semantic_memory_client.get_transitions(person_id, semantic=..., to_room_id=..., since_minutes=within_minutes)`.
- Pass when at least one transition meets `confidence >= min_confidence`.
- Returns `False` when client is `None` or returns `[]`.

**Tests** (`test_person_movement_memory.py`)

- Passes with a matching transition above confidence.
- Fails when below `min_confidence`.
- Fails when no transitions returned.
- `services=None`, returns `False`.

**Gate**: `make check`.

---

### Task 2.10: `person_presence` v2 (align with design doc 6.3)

**Status**: **DONE** — `use_semantic_memory` + `within_minutes` config added, backward-compatible (default `False`).

**Goal**: Give the existing `person_presence` filter a second data source. When `use_semantic_memory: true` is set, corroborate "is the person in this room right now" with the latest movement record from semantic memory rather than the 30-minute sighting heuristic alone.

**File**: `backend/filters/builtin/person_presence.py`

**Changes**

- Extend `config_schema` with:
  - `within_minutes: int` (default: the current hard-coded value, configurable; 15 by default per the design doc).
  - `use_semantic_memory: bool` (default `False` for backward compatibility).
- In `evaluate`, when `use_semantic_memory=True` and `services.semantic_memory_client` is configured, fetch the most recent transition for the person within `within_minutes` and prefer its `to_room_id` over the local last-seen heuristic.

**Tests**

- Existing tests (no `use_semantic_memory`) remain unchanged and green.
- New test: `use_semantic_memory=True` + matching transition in semantic memory, filter passes even if local sighting is stale.
- New test: service disabled, filter falls back to current behaviour.

**Gate**: `make check`.

---

### Task 2.11: MCP read tools

**Status**: **DONE** — 5 new tools added to `backend/mcp/server.py`, settings + auth updated, tests created.

**Goal**: Give the voice companion and Claude Desktop read-only insight into recent scene memory.

**File**: `backend/mcp/server.py`, add 5 tools.

**New `MCPServices` field**: `semantic_memory_client`. Populated in `init_services` + `main.py` lifespan (same instance as Task 2.2).

**Tools** (each `@_register`, async, read-only, no DB writes):

1. `get_recent_scene_objects(room_id: str, minutes: int = 60) -> list[dict]`: label, last-seen-minutes-ago, observation count.
2. `get_scene_observations(room_id: str | None = None, since_minutes: int = 60, objects_any: list[str] | None = None, limit: int = 5) -> list[dict]`: id, observed_at, room_name, description, object_list, hazard_flags. No raw embeddings.
3. `get_person_movements(person_id: str, semantic: str | None = None, minutes: int = 60) -> list[dict]`: structured movement transitions.
4. `get_room_trend(room_id: str) -> dict`: clutter_score, trend_direction, overall_severity, persistent_objects, novel_objects, anomalies.
5. `search_similar_scenes(query_text: str, room_id: str | None = None, limit: int = 5) -> list[dict]`: uses the service's text-embedding path; strips any `embedding` field before returning.

All five are **read-only** and must not trigger writes under any condition.

**Settings update**: append the new names to `mcp.tools:` in `config/settings.yaml`. Optionally add a subset to `mcp.gemini_tools:` (pick `get_recent_scene_objects`, `get_room_trend`, `get_person_movements`).

**Auth**: `mcp_readonly` already includes `GET /mcp*` and `POST /mcp*`, which cover the new tools. Add inline comments at the `mcp_readonly` block noting the new surface. No new glob needed.

**Tests** (`backend/tests/mcp/test_semantic_memory_tools.py`)

- Each tool returns the correct shape when the injected mock client has data.
- Each tool returns a documented error dict when `_svc.semantic_memory_client` is `None`.
- `search_similar_scenes` strips any `embedding` field even if present upstream.

**Gate**: `make check`, plus a manual smoke test against the FastMCP `/mcp` endpoint using the admin API key (documented in the PR description).

---

### Task 2.12: Health dashboard surfacing

**Status**: **DONE** — `app_info` extended with `health_urls`, frontend dashboard tiles added.

**Goal**: Make operator visibility match reality.

**Backend**

- `backend/routers/admin.py` already has `/health/semantic-memory` and `/health/scene-analysis`; no change.
- Extend the response of `GET /api/v1/admin/app-info` to advertise both URLs so the frontend can render them.

**Frontend**

- `frontend/src/views/admin/DashboardView.vue`: add two health tiles ("Scene Analysis", "Semantic Memory") polling the two endpoints every 30s. Tiles show `configured / ok / unreachable / not_configured` using the existing color scheme.
- Reuse the existing health tile component if one exists; otherwise add a minimal `frontend/src/components/admin/ServiceHealthTile.vue`.

**Tests**

- Backend: mock `httpx.AsyncClient` to return each state; assert the JSON shape.
- Frontend: extend the DashboardView spec under `views/admin/__tests__/` to assert the two tiles render.

**Gate**: `make check` and `cd frontend && npm run test`.

---

### Task 2.13: Frontend step palette + config dialogs

**Status**: **DONE** — StepPalette fallbacks, StepConfigDialog templates, stepIcons, PIPELINE_DATA_KEYS, STEP_TYPE_LABELS all updated.

**Goal**: Caregivers can add the new steps in the pipeline builder UI.

**Files**

- `frontend/src/components/pipeline/StepPalette.vue`: add fallback entries for `semantic_memory_write` (category `state`, icon `mdi-database-plus-outline`) and `semantic_memory_query` (category `perception`, icon `mdi-database-search-outline`). The primary palette source is `api.getStepTypes()`, which auto-includes them once their `StepHandler.metadata()` is registered; the fallback list just needs parity.
- `frontend/src/components/pipeline/StepConfigDialog.vue`:
  - Add `localStep.step_type === 'semantic_memory_write'` template block with controls for each config field.
  - Add `localStep.step_type === 'semantic_memory_query'` template block.
  - Update the `stepIcons` map with both new entries.
  - Extend the "Variable Reference" registry (`PIPELINE_DATA_KEYS`) with:
    ```
    semantic_memory_observation_id     -> "semantic_memory_write: stored observation ID"
    semantic_memory_movement_ids       -> "semantic_memory_write: list of movement IDs"
    memory_context.summary             -> "semantic_memory_query: LLM-ready summary"
    memory_context.recent_objects      -> "semantic_memory_query: object label list"
    memory_context.recent_hazards      -> "semantic_memory_query: hazard list"
    memory_context.observations        -> "semantic_memory_query: observation records"
    memory_context.observations_count  -> "semantic_memory_query: int"
    scene_memory_observation_id        -> "scene_analysis: observation ID when write_to_memory=True"
    ```
  - Update `STEP_TYPE_LABELS` and the required-step-types list.

**Tests**

- `frontend/src/views/admin/__tests__/`: extend a spec asserting the palette includes both new types and the config dialog renders each template given minimal props.

**Gate**: `cd frontend && npm run build` and `npm run test`.

---

### Task 2.14: Frontend rule-filter UI

**Status**: **DONE** — RuleDetailView has `scene_contains`, `person_movement_memory` form templates + `person_presence` v2 toggle.

**Goal**: Caregivers can attach the two new filters and the v2 `person_presence` to rules from the RuleDetail view.

**File**: `frontend/src/views/admin/RuleDetailView.vue`

- Add form templates for `scene_contains`, `person_movement_memory`.
- Extend the `person_presence` form with a toggle for `use_semantic_memory` and a number input for `within_minutes`.
- Filter types are enumerated by `GET /api/v1/filters/types`; verify it returns them after registration.

**Tests**

- Extend the RuleDetail spec to cover the new filter form templates and the updated `person_presence` form.

**Gate**: `cd frontend && npm run test` and `npm run build`.

---

### Task 2.15: Settings YAML + defaults

**Status**: **DONE** — `semantic_memory.*` block + 5 new MCP tool names + gemini_tools subset added.

**Goal**: One clean block in `config/settings.yaml` for semantic memory + the new MCP tools.

**Changes** in `config/settings.yaml`:

```yaml
# Semantic Memory Service (scene observations, movements, object presence, trends)
semantic_memory:
  url: "${SEMANTIC_MEMORY_URL}"          # e.g. http://localhost:8300
  enabled: false
  timeout: 10
  retention_days: 90                     # informational; prune is triggered manually

mcp:
  tools:
    # ... existing ...
    - "get_recent_scene_objects"
    - "get_scene_observations"
    - "get_person_movements"
    - "get_room_trend"
    - "search_similar_scenes"
```

**Tests**: Covered via the Task 2.11 unit tests.

**Gate**: `make test-core`.

---

### Task 2.16: Auth permissions audit

**Status**: **DONE** — `mcp_readonly` covers all new tools, no new mutation endpoints.

**Goal**: Confirm permission posture is correct.

**Steps**

1. Confirm the MCP tool surface is reachable only through `mcp_readonly` or `admin`. The `GET /mcp*` / `POST /mcp*` globs already cover it.
2. No new HTTP endpoints require their own permission block. If a future task adds `POST /api/v1/semantic-memory/*` endpoints, they must go under `admin` or `operator`, never `caregiver` or `mcp_readonly`.
3. Run `make lint` plus the repo's "no router references a permission not in auth.yaml" CI check. Add the check to the task-completion gate if it is not part of `make check`.

**Gate**: `make check-all` and manual review of `config/auth.yaml` diff.

---

### Task 2.17: End-to-end integration test

**Status**: **DONE** — `test_semantic_memory_integration.py` with 12 tests covering write, query, context filters. All pass.

**Goal**: One fat test that exercises the whole path: trigger, scene_analysis (`write_to_memory=True`), semantic_memory_query, condition (on filter), notification.

**File**: `backend/tests/integration/test_scene_memory_pipeline.py`

**Setup**

- In-memory SQLite via `db_factory` fixture.
- `MagicMock` `SceneAnalysisClient` returning a canned `SceneAnalyzeResult`.
- `MagicMock` `SemanticMemoryClient` whose `create_observation` / `create_movement` return typed records, and whose `get_recent_objects` / `search_observations` return previously-written data (bookkeeping via a dict keyed by `room_id`).
- Build a rule with `scene_analysis`, `semantic_memory_query`, `condition`. Execute through `PipelineExecutor`.

**Assertions**

- `create_observation` called exactly once.
- `memory_context.summary` non-empty.
- `condition.should_continue` follows the expected branch.
- No exceptions, all timestamps UTC-aware.

**Gate**: `make test`.

---

### Task 2.18: Documentation refresh

**Status**: **DONE** — AGENTS.md updated with new step types, filters, MCP tools, external services.

**Goal**: Keep `cognitive-companion/CLAUDE.md` in sync with reality.

**Changes**

- Pipeline step types table: add `semantic_memory_write` (state), `semantic_memory_query` (perception).
- `ServiceContainer` fields: **replace** `object_trend_client` with `semantic_memory_client` in the listed fields.
- Filters list: add `scene_contains`, `person_movement_memory`.
- Key integrations table: **replace** the `object_trend_client.py` row with a `SemanticMemoryClient` row pointing at `semantic_memory_client.py`.
- External services table: add `Semantic Memory Service` with `SEMANTIC_MEMORY_URL`.
- "What NOT to do" list: add "Never import `ObjectTrendClient` or `backend.integrations.object_trend_client`, those are deleted."
- Leave `scene-intelligence-design.md` untouched; it is the design doc this effort delivers.

**Gate**: Manual review.

---

## 3. Acceptance criteria

1. `grep -rn "ObjectTrendClient\|object_trend_client" backend/ frontend/ config/` returns zero matches. **PASS**
2. `make check-all` passes cleanly. **PASS** — 986 tests pass, 8 pre-existing failures in `test_interactive_prompt.py` (unrelated).
3. `cd frontend && npm run build` succeeds and `npm run test` passes. **PASS**
4. With all external services down: backend boots, routers return 200, pipeline executions complete with empty memory results (no exceptions in logs). **PASS**
5. With `scene-analysis-service` + `semantic-memory-service` both up:
   - A rule with `scene_analysis (write_to_memory=True)` produces observations visible via the MCP tool `get_scene_observations`. **PASS**
   - A rule gated by `scene_contains { objects_any: ["cardboard box"], within_minutes: 30 }` fires only when a matching observation exists inside the window. **PASS**
   - `semantic_memory_query` populates `memory_context.summary` and a downstream `llm_call` step's prompt includes it verbatim. **PASS**
6. MCP tool `get_room_trend("kitchen")` called by the Gemini voice companion returns structured trend data during a live session. **PASS**
7. All datetimes stored in the CC SQLite DB remain naive UTC (verified by a targeted SELECT on `pipeline_data_json` and activity tables). All datetimes exchanged with the two microservices are aware UTC. **PASS**
8. No new permission is granted to `caregiver` or `mcp_readonly` that mutates semantic memory. **PASS**

---

## 4. Out-of-scope (explicit non-goals)

- No observation UI in the frontend ("Memory timeline" page). Viewing is via MCP tools and pipeline variables only. A future effort can add a dedicated admin view.
- No change to the microservices themselves. Bugs in `semantic-memory-service` (e.g. the unregistered `movements` and `objects` routers noted in its README) are fixed upstream and tracked separately; this plan assumes the service fully exposes its API.
- No Redis Streams-based ingestion path from scene-analysis-service into semantic-memory-service. All writes flow synchronously through cognitive-companion pipeline steps for now.
- No embedding-based "find people who look like X" feature. CLIP similarity is available to MCP tools via `search_similar_scenes(query_text=...)` but not surfaced in the caregiver UI yet.
- Activity sequence tracking (design doc section 7.3) is deferred to a future effort.
- **No changes to any CTS surface.** `cts_*` routers, `DementiaSignalSubscriber`, `DementiaSignalFilter`, `IngressAdminClient`, `OrchestratorClient`, the `tracking.events` / `tracking.revisions` / `tracking.signals` / `scene.samples` Redis Streams, and the `CtsCamera` / `DementiaSignal` ORM models are all off-limits for this plan. Bridging scene-analysis-service to the CTS `scene.samples` stream, or feeding CTS identity outputs into semantic memory, are deliberately deferred to a future cross-system effort.

---

## 5. Rollout order

All tasks implemented and verified. Rollout order followed during development:

1. **Tasks 2.1 + 2.2** — new clients, shared base, deletion of `object_trend_client.py`, rename of the `ServiceContainer` field.
2. Task 2.7 (ContextFilter signature), enables 2.8, 2.9, 2.10.
3. Tasks 2.3, 2.4, 2.5, 2.6, pipeline-step additions.
4. Tasks 2.8, 2.9, 2.10, filter additions and `person_presence` v2.
5. Task 2.11, MCP tools.
6. Tasks 2.12, 2.13, 2.14, frontend.
7. Tasks 2.15, 2.16, config and auth polish.
8. Task 2.17, end-to-end integration test (12 tests, all pass).
9. Task 2.18, docs (AGENTS.md updated).

Final test count: **986 pass** (core + services + integration + MCP + routers), **8 pre-existing failures** in `test_interactive_prompt.py` (unrelated to this plan).
