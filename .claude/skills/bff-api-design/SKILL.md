---
name: bff-api-design
description: "Use when adding or changing a browser-visible BFF envelope, endpoint, MCP adapter, authorization mapping, or router/MCP parity test."
---

# BFF API Design

This skill covers how to add a new endpoint to the Cognitive Companion BFF in a way that automatically satisfies the MCP/BFF parity guarantee (design rule D6): the same service function powers both the Vue UI router and the MCP tool.

## The invariant

> Any data exposed to the Vue UI through a router must be exposed to MCP tools by reading the **same** service function.

MCP tools may not contain query logic, repository imports, or database access. They call service methods.
Operational telemetry endpoints still use one service function but are exempt from MCP parity when they are not caregiver-facing domain data, for example `/media/aggregators`.

## Step-by-step checklist

### 1. Define the response envelope

Create or extend a Pydantic v2 model in `backend/schemas/`. If the data carries quality metadata from CTS, add the four standard fields (see engineering-standards skill section 21):

```python
# backend/schemas/my_resource.py
from pydantic import BaseModel, Field

class MyResourceEnvelope(BaseModel):
    resource_id: str
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    quality: float = Field(ge=0.0, le=1.0)
    staleness_seconds: int = Field(ge=0)
    source: str
```

### 2. Write the service function once

Add the business logic to an existing service in `backend/services/` or create a new one. The function returns the envelope or raises an `AppError` subclass; it never returns a fabricated value on error.

When the BFF adapts an upstream service, validate the upstream envelope before enrichment. Required list/object/scalar fields must be present with the expected shape. Treat missing fields, wrong JSON types, and upstream 5xx responses as contract failures: log with upstream URL/status and return a typed 502/503. Do not use `.get("required_field", [])` for required data; that converts contract drift into an empty UI and makes incidents invisible.

For bulk mutations, expose one explicit batch contract through the BFF and upstream service. Do not make the browser loop over single-item endpoints for merge/delete/correct workflows: client-side loops create partial-success ambiguity, make retry/idempotency difficult, and hide the true unit of work from audit logs. Batch mutation responses must include `applied` plus the source/target identifiers needed to reconcile the UI.

```python
# backend/services/my_service.py
async def get_my_resource(resource_id: str) -> MyResourceEnvelope:
    row = await self._repo.get(resource_id)
    if row is None:
        raise NotFoundError("MyResource", resource_id)
    return MyResourceEnvelope(
        resource_id=resource_id,
        value=row.value,
        confidence=row.confidence,
        quality=row.quality,
        staleness_seconds=_staleness(row.last_updated_at),
        source=row.source,
    )
```

### 3. Wire the service in the lifespan

Add an attribute to `app.state` in `backend/main.py` (lifespan). Set it to `None` in every branch so the attribute always exists:

```python
# backend/main.py (lifespan)
app.state.my_service = MyService(...)
```

Add a typed dependency in `backend/routers/dependencies.py`:

```python
from backend.services.my_service import MyService

def get_my_service(request: Request) -> MyService:
    svc: MyService | None = request.app.state.my_service
    if svc is None:
        raise HTTPException(status_code=503, detail="my_service unavailable")
    return svc
```

### 4. Add the router endpoint

```python
# backend/routers/my_resource.py
@router.get("/{resource_id}", response_model=MyResourceEnvelope)
async def get_my_resource(
    resource_id: str,
    svc: MyService = Depends(get_my_service),
    _auth: AuthContext = Depends(require_permission("my_resource:read")),
) -> MyResourceEnvelope:
    return await svc.get_my_resource(resource_id)
```

### 5. Add the auth.yaml permission entry

Every new endpoint needs coverage in `config/auth.yaml`. The file has two layers:

```yaml
# config/auth.yaml
permission_map:
  "my_resource.read":
    - "GET /api/v1/my-resource/*"

  caregiver:
    - "my_resource.read"
```

Use the permission token in `require_permission("my_resource.read")`. If the route uses a concrete `"METHOD /path"` token instead, add that exact pattern to the intended role. Verify both the token definition and role assignment. Add a focused router test that expects `403` without the permission and success with it. `backend/tests/core/test_auth.py` tests permission expansion mechanics, but there is currently no global test that proves every router token appears in `auth.yaml`.

### 6. Add the MCP tool

Add a `@_register` decorated function in `backend/mcp/server.py`. It calls the same service function; it does not import a repository or run a query:

```python
@_register
async def get_my_resource(resource_id: str) -> dict:
    """Get a my-resource envelope by ID."""
    svc: MyService = request.app.state.my_service
    if svc is None:
        return {"error": "service unavailable"}
    env = await svc.get_my_resource(resource_id)
    return env.model_dump(mode="json")
```

Add the tool name to `config/settings.yaml` under the `mcp.tools` list.

### 7. Add to the import-linter contract

`backend/pyproject.toml` contains `[[tool.importlinter.contracts]]` definitions. The current MCP contract forbids direct repository imports from `backend.mcp`. Extend its `forbidden_modules` only when a new repository package would otherwise be reachable:

```toml
# pyproject.toml (add or verify)
[[tool.importlinter.contracts]]
name = "mcp-no-direct-db"
type = "forbidden"
source_modules = ["backend.mcp"]
forbidden_modules = [
    "backend.services.person_location.repositories",
    "backend.services.my_resource.repositories",
]
```

Run `make import-lint` to verify.

### 8. Add the parity test

There is no single `backend/tests/mcp/test_parity.py`. Put the test beside the closest existing pattern:

- `backend/tests/integrations/test_mcp_bff_parity.py` for shared read envelopes.
- `backend/tests/integrations/test_gait_mcp_bff_parity.py` for a domain-specific endpoint.
- `backend/tests/routers/test_signals_feed.py` for direct service/router/tool parity.
- `backend/tests/mcp/test_signal_ack_parity.py` for mutations.

The test must assert that both adapters call the same service method and return the same meaningful envelope fields:

```python
async def test_my_resource_parity():
    resource_id = "test-123"
    service = AsyncMock()
    service.get_my_resource.return_value = MyResourceEnvelope(
        resource_id=resource_id,
        value="example",
        confidence=1.0,
        quality=1.0,
        staleness_seconds=0,
        source="test",
    )
    # Router path
    router_result = await get_my_resource_endpoint(resource_id, svc=service)
    # MCP path
    _svc.my_service = service
    mcp_result = await mcp_get_my_resource(resource_id)
    assert router_result.resource_id == mcp_result["resource_id"]
    assert router_result.confidence == mcp_result["confidence"]
```

### 9. Update the docs and CLAUDE.md

Add the endpoint to `docs/api/reference.md`. If the surface area is significant, add a feature page.

## Guided-task MCP tools

Guided-task agent tools are `get_active_guided_step`,
`mark_guided_step_complete`, `repeat_guided_step`, `report_step_blocked`, and
`request_caregiver_help`. They follow the same single-service-layer rule as every
other MCP tool: call `GuidedTaskService`, with no query logic, repository import,
or store access in the tool function.

Add each tool to the `mcp.gemini_tools` allowlist in `config/settings.yaml`. Add
registry smoke coverage plus router/MCP parity or direct service/tool coverage for
any browser-visible guided-task data or mutation.

## Rules and Callable Rules (Gate Graphs)

Callable rules (vision gate graphs with `trigger_types == []`) are excluded from general rule-enumeration surfaces, cron schedulers, Telegram trigger lists, and webhook targets.
- **List and CRUD endpoints:** The `GET /rules` router endpoint and MCP tools (`list_rules`, `get_rules`) exclude callable rules by default.
- **Filtering:** Use the `callable` query parameter (e.g. `GET /api/v1/rules?callable=true`) to list callable rules specifically, or `callable=false` (default) to list normal triggered rules.
- **Parity:** Parity rules apply to both regular rules and callable rules. Always reuse the same underlying service functions.

### Gate-graph CRUD endpoints (`backend/routers/gate_graphs.py`, VG08)

Gate graphs get a thin gate-scoped router that **reuses the shared rule service** (`backend/services/rule_service.py`) instead of writing a parallel query. This is the single-service-layer rule in practice:
- `GET /api/v1/gate-graphs` -> `rule_service.list_rules(db, callable_only=True)`, returns `{items, total}`. The rules router's `list_rules` delegates to the same function, so both surfaces share the callable filter (`Rule.filter_callable`). The parity test (`test_gate_graph_list_uses_rule_service`) asserts the router calls `rule_service.list_rules`, not a bespoke query.
- `POST /api/v1/gate-graphs` creates a callable rule (`trigger_types == []`); `from_preset=<key>` builds through the shared `gate_presets` factory (one factory for presets, the backfill script, and tests).
- `GET /api/v1/gate-graphs/{id}` reuses `rule_service.get_rule` (rule + steps + edges). Step/edge editing reuses the existing `/rules/{id}` endpoints and `PUT /rules/{id}/edges`; do not duplicate them.
- `POST /api/v1/gate-graphs/{id}/validate` runs full `validate_gate_graph` (`gate_safe_only=False`): exactly one reachable `gate_verdict`, all steps gate-safe, plus per-step template linting.
- `POST /api/v1/gate-graphs/{id}/test-run` returns a `GateVerdict` envelope `{complete, confidence, reason, node_results, cost, profile}`. It is a **fail-closed preview**: a missing gate service or no cameras returns `complete=False` with a reason, never a 5xx. It delegates to `GuidedTaskService.run_gate_preview`, which reuses the live camera cascade + `GateGraphRunner`.
- `GET /api/v1/gate-presets` lists the seeded preset library metadata.

Auth: `gate_graphs:read` (GET gate-graphs + gate-presets) and `gate_graphs:write` (all POSTs incl. validate/test-run) in `config/auth.yaml`, granted to `caregiver`. Register every method in `frontend/src/services/contracts.js`.

## Verification commands

```bash
# Import linter
make import-lint

# Parity tests
backend/.venv/bin/pytest backend/tests/mcp/ -v

# Auth coverage: no endpoint without a permission
grep -n "my_resource.read\\|GET /api/v1/my-resource" config/auth.yaml
grep "my_resource" backend/routers/my_resource.py
```

## Common mistakes

| Mistake | Correct approach |
|---------|-----------------|
| MCP tool imports `Session` or runs a query | Call the service method; the service owns the query |
| Router and MCP tool each call different service methods | One service method, two callers |
| Missing `auth.yaml` entry | CI catches this; do not merge without it |
| MCP tool returns `{}` on error | Return `{"error": "..."}` with a log; let the caller surface the error |
| Fabricating a default value when data is missing | Raise `NotFoundError` or return documented `None`; never invent data |
| `.get("items", [])` on a required upstream envelope | Validate with Pydantic or explicit type checks; return 502 on contract violation |
