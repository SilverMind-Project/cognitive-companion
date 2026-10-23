# Layering and service wiring

Read before adding a module, a service, a router dependency, or an MCP tool. Part of the `engineering-standards` skill; the rules summary is in `../SKILL.md`.

## Code organization

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
bootstrap/       Service wiring, by phase, orchestrated by bootstrap/lifespan.py. The
                 only place services are constructed. May not import routers/; may not be
                 imported outside main.py (import-linter enforced). See bootstrap/README.md.
main.py          App factory only: FastAPI() creation, middleware, router includes, MCP mount.
```

**Cut-point rule:** If you find yourself importing from a layer to the right of your current layer, you have a circular dependency risk. Restructure.

**Never read another service's underscore attributes.** Reaching into `some_service._private_field` (e.g. `event_aggregator._minio`, `event_aggregator._db_session_factory`, or the wave-1-banned `repo._pool`) couples your module to that service's storage layout and bypasses its own invariants. Add a public method on the owning service instead (see `EventAggregator.recent_sensor_ids()` in `backend/services/event_aggregator.py`, which replaced `camera_selection.py`'s direct reach into aggregator internals) and call that from the consumer.

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

## Router service access

### The typed dependency pattern

Every service on ``app.state`` is set in a `backend/bootstrap/` phase module (to a concrete
instance or ``None``) -- see `backend/bootstrap/README.md` for which phase constructs which
attribute. Routers MUST use one of two patterns to access them; never ``getattr`` with a string
key.

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

Service wiring lives in `backend/bootstrap/` phase modules, orchestrated by
`bootstrap/lifespan.py`; `backend/main.py` only creates the app and includes routers.

1. Wire the service in the `backend/bootstrap/` phase matching its dependencies (set to
   ``None`` in every branch so the attribute always exists on ``app.state``).
2. Add it to the `backend/bootstrap/README.md` inventory and the
   `backend/tests/test_bootstrap_wiring.py` attribute-set pin.
3. If pipeline-consumed, add it to the `ServiceContainer` completeness map
   (`backend/services/container_wiring.py`).
4. Add a typed ``get_<name>`` callable in ``backend/routers/dependencies.py``.
5. Import and use ``Depends(get_<name>)`` in routers.

``import backend.main`` must stay side-effect free (see
`backend/tests/test_bootstrap_wiring.py::test_import_backend_main_performs_no_io`).

## When to abstract

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

## MCP and BFF single-service-layer rule

Any data exposed to the Vue UI through a FastAPI router must be exposed to MCP tools by reading the **same service function**. MCP tools contain no query logic of their own; they call service methods and adapt the result with `envelope_to_mcp()` or similar adapters.

Enforcement:
- Import-linter contract: `backend.mcp` may not import from `backend.models` or any repository module directly. Run `make import-lint` to verify.
- Smoke tests in `backend/tests/mcp/` assert that the tool registry resolves every registered tool name to a callable.
- Authorization parity: every tool declares the permission token it requires (`_register(token=...)`), enforced per call by `MCPAuthMiddleware` for HTTP and by the `mcp.gemini_tools` allowlist for the voice companion. `backend/tests/mcp/test_mcp_tool_authorization.py` pins the token of every state-changing tool.
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

## Unified envelope pattern

Location, occupancy, signal, and person-summary responses each have one Pydantic v2 envelope defined in `backend/schemas/cts_envelopes.py`. These fields are **always present and always server-computed**:

| Field | Type | Rule |
|-------|------|------|
| `confidence` | float | From the presence provider or identity resolver |
| `quality` | float | PH `mean_quality` from the CTS wire |
| `staleness_seconds` | int | Computed from `last_observed_at` at response time |
| `source` | str | Canonical provenance badge: `observation`, `transition`, `manual_override`, `ph_continuation` |

The frontend renders these fields via `CcProvenanceBadge`; it never computes them client-side (design rule D5).

The envelope is a **strict superset** of prior response shapes: every legacy field is present with the same name. New fields are added; nothing is renamed or removed until every consumer migrates.

## Extracting a reusable traversal/walk core

When two features need the same graph walk (such as the durable executor and the non-durable gate runner both executing DAGs), extract a callback-parameterised core (`execute_node` / `on_skip`) that owns only the graph walk bookkeeping. The callers' closures remain responsible for all side effects (DB writes, logging, event emissions). Cite `traverse_dag` in [pipeline_graph_traversal.py](file:///home/sriram/code/nanai/cognitive-companion/backend/services/pipeline_graph_traversal.py) as the canonical example.

### Regression-gating rule for executor refactors
Any refactor touching the executor's traversal path must be regression-gated: the full existing pipeline executor test suite must pass with **unchanged** expectations. Modifying any existing test expectation is a signal that behavior has drifted, which violates the requirement for a pure refactor.
